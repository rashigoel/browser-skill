#!/usr/bin/env bash
# Assignment 9 — VLM (Vision Layer) demo runner.
#
# Use case: Compare React, Vue, and Angular weekly npm download counts
# by reading the line chart on npmtrends.com.
#
# Why this invokes Layer 3 (VLM):
#   The npmtrends chart is rendered as SVG paths — the download numbers
#   live only in the visual chart, not in DOM text. The a11y driver
#   (Layer 2b) sees an empty legend with no chart values and calls
#   done(success=False). skills.py detects "download trend" in the goal
#   and sets force_path=vision, routing directly to SetOfMarksDriver
#   which takes an annotated screenshot and sends it to Gemini Vision.
#
# Usage:
#   ./run_assignment9_vlm.sh           # run + report
#   ./run_assignment9_vlm.sh report    # replay report only (last session)
#   ./run_assignment9_vlm.sh wipe      # clear state and logs

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="$SCRIPT_DIR/code"
GW_DIR="$SCRIPT_DIR/../llm_gatewayV9"
LOG_DIR="$SCRIPT_DIR/logs"

mkdir -p "$LOG_DIR"

# ── VLM comparison query ──────────────────────────────────────────────────────
QUERY="Compare weekly npm download trends for React, Vue, and Angular using npmtrends.com. Present a comparison table."

# ── helpers ──────────────────────────────────────────────────────────────────
check_gateway() {
  if curl -sf http://localhost:8109/v1/routers >/dev/null 2>&1; then
    echo "[vlm] V9 gateway is up at http://localhost:8109"
  else
    echo "[vlm] Starting V9 gateway from $GW_DIR ..."
    if [[ ! -d "$GW_DIR" ]]; then
      echo "[vlm] ERROR: gateway directory not found: $GW_DIR" >&2
      exit 1
    fi
    ( cd "$GW_DIR" && uv run main.py >/dev/null 2>&1 ) &
    for i in {1..45}; do
      sleep 1
      if curl -sf http://localhost:8109/v1/routers >/dev/null 2>&1; then
        echo "[vlm] Gateway started in ${i}s"
        break
      fi
      if [[ $i -eq 45 ]]; then
        echo "[vlm] ERROR: Gateway failed to start. Check $GW_DIR" >&2
        exit 1
      fi
    done
  fi
}

run_comparison() {
  local log="$LOG_DIR/assignment9_vlm.log"
  echo
  echo "===================================================================="
  echo "  Assignment 9 VLM: npm Download Trend Chart Comparison"
  echo "  Browser skill: Layer 3 — SetOfMarks vision (screenshot → Gemini)"
  echo "  Task: read React vs Vue vs Angular download chart"
  echo "===================================================================="
  echo
  echo "[vlm] Running VLM comparison query ..."
  echo "[vlm] Log -> $log"
  echo

  ( cd "$CODE_DIR" && uv run python flow.py "$QUERY" 2>&1 ) | tee "$log"

  local sid
  sid=$(ls -t "$CODE_DIR/state/sessions" 2>/dev/null | head -1)
  if [[ -z "$sid" ]]; then
    echo "[vlm] ERROR: no session created" >&2
    exit 1
  fi

  echo
  echo "[vlm] Session: $sid"
  echo "[vlm] Generating 8-element replay report ..."
  echo

  ( cd "$CODE_DIR" && uv run python replay_report.py "$sid" --md )

  local report="$CODE_DIR/state/sessions/$sid/replay_report.md"
  if [[ -f "$report" ]]; then
    echo
    echo "[vlm] Report written -> $report"
  fi
}

run_report_only() {
  local sid
  sid=$(ls -t "$CODE_DIR/state/sessions" 2>/dev/null | head -1)
  if [[ -z "$sid" ]]; then
    echo "[vlm] No sessions found under $CODE_DIR/state/sessions/" >&2
    exit 1
  fi
  echo "[vlm] Replaying session: $sid"
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
  echo "[vlm] Cleared: state/sessions, state/artifacts, FAISS index, logs"
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
