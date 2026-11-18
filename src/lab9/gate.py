"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _is_nonfinite(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return not math.isfinite(float(val))
    if isinstance(val, str):
        return val.strip().lower() in {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "-infinity"}
    return False


def _slice_map(rows: list[dict[str, Any]]) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    seen: dict[str, tuple[str, ...]] = {}
    problems: list[str] = []
    for r in rows:
        iid = r.get("item_id")
        tags = tuple(sorted(str(t) for t in (r.get("slices") or [])))
        if iid in seen and seen[iid] != tags:
            problems.append(f"inconsistent slice tags across seeds for {iid}")
        seen[iid] = tags
    return seen, problems


def _check_ratchet(spec: dict[str, Any], base_spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems
    pmap = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in pmap:
            problems.append(f"ratchet: metric {mid} removed on same eval_set_version")
            continue
        pm = pmap[mid]
        if bm.get("blocking") and not pm.get("blocking"):
            problems.append(f"ratchet: blocking metric {mid} became non-blocking")
        bth = bm.get("threshold") or {}
        pth = pm.get("threshold") or {}
        if "max" in bth:
            if "max" not in pth or pth["max"] > bth["max"]:
                problems.append(f"ratchet: {mid} max loosened ({bth['max']} -> {pth.get('max')})")
        if "min" in bth:
            if "min" not in pth or pth["min"] < bth["min"]:
                problems.append(f"ratchet: {mid} min loosened ({bth['min']} -> {pth.get('min')})")
        if "max_increase" in bth:
            if "max_increase" not in pth or pth["max_increase"] > bth["max_increase"]:
                problems.append(
                    f"ratchet: {mid} max_increase loosened ({bth['max_increase']} -> {pth.get('max_increase')})"
                )
        if bth.get("no_significant_drop") and not pth.get("no_significant_drop"):
            problems.append(f"ratchet: {mid} dropped no_significant_drop")

    pslices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        key = (bs["name"], bs["metric"])
        if key not in pslices:
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} removed")
            continue
        ps = pslices[key]
        if bs.get("blocking") and not ps.get("blocking"):
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} became non-blocking")
        if "min" in bs:
            if "min" not in ps or ps["min"] < bs["min"]:
                problems.append(
                    f"ratchet: slice {bs['name']}/{bs['metric']} min loosened ({bs['min']} -> {ps.get('min')})"
                )
        if "max" in bs:
            if "max" not in ps or ps["max"] > bs["max"]:
                problems.append(
                    f"ratchet: slice {bs['name']}/{bs['metric']} max loosened ({bs['max']} -> {ps.get('max')})"
                )
        if bs.get("no_significant_drop") and not ps.get("no_significant_drop"):
            problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} dropped no_significant_drop")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    for label, rep in (("pr", pr), ("baseline", base)):
        for mid, val in (rep.get("metrics") or {}).items():
            if _is_nonfinite(val):
                problems.append(f"{label} metric {mid} is non-finite ({val!r})")

    pr_manifest = pr.get("manifest") or {}
    base_manifest = base.get("manifest") or {}
    if pr_manifest.get("eval_set_sha") != base_manifest.get("eval_set_sha"):
        problems.append("PR eval_set_sha differs from baseline")

    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []

    expected_len = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(pr_rows) != expected_len:
        problems.append(f"PR row count {len(pr_rows)} != manifest items*seeds ({expected_len})")

    pr_keys = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    if len(set(pr_keys)) != len(pr_keys):
        problems.append("PR contains duplicate (item_id, seed) rows")

    base_keys = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(set(base_keys)) != len(base_keys):
        problems.append("baseline contains duplicate (item_id, seed) rows")

    if set(pr_keys) != set(base_keys):
        problems.append("PR (item_id, seed) set differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append(f"PR has {len(pr['evaluator_failures'])} evaluator_failures")

    graded_metrics = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or any(m["id"] in r for r in pr_rows)
    ]
    pr_metrics = pr.get("metrics") or {}
    for mid in graded_metrics:
        bad_rows = [
            f"{r.get('item_id')}@{r.get('seed')}"
            for r in pr_rows
            if r.get(mid) is None or _is_nonfinite(r.get(mid))
        ]
        if bad_rows:
            problems.append(f"PR metric {mid} has missing/non-finite row values: {bad_rows[:3]}")
        elif pr_rows and mid in pr_metrics and isinstance(pr_metrics[mid], (int, float)):
            vals = [float(bool(r[mid])) if isinstance(r[mid], bool) else float(r[mid]) for r in pr_rows]
            expected_agg = sum(vals) if mid in ("secret_leak", "approval_bypass") else (sum(vals) / len(vals))
            if abs(float(pr_metrics[mid]) - expected_agg) > 1e-3:
                problems.append(
                    f"PR metric {mid}={pr_metrics[mid]} disagrees with rows aggregate ({expected_agg:.4f})"
                )

    pr_slices, pr_slice_probs = _slice_map(pr_rows)
    problems.extend(pr_slice_probs)
    base_slices, _ = _slice_map(base_rows)
    if pr_slices != base_slices:
        problems.append("PR slice tags differ from baseline")

    if base_spec is not None:
        problems.extend(_check_ratchet(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        val = sum(a.values()) / len(a) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                b = per_item(base, mid, slice_name=name)
                keys = sorted(set(a) & set(b))
                if not keys:
                    verdict = "missing"
                else:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                        confidence=bs.get("confidence", 0.95),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(f"slice:{name}/{mid}")
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        disp_val = f"{round(val, 4)!s:<8}" if val is not None else f"{'None':<8}"
        th_summary = {k: v for k, v in s.items() if k in ("min", "max", "no_significant_drop")}
        lines.append(f"  slice:{name}/{mid:<10} {disp_val} {json.dumps(th_summary):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
