#!/usr/bin/env bash
# Assignment 9 — High-action browser demo runner (form fill variant).
#
# Use case: Find top 3 Python AI-agent repositories on GitHub using the
# Advanced Search form — filling multiple text fields and selecting
# dropdowns before submitting the search.
#
# Why this produces many browser actions (mix of type + click):
#   github.com/search/advanced has separate text fields for the search
#   query, language, minimum stars, and creation date. Each field
#   requires a type action; the submit + sort require clicks.
#
#   Expected action sequence:
#     1. type("ai agent")      — fill "Repositories" search field
#     2. type("Python")        — fill "Written in this language" field
#     3. type("500")           — fill "With this many stars" min field
#     4. type("2023-01-01")    — fill "Created after" date field
#     5. click(Search button)  — submit the form
#     6. click(Sort dropdown)  — open sort options
#     7. click("Most stars")   — apply sort
#     8. done                  — read top 3 repo cards
#
# Usage:
#   ./run_assignment9_actions.sh           # run + report
#   ./run_assignment9_actions.sh report    # replay report only (last session)
#   ./run_assignment9_actions.sh wipe      # clear state and logs

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="$SCRIPT_DIR/code"
GW_DIR="$SCRIPT_DIR/../llm_gatewayV9"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

# ── query ─────────────────────────────────────────────────────────────────────
QUERY="Find the top 3 most-starred Python AI agent repositories created after 2023 using GitHub Advanced Search at https://github.com/search/advanced. Extract each repository's name, star count, and description. Present a comparison table."

# ── helpers ───────────────────────────────────────────────────────────────────
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
  local log="$LOG_DIR/assignment9_actions.log"
  echo
  echo "===================================================================="
  echo "  Assignment 9 High-Action: GitHub Advanced Search (form fill)"
  echo "  Browser skill: a11y cascade — type + click + submit + sort"
  echo "  Query: ai agent | Language=Python | Stars>=500 | Since 2023"
  echo "===================================================================="
  echo
  echo "[a9] Running high-action comparison query ..."
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

case "${1:-run}" in
  run)    check_gateway; run_comparison ;;
  report) run_report_only ;;
  wipe)   wipe ;;
  *)
    echo "Usage: $0 [run|report|wipe]"
    exit 1
    ;;
esac
