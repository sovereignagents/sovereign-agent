"""Pre-publish audit — checks that the repo is safe to push to a public remote.

What this does
==============
Before you ``git remote add public … && git push``, you want to know:

  1. Are there any obviously-sensitive strings committed?
     (API keys, personal tokens, passwords, secrets)
  2. Are there any PII leaks?
     (emails, phone numbers, home addresses that shouldn't be public)
  3. Are internal URLs / dev endpoints baked in?
     (localhost:XXXX, corporate domains, staging servers)
  4. Are test/dev-only files committed that shouldn't be?
     (.env, .DS_Store, cache dirs, IDE files)
  5. Are there "TODO remove before release" comments still in place?
  6. Does the project look professional enough to launch?
     (LICENSE file, README with certain sections, pyproject metadata)
  7. Is the git history itself clean?
     (commit messages don't say "fix for client X", authors look right)

Philosophy
==========
This is a SAFETY NET, not a guarantee. A determined attacker could still
obfuscate secrets that a regex wouldn't catch. But the script catches the
most common accidents: a real AWS key pasted into a test file, a customer
email in a TODO, a cached .env file in git history.

Every check produces ✓ (safe), ⚠ (probably fine but worth reviewing), or
✗ (stop — fix this before pushing). Exit code is 0 if only ✓/⚠, 1 if any ✗.

Running
=======
  make pre-publish         # run the full audit
  python scripts/pre_publish.py --verbose    # show every file scanned
  python scripts/pre_publish.py --git        # also scan git history

Inspired by tools like gitleaks, trufflehog, and pypi-attestations — but
kept tiny, single-file, and zero-deps so it works in any fresh venv.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class Finding:
    """One issue the audit surfaced. If path+line are set, it's file-scoped."""

    check: str
    status: Status
    message: str
    path: Path | None = None
    line_no: int | None = None
    snippet: str = ""
    hint: str = ""


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str = ""
    findings: list[Finding] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Color helpers (shared style with doctor.py)
# ─────────────────────────────────────────────────────────────────────


class _C:
    _on = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def _wrap(cls, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if cls._on else s

    @classmethod
    def green(cls, s: str) -> str:
        return cls._wrap("32", s)

    @classmethod
    def red(cls, s: str) -> str:
        return cls._wrap("31", s)

    @classmethod
    def yellow(cls, s: str) -> str:
        return cls._wrap("33", s)

    @classmethod
    def cyan(cls, s: str) -> str:
        return cls._wrap("36", s)

    @classmethod
    def dim(cls, s: str) -> str:
        return cls._wrap("2", s)

    @classmethod
    def bold(cls, s: str) -> str:
        return cls._wrap("1", s)


_MARKS = {
    Status.OK: lambda: _C.green("✓"),
    Status.WARN: lambda: _C.yellow("⚠"),
    Status.FAIL: lambda: _C.red("✗"),
}


# ─────────────────────────────────────────────────────────────────────
# File iteration (respects .gitignore via git ls-files when in a git repo)
# ─────────────────────────────────────────────────────────────────────


def find_repo_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


def list_tracked_files(repo: Path) -> list[Path]:
    """Return every file that git would include in a push.

    Uses ``git ls-files`` when available (respects .gitignore). Falls back
    to a recursive walk if git isn't installed or the repo isn't a git repo.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0:
            return [repo / p for p in out.stdout.splitlines() if p.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: scan the tree but skip obvious non-source dirs
    skip_dirs = {
        ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
        ".mypy_cache", "dist", "build", "node_modules", "_transient",
        "sessions",
    }  # fmt: skip
    out: list[Path] = []
    for path in repo.rglob("*"):
        if path.is_dir():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        out.append(path)
    return out


# Files we don't want to scan for content (binary or irrelevant)
_SKIP_CONTENT_SUFFIXES = {
    ".lock", ".whl", ".tar.gz", ".gz", ".zip", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".svg", ".ico", ".pdf", ".pyc", ".pyo", ".so", ".dylib",
    ".woff", ".woff2", ".ttf", ".eot",
}  # fmt: skip


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in _SKIP_CONTENT_SUFFIXES:
        return False
    # Treat files >1MB as binary by default — unlikely to contain secrets
    # we'd catch with regex, likely to slow the audit down.
    try:
        if path.stat().st_size > 1_000_000:
            return False
    except OSError:
        return False
    # Probe for binary content
    try:
        chunk = path.read_bytes()[:1024]
        if b"\0" in chunk:
            return False
    except OSError:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────
# Secret / sensitive content scanning
# ─────────────────────────────────────────────────────────────────────

# Patterns that indicate a real secret. Each entry: (label, regex, severity).
# Severities:
#   FAIL  - this is almost certainly a live secret; block the publish
#   WARN  - this might be a secret or might be an example; human review needed
SECRET_PATTERNS: list[tuple[str, re.Pattern, Status]] = [
    # AWS — very distinctive format, near-zero false positive rate
    (
        "AWS access key ID",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        Status.FAIL,
    ),
    (
        "AWS secret access key",
        re.compile(
            r"(?i)aws[_\-\s]*secret[_\-\s]*access[_\-\s]*key['\"]?\s*[:=]\s*['\"]([A-Za-z0-9/+=]{40})['\"]"
        ),
        Status.FAIL,
    ),
    # GitHub tokens — new format is distinctive
    (
        "GitHub personal access token",
        re.compile(r"\bghp_[A-Za-z0-9]{36,255}\b"),
        Status.FAIL,
    ),
    (
        "GitHub OAuth token",
        re.compile(r"\bgho_[A-Za-z0-9]{36,255}\b"),
        Status.FAIL,
    ),
    (
        "GitHub app token",
        re.compile(r"\b(ghu|ghs)_[A-Za-z0-9]{36,255}\b"),
        Status.FAIL,
    ),
    # Generic "sk-..." — OpenAI, Anthropic, etc.
    (
        "OpenAI API key",
        re.compile(r"\bsk-(?!replace)[A-Za-z0-9]{20,}\b"),
        Status.FAIL,
    ),
    (
        "Anthropic API key",
        re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{40,}\b"),
        Status.FAIL,
    ),
    # Nebius / Token Factory — the signature from the user's own error messages
    (
        "Nebius / JWT-style key",
        re.compile(r"\bv1\.[A-Za-z0-9_\-]{30,}\.[A-Za-z0-9_\-]{30,}\b"),
        Status.FAIL,
    ),
    # Slack
    (
        "Slack token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        Status.FAIL,
    ),
    # Google Cloud service account key
    (
        "Google service account JSON",
        re.compile(r'"type":\s*"service_account"'),
        Status.FAIL,
    ),
    # Generic PEM private keys
    (
        "Private key (PEM)",
        re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
        Status.FAIL,
    ),
    # Less specific but still worth flagging
    (
        "Variable named like a secret with concrete value",
        re.compile(
            r"(?i)(password|passwd|secret|api[_\-]?key|auth[_\-]?token|access[_\-]?token)"
            r"\s*[:=]\s*['\"]([A-Za-z0-9][A-Za-z0-9_\-\.]{15,})['\"]"
        ),
        Status.WARN,
    ),
]

# Strings that should NEVER reach public, but are obvious placeholders that
# are OK to keep. If a match is exactly one of these, downgrade to ✓.
SECRET_PLACEHOLDERS: set[str] = {
    "sk-replace-me",
    "your-nebius-api-key",
    "your-api-key",
    "replace-with-your-key",
    "placeholder",
    "xxx",
    "fake",
    "fake-key",
    "fake-test-key-abc123",
    "fake-key-for-offline-test",
    "fake-key-for-routing-test",
}


# Lines we skip even when they match a secret pattern, because the line is
# obviously illustrative (docs, example config, comments that describe the
# shape of a key rather than containing one).
_COMMENT_SKIP_MARKERS = ("# example", "# e.g.", "<your-", "<YOUR_", "example:")


def scan_file_for_secrets(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        if any(m in lower for m in _COMMENT_SKIP_MARKERS):
            continue
        for label, pattern, severity in SECRET_PATTERNS:
            m = pattern.search(line)
            if not m:
                continue
            # Extract the matched secret itself. For regexes with groups,
            # prefer the last populated group (typically the value).
            matched = m.group(0)
            for g in reversed(m.groups() or ()):
                if g:
                    matched = g
                    break
            if matched.lower() in SECRET_PLACEHOLDERS:
                continue
            # Too short after stripping placeholder-like prefixes? skip
            if len(matched) < 10 and severity != Status.FAIL:
                continue
            findings.append(
                Finding(
                    check="secret-scan",
                    status=severity,
                    message=label,
                    path=path,
                    line_no=line_no,
                    snippet=line.strip()[:100],
                    hint=(
                        "If this is a real secret, remove it from the file AND "
                        "rewrite history (git filter-repo) before pushing."
                    ),
                )
            )
    return findings


# ─────────────────────────────────────────────────────────────────────
# PII and internal URL scanning
# ─────────────────────────────────────────────────────────────────────

# Rough email regex — matches john.doe@example.com but not arbitrary
# technical strings with @ in them (like git refs).
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Emails we expect to see: project maintainers, license headers, etc.
# Domains listed here produce no warning. Literal emails like
# cfo@example.com are also allowed individually.
_EMAIL_ALLOW_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.local",
    # Fictional fixture domains used in scenarios
    "evil.com",
    "attacker.com",
    "haymarket-tap.co.uk",  # pub_booking / session_resume_chain fixture
}

# Specific emails allowed even if their domain would normally warn.
_EMAIL_ALLOW_LITERALS = {
    "cfo@example.com",
}


# Internal URL patterns — localhost, 127.0.0.1, staging, etc.
_INTERNAL_URL_RE = re.compile(
    r"\b(https?://)(localhost|127\.0\.0\.1|0\.0\.0\.0|"
    r"[a-z0-9\-]+\.internal|[a-z0-9\-]+\.corp|[a-z0-9\-]+\.staging)"
    r"(:\d+)?\b",
    re.IGNORECASE,
)


def _line_is_commented(line: str) -> bool:
    """True if the first non-whitespace character is a comment marker.

    Works for Python (#), YAML (#), shell (#), and TOML (#). Markdown
    doesn't have comments but its fenced blocks are fine to scan.
    """
    stripped = line.lstrip()
    return stripped.startswith("#") or stripped.startswith("//")


def scan_file_for_pii(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        # Emails
        for m in _EMAIL_RE.finditer(line):
            email = m.group(0)
            if email.lower() in _EMAIL_ALLOW_LITERALS:
                continue
            domain = email.split("@")[-1].lower()
            if domain in _EMAIL_ALLOW_DOMAINS:
                continue
            findings.append(
                Finding(
                    check="pii-email",
                    status=Status.WARN,
                    message=f"email address: {email}",
                    path=path,
                    line_no=line_no,
                    snippet=line.strip()[:100],
                    hint="Ensure this email is appropriate for a public repo.",
                )
            )
        # Internal URLs — skip commented-out lines (they're examples, not live)
        if _line_is_commented(line):
            continue
        for m in _INTERNAL_URL_RE.finditer(line):
            url = m.group(0)
            # Heuristic: if the line also has 'test' or it's in docs, it's
            # probably a dev example, not a real internal URL
            lower = line.lower()
            if "test" in lower or "example" in lower or "doc" in lower:
                continue
            findings.append(
                Finding(
                    check="internal-url",
                    status=Status.WARN,
                    message=f"internal/dev URL: {url}",
                    path=path,
                    line_no=line_no,
                    snippet=line.strip()[:100],
                    hint="Localhost/staging URLs usually don't belong in public code.",
                )
            )
    return findings


# ─────────────────────────────────────────────────────────────────────
# TODO / FIXME scanning
# ─────────────────────────────────────────────────────────────────────

# Flag TODOs/FIXMEs that look embarrassing in a public repo. Generic
# TODOs are fine; specific ones referencing real people, clients, or
# "remove before push" are not.
_EMBARRASSING_TODO_RE = re.compile(
    r"#\s*(TODO|FIXME|XXX|HACK)[:\s]+([^\n]{0,200})",
    re.IGNORECASE,
)

_EMBARRASSING_MARKERS = (
    "before push",
    "before release",
    "before launch",
    "before public",
    "don't commit",
    "do not commit",
    "temporary",
    "hack",
    "kludge",
)


def scan_file_for_embarrassing_todos(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = _EMBARRASSING_TODO_RE.search(line)
        if not m:
            continue
        body = m.group(2).lower()
        if any(marker in body for marker in _EMBARRASSING_MARKERS):
            findings.append(
                Finding(
                    check="todo",
                    status=Status.WARN,
                    message=f"{m.group(1)}: {m.group(2).strip()[:80]}",
                    path=path,
                    line_no=line_no,
                    snippet=line.strip()[:100],
                    hint="Address this TODO or reword it before public release.",
                )
            )
    return findings


# ─────────────────────────────────────────────────────────────────────
# Structural checks — files that shouldn't be committed, metadata sanity
# ─────────────────────────────────────────────────────────────────────

_FORBIDDEN_FILE_PATTERNS = [
    re.compile(r"\.env$"),
    re.compile(r"\.env\.local$"),
    re.compile(r"\.DS_Store$"),
    re.compile(r"^\.idea/"),
    re.compile(r"^\.vscode/"),
    re.compile(r"\.pyc$"),
    re.compile(r"/__pycache__/"),
    re.compile(r"\.sqlite(\d+)?$"),
    re.compile(r"\.db$"),
    re.compile(r"\.log$"),
]


def check_forbidden_files(repo: Path, files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        rel = path.relative_to(repo).as_posix()
        for pat in _FORBIDDEN_FILE_PATTERNS:
            if pat.search(rel):
                findings.append(
                    Finding(
                        check="forbidden-file",
                        status=Status.FAIL,
                        message=f"committed file that shouldn't be in a public repo: {rel}",
                        path=path,
                        hint=(
                            f"Remove from git: git rm --cached '{rel}' && "
                            f"add the pattern to .gitignore."
                        ),
                    )
                )
                break
    return findings


def check_gitignore_sanity(repo: Path) -> list[Finding]:
    """Confirm .gitignore has the usual suspects."""
    gi = repo / ".gitignore"
    if not gi.exists():
        return [
            Finding(
                check="gitignore",
                status=Status.FAIL,
                message=".gitignore is missing",
                hint="Create one. Start with the GitHub Python template.",
            )
        ]
    content = gi.read_text()
    expected = [".env", "__pycache__", ".venv", ".pytest_cache", "dist"]
    missing = [m for m in expected if m not in content]
    if missing:
        return [
            Finding(
                check="gitignore",
                status=Status.WARN,
                message=f".gitignore doesn't ignore: {', '.join(missing)}",
                hint="Add these patterns so they don't leak.",
            )
        ]
    return []


def check_license(repo: Path) -> list[Finding]:
    for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
        if (repo / name).exists():
            return []
    return [
        Finding(
            check="license",
            status=Status.FAIL,
            message="no LICENSE file found",
            hint=(
                "Public repos should have a LICENSE. Apache 2.0 or MIT are "
                "common choices for libraries."
            ),
        )
    ]


def check_readme_quality(repo: Path) -> list[Finding]:
    """Quick heuristic for whether the README is launch-grade."""
    readme = repo / "README.md"
    if not readme.exists():
        return [
            Finding(
                check="readme",
                status=Status.FAIL,
                message="no README.md",
                hint="Write one. It's the first thing anyone sees.",
            )
        ]
    text = readme.read_text().lower()
    findings: list[Finding] = []

    required_sections = {
        "install": ["install", "pip install"],
        "quick example": ["```python", "```bash"],
        "license": ["license"],
    }
    for label, markers in required_sections.items():
        if not any(m in text for m in markers):
            findings.append(
                Finding(
                    check="readme",
                    status=Status.WARN,
                    message=f"README missing a '{label}' section (no match for: {markers})",
                    hint="Most READMEs have this; consider adding.",
                )
            )

    # Overly long READMEs scare people off
    line_count = len(text.splitlines())
    if line_count > 600:
        findings.append(
            Finding(
                check="readme",
                status=Status.WARN,
                message=f"README is long ({line_count} lines); consider moving detail to docs/",
                hint="Top-tier READMEs are 200-500 lines. Longer = people don't read.",
            )
        )
    return findings


def check_pyproject_metadata(repo: Path) -> list[Finding]:
    pyproject = repo / "pyproject.toml"
    if not pyproject.exists():
        return [
            Finding(
                check="pyproject",
                status=Status.FAIL,
                message="no pyproject.toml",
            )
        ]
    content = pyproject.read_text()
    findings: list[Finding] = []

    expected_fields = {
        "name": r'name\s*=\s*["\']',
        "version": r'version\s*=\s*["\']',
        "description": r'description\s*=\s*["\']',
        "license": r"license\s*=\s*",
        "authors": r"authors\s*=",
        "readme": r'readme\s*=\s*["\']',
        "requires-python": r'requires-python\s*=\s*["\']',
    }
    for field_name, pattern in expected_fields.items():
        if not re.search(pattern, content):
            findings.append(
                Finding(
                    check="pyproject",
                    status=Status.WARN,
                    message=f"pyproject.toml missing or empty '{field_name}'",
                    hint="PyPI shows this field on your project page; fill it in.",
                )
            )

    if "Homepage" not in content and "homepage" not in content:
        findings.append(
            Finding(
                check="pyproject",
                status=Status.WARN,
                message="pyproject.toml has no project URLs (Homepage/Repository/Issues)",
                hint="These appear on pypi.org/project/<your-package>/ as sidebar links.",
            )
        )
    return findings


# ─────────────────────────────────────────────────────────────────────
# Git history checks
# ─────────────────────────────────────────────────────────────────────


def check_git_history(repo: Path) -> list[Finding]:
    """Scan recent commit messages + authors for red flags."""
    try:
        out = subprocess.run(
            ["git", "log", "--all", "-100", "--pretty=format:%an|%ae|%s"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []

    findings: list[Finding] = []
    suspicious_message_markers = (
        "client ",
        "customer ",
        "remove later",
        "fix for acme",
        "hack ",
        "tmp commit",
        "wip — secrets",
        "add secret",
        "testing creds",
    )
    for line in out.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        _author, email, msg = parts
        msg_lower = msg.lower()
        for marker in suspicious_message_markers:
            if marker in msg_lower:
                findings.append(
                    Finding(
                        check="git-history",
                        status=Status.WARN,
                        message=f"commit mentions '{marker.strip()}': {msg[:80]}",
                        hint=(
                            "If this references a private context, consider "
                            "rewriting the commit message before going public."
                        ),
                    )
                )
                break
        # Author email on a personal domain is fine; corporate email visible
        # on a public project is a choice you should make deliberately.
        # We don't flag by default — too noisy.
    return findings


# ─────────────────────────────────────────────────────────────────────
# Running the checks
# ─────────────────────────────────────────────────────────────────────


def run_audit(repo: Path, include_git_history: bool, verbose: bool) -> list[CheckResult]:
    results: list[CheckResult] = []

    # --- Scan every tracked file for content issues ---
    files = list_tracked_files(repo)
    secret_findings: list[Finding] = []
    pii_findings: list[Finding] = []
    todo_findings: list[Finding] = []

    for path in files:
        if not _is_text_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(repo).as_posix()
        if verbose:
            print(_C.dim(f"    scanning {rel}"))
        # Skip this very script — it contains the patterns themselves,
        # which would trigger false positives.
        if rel == "scripts/pre_publish.py":
            continue
        secret_findings.extend(scan_file_for_secrets(path, text))
        pii_findings.extend(scan_file_for_pii(path, text))
        todo_findings.extend(scan_file_for_embarrassing_todos(path, text))

    # --- Collate into categorized CheckResults ---

    # Secrets
    sec_fail = [f for f in secret_findings if f.status == Status.FAIL]
    sec_warn = [f for f in secret_findings if f.status == Status.WARN]
    if sec_fail:
        status = Status.FAIL
        detail = f"{len(sec_fail)} likely real secret(s); block publish"
    elif sec_warn:
        status = Status.WARN
        detail = f"{len(sec_warn)} candidate(s); review manually"
    else:
        status = Status.OK
        detail = f"no secrets detected in {len(files)} files"
    results.append(CheckResult("secrets", status, detail, secret_findings))

    # Forbidden files
    ff = check_forbidden_files(repo, files)
    results.append(
        CheckResult(
            "forbidden-files",
            Status.FAIL if ff else Status.OK,
            f"{len(ff)} forbidden file(s) committed" if ff else "none detected",
            ff,
        )
    )

    # .gitignore
    gi = check_gitignore_sanity(repo)
    results.append(
        CheckResult(
            "gitignore",
            gi[0].status if gi else Status.OK,
            gi[0].message if gi else ".gitignore covers the usual suspects",
            gi,
        )
    )

    # PII
    pii_ok = Status.OK if not pii_findings else Status.WARN
    results.append(
        CheckResult(
            "pii",
            pii_ok,
            f"{len(pii_findings)} candidate(s)" if pii_findings else "no emails/internal URLs",
            pii_findings,
        )
    )

    # TODOs
    if not todo_findings:
        results.append(CheckResult("suspicious TODOs", Status.OK, "none detected", []))
    else:
        results.append(
            CheckResult(
                "suspicious TODOs",
                Status.WARN,
                f"{len(todo_findings)} TODO(s) with 'before release'-style language",
                todo_findings,
            )
        )

    # License
    lf = check_license(repo)
    results.append(
        CheckResult(
            "license",
            Status.FAIL if lf else Status.OK,
            lf[0].message if lf else "LICENSE file present",
            lf,
        )
    )

    # README
    rf = check_readme_quality(repo)
    if not rf:
        results.append(CheckResult("README", Status.OK, "README looks launch-grade", []))
    else:
        worst = max((f.status for f in rf), key=lambda s: ["ok", "warn", "fail"].index(s.value))
        results.append(CheckResult("README", worst, f"{len(rf)} observation(s)", rf))

    # pyproject
    pp = check_pyproject_metadata(repo)
    if not pp:
        results.append(
            CheckResult("pyproject.toml", Status.OK, "all expected metadata present", [])
        )
    else:
        worst = max((f.status for f in pp), key=lambda s: ["ok", "warn", "fail"].index(s.value))
        results.append(CheckResult("pyproject.toml", worst, f"{len(pp)} observation(s)", pp))

    # Git history (optional, may be slow)
    if include_git_history:
        gh = check_git_history(repo)
        if not gh:
            results.append(CheckResult("git history", Status.OK, "last 100 commits look clean", []))
        else:
            results.append(
                CheckResult("git history", Status.WARN, f"{len(gh)} suspicious commit(s)", gh)
            )

    return results


def _print_result(r: CheckResult) -> None:
    mark = _MARKS[r.status]()
    print(f"  {_C.dim(r.name.ljust(22))}  {mark}  {r.detail}")


def _print_findings(results: list[CheckResult]) -> None:
    """Print detail for any FAIL or WARN finding."""
    for r in results:
        if r.status == Status.OK or not r.findings:
            continue
        print()
        print(_C.bold(f"  → {r.name}") + _C.dim(f"  ({len(r.findings)} issue(s))"))
        # Show up to 10 findings per category to avoid overwhelming output
        for f in r.findings[:10]:
            mark = _MARKS[f.status]()
            if f.path is not None:
                rel = f.path.as_posix()
                loc = f":{f.line_no}" if f.line_no else ""
                print(f"    {mark}  {rel}{loc}")
                if f.message:
                    print(f"        {_C.dim(f.message)}")
                if f.snippet:
                    print(f"        {_C.dim('→ ' + f.snippet)}")
            else:
                print(f"    {mark}  {f.message}")
            if f.hint:
                print(f"        {_C.dim('hint: ' + f.hint)}")
        if len(r.findings) > 10:
            print(_C.dim(f"    ... and {len(r.findings) - 10} more (use --verbose to see all)"))


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="pre-publish audit for sovereign-agent")
    parser.add_argument(
        "--git",
        action="store_true",
        help="also scan git history (slower, checks commit messages)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print every file as it's scanned",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="print all findings (no truncation)",
    )
    args = parser.parse_args()

    repo = find_repo_root(Path(__file__).resolve().parent)

    print()
    print(_C.cyan("━" * 72))
    print(_C.bold("  sovereign-agent") + _C.dim("  ·  ") + _C.bold("pre-publish audit"))
    print(_C.dim(f"  repo: {repo}"))
    print(_C.cyan("━" * 72))
    print()

    results = run_audit(repo, include_git_history=args.git, verbose=args.verbose)

    print(_C.bold("  Summary"))
    print(_C.dim("  " + "─" * 66))
    for r in results:
        _print_result(r)

    # Detail for anything that failed or warned
    _print_findings(results)

    # Overall verdict
    n_fail = sum(1 for r in results if r.status == Status.FAIL)
    n_warn = sum(1 for r in results if r.status == Status.WARN)
    n_ok = sum(1 for r in results if r.status == Status.OK)

    print()
    print(_C.cyan("━" * 72))
    if n_fail:
        print(
            f"  {_C.red('✗')} "
            + _C.bold(f"{n_fail} blocker(s)")
            + _C.dim(f"  ·  {n_warn} warning(s)  ·  {n_ok} OK")
        )
        print()
        print(_C.bold("  DO NOT PUBLISH until the ✗ items are resolved."))
    elif n_warn:
        print(f"  {_C.yellow('⚠')} " + _C.bold(f"{n_warn} warning(s)") + _C.dim(f"  ·  {n_ok} OK"))
        print()
        print(
            _C.dim(
                "  Warnings aren't blockers — review them and proceed if they're false positives."
            )
        )
    else:
        print(f"  {_C.green('✓')} " + _C.bold(f"all {n_ok} checks passed — safe to publish"))
    print(_C.cyan("━" * 72))
    print()

    return 1 if n_fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(130)
