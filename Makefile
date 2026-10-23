# Makefile: the commands an agent or the owner runs most, so nobody has to guess a script's flags.
# Every target is a thin wrapper; the script's own docstring is the detail. `make` alone lists them.

PY ?= python3

.DEFAULT_GOAL := help
.PHONY: help check sync sanitise audit-docs replay

help:  ## list the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-9s %s\n", $$1, $$2}'

check:  ## the definition of done: lint must pass (same check as the pre-commit hook)
	@$(PY) scripts/lint.py

sync:  ## pull, commit, push now (laptop settings, no 10-minute wait); last log lines after
	@mkdir -p "$(HOME)/.local/state"
	@DIVAN_MANUAL=1 DIVAN_REPO="$(CURDIR)" DIVAN_ROLE=laptop DIVAN_LOG="$(HOME)/.local/state/divan-sync.log" scripts/divan-sync; \
	  tail -n 3 "$(HOME)/.local/state/divan-sync.log"

sanitise:  ## scan for personal data before a public commit (terms: ~/.config/divan/sanitise-terms.txt)
	@$(PY) scripts/sanitise.py

audit-docs:  ## monthly read-only doc audit (3 Sonnet runs merged); report in logs/audits/
	@bash scripts/audit_docs.sh

replay:  ## do lessons still change the agent? make replay [RUNS=10] [MODEL=sonnet] [ONLY="name"]
	@$(PY) scripts/replay.py "$(HOME)/scratch/divan-replay-$(or $(MODEL),sonnet)" --runs $(or $(RUNS),10) --model $(or $(MODEL),sonnet) $(ONLY)
