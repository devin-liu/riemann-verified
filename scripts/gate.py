#!/usr/bin/env python3
"""The gate: put a proof in the real file, build, and record what Lean says. Zero model calls.

  scripts/gate.py time <file>                      # elaboration time of the file as it is now
  scripts/gate.py apply <file> <decl> --from-run RUN            # a win found by firstpass.py
  scripts/gate.py apply <file> <decl> --proof-file F --route R  # any other proof (see firstpass.py for the format)
  scripts/gate.py axioms <file> <decl> [<decl> ...]
  scripts/gate.py baseline                         # statement hashes of the clean tree (full build)
  scripts/gate.py handin                           # full build, lint, statement comparison, privacy check

`apply` edits one declaration, builds that one module, and keeps the edit only if the build
passes. A failed build restores the file. It never changes a statement: only the text after the
declaration's final `:=` is replaced, and helpers go directly above it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rvlib as rv  # noqa: E402

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(r"\b(sorry|admit|sorryAx|native_decide|implemented_by|unsafe)\b|maxHeartbeats|^\s*axiom\b", re.M)


def first_error(out: str) -> str:
    msgs = [m for m in rv.parse_messages(out) if m["sev"] == "error"]
    if msgs:
        return f"line {msgs[0]['line']}: {rv.short(msgs[0]['text'], 400)}"
    lines = [l for l in out.splitlines() if "error" in l.lower()]
    return rv.short(" | ".join(lines[:3]) or out[-400:], 500)


def read_axioms(wt: pathlib.Path, rel: str, text: str, decls: list[str], timeout: int) -> dict[str, list[str] | None]:
    names = {}
    for d in decls:
        base = d.split(".")[-1]
        m = re.search(rf"^(?:(?:private|protected|nonrec)[ \t]+)*(?:theorem|lemma)[ \t]+((?:[\w.']+\.)?{re.escape(base)})\b",
                      text, re.M)
        if not m:
            rv.die(f"{d}: not found in {rel}")
        ns = rv.namespace_at(text, m.start())
        # keep the name as declared, e.g. `Printed.foo_false`, so `#print axioms` finds it
        names[d] = f"{ns}.{m.group(1)}" if ns else m.group(1)
    scratch = f"import {rv.module_name(rel)}\n" + "".join(f"#print axioms {n}\n" for n in names.values())
    srel = ".agent/rv/Axioms.lean"
    (wt / srel).parent.mkdir(parents=True, exist_ok=True)
    (wt / srel).write_text(scratch)
    rc, out, secs, timed_out = rv.lake_lean(wt, srel, timeout)
    res: dict[str, list[str] | None] = {d: None for d in decls}
    for m in rv.parse_messages(out, only=srel):
        for d, full in names.items():
            if f"'{full}'" in m["text"] or f"`{full}`" in m["text"]:
                if "does not depend on any axioms" in m["text"]:
                    res[d] = []
                else:
                    inner = re.search(r"\[(.*)\]", m["text"], re.S)
                    res[d] = [x.strip() for x in inner.group(1).split(",")] if inner else None
    return res


def cmd_time(a) -> None:
    wt = rv.worktree()
    with rv.build_lock(wt):
        rc, out, secs, timed_out = rv.lake_lean(wt, a.file, rv.cfg().get("build_timeout_sec", 3600))
    msgs = rv.parse_messages(out, only=a.file)
    errs = [m for m in msgs if m["sev"] == "error"]
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "time", "file": a.file, "sha": rv.git_sha(wt),
                                 "secs": round(secs, 1), "errors": len(errs), "timed_out": timed_out})
    print(f"{a.file}: {secs:.0f}s, {len(errs)} errors" + (" (TIMED OUT)" if timed_out else ""))
    if errs or timed_out or (rc != 0 and not msgs):
        print("  " + (f"line {errs[0]['line']}: {rv.short(errs[0]['text'], 400)}" if errs else rv.short(rv.other_output(out)[-500:], 500)))
        sys.exit(3)


def cmd_apply(a) -> None:
    wt = rv.worktree()
    src = wt / a.file
    text = src.read_text(encoding="utf-8")
    t = rv.find_target(text, a.decl)
    if not isinstance(t, rv.Target):
        rv.die(f"{a.decl}: {t}")
    if a.from_run:
        wins = json.loads((rv.STATE / "runs" / a.from_run / "wins.json").read_text())
        key = a.decl if a.decl in wins else a.decl.split(".")[-1]  # wins are keyed by the short name
        if key not in wins:
            rv.die(f"run {a.from_run} has no win for {a.decl}")
        proof, helpers, route, label = (wins[key][k] for k in ("proof", "helpers", "route", "label"))
    else:
        if not a.route:
            rv.die("--proof-file needs --route (lean-only, model:<name>, private or human)")
        body = pathlib.Path(a.proof_file).read_text(encoding="utf-8")
        helpers, sep, proof = body.partition("\n-- rv:proof\n")
        if not sep:
            helpers, proof = "", body
        route, label = a.route, pathlib.Path(a.proof_file).name
    proof, helpers = proof.strip(), helpers.strip()
    bad = FORBIDDEN.search(proof + "\n" + helpers)
    if bad:
        rv.die(f"the proof text contains `{bad.group(0).strip()}`; not applied")
    if re.search(r"\bexact\?|\bapply\?|\bsimp\?|\brw\?", proof):
        rv.die("the proof still contains a search tactic; use the term it suggested")
    if helpers and re.search(r"^(?!private (theorem|lemma)\b)\S", re.sub(r"/-.*?-/", "", helpers, flags=re.S), re.M):
        print("note: helpers contain something other than `private theorem`; upstream will route the PR to a reader")

    new = text[:t.start] + (helpers + "\n\n" if helpers else "") + text[t.start:t.tail_start] + ":= " + proof + text[t.end:]
    backup = rv.scratch_dir(wt) / f"backup-{time.strftime('%Y%m%d-%H%M%S')}-{pathlib.Path(a.file).name}"
    backup.write_text(text, encoding="utf-8")
    src.write_text(new, encoding="utf-8")
    module = rv.module_name(a.file)
    print(f"applied to {a.file}; building {module} …", flush=True)
    with rv.build_lock(wt):
        rc, out, secs, timed_out = rv.run(["lake", "build", module], wt, rv.cfg().get("build_timeout_sec", 3600))
        axioms = read_axioms(wt, a.file, new, [a.decl], rv.cfg().get("lean_timeout_sec", 600))[a.decl] if rc == 0 else None
    base = {"ts": rv.now(), "type": "apply", "decl": a.decl, "file": a.file, "sha": rv.git_sha(wt),
            "route": route, "label": label, "build_secs": round(secs, 1)}
    known = rv.load_targets().get(a.decl, {})
    if rc != 0 or axioms is None:
        src.write_text(text, encoding="utf-8")
        why = "timed out" if timed_out else (first_error(out) if rc != 0 else "built, but `#print axioms` gave no answer")
        rv.append("attempts.jsonl", {**base, "result": "miss", "detail": rv.short(why, 400)})
        print(f"REJECTED ({secs:.0f}s): {why}\nfile restored; the attempt is in ledger/attempts.jsonl")
        sys.exit(1)
    extra = sorted(set(axioms) - ALLOWED_AXIOMS - {"sorryAx"})
    if extra:
        src.write_text(text, encoding="utf-8")
        rv.append("attempts.jsonl", {**base, "result": "miss", "detail": f"forbidden axioms {extra}"})
        rv.die(f"REJECTED: depends on axioms {extra}; file restored")
    inherited = "sorryAx" in axioms
    rv.append("attempts.jsonl", {**base, "result": "win", "axioms": axioms, "inherited_sorry": inherited})
    rv.set_target(a.decl, state="proved-local", route=route.split(":")[0],
                  model=(route.split(":", 1)[1] if ":" in route else None), file=a.file,
                  issue=known.get("issue"), axioms=axioms, inherited_sorry=inherited, build_secs=round(secs, 1))
    times = [r["secs"] for r in rv.read_jsonl("attempts.jsonl") if r.get("type") == "time" and r.get("file") == a.file]
    print(f"ACCEPTED: {a.decl} builds in {module} ({secs:.0f}s"
          + (f"; file baseline {times[0]:.0f}s" if times else "; no baseline, run `gate.py time` on a clean file first") + ")")
    print(f"  axioms: {', '.join(axioms) or 'none'}"
          + ("\n  sorryAx is inherited from other unproved declarations: disclose it in the pull request" if inherited else ""))
    if times and secs > times[0] + 60:
        print("  WARNING: this proof adds more than a minute to the file. Find the slow step before handing in.")
    if known.get("issue"):
        print(f"next: claim #{known['issue']} now: scripts/rv preflight {a.file}, then scripts/rv draft claim {a.decl}"
              " (AGENTS.md, \"Outward actions\")")


def cmd_axioms(a) -> None:
    wt = rv.worktree()
    text = (wt / a.file).read_text(encoding="utf-8")
    with rv.build_lock(wt):
        res = read_axioms(wt, a.file, text, a.decl, rv.cfg().get("lean_timeout_sec", 600))
    for d, ax in res.items():
        print(f"{d}: " + ("no answer (does the module build?)" if ax is None else (", ".join(ax) or "none")))


def cmd_baseline(a) -> None:
    wt = rv.worktree()
    if subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=wt, capture_output=True, text=True).stdout.strip():
        rv.die("the worktree has uncommitted changes; a baseline is taken on a clean tree")
    out_path = rv.scratch_dir(wt) / f"sig-{rv.git_sha(wt)}.txt"
    print("full build and statement hashes (slow the first time) …", flush=True)
    with rv.build_lock(wt):
        rc, out, secs, _ = rv.run(["bash", "scripts/signatures.sh"], wt, rv.cfg().get("build_timeout_sec", 3600) * 2)
    if rc != 0:
        rv.die(f"scripts/signatures.sh failed after {secs:.0f}s: {rv.short(out[-600:], 600)}")
    out_path.write_text(out)
    (rv.scratch_dir(wt) / "baseline").write_text(out_path.name)
    print(f"baseline: {out_path} ({out.count(chr(10))} declarations, {secs:.0f}s)")


def cmd_handin(a) -> None:
    wt = rv.worktree()
    big = rv.cfg().get("build_timeout_sec", 3600) * 2
    ok = True
    steps = []

    def step(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        steps.append({"step": name, "ok": passed, "detail": rv.short(detail, 300)})
        print(f"  {'ok  ' if passed else 'FAIL'} {name}" + (f": {rv.short(detail, 300)}" if detail else ""), flush=True)

    with rv.build_lock(wt):
        rc, out, secs, to = rv.run(["lake", "build"], wt, big)
        step("lake build", rc == 0, f"{secs:.0f}s" if rc == 0 else first_error(out))
        rc, out, _, _ = rv.run(["bash", "scripts/lint.sh"], wt, 600)
        step("scripts/lint.sh", rc == 0, "" if rc == 0 else out[-300:])
        marker = rv.scratch_dir(wt) / "baseline"
        if not marker.exists():
            step("statements unchanged", False, "no baseline; run `scripts/gate.py baseline` on a clean tree at the branch point")
        else:
            rc, sig, _, _ = rv.run(["bash", "scripts/signatures.sh"], wt, big)
            after = rv.scratch_dir(wt) / "sig-after.txt"
            after.write_text(sig)
            rc2, cmp_out, _, _ = rv.run(["bash", "scripts/signatures.sh", "--compare",
                                         str(rv.scratch_dir(wt) / marker.read_text().strip()), str(after)], wt, 600)
            step("statements unchanged", rc == 0 and rc2 == 0, cmp_out)
    changed = subprocess.run(["git", "diff", "--name-only"], cwd=wt, capture_output=True, text=True).stdout.split()
    ours = {r.get("file") for r in rv.load_targets().values() if r.get("state") == "proved-local"}
    stray = [f for f in changed if f not in ours]
    step("only target files edited", not stray, ", ".join(stray))
    rc = subprocess.run(["bash", str(rv.ROOT / "scripts" / "leakcheck.sh"), "--outgoing"], cwd=rv.ROOT).returncode
    step("privacy check on outgoing text", rc == 0)
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "handin-check", "sha": rv.git_sha(wt), "ok": ok, "steps": steps})
    print("\nhand-in checks " + ("PASSED. Next: scripts/rv draft pr, read the diff, then open the PR in this turn (AGENTS.md, \"Outward actions\")."
                                 if ok else "FAILED. Fix and rerun; nothing is submitted."))
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("time"); p.add_argument("file"); p.set_defaults(fn=cmd_time)
    p = sub.add_parser("apply"); p.add_argument("file"); p.add_argument("decl")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--from-run"); g.add_argument("--proof-file")
    p.add_argument("--route"); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("axioms"); p.add_argument("file"); p.add_argument("decl", nargs="+"); p.set_defaults(fn=cmd_axioms)
    p = sub.add_parser("baseline"); p.set_defaults(fn=cmd_baseline)
    p = sub.add_parser("handin"); p.set_defaults(fn=cmd_handin)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
