#!/usr/bin/env bash
# Assignment 9 — Browser Comparison Agent runner.
#
# Task: Navigate to github.com/trending, filter by Language=Python and
#       Date Range=This week using real browser interactions, then
#       extract and compare the top 3 trending Python repositories.
#
# What this script does:
#   1. Checks the V9 gateway is running (starts it if not)
#   2. Runs the comparison query through flow.py
#   3. Prints the 8-element replay report to stdout
#   4. Writes the report to state/sessions/<sid>/replay_report.md
#
# Prerequisites:
#   - uv installed  (https://github.com/astral-sh/uv)
#   - llm_gatewayV9 built alongside this repo (../llm_gatewayV9/)
#   - API keys in ../llm_gatewayV9/.env  (Gemini key required)
#   - Playwright browsers installed: uv run playwright install chromium
#
# Usage:
#   ./run_assignment9.sh           # full run: gateway + query + report
#   ./run_assignment9.sh report    # replay report only (last session)
#   ./run_assignment9.sh wipe      # clear state and logs

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="$SCRIPT_DIR/code"
GW_DIR="$SCRIPT_DIR/../llm_gatewayV9"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

# ── comparison query ─────────────────────────────────────────────────────────
QUERY="Navigate to https://github.com/trending and compare the top 3 trending Python repositories this week. On the trending page: (1) click the Language dropdown and select Python, (2) click the Date Range dropdown and select This week, (3) then read the top 3 repository cards. For each repo extract: repository full name (owner/repo), star count, fork count, and the one-line description. Present a structured comparison table."

# ── helpers ──────────────────────────────────────────────────────────────────
check_gateway() {
  if curl -sf http://localhost:8109/v1/routers >/dev/null 2>&1; then
    echo "[a9] V9 gateway is up at http://localhost:8109"
  else
    echo "[a9] Starting V9 gateway from $GW_DIR ..."
    if [[ ! -d "$GW_DIR" ]]; then
      echo "[a9] ERROR: gateway directory not found: $GW_DIR" >&2
      exit 1
    fi
    ( cd "$GW_DIR" && uv run main.py >/dev/null 2>&1 ) &
    for i in {1..45}; do
      sleep 1
      if curl -sf http://localhost:8109/v1/routers >/dev/null 2>&1; then
        echo "[a9] Gateway started in ${i}s"
        break
      fi
      if [[ $i -eq 45 ]]; then
        echo "[a9] ERROR: Gateway failed to start. Check $GW_DIR" >&2
        exit 1
      fi
    done
  fi
}

run_comparison() {
  local log="$LOG_DIR/assignment9.log"
  echo
  echo "===================================================================="
  echo "  Assignment 9: GitHub Trending Python Repos Comparison"
  echo "  Browser skill: a11y cascade (extract → a11y → vision)"
  echo "  Task: filter Language=Python, Date=This week, extract top 3"
  echo "===================================================================="
  echo
  echo "[a9] Running comparison query ..."
  echo "[a9] Log -> $log"
  echo

  ( cd "$CODE_DIR" && uv run python flow.py "$QUERY" 2>&1 ) | tee "$log"

  local sid
  sid=$(ls -t "$CODE_DIR/state/sessions" 2>/dev/null | head -1)
  if [[ -z "$sid" ]]; then
    echo "[a9] ERROR: no session created" >&2
    exit 1
  fi

  echo
  echo "[a9] Session: $sid"
  echo "[a9] Generating 8-element replay report ..."
  echo

  ( cd "$CODE_DIR" && uv run python replay_report.py "$sid" --md )

  local report="$CODE_DIR/state/sessions/$sid/replay_report.md"
  if [[ -f "$report" ]]; then
    echo
    echo "[a9] Report written -> $report"
    echo "[a9] To re-view the interactive step-by-step replay:"
    echo "       cd $CODE_DIR && uv run python replay.py $sid"
  fi
}

run_report_only() {
  local sid
  sid=$(ls -t "$CODE_DIR/state/sessions" 2>/dev/null | head -1)
  if [[ -z "$sid" ]]; then
    echo "[a9] No sessions found under $CODE_DIR/state/sessions/" >&2
    exit 1
  fi
  echo "[a9] Replaying session: $sid"
  ( cd "$CODE_DIR" && uv run python replay_report.py "$sid" --md )
}

wipe() {
  rm -rf \
    "$CODE_DIR/state/sessions" \
    "$CODE_DIR/state/artifacts" \
    "$CODE_DIR/state/index.faiss" \
    "$CODE_DIR/state/index_ids.json" \
    "$CODE_DIR/state/memory.json" \
    "$LOG_DIR"
  mkdir -p "$LOG_DIR"
  echo "[a9] Cleared: state/sessions, state/artifacts, FAISS index, logs"
}

# ── dispatch ─────────────────────────────────────────────────────────────────
case "${1:-run}" in
  run)    check_gateway; run_comparison ;;
  report) run_report_only ;;
  wipe)   wipe ;;
  *)
    echo "Usage: $0 [run|report|wipe]"
    exit 1
    ;;
esac
