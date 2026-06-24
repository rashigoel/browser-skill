# Assignment 9 — Architecture Note

## Comparison Task

**Goal**: Compare 5 AI coding tools (GitHub Copilot, Cursor, Tabnine, Codeium, Amazon Q Developer) by visiting each tool's official pricing page. For each: free plan limits, paid plan price/month, top 3 differentiating features.

**Why browser agents are required**: Pricing pages for all five tools use JavaScript-rendered content — plan cards, feature toggles, and pricing tiers only appear after JS execution. `web_search` / `fetch_url` (Session 8's tools) return the page shell without the data. The Browser skill's Playwright-backed layers handle this.

---

## Architecture

```
User Query
    │
    ▼
Planner (gemini)
  Creates one Browser node per tool (5 parallel) + Distiller + Critic + Formatter
    │
    ├─► Browser(GitHub Copilot pricing)  ─┐
    ├─► Browser(Cursor pricing)           │
    ├─► Browser(Tabnine pricing)          ├─► Distiller ─► Critic ─► Formatter
    ├─► Browser(Codeium pricing)          │
    └─► Browser(Amazon Q pricing)        ─┘
```

**No orchestrator changes.** Everything plugs in through the existing skill catalogue (`agent_config.yaml`). The orchestrator (`flow.py`) is untouched.

---

## Four-Layer Browser Cascade

The Browser skill chooses the cheapest path that yields useful data:

| Layer | Mechanism | LLM cost | Used when |
|-------|-----------|----------|-----------|
| 1 — extract | httpx + trafilatura | $0.00 | Static HTML pages |
| 2a — deterministic | Playwright + CSS selectors | $0.00 | Known, stable selectors |
| 2b — a11y | Playwright + accessibility tree + cheap LLM | ~$0.00 | JS-rendered pages with ARIA labels |
| 3 — vision | Playwright + set-of-marks + VLM | ~$0.001/turn | Canvas-only or fully opaque pages |

For AI coding tool pricing pages, **Layer 2b (a11y)** is the natural landing point: all five sites render plan cards via JavaScript but label them with ARIA roles. Layer 1 returns the shell; the a11y tree surfaces the full plan content in ~3–5 turns per site.

---

## Key Design Decisions

1. **One browser node per tool** — lets the orchestrator run all five in parallel. Fan-out is declared by the Planner; the orchestrator executes concurrently.

2. **Distiller with auto-critic** — `critic: true` on the Distiller skill makes the orchestrator automatically splice a Critic node onto the Distiller→Formatter edge. The Critic verifies that each tool's structured fields (free plan, paid price, top features) are present before the Formatter renders the table.

3. **Replay report separate from replay.py** — the existing `replay.py` is interactive (stdin-driven, per-node). The new `replay_report.py` produces a static 8-element report suitable for submission and recording, without touching the orchestrator or persistence layer.

4. **Gateway auto-start** — `gateway.py` in the S9 code auto-starts `llm_gatewayV9` if it is not already running. No manual gateway management is needed before `./run_assignment9.sh`.

---

## Files Added (no orchestrator changes)

```
S9SharedCode/
├── code/
│   └── replay_report.py      NEW — 8-element static replay report generator
├── run_assignment9.sh         NEW — one-command runner (gateway + query + report)
└── ARCHITECTURE.md            NEW — this file
```

The `flow.py` orchestrator, `skills.py` dispatcher, `browser/skill.py`, and all existing prompts are **unchanged**.

---

## Running

```bash
# Prerequisites
cd llm_gatewayV9 && uv run playwright install chromium

# Full run (starts gateway, runs comparison, generates report)
cd S9SharedCode && ./run_assignment9.sh

# Re-generate report from last session (no new LLM calls)
cd S9SharedCode && ./run_assignment9.sh report

# Clear all session data
cd S9SharedCode && ./run_assignment9.sh wipe
```

---

## Cost Profile

| Layer | Per-session cost | Notes |
|-------|-----------------|-------|
| Planner (1 call) | ~$0.00 | Gemini Flash-Lite free tier |
| Browser × 5 (a11y, ~4 turns each) | ~$0.00 | Gemini Flash-Lite free tier |
| Distiller (1 call) | ~$0.00 | Gemini Flash-Lite free tier |
| Critic (1 call) | ~$0.00 | Groq Llama 70B free tier |
| Formatter (1 call) | ~$0.00 | Gemini Flash-Lite free tier |
| **Total** | **~$0.00** | All on free-tier providers |

The cascade keeps browser sessions cheap because **Layer 2b never pays for vision**. If a pricing page blocks the a11y path, the skill escalates to Layer 3 (vision at ~$0.001/turn) and the total still stays under $0.01.
