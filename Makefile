# ==============================================================================
#  sovereign-agent — Makefile
# ==============================================================================
#
# The canonical entry point for every workflow in the repo. This Makefile is
# intentionally *also the README for contributors*: run `make help` and the
# typical workflows plus every target are printed, grouped and explained.
#
# Quick start:
#   make first-run           # install uv project + dev tools + run preflight
#   make test                # 257 tests, ~16s
#   make demo-ch5            # full working agent end-to-end
#   make example-research    # research-assistant example end-to-end
#   make bundle              # tar the repo for sharing
#
# Overridable variables:
#   EXTRAS    extras to include in `uv sync`   (default: all)
#   K         pytest keyword filter            (default: unset)
#   CHAPTER   chapter slug for demo-N targets  (default: all)
#   SCOPE     dir for flatten                  (default: .)
# ==============================================================================

.DEFAULT_GOAL := help
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --no-builtin-rules --no-builtin-variables

# ── Runners ──────────────────────────────────────────────────────────────────
# Everything in this Makefile uses uv. If uv is not installed, `make first-run`
# will tell you where to get it. No pip fallbacks — uv IS the package manager
# for this project.
UV              ?= uv
UV_RUN          := $(UV) run
PY              := $(UV_RUN) python
PYTEST          := $(UV_RUN) pytest
RUFF            := $(UV_RUN) ruff
MYPY            := $(UV_RUN) mypy
MKDOCS          := $(UV_RUN) mkdocs
SOVEREIGN_AGENT := $(UV_RUN) sovereign-agent

# ── Overridable knobs ────────────────────────────────────────────────────────
EXTRAS  ?= all
K       ?=
CHAPTER ?=
SCOPE   ?= .

_PYTEST_K := $(if $(strip $(K)),-k "$(K)",)

# ── Paths ────────────────────────────────────────────────────────────────────
PKG_DIR       := sovereign_agent
TESTS_DIR     := tests
CHAPTERS_DIR  := chapters
EXAMPLES_DIR  := examples
DOCS_DIR      := docs
TRANSIENT_DIR := _transient
BUNDLE_DIR    := $(TRANSIENT_DIR)/bundle
FLATTEN_DIR   := $(TRANSIENT_DIR)/flatten

# ── Colors (auto-disabled when stdout is not a tty) ──────────────────────────
TTY := $(shell test -t 1 && echo 1 || echo 0)
ifeq ($(TTY),1)
BLUE    := $(shell tput setaf 4  2>/dev/null)
GREEN   := $(shell tput setaf 2  2>/dev/null)
YELLOW  := $(shell tput setaf 3  2>/dev/null)
RED     := $(shell tput setaf 1  2>/dev/null)
CYAN    := $(shell tput setaf 6  2>/dev/null)
MAGENTA := $(shell tput setaf 5  2>/dev/null)
BOLD    := $(shell tput bold     2>/dev/null)
DIM     := $(shell tput dim      2>/dev/null)
RESET   := $(shell tput sgr0     2>/dev/null)
endif

RULE    := ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUBRULE := ────────────────────────────────────────────────────────────────────

# ==============================================================================
##@ Help
# ==============================================================================

.PHONY: help
help: ## Show this help with typical workflows and every target
	@printf "\n$(CYAN)%s$(RESET)\n" "$(RULE)"
	@printf " $(BOLD)sovereign-agent$(RESET) $(DIM)·$(RESET) $(BOLD)always-on AI agents that you actually own$(RESET)\n"
	@printf " $(DIM)uv-native · files-first · three surfaces: framework + chapters + lessons$(RESET)\n"
	@printf "$(CYAN)%s$(RESET)\n" "$(RULE)"
	@printf "\n $(DIM)Usage:$(RESET) $(CYAN)make$(RESET) $(BOLD)<target>$(RESET) $(DIM)[VAR=value ...]$(RESET)\n"
	@printf "\n $(MAGENTA)━━━$(RESET) $(BOLD)Typical workflows$(RESET) $(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n\n"
	@printf "  $(BOLD)◆ First time on this repo$(RESET)\n"
	@printf "      $(DIM)1$(RESET)  $(CYAN)make first-run$(RESET)              install uv project + dev tools, run preflight\n"
	@printf "      $(DIM)2$(RESET)  $(DIM)cp .env.example .env$(RESET)         then edit .env and set $(BOLD)NEBIUS_KEY$(RESET)\n"
	@printf "      $(DIM)3$(RESET)  $(CYAN)make verify$(RESET)                 full setup check incl. real LLM round-trip\n"
	@printf "      $(DIM)4$(RESET)  $(CYAN)make demo-ch5-real$(RESET)          your first real agent run\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Daily dev loop$(RESET)\n"
	@printf "      $(DIM)1$(RESET)  $(CYAN)make lint$(RESET)                   ruff check\n"
	@printf "      $(DIM)2$(RESET)  $(CYAN)make test$(RESET)                   run the suite\n"
	@printf "      $(DIM)3$(RESET)  $(CYAN)make demos$(RESET)                  run every chapter demo\n"
	@printf "      $(DIM)4$(RESET)  $(CYAN)make examples$(RESET)               run every example scenario\n"
	@printf "      $(DIM)5$(RESET)  $(CYAN)make drift$(RESET)                  chapter solutions still match production?\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Run a focused subset$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make test K=planner$(RESET)           pytest -k filter\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make demo-ch3$(RESET)               one chapter demo\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-pub-booking$(RESET)    one example scenario\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Real-LLM runs$(RESET) $(DIM)(burns Nebius tokens; reads NEBIUS_KEY from .env)$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-estimate$(RESET)               preview cost + time (no API calls)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real$(RESET)                        $(BOLD)run EVERY -real scenario, collect pass/fail$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-summary$(RESET)                one-line verdict from the most recent run\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-history$(RESET)                list recent runs with pass/fail counts\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-retry-failed$(RESET)           rerun only the scenarios that failed last time\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-clean$(RESET)                  keep 5 most recent runs, delete older\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-quick$(RESET)                  single cheapest call — confirm auth+network\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci-real-logs$(RESET)                   show where the most recent logs live\n"
	@printf "      $(DIM)$(RESET)     $(DIM)— individual scenarios:$(RESET)\n"
	@printf "      $(DIM)$(RESET)     $(DIM)— individual scenarios:$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-research-real$(RESET)          research-assistant against live LLM\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-reviewer-real$(RESET)          code-reviewer against live LLM\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-pub-booking-real$(RESET)       pub-booking against live LLM\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-parallel-research-real$(RESET) v0.2 parallel dispatch against live LLM\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-isolated-worker-real$(RESET)   v0.2 sandbox probe + real-LLM ping\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-classifier-rule-real$(RESET)   v0.2 LLMJudgeVerifier instead of fake classifier\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make example-hitl-deposit-real$(RESET)      v0.2 real LLM adapts to GRANT/DENY\n"
	@printf "      $(DIM)$(RESET)     $(DIM)Artifacts persist at the platform user-data dir$(RESET) $(DIM)(e.g.$(RESET) $(BOLD)~/Library/Application Support/sovereign-agent/examples/$(RESET)$(DIM) on macOS)$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Investigate a failure$(RESET)\n"
	@printf "      $(DIM)1$(RESET)  $(CYAN)make preflight$(RESET)              comprehensive sanity check\n"
	@printf "      $(DIM)2$(RESET)  $(CYAN)make test-verbose$(RESET)           pytest -v --tb=long\n"
	@printf "      $(DIM)3$(RESET)  $(CYAN)make test K=<failing>$(RESET)       rerun just the failing test\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Before a PR$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make ci$(RESET)                     what CI runs: format-check + lint + test + drift\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Docs site$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make docs-serve$(RESET)             mkdocs serve on :8000\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make docs-build$(RESET)             build static site to site/\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Share with an LLM$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make flatten$(RESET)                bundle repo into $(BOLD)$(FLATTEN_DIR)/$(RESET) for pasting\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make flatten SCOPE=$(PKG_DIR)$(RESET)  flatten only the package source\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Ship to PyPI$(RESET) $(DIM)(first-time release workflow)$(RESET)\n"
	@printf "      $(DIM)1$(RESET)  $(CYAN)make pre-publish$(RESET)            audit for secrets, PII, forbidden files\n"
	@printf "      $(DIM)2$(RESET)  $(CYAN)make ready-to-ship$(RESET)          preflight + pre-publish + build in one shot\n"
	@printf "      $(DIM)3$(RESET)  $(DIM)git tag v0.2.0-alpha && git push --tags$(RESET)   triggers publish.yml\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make build$(RESET)                  $(DIM)uv build$(RESET) wheel+sdist locally\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make publish-test$(RESET)           $(DIM)uv publish$(RESET) to TestPyPI (manual)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make bundle$(RESET)                 tar the repo to $(BOLD)$(BUNDLE_DIR)/$(RESET)\n"
	@printf "\n"
	@printf "  $(BOLD)◆ Clean up$(RESET)\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make clean$(RESET)                  remove caches\n"
	@printf "      $(DIM)·$(RESET)  $(CYAN)make distclean$(RESET)              $(DIM)clean$(RESET) + remove $(BOLD)$(TRANSIENT_DIR)/$(RESET), $(BOLD).venv$(RESET), $(BOLD)dist/$(RESET)\n"
	@printf "\n $(MAGENTA)━━━$(RESET) $(BOLD)All targets by category$(RESET) $(MAGENTA)━━━━━━━━━━━━━━━━━━━━━━━━━$(RESET)\n"
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@ / { \
			title = substr($$0, 5); \
			printf "\n $(DIM)───$(RESET) $(BOLD)%s$(RESET) $(DIM)", title; \
			for (i = 0; i < 55 - length(title); i++) printf "─"; \
			printf "$(RESET)\n"; \
			next \
		} \
		/^[a-zA-Z0-9_-]+:.*?## / { \
			printf "  $(CYAN)▸$(RESET) $(BOLD)%-36s$(RESET)  %s\n", $$1, $$2 \
		}' $(MAKEFILE_LIST)
	@printf "\n$(CYAN)%s$(RESET)\n" "$(RULE)"
	@printf " $(DIM)current:$(RESET)  EXTRAS=$(BOLD)$(EXTRAS)$(RESET)"
	@printf "  K=$(if $(K),$(BOLD)$(K)$(RESET),$(DIM)unset$(RESET))"
	@printf "  CHAPTER=$(if $(CHAPTER),$(BOLD)$(CHAPTER)$(RESET),$(DIM)unset$(RESET))"
	@printf "  SCOPE=$(BOLD)$(SCOPE)$(RESET)\n"
	@printf "$(CYAN)%s$(RESET)\n\n" "$(RULE)"

# ==============================================================================
##@ Setup
# ==============================================================================

.PHONY: install
install: ## Install the project + dev group via uv sync
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Installing project and dev tools$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@if ! command -v $(UV) >/dev/null 2>&1; then \
		printf "$(RED)✗$(RESET) uv is not installed.\n"; \
		printf "  $(CYAN)➜$(RESET) install from $(BOLD)https://astral.sh/uv$(RESET) or with:\n"; \
		printf "      $(CYAN)curl -LsSf https://astral.sh/uv/install.sh | sh$(RESET)\n"; \
		exit 127; \
	fi
	@if [ "$(EXTRAS)" = "none" ]; then \
		$(UV) sync --all-groups; \
	else \
		$(UV) sync --all-groups --extra $(EXTRAS); \
	fi
	@printf "$(GREEN)✓$(RESET) $(BOLD)Installed.$(RESET)  $(CYAN)➜$(RESET) next: $(CYAN)make doctor$(RESET) or $(CYAN)make test$(RESET)\n\n"

.PHONY: lock
lock: ## Refresh uv.lock to reflect changes in pyproject.toml
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Refreshing uv.lock$(RESET)\n"
	@$(UV) lock
	@printf "$(GREEN)✓$(RESET) Lockfile updated\n"

.PHONY: upgrade
upgrade: ## Upgrade all dependencies to latest within constraints
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Upgrading dependencies$(RESET)\n"
	@$(UV) lock --upgrade
	@$(UV) sync --all-groups
	@printf "$(GREEN)✓$(RESET) Dependencies upgraded (review uv.lock, then commit)\n"

.PHONY: doctor
doctor: ## Comprehensive environment check — Python, uv, .env, deps, imports, CI
	@$(PY) scripts/doctor.py

.PHONY: doctor-basic
doctor-basic: ## The older sovereign-agent CLI doctor (subset of what `make doctor` checks)
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)sovereign-agent CLI doctor$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@if [ -n "$${NEBIUS_KEY:-}" ]; then \
		$(SOVEREIGN_AGENT) doctor; \
	else \
		printf "$(DIM)NEBIUS_KEY not in shell env; running with --skip-llm.$(RESET)\n"; \
		printf "$(DIM)(If it's in .env, the real doctor will find it — run $(RESET)$(CYAN)$(SOVEREIGN_AGENT) doctor$(RESET)$(DIM) directly.)$(RESET)\n\n"; \
		NEBIUS_KEY=fake $(SOVEREIGN_AGENT) doctor --skip-llm; \
	fi

.PHONY: preflight
preflight: ## Comprehensive contributor preflight (covers the release checklist)
	@$(PY) scripts/preflight.py

.PHONY: verify
verify: ## Verify the full setup: .env, API key, real LLM round-trip, filesystem
	@$(PY) scripts/verify_setup.py

.PHONY: first-run
first-run: install preflight ## Complete first-time setup (install + preflight)
	@printf "\n$(CYAN)%s$(RESET)\n" "$(RULE)"
	@printf " $(GREEN)✓$(RESET) $(BOLD)First-run complete.$(RESET) You're ready.\n"
	@printf "$(CYAN)%s$(RESET)\n" "$(RULE)"
	@printf " $(BOLD)Try next:$(RESET)\n"
	@printf "   $(CYAN)➜$(RESET) $(CYAN)make test$(RESET)           $(DIM)run the suite$(RESET)\n"
	@printf "   $(CYAN)➜$(RESET) $(CYAN)make demo-ch5$(RESET)       $(DIM)see an end-to-end agent run$(RESET)\n"
	@printf "   $(CYAN)➜$(RESET) $(CYAN)make example-research$(RESET) $(DIM)the research-assistant scenario$(RESET)\n"
	@printf "$(CYAN)%s$(RESET)\n\n" "$(RULE)"

# ==============================================================================
##@ Testing
# ==============================================================================

.PHONY: test
test: ## Run the full test suite (core + chapters)
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Running test suite$(RESET)"
	@[ -n "$(K)" ] && printf "  $(DIM)(filter: $(K))$(RESET)" || true
	@printf "\n$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@$(PYTEST) -q $(_PYTEST_K)

.PHONY: test-verbose
test-verbose: ## Verbose pytest with long tracebacks
	@$(PYTEST) -v --tb=long $(_PYTEST_K)

.PHONY: test-unit
test-unit: ## Only unit tests under tests/
	@$(PYTEST) -q tests/ $(_PYTEST_K)

.PHONY: test-integration
test-integration: ## Only the integration tests
	@$(PYTEST) -q tests/integration/ $(_PYTEST_K)

.PHONY: test-examples
test-examples: ## Only the examples-integration tests (v0.1.0 + v0.2 examples as subprocesses)
	@$(PYTEST) -v tests/integration/test_examples.py $(_PYTEST_K)

.PHONY: test-chapters
test-chapters: ## Only chapter tests
	@$(PYTEST) -q chapters/ $(_PYTEST_K)

.PHONY: test-collect
test-collect: ## Show which tests would run, without running them
	@$(PYTEST) --collect-only -q

.PHONY: test-cov
test-cov: ## Run tests with coverage (needs coverage extra)
	@$(UV_RUN) --with coverage python -m coverage run -m pytest -q
	@$(UV_RUN) --with coverage python -m coverage report --show-missing

# ==============================================================================
##@ Chapter demos
# ==============================================================================

.PHONY: demos
demos: ## Run every chapter demo in sequence
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Running every chapter demo$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@for ch in chapter_01_session chapter_02_queue chapter_03_ipc chapter_04_scheduler chapter_05_planner_executor; do \
		printf "  $(CYAN)▸$(RESET) $$ch  "; \
		if $(PY) -m chapters.$$ch.demo > /dev/null 2>&1; then \
			printf "$(GREEN)ok$(RESET)\n"; \
		else \
			printf "$(RED)FAILED$(RESET)\n"; exit 1; \
		fi; \
	done
	@printf "$(GREEN)✓$(RESET) All demos completed\n"

.PHONY: demo-ch1
demo-ch1: ## Chapter 1 demo — session directory
	@$(PY) -m chapters.chapter_01_session.demo

.PHONY: demo-ch2
demo-ch2: ## Chapter 2 demo — SessionQueue
	@$(PY) -m chapters.chapter_02_queue.demo

.PHONY: demo-ch3
demo-ch3: ## Chapter 3 demo — IPC and tickets
	@$(PY) -m chapters.chapter_03_ipc.demo

.PHONY: demo-ch4
demo-ch4: ## Chapter 4 demo — drift-corrected scheduler
	@$(PY) -m chapters.chapter_04_scheduler.demo

.PHONY: demo-ch5
demo-ch5: ## Chapter 5 demo — the full working agent
	@$(PY) -m chapters.chapter_05_planner_executor.demo

.PHONY: demo-ch5-real
demo-ch5-real: ## Chapter 5 demo against a real LLM (reads NEBIUS_KEY from .env)
	@$(PY) -m chapters.chapter_05_planner_executor.demo --real

# ==============================================================================
##@ Example scenarios (offline)
# ==============================================================================

.PHONY: examples
examples: ## Run every example scenario (offline)
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Running every example scenario$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@for ex in research_assistant code_reviewer pub_booking \
	            parallel_research isolated_worker session_resume_chain \
	            classifier_rule hitl_deposit; do \
		printf "  $(CYAN)▸$(RESET) $$ex  "; \
		if $(PY) -m examples.$$ex.run > /dev/null 2>&1; then \
			printf "$(GREEN)ok$(RESET)\n"; \
		else \
			printf "$(RED)FAILED$(RESET)\n"; exit 1; \
		fi; \
	done
	@printf "  $(CYAN)▸$(RESET) pub_booking --oversize  "
	@$(PY) -m examples.pub_booking.run --oversize > /dev/null 2>&1 && printf "$(GREEN)ok$(RESET)\n" || { printf "$(RED)FAILED$(RESET)\n"; exit 1; }
	@printf "  $(CYAN)▸$(RESET) parallel_research --sequential  "
	@$(PY) -m examples.parallel_research.run --sequential > /dev/null 2>&1 && printf "$(GREEN)ok$(RESET)\n" || { printf "$(RED)FAILED$(RESET)\n"; exit 1; }
	@printf "$(GREEN)✓$(RESET) All example scenarios completed\n"

# -- v0.1 examples -------------------------------------------------------------

.PHONY: example-research
example-research: ## Research-assistant scenario
	@$(PY) -m examples.research_assistant.run

.PHONY: example-reviewer
example-reviewer: ## Code-reviewer scenario
	@$(PY) -m examples.code_reviewer.run

.PHONY: example-pub-booking
example-pub-booking: ## Pub-booking scenario (the reference two-half flow)
	@$(PY) -m examples.pub_booking.run

.PHONY: example-pub-booking-oversize
example-pub-booking-oversize: ## Pub booking with party over cap (triggers escalation)
	@$(PY) -m examples.pub_booking.run --oversize

# -- v0.2 examples -------------------------------------------------------------

.PHONY: example-parallel-research
example-parallel-research: ## v0.2 Module 1 — parallel tool dispatch (5 arXiv lookups)
	@$(PY) -m examples.parallel_research.run

.PHONY: example-parallel-research-sequential
example-parallel-research-sequential: ## v0.2 Module 1 — same demo forced sequential for comparison
	@$(PY) -m examples.parallel_research.run --sequential

.PHONY: example-isolated-worker
example-isolated-worker: ## v0.2 Module 2 — subprocess worker under Landlock/sandbox-exec
	@$(PY) -m examples.isolated_worker.run

.PHONY: example-session-resume-chain
example-session-resume-chain: ## v0.2 Module 3 — three-generation session resume
	@$(PY) -m examples.session_resume_chain.run

.PHONY: example-classifier-rule
example-classifier-rule: ## v0.2 Module 4 — ClassifierVerifier driving a StructuredHalf rule
	@$(PY) -m examples.classifier_rule.run

.PHONY: example-hitl-deposit
example-hitl-deposit: ## v0.2 Module 5 — human-in-the-loop deposit approval (grant + deny paths)
	@$(PY) -m examples.hitl_deposit.run

# ==============================================================================
##@ Example scenarios (real LLM — burns Nebius tokens)
# ==============================================================================
#
# All -real targets:
#   - require NEBIUS_KEY, which is loaded by Python from .env (not by the
#     shell). Put NEBIUS_KEY=sk-... in .env at the repo root and it just works.
#     If the key is missing, Python produces [SA_VAL_MISSING_KEY] with
#     a clear pointer to what's wrong.
#   - persist session artifacts under the platform user-data dir, not a tempdir,
#     so you can inspect `trace.jsonl`, `tickets/`, `workspace/` afterwards.
#   - print the artifact path at the end of the run.
#
# Override the persistence location with SOVEREIGN_AGENT_DATA_DIR=<path>.

# -- v0.1 examples (real) ------------------------------------------------------

.PHONY: example-research-real
example-research-real: ## Research-assistant scenario against a real LLM (reads NEBIUS_KEY from .env)
	@$(PY) -m examples.research_assistant.run --real

.PHONY: example-reviewer-real
example-reviewer-real: ## Code-reviewer scenario against a real LLM (reads NEBIUS_KEY from .env)
	@$(PY) -m examples.code_reviewer.run --real

.PHONY: example-pub-booking-real
example-pub-booking-real: ## Pub-booking scenario against a real LLM (reads NEBIUS_KEY from .env)
	@$(PY) -m examples.pub_booking.run --real

.PHONY: example-pub-booking-oversize-real
example-pub-booking-oversize-real: ## Pub-booking oversize (escalation) against a real LLM
	@$(PY) -m examples.pub_booking.run --real --oversize

# -- v0.2 examples (real) ------------------------------------------------------

.PHONY: example-parallel-research-real
example-parallel-research-real: ## v0.2 Module 1 — parallel tool dispatch against a real LLM
	@$(PY) -m examples.parallel_research.run --real

.PHONY: example-isolated-worker-real
example-isolated-worker-real: ## v0.2 Module 2 — sandbox probe + real-LLM round-trip
	@$(PY) -m examples.isolated_worker.run --real

.PHONY: example-session-resume-chain-real
example-session-resume-chain-real: ## v0.2 Module 3 — resume chain + real-LLM round-trip
	@$(PY) -m examples.session_resume_chain.run --real

.PHONY: example-classifier-rule-real
example-classifier-rule-real: ## v0.2 Module 4 — swap FakeClassifier for LLMJudgeVerifier
	@$(PY) -m examples.classifier_rule.run --real

.PHONY: example-hitl-deposit-real
example-hitl-deposit-real: ## v0.2 Module 5 — real LLM + real interactive human (asks on stdin)
	@$(PY) -m examples.hitl_deposit.run --real

.PHONY: example-hitl-deposit-real-approve
example-hitl-deposit-real-approve: ## v0.2 Module 5 — real LLM, auto-approve (for CI/recordings)
	@$(PY) -m examples.hitl_deposit.run --real --approve

.PHONY: example-hitl-deposit-real-deny
example-hitl-deposit-real-deny: ## v0.2 Module 5 — real LLM, auto-deny (for CI/recordings)
	@$(PY) -m examples.hitl_deposit.run --real --deny "£500 exceeds policy; propose alternative under £300"

.PHONY: example-hitl-deposit-real-counter
example-hitl-deposit-real-counter: ## v0.2 Module 5 — real LLM, counter-offer £300 cap
	@$(PY) -m examples.hitl_deposit.run --real --counter-offer 300

# ==============================================================================
##@ Quality
# ==============================================================================

.PHONY: lint
lint: ## ruff check
	@$(RUFF) check $(PKG_DIR)/ $(TESTS_DIR)/ $(CHAPTERS_DIR)/ $(EXAMPLES_DIR)/ scripts/ tools/

.PHONY: fix
fix: ## ruff check --fix (auto-fix what can be auto-fixed)
	@$(RUFF) check --fix $(PKG_DIR)/ $(TESTS_DIR)/ $(CHAPTERS_DIR)/ $(EXAMPLES_DIR)/ scripts/ tools/

.PHONY: format
format: ## ruff format
	@$(RUFF) format $(PKG_DIR)/ $(TESTS_DIR)/ $(CHAPTERS_DIR)/ $(EXAMPLES_DIR)/ scripts/ tools/

.PHONY: format-check
format-check: ## ruff format --check (does not modify files)
	@$(RUFF) format --check $(PKG_DIR)/ $(TESTS_DIR)/ $(CHAPTERS_DIR)/ $(EXAMPLES_DIR)/ scripts/ tools/

.PHONY: typecheck
typecheck: ## mypy (not enforced in CI but useful locally)
	@$(MYPY) $(PKG_DIR)/ || true

.PHONY: drift
drift: ## Verify chapter solutions re-export from the expected production modules
	@$(PY) tools/verify_chapter_drift.py

# ==============================================================================
##@ Docs
# ==============================================================================

.PHONY: docs-serve
docs-serve: ## Serve the docs site on localhost:8000 with live reload
	@$(MKDOCS) serve

.PHONY: docs-build
docs-build: ## Build the static docs site to site/
	@$(MKDOCS) build

.PHONY: docs-strict
docs-strict: ## Build docs with --strict (fails on warnings)
	@$(MKDOCS) build --strict

# ==============================================================================
##@ Build & release
# ==============================================================================

.PHONY: pre-publish
pre-publish: ## Audit for secrets/PII/forbidden files — run BEFORE first public push
	@$(PY) scripts/pre_publish.py

.PHONY: pre-publish-strict
pre-publish-strict: ## pre-publish + scan git history (slower but more thorough)
	@$(PY) scripts/pre_publish.py --git

.PHONY: ready-to-ship
ready-to-ship: preflight pre-publish build ## Full launch checklist: preflight + pre-publish + build
	@printf "\n$(GREEN)✓$(RESET) $(BOLD)Ready to ship.$(RESET)\n"
	@printf "  $(CYAN)➜$(RESET) next: $(CYAN)git tag v0.2.0-alpha && git push origin v0.2.0-alpha$(RESET)\n"
	@printf "  $(DIM)(the publish.yml workflow takes over from there)$(RESET)\n\n"

.PHONY: build
build: ## Build wheel + sdist into dist/ via uv build
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Building distribution$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@$(UV) build
	@ls -lh dist/ 2>/dev/null | tail -n +2

.PHONY: publish-test
publish-test: build ## Publish to TestPyPI (dry-run first with uv publish --dry-run)
	@printf "\n$(YELLOW)▶$(RESET) $(BOLD)Publishing to TestPyPI$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@$(UV) publish --publish-url https://test.pypi.org/legacy/

.PHONY: publish
publish: build ## Publish to PyPI (production)
	@printf "\n$(RED)▶$(RESET) $(BOLD)Publishing to PyPI (PRODUCTION)$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@printf "  This will publish $(BOLD)sovereign-agent$(RESET) to production PyPI.\n"
	@printf "  Press ENTER to continue, Ctrl-C to abort: "
	@read
	@$(UV) publish

.PHONY: bundle
bundle: ## Tar the repo (excluding caches/build artifacts) into _transient/bundle/
	@printf "\n$(BLUE)▶$(RESET) $(BOLD)Bundling repo$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@mkdir -p $(BUNDLE_DIR)
	@tar -czf $(BUNDLE_DIR)/sovereign-agent.tar.gz \
		--exclude='.venv' \
		--exclude='$(TRANSIENT_DIR)' \
		--exclude='dist' \
		--exclude='build' \
		--exclude='site' \
		--exclude='**/__pycache__' \
		--exclude='**/*.pyc' \
		--exclude='**/.pytest_cache' \
		--exclude='**/.ruff_cache' \
		--exclude='**/.mypy_cache' \
		--exclude='**/*.egg-info' \
		--exclude='.git' \
		.
	@ls -lh $(BUNDLE_DIR)/sovereign-agent.tar.gz | awk '{printf "  $(GREEN)✓$(RESET) %s  %s\n", $$5, $$NF}'

# ==============================================================================
##@ LLM sharing (flatten)
# ==============================================================================

.PHONY: flatten
flatten: ## Flatten the repo into a text bundle for pasting into an LLM
	@$(PY) scripts/flatten.py --scope $(SCOPE) --out-dir $(FLATTEN_DIR)
	@printf "$(GREEN)✓$(RESET) See $(BOLD)$(FLATTEN_DIR)/manifest.md$(RESET)\n"

.PHONY: flatten-pkg
flatten-pkg: ## Flatten only the package source (smaller bundle)
	@$(PY) scripts/flatten.py --scope $(PKG_DIR) --out-dir $(FLATTEN_DIR)

.PHONY: flatten-clean
flatten-clean: ## Remove flatten outputs
	@rm -rf $(FLATTEN_DIR)
	@printf "$(GREEN)✓$(RESET) Flatten outputs removed\n"

# ==============================================================================
##@ Cleanup
# ==============================================================================

.PHONY: clean
clean: ## Remove Python caches and bytecode
	@find . -type d -name __pycache__   -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .ruff_cache   -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .mypy_cache   -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info"  -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc"       -delete 2>/dev/null || true
	@printf "$(GREEN)✓$(RESET) Caches cleaned\n"

.PHONY: clean-dist
clean-dist: ## Remove dist/ and build/
	@rm -rf dist build
	@printf "$(GREEN)✓$(RESET) Build artifacts removed\n"

.PHONY: distclean
distclean: clean clean-dist flatten-clean ## Nuke everything transient (caches, .venv, dist, bundles)
	@rm -rf $(TRANSIENT_DIR) .venv site
	@printf "$(GREEN)✓$(RESET) $(BOLD)Everything transient removed$(RESET)\n"

# ==============================================================================
##@ Meta
# ==============================================================================

.PHONY: ci
ci: format-check lint test drift test-examples ## What CI runs: format check + lint + test + drift + examples
	@printf "\n$(GREEN)✓$(RESET) $(BOLD)CI pipeline green$(RESET)\n"

.PHONY: ci-real
ci-real: ## Run every -real scenario against live LLM; retries transient errors; prints failing logs inline
	@$(PY) scripts/ci_real.py run

.PHONY: ci-real-estimate
ci-real-estimate: ## Preview cost and time for a full ci-real run (no API calls)
	@$(PY) scripts/ci_real.py estimate

.PHONY: ci-real-summary
ci-real-summary: ## One-line verdict from the most recent ci-real run
	@$(PY) scripts/ci_real.py summary

.PHONY: ci-real-history
ci-real-history: ## List recent ci-real runs with pass/fail counts
	@$(PY) scripts/ci_real.py history

.PHONY: ci-real-retry-failed
ci-real-retry-failed: ## Rerun only the scenarios that failed in the most recent ci-real
	@$(PY) scripts/ci_real.py retry-failed

.PHONY: ci-real-clean
ci-real-clean: ## Keep the 5 most recent ci-real runs, delete older
	@$(PY) scripts/ci_real.py clean

.PHONY: ci-real-logs
ci-real-logs: ## Show where the last `make ci-real` run's logs live + tail them
	@$(PY) -c "import os, sys; from pathlib import Path; \
		base = (Path.home()/'Library/Caches') if sys.platform=='darwin' else \
		       (Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')) if sys.platform=='win32' else \
		       (Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')); \
		d = base/'sovereign-agent'/'ci-real'; \
		print(f'  cache root: {d}'); \
		latest = d/'latest'; \
		target = latest.readlink() if latest.is_symlink() else None; \
		resolved = (d/target) if target else None; \
		print(f'  latest run: {resolved}' if resolved else '  latest run: (none yet)'); \
		logs = sorted(resolved.glob('*.log')) if resolved and resolved.exists() else []; \
		[print(f'  - {p.name}') for p in logs]; \
		print(); \
		print(f'  tail one:   tail -40 \"{resolved}/<n>.log\"' if resolved else ''); \
		print(f'  summary:    cat \"{resolved}/summary.txt\"' if resolved else '')"

.PHONY: ci-real-quick
ci-real-quick: ## Single cheapest real-LLM round-trip to confirm auth/network/model work
	@printf "\n$(YELLOW)▶$(RESET) $(BOLD)Quick real-LLM smoke (parallel_research is cheapest)$(RESET)\n"
	@printf "$(DIM)%s$(RESET)\n" "$(SUBRULE)"
	@$(MAKE) -s example-parallel-research-real 2>&1 | tail -20

.PHONY: all
all: install preflight test demos examples ## Everything end-to-end (install → tests → demos → examples)

.PHONY: all-with-real
all-with-real: all ci-real ## Everything above + every -real scenario (burns Nebius tokens)

.PHONY: status
status: ## One-line status line
	@$(PY) -c "import sovereign_agent as sa; print(f'sovereign-agent {sa.__version__}, {len(sa.__all__)} exports')"
