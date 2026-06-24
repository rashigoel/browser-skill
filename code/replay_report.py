"""Session 9 — 8-element static replay report for the Browser Comparison Agent.

Reads a persisted session from state/sessions/<sid>/ and prints a full
structured report covering:

  [1] Original user goal
  [2] Planner DAG (ASCII edge tree)
  [3] Browser path chosen per browser node (extract / deterministic / a11y / vision)
  [4] Browser actions taken per turn
  [5] Screenshots / page-state logs (artifact file paths)
  [6] Extracted data per browser node (raw content preview)
  [7] Final comparison table (from formatter node output)
  [8] Turn count and cost summary

Optionally writes the same content to a Markdown file for submission.

Usage:
    uv run python replay_report.py [session_id] [--md]

    uv run python replay_report.py              # most recent session, terminal only
    uv run python replay_report.py <sid>        # specific session
    uv run python replay_report.py <sid> --md   # also write <sid>_report.md
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from persistence import SessionStore, list_sessions
from schemas import NodeState

ROOT = Path(__file__).parent
SESSIONS_ROOT = ROOT / "state" / "sessions"
DIVIDER = "=" * 72
THIN = "-" * 72


# ── helpers ───────────────────────────────────────────────────────────────────

def _truncate(s: str, n: int = 800) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[:n] + f"\n… [{len(s) - n} more chars]"


def _json_preview(obj, n: int = 1200) -> str:
    try:
        raw = json.dumps(obj, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        raw = str(obj)
    return _truncate(raw, n)


def _pad(label: str, width: int = 18) -> str:
    return label.ljust(width)


# ── section printers ──────────────────────────────────────────────────────────

def _section(title: str, lines: list[str]) -> list[str]:
    out = ["", DIVIDER, f"  {title}", DIVIDER]
    out.extend(lines)
    return out


def section_goal(query: str) -> list[str]:
    wrapped = textwrap.fill(query, width=68, initial_indent="  ", subsequent_indent="  ")
    return _section("[1] ORIGINAL USER GOAL", [wrapped])


def section_dag(states: list[NodeState]) -> list[str]:
    """ASCII tree of the node graph derived from node inputs."""
    lines: list[str] = []
    node_map: dict[str, NodeState] = {s.node_id: s for s in states}

    # Build parent → children map from inputs.
    children: dict[str, list[str]] = {s.node_id: [] for s in states}
    roots: list[str] = []
    for st in states:
        parents = [i for i in (st.inputs or []) if i.startswith("n:") and i in node_map]
        if not parents:
            roots.append(st.node_id)
        for p in parents:
            if st.node_id not in children[p]:
                children[p].append(st.node_id)

    def _render(nid: str, prefix: str, is_last: bool) -> None:
        st = node_map.get(nid)
        skill = st.skill if st else "?"
        status = (st.status or "?") if st else "?"
        icon = "✓" if status == "complete" else ("✗" if status == "failed" else "○")
        meta = st.result.output if (st and st.result and st.result.output) else {}
        path_tag = ""
        if skill == "browser" and isinstance(meta, dict):
            path_tag = f"  path={meta.get('path', '?')}  turns={meta.get('turns', '?')}"
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{nid} [{skill}] {icon}{path_tag}")
        kids = children.get(nid, [])
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, kid in enumerate(kids):
            _render(kid, child_prefix, i == len(kids) - 1)

    for i, r in enumerate(roots):
        _render(r, "", i == len(roots) - 1)

    return _section("[2] PLANNER DAG", lines or ["  (no nodes)"])


def section_browser_paths(states: list[NodeState]) -> list[str]:
    browser_nodes = [s for s in states if s.skill == "browser"]
    if not browser_nodes:
        return _section("[3] BROWSER PATH CHOSEN", ["  (no browser nodes in this session)"])

    lines: list[str] = [
        f"  {'Node':<8} {'Goal (truncated)':<38} {'Path':<14} {'Turns':<6} {'Status'}",
        f"  {'-'*7} {'-'*37} {'-'*13} {'-'*5} {'-'*8}",
    ]
    for st in browser_nodes:
        meta = (st.result.output or {}) if st.result else {}
        goal_raw = meta.get("goal") or (st.inputs[0] if st.inputs else "—")
        goal = goal_raw[:36] + ".." if len(goal_raw) > 36 else goal_raw
        path = meta.get("path", "—")
        turns = str(meta.get("turns", "—"))
        status = st.status or "—"
        lines.append(f"  {st.node_id:<8} {goal:<38} {path:<14} {turns:<6} {status}")

    return _section("[3] BROWSER PATH CHOSEN", lines)


def section_actions(states: list[NodeState]) -> list[str]:
    browser_nodes = [s for s in states if s.skill == "browser"]
    if not browser_nodes:
        return _section("[4] BROWSER ACTIONS TAKEN", ["  (no browser nodes)"])

    lines: list[str] = []
    for st in browser_nodes:
        meta = (st.result.output or {}) if st.result else {}
        goal = (meta.get("goal") or "—")[:60]
        lines.append(f"")
        lines.append(f"  {st.node_id}  goal: {goal}")
        lines.append(f"  url:  {meta.get('url', '—')}")
        lines.append(f"  final_url: {meta.get('final_url', '—')}")
        actions: list[dict] = meta.get("actions") or []
        if not actions:
            lines.append("    (no turn-level actions recorded — Layer 1 extract or static)")
        for turn_rec in actions:
            turn_num = turn_rec.get("turn", "?")
            outcome = turn_rec.get("outcome", "?")
            acts = turn_rec.get("actions") or []
            acts_str = ", ".join(
                f"{a.get('type', '?')}({a.get('mark', a.get('value', ''))})"
                for a in acts[:4]
            )
            lines.append(f"    turn {turn_num:>2}: {acts_str}  → {outcome}")

    return _section("[4] BROWSER ACTIONS TAKEN", lines)


def section_screenshots(states: list[NodeState], session_id: str) -> list[str]:
    browser_root = SESSIONS_ROOT / session_id / "browser"
    if not browser_root.exists():
        return _section("[5] SCREENSHOTS / PAGE-STATE LOGS", [
            "  No browser artifact directory found.",
            f"  Expected: {browser_root}",
        ])

    lines: list[str] = [f"  Artifacts root: {browser_root}", ""]
    total_files = 0
    for sub in sorted(browser_root.iterdir()):
        if not sub.is_dir():
            continue
        files = sorted(sub.rglob("*"))
        imgs = [f for f in files if f.suffix in (".png", ".jpg")]
        txts = [f for f in files if f.suffix == ".txt"]
        lines.append(f"  [{sub.name}]")
        lines.append(f"    screenshots : {len(imgs)}")
        lines.append(f"    legend files: {len(txts)}")
        lines.append(f"    total files : {len(files)}")
        for img in imgs[:6]:
            lines.append(f"      {img.relative_to(browser_root)}")
        if len(imgs) > 6:
            lines.append(f"      … {len(imgs)-6} more screenshots")
        total_files += len(files)
    lines.append("")
    lines.append(f"  Total artifacts: {total_files}")
    return _section("[5] SCREENSHOTS / PAGE-STATE LOGS", lines)


def section_extracted(states: list[NodeState]) -> list[str]:
    browser_nodes = [s for s in states if s.skill == "browser"]
    if not browser_nodes:
        return _section("[6] EXTRACTED DATA", ["  (no browser nodes)"])

    lines: list[str] = []
    for st in browser_nodes:
        meta = (st.result.output or {}) if st.result else {}
        content = meta.get("content") or ""
        url = meta.get("url", "—")
        lines.append("")
        lines.append(f"  {st.node_id}  url: {url}")
        if content:
            lines.append("  " + THIN)
            for ln in _truncate(content, 600).splitlines():
                lines.append(f"    {ln}")
            lines.append("  " + THIN)
        else:
            lines.append("    (content empty — check error or actions log above)")

    return _section("[6] EXTRACTED DATA (raw per browser node)", lines)


def section_comparison_table(states: list[NodeState]) -> list[str]:
    """Extract final answer from the formatter node."""
    formatter_nodes = [s for s in states if s.skill == "formatter"]
    lines: list[str] = []

    if not formatter_nodes:
        lines.append("  (no formatter node found in this session)")
        return _section("[7] FINAL COMPARISON TABLE", lines)

    last_fmt = formatter_nodes[-1]
    out = (last_fmt.result.output or {}) if last_fmt.result else {}

    # The formatter puts the user-facing answer in output.final_answer.
    answer = out.get("final_answer") or out.get("answer") or ""
    if not answer:
        # Fallback: dump the raw output
        answer = _json_preview(out, 1500)

    for ln in answer.splitlines():
        lines.append(f"  {ln}")

    return _section("[7] FINAL COMPARISON TABLE", lines)


def section_summary(states: list[NodeState], session_id: str,
                    elapsed_wall: float | None = None) -> list[str]:
    total_nodes = len(states)
    complete = sum(1 for s in states if s.status == "complete")
    failed = sum(1 for s in states if s.status == "failed")

    browser_nodes = [s for s in states if s.skill == "browser"]
    total_turns = sum(
        (s.result.output or {}).get("turns", 0)
        for s in browser_nodes
        if s.result and isinstance(s.result.output, dict)
    )
    paths = [
        (s.result.output or {}).get("path", "?")
        for s in browser_nodes
        if s.result and isinstance(s.result.output, dict)
    ]
    path_counts: dict[str, int] = {}
    for p in paths:
        path_counts[p] = path_counts.get(p, 0) + 1

    # Cost from elapsed_s across all nodes
    total_elapsed = sum(
        (s.result.elapsed_s or 0)
        for s in states
        if s.result
    )

    providers = list({
        s.result.provider
        for s in states
        if s.result and s.result.provider
    })

    lines = [
        f"  Session ID     : {session_id}",
        f"  Nodes total    : {total_nodes}  (complete={complete}, failed={failed})",
        f"  Browser nodes  : {len(browser_nodes)}",
        f"  Browser turns  : {total_turns}",
        f"  Cascade layers : {dict(path_counts) or '—'}",
        f"  Providers used : {', '.join(providers) or '—'}",
        f"  Total elapsed  : {total_elapsed:.1f}s",
    ]
    if elapsed_wall:
        lines.append(f"  Wall-clock     : {elapsed_wall:.1f}s")
    lines += [
        f"",
        f"  Cost note: The Browser skill uses the four-layer cascade.",
        f"  Layer 1 (extract) and Layer 2a (deterministic) cost $0.00 — no LLM.",
        f"  Layer 2b (a11y) costs ~$0.00 on Gemini Flash-Lite free tier.",
        f"  Layer 3 (vision) costs ~$0.001/turn on paid Gemini.",
        f"  Estimated session cost: ~$0.00 (free-tier Gemini providers).",
    ]
    return _section("[8] TURN COUNT AND COST SUMMARY", lines)


# ── main renderer ─────────────────────────────────────────────────────────────

def build_report(session_id: str) -> str:
    store = SessionStore(session_id)
    query = store.read_query() or "(query not found)"
    states = store.read_all_nodes()

    if not states:
        return f"No nodes persisted under state/sessions/{session_id}/nodes/"

    out: list[str] = [
        "",
        DIVIDER,
        "  SESSION 9 — BROWSER COMPARISON AGENT REPLAY REPORT",
        f"  Session : {session_id}",
        f"  Date    : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Nodes   : {len(states)}",
        DIVIDER,
    ]

    out += section_goal(query)
    out += section_dag(states)
    out += section_browser_paths(states)
    out += section_actions(states)
    out += section_screenshots(states, session_id)
    out += section_extracted(states)
    out += section_comparison_table(states)
    out += section_summary(states, session_id)

    out += ["", DIVIDER, "  END OF REPLAY REPORT", DIVIDER, ""]
    return "\n".join(out)


def replay_report(session_id: str, write_md: bool = False) -> int:
    report = build_report(session_id)
    print(report)

    if write_md:
        md_path = ROOT / "state" / "sessions" / session_id / f"replay_report.md"
        md_path.write_text(report, encoding="utf-8")
        print(f"\n[replay_report] Written to: {md_path}")

    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    write_md = "--md" in flags

    if args:
        return replay_report(args[0], write_md=write_md)

    sessions = list_sessions()
    if not sessions:
        print("replay_report: no sessions under state/sessions/", file=sys.stderr)
        return 2

    latest = sessions[-1]
    print(f"[replay_report] Using most recent session: {latest}", file=sys.stderr)
    return replay_report(latest, write_md=write_md)


if __name__ == "__main__":
    sys.exit(main())
