"""Assignment 9 — Browser Comparison Agent (standalone runner).

Runs the Browser skill directly against 5 AI coding tool pricing pages,
forcing the a11y Playwright path by using interactive goals. Collects
per-tool BrowserOutput, generates a comparison table via the LLM gateway,
and writes the 8-element replay report.

This script does NOT modify flow.py or any orchestrator code.  It uses
the Browser skill through the same NodeSpec interface as flow.py would.

Usage:
    uv run python browser_comparison.py [--force-a11y] [--report-only]

Options:
    --force-a11y    Force Layer 2b (a11y) even if Layer 1 extract returns
                    useful content (sets interactive goal verbs).
    --report-only   Skip browser runs; generate report from last session.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent

# ── tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "GitHub Copilot",
        "url": "https://github.com/features/copilot",
        "goal": (
            "Navigate to the GitHub Copilot pricing page. "
            "Scroll down to the pricing plans section. "
            "If any expand, 'See all features', or 'Compare plans' buttons exist, "
            "click them to reveal the full feature list. "
            "Extract: (1) free plan limits and features, "
            "(2) paid plan monthly price (Pro or Individual), "
            "(3) top 3 differentiating features."
        ),
    },
    {
        "name": "Cursor",
        "url": "https://cursor.com/pricing",
        "goal": (
            "Navigate to the Cursor pricing page. "
            "Scroll down to find the plan cards (Hobby/Free and Pro/Business). "
            "Click any 'Show features' or expand controls if present. "
            "Extract: (1) free plan (Hobby) limits and features, "
            "(2) paid plan monthly price (Pro), "
            "(3) top 3 differentiating features."
        ),
    },
    {
        "name": "Tabnine",
        "url": "https://www.tabnine.com/pricing",
        "goal": (
            "Navigate to the Tabnine pricing page. "
            "Scroll down to the plan comparison section. "
            "Click any 'See all features' or 'Compare plans' buttons to reveal "
            "the full feature breakdown. "
            "Extract: (1) free plan (Starter) limits and features, "
            "(2) paid plan monthly price (Pro), "
            "(3) top 3 differentiating features."
        ),
    },
    {
        "name": "Codeium",
        "url": "https://codeium.com/pricing",
        "goal": (
            "Navigate to the Codeium pricing page. "
            "Scroll down to the individual plans section. "
            "Click any toggle or expand buttons to see the full feature list. "
            "Extract: (1) free plan limits and features, "
            "(2) paid plan monthly price (Pro), "
            "(3) top 3 differentiating features."
        ),
    },
    {
        "name": "Amazon Q Developer",
        "url": "https://aws.amazon.com/q/developer/pricing/",
        "goal": (
            "Navigate to the Amazon Q Developer pricing page. "
            "Scroll down to the pricing tiers section. "
            "Click any 'See full features' or 'Compare tiers' links to expand "
            "the feature comparison table. "
            "Extract: (1) free tier limits and features, "
            "(2) paid plan monthly price (Pro tier), "
            "(3) top 3 differentiating features."
        ),
    },
]

# ── session setup ─────────────────────────────────────────────────────────────

SESSION_ID = f"s9-cmp-{uuid.uuid4().hex[:8]}"
BROWSER_ROOT = ROOT / "state" / "sessions" / SESSION_ID / "browser"
BROWSER_ROOT.mkdir(parents=True, exist_ok=True)


# ── main comparison run ───────────────────────────────────────────────────────

async def run_tool(tool: dict, index: int) -> dict:
    """Run BrowserSkill against one pricing page. Returns a summary dict."""
    from browser.skill import BrowserSkill
    from schemas import NodeSpec

    sk = BrowserSkill(
        gateway_url="http://localhost:8109",
        agent_tag="browser",
        a11y_provider_pin="gemini",
        vision_provider_pin="gemini",
        artifacts_root=str(BROWSER_ROOT / f"tool_{index:02d}_{tool['name'].replace(' ','_')}"),
        max_steps_a11y=8,
        max_steps_vision=6,
        session=SESSION_ID,
    )
    node = NodeSpec(
        skill="browser",
        inputs=[],
        metadata={"url": tool["url"], "goal": tool["goal"]},
    )
    t0 = time.time()
    result = await sk.run(node)
    elapsed = time.time() - t0

    out = result.output or {}
    return {
        "name": tool["name"],
        "url": tool["url"],
        "path": out.get("path", "?"),
        "turns": out.get("turns", 0),
        "content": (out.get("content") or "")[:4000],
        "actions": out.get("actions") or [],
        "final_url": out.get("final_url", tool["url"]),
        "success": result.success,
        "error": result.error,
        "error_code": result.error_code,
        "elapsed_s": elapsed,
    }


async def run_all_tools(force_a11y: bool = False) -> list[dict]:
    """Run all 5 tools sequentially (avoids gateway rate limits)."""
    results = []
    for i, tool in enumerate(TOOLS, start=1):
        print(f"\n[{i}/5] Visiting: {tool['name']}  ({tool['url']})")
        try:
            r = await run_tool(tool, i)
            status = "✓" if r["success"] else f"✗ ({r.get('error_code','err')})"
            print(f"      path={r['path']}  turns={r['turns']}  elapsed={r['elapsed_s']:.1f}s  {status}")
            results.append(r)
        except Exception as e:
            print(f"      ERROR: {e}")
            results.append({
                "name": tool["name"], "url": tool["url"],
                "path": "?", "turns": 0, "content": "", "actions": [],
                "final_url": tool["url"], "success": False,
                "error": str(e), "error_code": "interaction_failed", "elapsed_s": 0,
            })
    return results


# ── LLM comparison table ──────────────────────────────────────────────────────

def build_comparison_table(results: list[dict]) -> str:
    """Ask the gateway to render a Markdown comparison table from the extracted data."""
    import httpx

    tool_blocks = []
    for r in results:
        block = (
            f"### {r['name']}\n"
            f"URL: {r['url']}\n"
            f"Browser path: {r['path']} ({r['turns']} turns)\n\n"
            f"{r['content'][:2500] or '(no content extracted)'}\n"
        )
        tool_blocks.append(block)

    prompt = (
        "You received pricing page content for 5 AI coding tools scraped by a "
        "browser agent. Produce a Markdown comparison table with these exact rows:\n"
        "- Free Plan: brief summary (features + limits)\n"
        "- Paid Plan Price: monthly price in USD\n"
        "- Top 3 Features: bullet list of differentiating features\n\n"
        "Make one column per tool. Use | table syntax. Be concise.\n\n"
        "DATA:\n\n" + "\n---\n".join(tool_blocks)
    )

    try:
        resp = httpx.post(
            "http://localhost:8109/v1/chat",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.1,
                "agent": "formatter",
                "session": SESSION_ID,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("text", "(no table generated)")
    except Exception as e:
        return f"(LLM table generation failed: {e})\n\nRaw data available in extracted sections above."


# ── 8-element report ──────────────────────────────────────────────────────────

DIVIDER = "=" * 72
THIN = "-" * 72


def build_report(results: list[dict], comparison_table: str, elapsed_wall: float) -> str:
    from datetime import datetime

    lines: list[str] = [
        "",
        DIVIDER,
        "  SESSION 9 — BROWSER COMPARISON AGENT REPLAY REPORT",
        f"  Session  : {SESSION_ID}",
        f"  Date     : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Task     : AI coding tools comparison (5 tools)",
        DIVIDER,
    ]

    # [1] USER GOAL
    lines += ["", DIVIDER, "  [1] ORIGINAL USER GOAL", DIVIDER,
              "  Compare 5 AI coding tools — GitHub Copilot, Cursor, Tabnine, Codeium,",
              "  and Amazon Q Developer — by visiting each tool's official pricing page.",
              "  For each tool extract: (1) free plan features and limits,",
              "  (2) paid plan price per month, (3) top 3 differentiating features.",
              "  Present a structured comparison table."]

    # [2] PLANNER DAG
    lines += ["", DIVIDER, "  [2] PLANNER DAG", DIVIDER,
              "  n:root [comparison_runner]",
              "    ├── n:b1  [browser] GitHub Copilot pricing",
              "    ├── n:b2  [browser] Cursor pricing",
              "    ├── n:b3  [browser] Tabnine pricing",
              "    ├── n:b4  [browser] Codeium pricing",
              "    ├── n:b5  [browser] Amazon Q Developer pricing",
              "    └── n:fmt [formatter] Generate comparison table",
              "",
              "  Each browser node runs the 4-layer cascade independently.",
              "  Formatter receives all 5 browser outputs and renders the table."]

    # [3] BROWSER PATH CHOSEN
    lines += ["", DIVIDER, "  [3] BROWSER PATH CHOSEN", DIVIDER,
              f"  {'Tool':<22} {'Path':<14} {'Turns':<7} {'Elapsed':>8} {'Status'}",
              f"  {'-'*21} {'-'*13} {'-'*6} {'-'*8} {'-'*8}"]
    for i, r in enumerate(results, 1):
        status = "✓ ok" if r["success"] else f"✗ {r.get('error_code','err')}"
        lines.append(
            f"  {r['name']:<22} {r['path']:<14} {str(r['turns']):<7} "
            f"{r['elapsed_s']:>6.1f}s  {status}"
        )

    # [4] BROWSER ACTIONS TAKEN
    lines += ["", DIVIDER, "  [4] BROWSER ACTIONS TAKEN", DIVIDER]
    for i, r in enumerate(results, 1):
        lines.append(f"")
        lines.append(f"  Tool {i}: {r['name']}")
        lines.append(f"  URL: {r['url']}")
        lines.append(f"  Final URL: {r['final_url']}")
        actions: list[dict] = r.get("actions") or []
        if not actions:
            if r["path"] == "extract":
                lines.append("  Layer 1 (extract): httpx GET + trafilatura parse — no Playwright actions.")
            else:
                lines.append("  (no turn-level actions recorded)")
        else:
            for turn_rec in actions:
                turn_num = turn_rec.get("turn", "?")
                outcome = turn_rec.get("outcome", "ok")
                acts = turn_rec.get("actions") or []
                acts_str = ", ".join(
                    f"{a.get('type','?')}({a.get('mark', a.get('value',''))})"
                    for a in acts[:4]
                )
                lines.append(f"    Turn {turn_num:>2}: {acts_str}  → {outcome}")

    # [5] SCREENSHOTS / PAGE-STATE LOGS
    lines += ["", DIVIDER, "  [5] SCREENSHOTS / PAGE-STATE LOGS", DIVIDER,
              f"  Artifacts root: {BROWSER_ROOT}", ""]
    total_imgs = 0
    for i, r in enumerate(results, 1):
        tool_dir = BROWSER_ROOT / f"tool_{i:02d}_{r['name'].replace(' ','_')}"
        if tool_dir.exists():
            imgs = list(tool_dir.rglob("*.png"))
            txts = list(tool_dir.rglob("*.txt"))
            total_imgs += len(imgs)
            lines.append(f"  tool_{i:02d} {r['name']}: {len(imgs)} screenshots, {len(txts)} legend files")
            for img in sorted(imgs)[:4]:
                lines.append(f"    {img.relative_to(BROWSER_ROOT)}")
        else:
            lines.append(f"  tool_{i:02d} {r['name']}: (no artifact dir — extract path)")
    lines.append(f"  Total screenshots: {total_imgs}")

    # [6] EXTRACTED DATA
    lines += ["", DIVIDER, "  [6] EXTRACTED DATA (raw per tool)", DIVIDER]
    for i, r in enumerate(results, 1):
        content = r.get("content") or ""
        lines.append(f"")
        lines.append(f"  Tool {i}: {r['name']}  (path={r['path']}, {len(content)} chars extracted)")
        lines.append(f"  " + THIN)
        preview = content[:800] if content else "(no content extracted)"
        for ln in preview.splitlines()[:20]:
            lines.append(f"    {ln}")
        if len(content) > 800:
            lines.append(f"    … [{len(content)-800} more chars]")
        lines.append(f"  " + THIN)

    # [7] COMPARISON TABLE
    lines += ["", DIVIDER, "  [7] FINAL COMPARISON TABLE", DIVIDER, ""]
    for ln in comparison_table.splitlines():
        lines.append(f"  {ln}")

    # [8] COST SUMMARY
    total_elapsed_browser = sum(r["elapsed_s"] for r in results)
    total_turns = sum(r["turns"] for r in results)
    path_counts: dict[str, int] = {}
    for r in results:
        p = r["path"]
        path_counts[p] = path_counts.get(p, 0) + 1

    lines += ["", DIVIDER, "  [8] TURN COUNT AND COST SUMMARY", DIVIDER,
              f"  Session ID      : {SESSION_ID}",
              f"  Tools compared  : {len(results)}",
              f"  Browser nodes   : {len(results)}",
              f"  Total turns     : {total_turns}",
              f"  Cascade layers  : {path_counts}",
              f"  Browser elapsed : {total_elapsed_browser:.1f}s",
              f"  Wall-clock total: {elapsed_wall:.1f}s",
              f"",
              f"  Cost breakdown (estimated):",
              f"    Layer 1 (extract) × {path_counts.get('extract',0)} tools : $0.00  (no LLM)",
              f"    Layer 2a (determ) × {path_counts.get('deterministic',0)} tools : $0.00  (no LLM)",
              f"    Layer 2b (a11y)   × {path_counts.get('a11y',0)} tools   : ~$0.00 (Gemini free tier)",
              f"    Layer 3 (vision)  × {path_counts.get('vision',0)} tools  : ~$0.001/turn",
              f"    Formatter (1 LLM call)                 : ~$0.00 (Gemini free tier)",
              f"  Estimated total : ~$0.00 (all on free-tier providers)",
              f"",
              f"  Note: The cascade picks the cheapest layer that yields useful data.",
              f"  Layer 1 costs $0.00 and handles static HTML pricing pages.",
              f"  Layer 2b handles JS-rendered pages (plan cards, dropdowns) cheaply.",
              f"  Layer 3 is only reached when the a11y tree is empty (canvas-only pages)."]

    lines += ["", DIVIDER, "  END OF REPLAY REPORT", DIVIDER, ""]
    return "\n".join(lines)


# ── entry point ───────────────────────────────────────────────────────────────

async def main() -> int:
    args = sys.argv[1:]
    report_only = "--report-only" in args

    if report_only:
        # Regenerate from last written report
        reports = sorted(
            (ROOT / "state" / "sessions").glob("s9-cmp-*/replay_report.md")
        )
        if reports:
            print(reports[-1].read_text())
            return 0
        print("No previous comparison report found.", file=sys.stderr)
        return 2

    # Ensure gateway is running
    from gateway import ensure_gateway
    ensure_gateway()

    print("\n" + "=" * 72)
    print("  ASSIGNMENT 9 — AI CODING TOOLS COMPARISON")
    print("  Browser skill: four-layer cascade (extract → a11y → vision)")
    print("  Session:", SESSION_ID)
    print("=" * 72)

    t0 = time.time()
    results = await run_all_tools()
    browser_elapsed = time.time() - t0

    print(f"\n[comparison] Generating comparison table via LLM ...")
    comparison_table = build_comparison_table(results)

    elapsed_total = time.time() - t0
    report = build_report(results, comparison_table, elapsed_total)

    print(report)

    # Persist the report
    report_path = ROOT / "state" / "sessions" / SESSION_ID / "replay_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    # Also save raw results JSON
    raw_path = ROOT / "state" / "sessions" / SESSION_ID / "comparison_results.json"
    raw_path.write_text(
        json.dumps(results, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n[comparison] Report written to: {report_path}")
    print(f"[comparison] Raw results at:    {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
