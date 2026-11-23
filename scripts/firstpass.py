#!/usr/bin/env python3
"""Lean-only first pass: try cheap tactics (and, optionally, candidate proofs) on scratch copies.

Zero model calls. One `lake lean` run per tier covers every target of the file.

  scripts/firstpass.py RiemannMasullo/<Chapter>/<File>.lean --decl NAME [--decl NAME ...]
  scripts/firstpass.py <file> --all-sorry                 # every theorem whose proof is `sorry`
  scripts/firstpass.py <file> --decl NAME --candidates inbox/   # also check inbox/NAME.*.lean
  scripts/firstpass.py <file> --outline                   # declaration map of the file, no Lean run
  scripts/firstpass.py <file> --decl NAME --dry-run       # write the scratch file, do not run Lean

How the scratch file is built (this is what keeps a "win" honest):
  * it is the real file's text up to the last target, so imports, options, notations and
    section variables are exactly the original ones, and it does not import the real module;
  * each target theorem is removed and replaced by one `example` per tactic. An `example` is not
    added to the environment, and the original `sorry` theorem is gone, so `exact?` cannot close
    a goal with the target itself or with another attempt;
  * everything after the last target is dropped.
A win here is a lead, not a result: `scripts/gate.py apply` puts it in the real file and builds.

Candidate file format (`<dir>/<decl>.<label>.lean`): the text that goes after `:=`, normally
`by` and a tactic block. Optional `private theorem` helpers may come first, followed by a line
containing only `-- rv:proof`.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rvlib as rv  # noqa: E402

GOAL = "__goal__"


def load_tactics() -> dict[int, list[str]]:
    tiers: dict[int, list[str]] = {}
    for line in (rv.ROOT / "config" / "tactics.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tier, tac = line.split(None, 1)
        tiers.setdefault(int(tier), []).append(tac.strip())
    return tiers


def load_candidates(cdir: pathlib.Path, decl: str) -> list[tuple[str, str, str]]:
    """(label, helpers, proof) for each candidate file of one declaration."""
    out = []
    for p in sorted(cdir.glob(f"{decl}.*.lean")) + sorted(cdir.glob(f"{decl}.lean")):
        body = p.read_text(encoding="utf-8")
        if re.search(r"\b(sorry|admit|sorryAx)\b", body):
            print(f"  skip {p.name}: contains sorry/admit")
            continue
        helpers, sep, proof = body.partition("\n-- rv:proof\n")
        if not sep:
            helpers, proof = "", body
        out.append((p.name, helpers.strip(), proof.strip()))
    return out


def build_scratch(text: str, targets: list[rv.Target], attempts: dict[str, list[dict]]) -> tuple[str, list[dict]]:
    """Scratch text plus, for each attempt, the line range its messages will fall in."""
    out: list[str] = []
    ranges: list[dict] = []
    cur = 0

    def lines_so_far() -> int:
        return sum(s.count("\n") for s in out) + 1

    for t in sorted(targets, key=lambda t: t.start):
        out.append(text[cur:t.start])
        stmt = rv.statement_as_example(text, t)
        for k, a in enumerate(attempts[t.name]):
            first = lines_so_far()
            if a.get("helpers"):
                out.append(f"namespace RVc{k}_{re.sub(r'[^0-9A-Za-z_]', '_', t.name)}\n{a['helpers']}\n\n")
            out.append(f"{stmt}:= {a['proof']}\n")
            if a.get("helpers"):
                out.append(f"end RVc{k}_{re.sub(r'[^0-9A-Za-z_]', '_', t.name)}\n")
            ranges.append({"decl": t.name, "label": a["label"], "first": first, "last": lines_so_far() - 1,
                           "proof": a["proof"], "helpers": a.get("helpers", "")})
            out.append("\n")
        cur = t.end
    return "".join(out), ranges


def classify(ranges: list[dict], msgs: list[dict], timed_out: bool, first_line: int) -> list[dict]:
    prefix_errors = [m for m in msgs if m["sev"] == "error" and m["line"] < first_line]
    for r in ranges:
        mine = [m for m in msgs if r["first"] <= m["line"] <= r["last"]]
        errors = [m for m in mine if m["sev"] == "error"]
        has_sorry = any("sorry" in m["text"] and m["sev"] == "warning" for m in mine)
        r["suggestion"] = None
        for m in mine:
            if m["sev"] == "info" and m["text"].lstrip().startswith("Try this"):
                s = m["text"].split("Try this", 1)[1].lstrip(":").strip()
                r["suggestion"] = re.sub(r"^\[apply\]\s*", "", s)
                break
        if r["label"] == GOAL:
            traces = [m["text"] for m in mine if m["sev"] == "info"]
            r["result"], r["detail"] = "goal", (traces[0] if traces else "")
        elif prefix_errors:
            r["result"], r["detail"] = "invalid", "the file's own text before the target has errors"
        elif errors:
            r["result"], r["detail"] = "miss", rv.short(errors[0]["text"], 400)
        elif timed_out:
            r["result"], r["detail"] = "timeout", "wall-clock limit hit before Lean finished the file"
        elif has_sorry:
            r["result"], r["detail"] = "miss", "proof still uses sorry"
        else:
            r["result"], r["detail"] = "win", r["suggestion"] or ""
    return prefix_errors


def failures_md(run: str, rel: str, sha: str, text: str, targets, results, issues) -> str:
    """One bounded bundle of everything a model needs for a single pass over the misses."""
    wins = {r["decl"] for r in results if r["result"] == "win"}
    cap = rv.cfg().get("failure_bundle_chars", 14000)
    parts = [f"# Lean-only misses: {rel} @ {sha} (run {run})\n",
             "Each statement below is on upstream `main` exactly as shown; do not change it. "
             "Write one candidate per file as `inbox/<decl>.<label>.lean` (see `prompts/model-pass.md`).\n"]
    for t in sorted(targets, key=lambda t: t.start):
        if t.name in wins:
            continue
        parts.append(f"\n## {t.name}" + (f" (#{issues[t.name]})" if issues.get(t.name) else "")
                     + f", line {rv.line_of(text, t.head)}\n\n```lean\n{text[t.start:t.end]}\n```\n")
        goal = next((r["detail"] for r in results if r["decl"] == t.name and r["label"] == GOAL), "")
        if goal:
            parts.append("Goal:\n```\n" + (goal if len(goal) < 2500 else goal[:2500] + "\n… (cut)") + "\n```\n")
        for r in results:
            if r["decl"] == t.name and r["label"] != GOAL:
                parts.append(f"- `{r['label']}`: {r['result']}: {rv.short(r['detail'], 220)}\n")
    last = max(t.end for t in targets)
    parts.append("\n## Declarations above the last target (line, kind, name; * = proof is still `sorry`)\n\n")
    for line, kw, name, s in rv.outline(text[:last]):
        parts.append(f"- {line} {kw} {name}{' *' if s else ''}\n")
    md = "".join(parts)
    return md if len(md) <= cap else md[:cap] + f"\n\n… cut at {cap} characters (config: failure_bundle_chars)\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="path of the Lean file, relative to the upstream worktree")
    ap.add_argument("--decl", action="append", default=[])
    ap.add_argument("--all-sorry", action="store_true")
    ap.add_argument("--candidates", help="directory of candidate proofs; skips the tactic tiers")
    ap.add_argument("--route", default=None, help="who wrote the candidates: model:<name>, private, human")
    ap.add_argument("--tier", type=int, action="append", help="run only these tiers")
    ap.add_argument("--timeout", type=int, help="seconds per Lean run (default: config lean_timeout_sec)")
    ap.add_argument("--outline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    wt = rv.worktree()
    src = wt / a.file
    if not src.exists():
        rv.die(f"{src} does not exist. Run scripts/setup.sh first, or check the path.")
    text = src.read_text(encoding="utf-8")

    if a.outline:
        for line, kw, name, s in rv.outline(text):
            print(f"{line:5d} {kw:9s} {name}{'   <- sorry' if s else ''}")
        return

    names = rv.bare_sorries(text) if a.all_sorry else a.decl
    if not names:
        rv.die("name at least one --decl, or use --all-sorry")
    targets, skipped = [], []
    for n in names:
        t = rv.find_target(text, n)
        (targets if isinstance(t, rv.Target) else skipped).append(t if isinstance(t, rv.Target) else (n, t))
    for n, why in skipped:
        print(f"skip {n}: {why}")
    if not targets:
        rv.die("no target left to try")

    known = rv.load_targets()
    issues = {t.name: known.get(t.name, {}).get("issue") for t in targets}
    timeout = a.timeout or rv.cfg().get("lean_timeout_sec", 600)
    sha = rv.git_sha(wt)
    run = time.strftime("%Y%m%d-%H%M%S") + "-" + pathlib.Path(a.file).stem
    rundir = rv.STATE / "runs" / run
    rundir.mkdir(parents=True, exist_ok=True)

    if a.candidates:
        cdir = pathlib.Path(a.candidates)
        cdir = cdir if cdir.is_absolute() else rv.STATE / cdir
        route = a.route or rv.die("--candidates needs --route (model:<name>, private or human)")
        plan = {0: {t.name: [{"label": l, "helpers": h, "proof": p} for l, h, p in load_candidates(cdir, t.name)]
                    for t in targets}}
        plan[0] = {k: v for k, v in plan[0].items() if v}
        targets = [t for t in targets if t.name in plan[0]]
        if not targets:
            rv.die(f"no candidate files named <decl>.<label>.lean in {cdir}")
    else:
        route = "lean-only"
        tiers = load_tactics()
        plan = {}
        for tier in sorted(tiers):
            if a.tier and tier not in a.tier:
                continue
            extra = [{"label": GOAL, "proof": "by (trace_state; sorry)"}] if tier == min(tiers) else []
            plan[tier] = {t.name: extra + [{"label": tac, "proof": f"by {tac}"} for tac in tiers[tier]]
                          for t in targets}

    results: list[dict] = []
    won: set[str] = set()
    for tier, attempts in plan.items():
        todo = [t for t in targets if t.name not in won]
        if not todo:
            break
        scratch, ranges = build_scratch(text, todo, attempts)
        rel = f".agent/rv/{run}-t{tier}.lean"
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(scratch, encoding="utf-8")
        if a.dry_run:
            print(f"wrote {wt / rel} ({scratch.count(chr(10))} lines, {len(ranges)} attempts); not run")
            continue
        print(f"tier {tier}: {len(ranges)} attempts on {len(todo)} targets, limit {timeout}s …", flush=True)
        with rv.build_lock(wt):
            rc, out, secs, timed_out = rv.lake_lean(wt, rel, timeout)
        (rundir / f"t{tier}.out").write_text(out, encoding="utf-8")
        msgs = rv.parse_messages(out, only=rel)
        prefix_errors = classify(ranges, msgs, timed_out, ranges[0]["first"])
        rv.append("attempts.jsonl", {"ts": rv.now(), "type": "compile", "run": run, "file": a.file, "sha": sha,
                                     "tier": tier, "secs": round(secs, 1), "timed_out": timed_out,
                                     "attempts": len(ranges), "model_calls": 0})
        if prefix_errors or (rc != 0 and not msgs and not timed_out):
            print(f"\nENVIRONMENT PROBLEM, nothing was tested (exit {rc}, {secs:.0f}s).")
            for m in prefix_errors[:3]:
                print(f"  line {m['line']}: {rv.short(m['text'])}")
            if not msgs:
                print("  " + rv.short(rv.other_output(out), 600))
            print(f"  full output: {rundir / f't{tier}.out'}")
            print("  Fix the setup (scripts/setup.sh; is Mathlib from the cache?) before any proof work.")
            sys.exit(3)
        for r in ranges:
            r["tier"] = tier
            results.append(r)
            if r["label"] == GOAL:
                (rundir / f"goal-{r['decl']}.txt").write_text(r["detail"], encoding="utf-8")
                continue
            key = rv.ledger_key(r["decl"], a.file)
            rv.append("attempts.jsonl", {"ts": rv.now(), "type": "try", "run": run, "decl": key,
                                         "issue": issues.get(r["decl"], issues.get(key)), "file": a.file, "sha": sha,
                                         "route": route, "tier": tier, "label": r["label"],
                                         "result": r["result"], "detail": rv.short(r["detail"], 300)})
            if r["result"] == "win":
                won.add(r["decl"])
        print(f"  done in {secs:.0f}s" + (" (TIMED OUT)" if timed_out else ""))
    if a.dry_run:
        return

    wins = {}
    for r in results:
        if r["result"] == "win" and r["decl"] not in wins:
            proof = ("by\n  " + r["suggestion"].replace("\n", "\n  ")) if r["suggestion"] else r["proof"]
            wins[r["decl"]] = {"decl": r["decl"], "label": r["label"], "route": route,
                               "proof": proof, "helpers": r["helpers"]}
    (rundir / "wins.json").write_text(json.dumps(wins, indent=1, ensure_ascii=False), encoding="utf-8")
    misses = [t for t in targets if t.name not in wins]
    if misses:
        (rundir / "FAILURES.md").write_text(failures_md(run, a.file, sha, text, targets, results, issues),
                                            encoding="utf-8")

    print(f"\nrun {run}  ({route}, model calls: 0)")
    for t in sorted(targets, key=lambda t: t.start):
        tag = f"#{issues[t.name]} " if issues.get(t.name) else ""
        if t.name in wins:
            print(f"  WIN   {tag}{t.name}  via {wins[t.name]['label']}: {rv.short(wins[t.name]['proof'], 100)}")
        else:
            tried = [r for r in results if r["decl"] == t.name and r["label"] != GOAL]
            kinds = sorted({r["result"] for r in tried})
            print(f"  miss  {tag}{t.name}  ({len(tried)} tried: {', '.join(kinds)})")
    if wins:
        print(f"\nnext: scripts/gate.py apply {a.file} <decl> --from-run {run}   (one at a time; it builds the module)")
    if misses:
        print(f"misses bundled for one model pass: runs/{run}/FAILURES.md")


if __name__ == "__main__":
    main()
