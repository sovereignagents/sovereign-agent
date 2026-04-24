"""Human-in-the-loop approval protocol (v0.2, Module 5).

When a tool returns `ToolResult(requires_human_approval=True, ...)`, the
executor does NOT execute any further tool calls in the current turn. It
writes an approval request file to `ipc/awaiting_approval/` and returns a
subgoal result with `next_action="awaiting_approval"`.

A human (via `sa-approve <session_id> <request_id>`, an external UI, or
another agent) responds by writing either:

    ipc/approval_granted/<request_id>.json
    ipc/approval_denied/<request_id>.json

When the session is resumed (either by an orchestrator watcher seeing the
file appear, or by an explicit `resume_from_approval()` call), the
executor re-enters the loop, reads the response, and either:

  * replays the original tool call with the approved arguments
    (if granted), surfacing its output to the LLM
  * returns the denial reason to the LLM as the tool result
    (if denied), allowing the LLM to adapt

This keeps approvals auditable (every request and response lives in
`logs/approvals/`) and non-blocking (no thread or coroutine holds state
across the wait — the session can idle for hours and resume cleanly).

Design principles:
  * Approval requests are IPC messages, not blocking waits.
  * The executor never sleeps waiting for a human. It exits.
  * Every request has a unique `request_id` derived from the ticket ID
    and tool call ID — so a session can legitimately have multiple
    pending approvals (though this is unusual).
  * Approvals are tamper-evident: the request file includes a SHA-256
    of the tool arguments, and the response is matched by request_id.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sovereign_agent._internal.atomic import atomic_write_json
from sovereign_agent.errors import IOError as SovereignIOError
from sovereign_agent.session.directory import Session
from sovereign_agent.session.state import now_utc

AWAITING_DIR_NAME = "awaiting_approval"
GRANTED_DIR_NAME = "approval_granted"
DENIED_DIR_NAME = "approval_denied"
# Where we archive fully-processed approval cycles for audit.
LOGS_DIR_NAME = "approvals"


@dataclass
class ApprovalRequest:
    """An executor-side record of a pending approval.

    Written to `ipc/awaiting_approval/<request_id>.json` by the executor.
    Read by CLI tools, external UIs, and the resume_from_approval flow.
    """

    request_id: str
    session_id: str
    subgoal_id: str
    ticket_id: str
    tool_name: str
    tool_arguments: dict
    # Hash of the arguments the tool was called with. When a human grants
    # the request they are granting THIS specific invocation; if something
    # retries with different args we want to know.
    arguments_sha256: str
    # What the tool itself produced in the "dry-run" phase. Some tools
    # compute their result, detect that human approval is needed, and set
    # the flag while returning the proposed result. Showing this to the
    # human makes the approval decision informed rather than blind.
    proposed_output: dict
    tool_summary: str
    created_at: str
    # Free-form reason/context the tool wants the human to see.
    # Example: "Deposit £400 exceeds auto-approve threshold £300."
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "subgoal_id": self.subgoal_id,
            "ticket_id": self.ticket_id,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "arguments_sha256": self.arguments_sha256,
            "proposed_output": self.proposed_output,
            "tool_summary": self.tool_summary,
            "created_at": self.created_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ApprovalRequest:
        return cls(
            request_id=d["request_id"],
            session_id=d["session_id"],
            subgoal_id=d["subgoal_id"],
            ticket_id=d["ticket_id"],
            tool_name=d["tool_name"],
            tool_arguments=d.get("tool_arguments", {}),
            arguments_sha256=d.get("arguments_sha256", ""),
            proposed_output=d.get("proposed_output", {}),
            tool_summary=d.get("tool_summary", ""),
            created_at=d["created_at"],
            reason=d.get("reason", ""),
        )


@dataclass
class ApprovalResponse:
    """A human/UI/agent response to an ApprovalRequest.

    Written to `ipc/approval_granted/<request_id>.json` or
    `ipc/approval_denied/<request_id>.json` by the CLI or an external
    caller.
    """

    request_id: str
    decision: Literal["granted", "denied"]
    # Who/what approved or denied. Free-form — could be a username, a UI
    # identifier, a service account, etc.
    approver: str
    decided_at: str
    # Human-readable reason. For denials, this is surfaced to the LLM so
    # it can adapt its next action.
    reason: str = ""
    # Optional: the approver may override the tool's proposed output
    # (e.g. "yes, book but for 6 people instead of 12"). If set, this
    # is what the LLM sees instead of the original proposed_output.
    override_output: dict | None = None

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "request_id": self.request_id,
            "decision": self.decision,
            "approver": self.approver,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "override_output": self.override_output,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ApprovalResponse:
        dec = d["decision"]
        if dec not in ("granted", "denied"):
            raise ValueError(f"decision must be 'granted' or 'denied', got {dec!r}")
        return cls(
            request_id=d["request_id"],
            decision=dec,
            approver=d.get("approver", "unknown"),
            decided_at=d["decided_at"],
            reason=d.get("reason", ""),
            override_output=d.get("override_output"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_arguments_sha256(arguments: dict) -> str:
    """Stable hash of tool-call arguments. JSON-serialised with sorted keys
    so {"a":1,"b":2} and {"b":2,"a":1} produce the same hash."""
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_request_id(ticket_id: str, tool_call_id: str) -> str:
    """Build a request_id that's stable for the same (ticket, tool call).

    Using both ensures a session can have concurrent pending approvals
    without collision, and that a retry of the same tool call — which
    would have a different tool_call_id from the LLM — is treated as a
    distinct approval request.
    """
    return f"appr_{ticket_id[-8:]}_{tool_call_id[-8:]}"


def _approval_dirs(session: Session) -> dict[str, Path]:
    ipc = session.ipc_dir
    return {
        "awaiting": ipc / AWAITING_DIR_NAME,
        "granted": ipc / GRANTED_DIR_NAME,
        "denied": ipc / DENIED_DIR_NAME,
        "logs": session.logs_dir / LOGS_DIR_NAME,
    }


# ---------------------------------------------------------------------------
# Write side — used by the executor
# ---------------------------------------------------------------------------


def write_approval_request(session: Session, request: ApprovalRequest) -> Path:
    """Write an approval request to `ipc/awaiting_approval/<request_id>.json`.

    Also writes a mirror copy under `logs/approvals/<request_id>.request.json`
    for durable audit: even if the awaiting file gets archived after the
    decision, the request itself is preserved.
    """
    dirs = _approval_dirs(session)
    dirs["awaiting"].mkdir(parents=True, exist_ok=True)
    dirs["logs"].mkdir(parents=True, exist_ok=True)

    filename = f"{request.request_id}.json"
    awaiting_path = dirs["awaiting"] / filename
    atomic_write_json(awaiting_path, request.to_dict())

    log_path = dirs["logs"] / f"{request.request_id}.request.json"
    atomic_write_json(log_path, request.to_dict())

    return awaiting_path


# ---------------------------------------------------------------------------
# Read side — used by CLI, UIs, resume flow
# ---------------------------------------------------------------------------


def list_pending_approvals(session: Session) -> list[ApprovalRequest]:
    """All approval requests that have been written but not yet decided.

    Returned in stable (filename) order. An approved/denied request is
    NOT in this list — only ones still awaiting a human.
    """
    dirs = _approval_dirs(session)
    awaiting = dirs["awaiting"]
    if not awaiting.exists():
        return []
    out: list[ApprovalRequest] = []
    for entry in sorted(awaiting.iterdir()):
        if not entry.is_file() or entry.suffix != ".json":
            continue
        try:
            with open(entry, encoding="utf-8") as f:
                data = json.load(f)
            out.append(ApprovalRequest.from_dict(data))
        except (OSError, json.JSONDecodeError, KeyError):
            # Malformed request files are skipped rather than breaking the
            # whole listing. The orchestrator-level watcher can flag these.
            continue
    return out


def get_pending_approval(session: Session, request_id: str) -> ApprovalRequest | None:
    """Fetch a single pending approval by its request_id."""
    dirs = _approval_dirs(session)
    path = dirs["awaiting"] / f"{request_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return ApprovalRequest.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def record_decision(
    session: Session,
    response: ApprovalResponse,
) -> Path:
    """Called by CLI/UI to record a grant or deny.

    Moves the awaiting file to `ipc/approval_{granted,denied}/<id>.json`
    with the decision payload merged in, and archives the pair under
    `logs/approvals/<id>.decision.json`.

    Raises SovereignIOError if there is no matching pending request.
    """
    dirs = _approval_dirs(session)
    awaiting_path = dirs["awaiting"] / f"{response.request_id}.json"
    if not awaiting_path.exists():
        raise SovereignIOError(
            code="SA_IO_NOT_FOUND",
            message=f"no pending approval request with id {response.request_id!r}",
            context={
                "session_id": session.session_id,
                "awaiting_dir": str(dirs["awaiting"]),
            },
        )

    target_key = "granted" if response.decision == "granted" else "denied"
    target_dir = dirs[target_key]
    target_dir.mkdir(parents=True, exist_ok=True)

    # Combine the original request with the decision for richer downstream
    # consumption. Old request file is removed after the new one is atomically
    # in place.
    with open(awaiting_path, encoding="utf-8") as f:
        request_data = json.load(f)
    merged = {
        "request": request_data,
        "response": response.to_dict(),
    }
    target_path = target_dir / f"{response.request_id}.json"
    atomic_write_json(target_path, merged)

    # Archive for audit.
    dirs["logs"].mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        dirs["logs"] / f"{response.request_id}.decision.json",
        merged,
    )

    # Remove the pending file only after the target is fully written.
    try:
        awaiting_path.unlink()
    except FileNotFoundError:
        pass

    return target_path


def find_decision(session: Session, request_id: str) -> ApprovalResponse | None:
    """Look for a decision (granted or denied) for a request_id.

    Returns None if no decision has been made yet. Used by the executor's
    resume flow to check whether it's safe to re-enter the loop.
    """
    dirs = _approval_dirs(session)
    for key in ("granted", "denied"):
        path = dirs[key] / f"{request_id}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                return ApprovalResponse.from_dict(data["response"])
            except (OSError, json.JSONDecodeError, KeyError, ValueError):
                continue
    return None


# ---------------------------------------------------------------------------
# Convenience builder — called from the executor
# ---------------------------------------------------------------------------


def build_request_from_tool_result(
    *,
    session: Session,
    subgoal_id: str,
    ticket_id: str,
    tool_name: str,
    tool_call_id: str,
    tool_arguments: dict,
    tool_output: dict,
    tool_summary: str,
    reason: str = "",
) -> ApprovalRequest:
    """Build an ApprovalRequest from the information the executor has at
    the moment a tool returns with requires_human_approval=True."""
    return ApprovalRequest(
        request_id=make_request_id(ticket_id, tool_call_id),
        session_id=session.session_id,
        subgoal_id=subgoal_id,
        ticket_id=ticket_id,
        tool_name=tool_name,
        tool_arguments=tool_arguments,
        arguments_sha256=compute_arguments_sha256(tool_arguments),
        proposed_output=tool_output,
        tool_summary=tool_summary,
        created_at=now_utc().isoformat(),
        reason=reason,
    )


__all__ = [
    "ApprovalRequest",
    "ApprovalResponse",
    "AWAITING_DIR_NAME",
    "GRANTED_DIR_NAME",
    "DENIED_DIR_NAME",
    "LOGS_DIR_NAME",
    "build_request_from_tool_result",
    "compute_arguments_sha256",
    "find_decision",
    "get_pending_approval",
    "list_pending_approvals",
    "make_request_id",
    "record_decision",
    "write_approval_request",
]
