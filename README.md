# Browser Skill — Assignment 9: Browser Comparison Agent + Replay Viewer

A browser-capable multi-agent system built on the S9SharedCode runtime. The agent performs real comparison tasks on the web using a four-layer browser cascade and produces an 8-element static replay report.

## Four-Layer Browser Cascade

```
Layer 1   HTTP extract via trafilatura       $0.00 — no LLM
Layer 2a  Deterministic CSS selectors        $0.00 — no LLM
Layer 2b  A11y driver (accessibility tree)   cheap — text-only LLM call
Layer 3   Set-of-Marks vision driver         vision LLM call per turn
```

Each layer escalates only when the previous one is insufficient. Interactive goals (containing "click", "filter", "sort", etc.) skip Layer 1 automatically.

## Use Cases

| Script | Task | Layer |
|--------|------|-------|
| `run_assignment9.sh` | GitHub trending top-3 Python repos this week | a11y (Layer 2b) |
| `run_assignment9_vlm.sh` | npm download trend chart — React vs Vue vs Angular | vision (Layer 3) |
| `run_assignment9_actions.sh` | GitHub Advanced Search with form fill | vision (Layer 3) |

## Usage

```bash
# Prerequisites
uv run playwright install chromium

# Start gateway (one-time)
cd ../llm_gatewayV9 && uv run main.py &

# Run comparison + generate replay report
bash run_assignment9_actions.sh

# Replay report only (last session)
bash run_assignment9_actions.sh report

# Wipe session state
bash run_assignment9_actions.sh wipe
```

---

## Execution Output — GitHub Advanced Search (run_assignment9_actions.sh)

**Session:** `s8-cf44fa98` | **Date:** 2026-06-24 14:22 | **Nodes:** 7

### [1] Original User Goal

```
Find the top 3 most-starred Python AI agent repositories created
after 2023 using GitHub Advanced Search at
https://github.com/search/advanced. Extract each repository's
name, star count, and description. Present a comparison table.
```

### [2] Planner DAG

```
├── n:1 [planner] ✓
├── n:2 [browser] ✗  path=?  turns=?
├── n:5 [planner] ✓
└── n:6 [browser] ✓  path=vision  turns=6
    └── n:7 [distiller] ✓
        ├── n:8 [formatter] ✓
        └── n:9 [critic] ✓
```

### [3] Browser Path Chosen

| Node | Goal | Path | Turns | Status |
|------|------|------|-------|--------|
| n:2 | — | — | — | failed |
| n:6 | Search for 'ai agent language:python created:>2023-01-01', sort... | **vision** | 6 | complete |

> n:6 naturally escalated to **Layer 3 (vision)** — the recovery planner redirected to `github.com/search` (not the advanced form), and the a11y layer could not complete the search+sort sequence, escalating to the Set-of-Marks vision driver which sent annotated screenshots to Gemini Vision.

### [4] Browser Actions Taken

**n:6** — `https://github.com/search` → `https://github.com/search?q=ai+agent+language%3Apython+created%3A%3E2023-01-01&type=repositories&s=stars&o=desc`

```
turn 1: type(1), key(Enter)   → ok | ok   [typed full search query, submitted]
turn 2: click(13)             → ok        [clicked Repositories filter]
turn 3: click(34)             → ok        [clicked Sort dropdown]
turn 4: click(43)             → ok        [selected Most stars]
turn 5: wait()                → ok        [waited for results to load]
turn 6: done(success=True)    → done      [extracted top 3 repos]
```

### [5] Screenshots / Page-State Logs

51 total artifacts across 2 browser runs. n:6 produced **24 screenshots** (6 turns × raw + marked) stored under `state/sessions/s8-cf44fa98/browser/browser_1782291077/`.

### [6] Extracted Data

```
repositories Search Results · ai agent language:python created:>2023-01-01
Filter by Languages | Advanced | 182k results
Langflow is a powerful tool for building and deploying AI-powered agents and workflows.
OpenHands: AI-Driven Development
An open-source long-horizon SuperAgent harness...
```

### [7] Final Comparison Table

| Repository Name | Stars | Description |
|:----------------|:------|:------------|
| NousResearch/hermes-agent | 201k | The agent that grows with you |
| langflow-ai/langflow | 150k | Langflow is a powerful tool for building and deploying AI-powered agents and workflows. |
| Shubhamsaboo/awesome-llm-apps | 115k | 100+ AI Agent & RAG apps you can actually run — clone, customize, ship. |

### [8] Turn Count and Cost Summary

| Metric | Value |
|--------|-------|
| Session ID | s8-cf44fa98 |
| Nodes total | 7 (complete=6, failed=1) |
| Browser nodes | 2 |
| Browser turns | 6 |
| Cascade layers | vision (Layer 3) |
| Providers used | gemini, groq |
| Total elapsed | 93.8s |
| Estimated cost | ~$0.00 (free-tier Gemini) |
