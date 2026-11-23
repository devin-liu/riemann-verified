#!/usr/bin/env python3
"""State, turns and drafts for the riemann-verified workspace. Zero model calls.

  scripts/rv status                      # start here: who holds the turn, where every target stands, what is next
  scripts/rv turn start --agent NAME     # take the turn (fails if someone else holds it)
  scripts/rv turn end --did "…" --next "…" [--needs "…"]   # hand over; rewrites NEXT.md
  scripts/rv turn steal --agent NAME --why "…"             # only when the lock is stale
  scripts/rv preflight <file> [--add]    # read-only look at upstream: claims, open PRs, drift
  scripts/rv scout                       # read-only: which upstream files are uncrowded and have free statements
  scripts/rv add --issue N --decl NAME --file PATH [--group TAG]
  scripts/rv set DECL [DECL …] --state S [--pr N] [--note "…"]
  scripts/rv show DECL                   # one target and its recent attempts
  scripts/rv model-pass --model NAME --tier mid|strong --targets a,b --purpose "…" [--lemma L] [--usage-before "…"]
  scripts/rv usage "what the usage meter showed, before and after"
  scripts/rv draft claim|release|pr      # write outgoing text to outbox/ for the operator to send
  scripts/rv report                      # regenerate REPORT.md from the ledgers
  scripts/rv check                       # ledger consistency
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rvlib as rv  # noqa: E402

LOCK = rv.STATE / ".turn" / "lock.json"
ROUTE_NAMES = {"lean-only": "Lean-only search", "model": "after a model pass",
               "private": "undisclosed method", "human": "by hand"}


def hours_since(ts: str) -> float:
    return (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(ts)).total_seconds() / 3600


def gh(args: list[str]) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        rv.die(f"gh {' '.join(args[:4])} …: {r.stderr.strip()[:300]}")
    return r.stdout


# ---------------------------------------------------------------- turns

def lock_info() -> dict | None:
    return json.loads(LOCK.read_text()) if LOCK.exists() else None


def cmd_turn(a) -> None:
    stale_h = rv.cfg().get("turn_stale_hours", 4)
    cur = lock_info()
    if a.action == "start":
        LOCK.parent.mkdir(exist_ok=True)
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = hours_since(cur["since"])
            rv.die(f"the turn is held by {cur['agent']} since {cur['since']} ({age:.1f}h). "
                   + (f"It is stale (over {stale_h}h): `scripts/rv turn steal --agent {a.agent} --why …` if its work is not running."
                      if age > stale_h else "Do not work in this folder now; stop and tell the operator."), 75)
        with os.fdopen(fd, "w") as f:
            json.dump({"agent": a.agent, "since": rv.now()}, f)
        print(f"turn taken by {a.agent}.\n")
        cmd_status(a)
    elif a.action == "steal":
        if not cur:
            rv.die("nobody holds the turn; use `turn start`")
        if hours_since(cur["since"]) <= stale_h:
            rv.die(f"the lock is only {hours_since(cur['since']):.1f}h old (stale after {stale_h}h); ask the operator")
        rv.append("sessions.jsonl", {"start": cur["since"], "end": rv.now(), "agent": cur["agent"], "ended": "stolen",
                                     "did": f"(no handover; turn taken over by {a.agent}: {a.why})"})
        LOCK.write_text(json.dumps({"agent": a.agent, "since": rv.now()}))
        print(f"turn taken over by {a.agent}. Check the worktree for half-finished edits before anything else.")
    elif a.action == "end":
        if not cur:
            rv.die("nobody holds the turn")
        rows = [r for r in rv.read_jsonl("attempts.jsonl") if r.get("ts", "") >= cur["since"]]
        row = {"start": cur["since"], "end": rv.now(), "agent": cur["agent"], "ended": "handover",
               "did": a.did, "next": a.next, "needs": a.needs or "",
               "lean_runs": sum(r.get("type") in ("compile", "apply", "time") for r in rows),
               "model_passes": sum(r.get("type") == "model-pass" for r in rows)}
        rv.append("sessions.jsonl", row)
        (rv.STATE / "NEXT.md").write_text(
            "# Next\n\n"
            "Written by `scripts/rv turn end`. Do not edit by hand and do not append: the next handover replaces it.\n\n"
            f"Updated {row['end']} by {row['agent']} "
            f"({row['lean_runs']} Lean runs, {row['model_passes']} model passes this turn).\n\n"
            f"## Done last turn\n\n{a.did.strip()}\n\n"
            f"## Next action\n\n{a.next.strip()}\n\n"
            f"## Waiting on the operator\n\n{(a.needs or 'Nothing.').strip()}\n", encoding="utf-8")
        LOCK.unlink()
        print("turn released; NEXT.md rewritten.")


# ---------------------------------------------------------------- status

def cmd_status(a) -> None:
    c = rv.cfg()
    cur = lock_info()
    print("TURN      " + (f"held by {cur['agent']} since {cur['since']} ({hours_since(cur['since']):.1f}h)" if cur else "free"))
    wt = rv.worktree()
    if (wt / "lakefile.toml").exists():
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=wt,
                               capture_output=True, text=True).stdout.split("\n")
        dirty = [d for d in dirty if d.strip()]
        print(f"WORKTREE  {wt.relative_to(rv.ROOT) if wt.is_relative_to(rv.ROOT) else wt} @ {rv.git_sha(wt)}"
              + (f", {len(dirty)} edited: " + ", ".join(d.split()[-1] for d in dirty[:3]) if dirty else ", clean"))
    else:
        print("WORKTREE  not set up: run scripts/setup.sh (needs the operator's go-ahead: it downloads several GB)")
    t = rv.load_targets()
    by: dict[str, int] = {}
    for r in t.values():
        by[r["state"]] = by.get(r["state"], 0) + 1
    print(f"TARGETS   {len(t)}: " + (", ".join(f"{k} {v}" for k, v in sorted(by.items())) or "none yet"))
    att = rv.read_jsonl("attempts.jsonl")
    for d, r in sorted(t.items(), key=lambda kv: (kv[1].get("file", ""), kv[1].get("issue") or 0)):
        tries = [x for x in att if rv.same_decl(x.get("decl"), d) and x.get("type") == "try"]
        warn = ""
        if r["state"] in ("claimed", "proved-local", "stuck") and r.get("claimed_at"):
            h = hours_since(r["claimed_at"])
            if h > c.get("claim_expires_hours", 8) - 2:
                warn = f"  !! claim is {h:.1f}h old; upstream releases it at {c.get('claim_expires_hours', 8)}h"
        print(f"  #{r.get('issue') or '—':<5} {d:<40.40} {r['state']:<12} "
              f"{(r.get('route') or ''):<9} tries {len(tries):<3}"
              + (f" PR #{r['pr']}" if r.get("pr") else "") + (f" [{r['group']}]" if r.get("group") else "") + warn)
    passes = [x for x in att if x.get("type") == "model-pass"]
    compiles = [x for x in att if x.get("type") == "compile"]
    print(f"SPEND     Lean runs {len(compiles)} ({sum(x.get('secs', 0) for x in compiles) / 60:.0f} min), "
          f"model passes {len(passes)}"
          + (" (" + ", ".join(f"{x['tier']}:{x['model']}" for x in passes[-4:]) + ")" if passes else ""))
    nxt = rv.STATE / "NEXT.md"
    if nxt.exists():
        body = nxt.read_text(encoding="utf-8").split("## Done last turn", 1)[-1]
        print("NEXT.md   ## Done last turn" + body.rstrip())


def cmd_show(a) -> None:
    t = rv.load_targets().get(a.decl) or rv.die(f"{a.decl} is not a target")
    print(json.dumps(t, indent=1, ensure_ascii=False))
    for r in [x for x in rv.read_jsonl("attempts.jsonl") if x.get("decl") == a.decl][-a.n:]:
        print(f"  {r['ts'][5:16]} {r.get('type'):<7} {r.get('route', ''):<12} {r.get('label', '') or r.get('to', ''):<22.22} "
              f"{r.get('result', ''):<7} {rv.short(str(r.get('detail') or r.get('note') or ''), 110)}")


# ---------------------------------------------------------------- targets

def cmd_add(a) -> None:
    row = rv.set_target(a.decl, issue=a.issue, file=a.file, group=a.group, state="open")
    print(f"target {a.decl} (#{row.get('issue')}) in {row.get('file')}: {row['state']}")


def cmd_set(a) -> None:
    for d in a.decl:
        if d not in rv.load_targets():
            rv.die(f"{d} is not a target; `scripts/rv add` it first")
        if not a.state and not a.claimed:
            rv.die("give --state, or --claimed to record a `Claiming` comment seen upstream")
        extra = {"claimed_at": rv.now()} if a.state == "claimed" or a.claimed else {}
        row = rv.set_target(d, state=a.state, pr=a.pr, note=a.note, **extra)
        print(f"{d}: {row['state']}" + (f" (PR #{row['pr']})" if row.get("pr") else "")
              + (f", claimed {row['claimed_at']}" if a.claimed else ""))


def cmd_model_pass(a) -> None:
    b = rv.cfg()["budget"]
    targets = [x for x in a.targets.split(",") if x]
    files = {rv.load_targets().get(x, {}).get("file") for x in targets}
    prior = [r for r in rv.read_jsonl("attempts.jsonl") if r.get("type") == "model-pass" and set(r.get("files", [])) & files]
    problems = []
    if a.tier == "strong" and (not a.lemma or len(targets) < 2):
        problems.append(f"a strong-model pass needs {b['strong_model_requires']} (--lemma, and two or more --targets)")
    if a.tier == "mid" and len([r for r in prior if r["tier"] == "mid"]) >= b["model_passes_per_batch"]:
        problems.append(f"this file already had {b['model_passes_per_batch']} mid-tier pass(es); the budget is one per batch")
    if problems and not a.operator_ok:
        rv.die("; ".join(problems) + ". Ask the operator, then repeat with --operator-ok.")
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "model-pass", "model": a.model, "tier": a.tier,
                                 "targets": targets, "files": sorted(f for f in files if f), "purpose": a.purpose,
                                 "lemma": a.lemma, "usage_before": a.usage_before or "unmeasured",
                                 "operator_ok": bool(a.operator_ok)})
    print(f"recorded: {a.tier} pass with {a.model} on {len(targets)} targets"
          + ("" if a.usage_before else "; usage before the pass: unmeasured"))


def cmd_usage(a) -> None:
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "usage", "note": a.note})
    print("usage note recorded")


# ---------------------------------------------------------------- upstream, read-only

# Upstream's own rule (scripts/ci/stale_claims.py, .github/workflows/claims.yml): a comment whose
# first line starts with "Claiming"/"Claimed" claims the issue; "Releasing"/"Released" undoes it.
# The `claimed` label is set by a workflow that can sit in a queue for a long time, so the
# comments, not the label, decide.
CLAIM_RE = re.compile(r"\s*claim(ing|ed)?([^a-z]|$)", re.I)
RELEASE_RE = re.compile(r"\s*releas(ing|ed?)?([^a-z]|$)", re.I)


# The pool is upstream's own "unclaimed" query (CONTRIBUTING.md, step 1): open, `proof`, and none
# of these labels. `refutation` issues (prove that a printed statement is false) are in the pool.
BLOCKING_LABELS = {"claimed", "stuck", "gap"}


def issue_holder(up: str, number: int, comments: list[dict]) -> tuple[str, str] | None:
    """Who holds an issue right now, for one whose `claimed` label is absent.

    The label lags (its workflow can sit in a queue), so a recent `Claiming` comment still
    counts. But the owner or the bot also releases a claim by removing the label without a
    comment, and upstream lets a claim lapse after eight hours, so the timeline decides:
    the first claim not undone by a release comment, an `unlabeled claimed` event or age."""
    if not any(CLAIM_RE.match((c.get("body") or "").split("\n", 1)[0]) for c in comments or []):
        return None
    jq = ('.[] | {event, t: .created_at, label: (.label.name // ""), body: (.body // ""), '
          'who: (.user.login // .actor.login // "?"), assoc: (.author_association // "")}')
    lines = gh(["api", f"repos/{up}/issues/{number}/timeline", "--paginate", "--jq", jq]).splitlines()
    holder = None
    for e in sorted((json.loads(x) for x in lines if x.strip()), key=lambda e: e["t"] or ""):
        if e["event"] == "unlabeled" and e["label"] == "claimed":
            holder = None
        elif e["event"] == "commented":
            first = e["body"].split("\n", 1)[0]
            if CLAIM_RE.match(first):
                holder = holder or (e["who"], e["t"])
            elif holder and e["who"].startswith("github-actions") and "released automatically" in first:
                holder = None
            elif RELEASE_RE.match(first) and holder and (
                    e["who"] == holder[0] or e["who"].startswith("github-actions")
                    or e["assoc"] in ("OWNER", "MEMBER", "COLLABORATOR")):
                holder = None
    if holder and hours_since(holder[1]) > rv.cfg().get("claim_expires_hours", 8):
        return None  # lapsed; upstream's hourly job will release it
    return holder


def comment_claim(comments: list[dict]) -> tuple[str, str] | None:
    """(login, time) of whoever holds the issue by its comments: the first claim not released
    since by its author, by a bot or by a later release comment from a member; None if free."""
    holder = None
    for c in sorted(comments or [], key=lambda c: c.get("createdAt", "")):
        first = (c.get("body") or "").split("\n", 1)[0]
        who = (c.get("author") or {}).get("login", "?")
        if CLAIM_RE.match(first):
            holder = holder or (who, c.get("createdAt", ""))
        elif holder and who in ("github-actions", "github-actions[bot]") and "released automatically" in first:
            holder = None  # upstream's hourly stale-claim release (scripts/ci/stale_claims.py)
        elif RELEASE_RE.match(first) and holder and (
                who == holder[0] or who.endswith("[bot]") or who == "github-actions"
                or c.get("authorAssociation") in ("OWNER", "MEMBER", "COLLABORATOR")):
            holder = None
    return holder

def open_prs(owner: str, name: str) -> list[dict]:
    prs, cursor = [], None
    while True:
        q = ('query($o:String!,$n:String!,$c:String){repository(owner:$o,name:$n){pullRequests(states:OPEN,first:50,after:$c)'
             '{pageInfo{hasNextPage endCursor} nodes{number title isDraft author{login} files(first:100){nodes{path}}'
             ' closingIssuesReferences(first:50){nodes{number}}}}}}')
        args = ["api", "graphql", "-f", f"query={q}", "-f", f"o={owner}", "-f", f"n={name}"]
        page = json.loads(gh(args + (["-f", f"c={cursor}"] if cursor else [])))["data"]["repository"]["pullRequests"]
        prs += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return prs
        cursor = page["pageInfo"]["endCursor"]


def cmd_scout(a) -> None:
    """Rank upstream files by free proof issues and by how many other people are in them."""
    up = rv.cfg()["upstream"]
    owner, name = up.split("/")
    me = gh(["api", "user", "--jq", ".login"]).strip()
    issues = json.loads(gh(["issue", "list", "-R", up, "--state", "open", "--label", "proof", "--limit", "2000",
                            "--json", "number,labels,assignees,body,comments"]))
    prs = open_prs(owner, name)
    in_pr = {n["number"]: (p["author"] or {}).get("login", "?") for p in prs
             for n in p["closingIssuesReferences"]["nodes"]}
    files: dict[str, dict] = {}
    for i in issues:
        m = re.search(r"<!-- sorry: (.+?)::(.+?) -->", i["body"])
        if not m:
            continue
        f = files.setdefault(m.group(1), {"free": 0, "held": 0, "people": set(), "prs": 0, "ids": []})
        labels = {l["name"] for l in i["labels"]}
        who = {x["login"] for x in i["assignees"]} - {me}
        if not labels & BLOCKING_LABELS:
            held = issue_holder(up, i["number"], i.get("comments"))
            if held and held[0] != me:
                labels.add("claimed")
                who = {held[0]}
            elif i["number"] in in_pr and in_pr[i["number"]] != me:
                labels.add("claimed")
                who = {in_pr[i["number"]]}
        if labels & BLOCKING_LABELS:
            f["held"] += 1
            f["people"] |= who if "claimed" in labels else set()
        else:
            f["free"] += 1
            f["ids"].append(f"#{i['number']}" + (" (refutation)" if "refutation" in labels else ""))
    for p in prs:
        for path in {x["path"] for x in p["files"]["nodes"]}:
            if path in files and (p["author"] or {}).get("login") != me:
                files[path]["prs"] += 1
                files[path]["people"].add((p["author"] or {}).get("login", "?"))
    rows = [(f, d) for f, d in files.items() if d["free"] >= a.min_free]
    rows.sort(key=lambda kv: (len(kv[1]["people"]), kv[1]["free"] + kv[1]["held"], -kv[1]["free"]))
    print(f"{len(issues)} open proof issues in {len(files)} files; {len(rows)} files with at least {a.min_free} free.")
    print("Fewest other people first, then fewest statements left (a nearly finished file stops being rebuilt).")
    print(f"{'others':>6} {'left':>4} {'free':>4} {'PRs':>3}  file")
    for f, d in rows[:a.n]:
        print(f"{len(d['people']):>6} {d['free'] + d['held']:>4} {d['free']:>4} {d['prs']:>3}  {f}  "
              + " ".join(sorted(d["ids"])))
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "scout", "open_proof_issues": len(issues), "files": len(files),
                                 "top": [f for f, _ in rows[:5]]})


def cmd_preflight(a) -> None:
    c = rv.cfg()
    up, branch = c["upstream"], c.get("upstream_branch", "main")
    owner, name = up.split("/")
    me = gh(["api", "user", "--jq", ".login"]).strip()
    base = pathlib.Path(a.file).name
    issues = json.loads(gh(["issue", "list", "-R", up, "--state", "open", "--label", "proof", "--limit", "300",
                            "--search", f"{base} in:body", "--json", "number,title,labels,assignees,body,comments"]))
    issues = [i for i in issues if f"<!-- sorry: {a.file}::" in i["body"]]
    all_prs = open_prs(owner, name)
    in_pr = {n["number"]: (p["author"] or {}).get("login", "?") for p in all_prs
             for n in p["closingIssuesReferences"]["nodes"]}
    prs = [p for p in all_prs if any(f["path"] == a.file for f in p["files"]["nodes"])]

    known = rv.load_targets()
    print(f"UPSTREAM  {up}: {len(issues)} open proof issues for {a.file}, {len(prs)} open PRs touching it")
    free = others = 0
    people: set[str] = set()
    for i in sorted(issues, key=lambda i: i["number"]):
        decl = re.search(r"<!-- sorry: .*?::(.+?) -->", i["body"]).group(1)
        labels = {l["name"] for l in i["labels"]}
        who = ",".join(x["login"] for x in i["assignees"])
        held = None if labels & BLOCKING_LABELS else issue_holder(up, i["number"], i.get("comments"))
        if held:
            labels.add("claimed")
            who = held[0]
        elif not labels & BLOCKING_LABELS and i["number"] in in_pr:
            labels.add("claimed")
            who = f"{in_pr[i['number']]} (PR)"
        flags = sorted(labels & BLOCKING_LABELS)
        mine = held[0] == me if held else me in who.split(",")
        if flags and not mine:
            others += "claimed" in flags
            people |= {x for x in who.split(",") if x and "claimed" in flags}
        elif not flags:
            free += 1
        tag = ("ours" if decl in known else "") + (f" since {held[1]}" if held else "")
        print(f"  #{i['number']:<5} {decl:<44.44} {','.join(flags) or 'free':<14} {who:<16} {tag}")
        if decl in known:
            row = known[decl]
            if "claimed" in flags and not mine and row["state"] == "open":
                rv.set_target(decl, state="taken", note=f"claimed upstream by {who or 'someone else'}")
        elif a.add and not flags:
            rv.set_target(decl, issue=i["number"], file=a.file, state="open")
    for p in prs:
        print(f"  PR #{p['number']} by {(p['author'] or {}).get('login', '?')}{' (draft)' if p['isDraft'] else ''}: {rv.short(p['title'], 80)}")
    gone = [d for d, r in known.items() if r.get("file") == a.file and r["state"] in ("open", "claimed")
            and r.get("issue") and r["issue"] not in {i["number"] for i in issues}]
    for d in gone:
        print(f"  !! #{known[d]['issue']} {d}: no longer an open proof issue upstream (proved or closed by someone else?)")

    wt = rv.worktree()
    if (wt / a.file).exists():
        subprocess.run(["git", "fetch", "--quiet", "origin", branch], cwd=wt, stdin=subprocess.DEVNULL)
        behind = subprocess.run(["git", "rev-list", "--count", f"HEAD..origin/{branch}"], cwd=wt, capture_output=True, text=True).stdout.strip()
        moved = subprocess.run(["git", "diff", "--quiet", "HEAD", f"origin/{branch}", "--", a.file], cwd=wt).returncode != 0
        print(f"LOCAL     worktree is {behind or '?'} commits behind origin/{branch}; "
              f"{a.file} {'DIFFERS from upstream: update before working (statements or helpers may have changed)' if moved else 'is the same as upstream'}")
        text = (wt / a.file).read_text(encoding="utf-8")
        for d, r in known.items():
            if r.get("file") == a.file and r["state"] in ("open", "claimed") and not isinstance(rv.find_target(text, d), rv.Target):
                print(f"  !! {d}: the issue says open, but in the local file {rv.find_target(text, d)}")
    people |= {(p["author"] or {}).get("login", "?") for p in prs} - {me}
    verdict = ("crowded: upstream's advice is to choose another file when two or three others are in it" if len(people) >= 2
               else "one other person is active here: recheck right before claiming, and keep the PR small" if people
               else "uncrowded")
    print(f"VERDICT   {free} free, {others} claimed by {len(people)} other people"
          f"{' (' + ', '.join(sorted(people)) + ')' if people else ''}, {len(prs)} open PRs -> {verdict}")
    rv.append("attempts.jsonl", {"ts": rv.now(), "type": "preflight", "file": a.file, "free": free,
                                 "claimed_by_others": others, "other_people": len(people),
                                 "open_prs": [p["number"] for p in prs], "verdict": verdict})


# ---------------------------------------------------------------- outgoing drafts

def cmd_draft(a) -> None:
    up = rv.cfg()["upstream"]
    out = rv.STATE / "outbox"
    out.mkdir(exist_ok=True)
    t = rv.load_targets()
    if a.kind == "claim":
        # Claims are made when `gate.py apply` accepts a target (AGENTS.md, "Outward actions"):
        # the row stays `proved-local` and gets a `claimed_at`. `open` rows can still be claimed by hand.
        # `stuck` rows are claimed only when named, right before they go to a private attempt
        # (AGENTS.md, "Standing: claim before a private attempt"); they stay `stuck` with a `claimed_at`.
        rows = [r for r in t.values() if r.get("issue") and (not a.decl or r["decl"] in a.decl)
                and not r.get("claimed_at")
                and (r["state"] in ("open", "proved-local") or (r["state"] == "stuck" and a.decl))]
        if not rows:
            rv.die("no unclaimed target in state `proved-local` or `open` (or a named `stuck` one) with an issue number")
        lines = [f'gh issue comment {r["issue"]} -R {up} --body "Claiming"   # {r["decl"]}' for r in rows]
        (out / "claim.sh").write_text("\n".join(lines) + "\n")
        won = [r["decl"] for r in rows if r["state"] in ("proved-local", "stuck")]
        rest = [r["decl"] for r in rows if r["state"] == "open"]
        after = " ; ".join(([f"scripts/rv set {' '.join(won)} --claimed"] if won else [])
                           + ([f"scripts/rv set {' '.join(rest)} --state claimed"] if rest else []))
    elif a.kind == "release":
        rows = [r for r in t.values() if r["state"] in ("claimed", "stuck") and r.get("issue")]
        if not rows:
            rv.die("nothing claimed or stuck to release")
        lines = []
        for r in rows:
            note = r.get("note") or rv.die(f"{r['decl']}: write what was tried first: scripts/rv set {r['decl']} --state stuck --note \"…\"")
            body = out / f"release-{r['issue']}.md"
            body.write_text(f"Releasing.\n\n{note}\n", encoding="utf-8")
            lines.append(f"gh issue comment {r['issue']} -R {up} --body-file outbox/{body.name}   # {r['decl']}")
        (out / "release.sh").write_text("\n".join(lines) + "\n")
        after = f"scripts/rv set {' '.join(r['decl'] for r in rows)} --state released"
    else:
        rows = [r for r in t.values() if r["state"] == "proved-local"]
        if not rows:
            rv.die("no target in state `proved-local`")
        wt = rv.worktree()
        sha = rv.git_sha(wt)
        checks = [r for r in rv.read_jsonl("attempts.jsonl") if r.get("type") == "handin-check"]
        checked = bool(checks) and checks[-1]["ok"] and checks[-1]["sha"] == sha
        files = sorted({pathlib.Path(r["file"]).stem for r in rows})
        body = [f"Prove {len(rows)} declaration{'s' if len(rows) != 1 else ''} in {', '.join(files)}", ""]
        body += [f"Closes #{r['issue']}" for r in sorted(rows, key=lambda r: r.get("issue") or 0) if r.get("issue")]
        body += ["", "Proofs only: no statement is changed."
                 + (" Locally, `lake build` and `scripts/lint.sh` pass and `scripts/signatures.sh --compare` lists nothing." if checked else ""),
                 "", "`#print axioms`:"]
        for r in sorted(rows, key=lambda r: r.get("issue") or 0):
            body.append(f"- `{r['decl']}`: {', '.join(r.get('axioms') or []) or 'none'}"
                        + (" (`sorryAx` is inherited from declarations that are still unproved)" if r.get("inherited_sorry") else ""))
        (out / "PR.md").write_text("\n".join(body) + "\n", encoding="utf-8")
        # Relative paths only: outbox/ is scanned by `leakcheck.sh --outgoing`, which rejects home paths.
        lines = [f"# in {os.path.relpath(wt, out.parent)}: review `git diff` first",
                 f'gh pr create -R {up} --base main --title "{body[0]}" --body-file <(tail -n +3 {os.path.relpath(out / "PR.md", wt)})']
        (out / "pr.sh").write_text("\n".join(lines) + "\n")
        after = f"scripts/rv set {' '.join(r['decl'] for r in rows)} --state pr-open --pr <number>"
        if not checked:
            print("WARNING: no passing `scripts/gate.py handin` for this commit; the PR text makes no claim about checks. Run it first.")
        unclaimed = [r["decl"] for r in rows if not r.get("claimed_at")]
        if unclaimed:
            print(f"WARNING: not claimed upstream yet: {', '.join(unclaimed)}. Claim at gate accept (AGENTS.md, \"Outward actions\").")
    print(f"drafted in outbox/ ({a.kind}): {len(rows)} item(s). Nothing was sent.")
    if a.kind in ("claim", "pr"):
        print("For targets `gate.py apply` accepted this turn, this is covered by the standing go-ahead;"
              " anything else needs the operator's go-ahead (AGENTS.md, \"Outward actions\").")
    else:
        print("Outgoing actions need the operator's go-ahead in this session (AGENTS.md, \"Outward actions\").")
    print(f"After it is sent: {after}")


# ---------------------------------------------------------------- report and check

def cmd_report(a) -> None:
    t = rv.load_targets()
    att = rv.read_jsonl("attempts.jsonl")
    done = [r for r in t.values() if r["state"] in ("proved-local", "pr-open", "merged")]
    lines = ["# Progress report", "",
             f"Generated {rv.now()} by `scripts/rv report` from `ledger/`. Do not edit by hand.", "",
             f"Upstream: [{rv.cfg()['upstream']}](https://github.com/{rv.cfg()['upstream']}). "
             "Every proof counted here was accepted by Lean in a build of the real module; none is counted on a model's say-so.", "",
             "## Where the targets stand", "", "| State | Count |", "|---|---|"]
    for s in rv.STATES:
        n = sum(r["state"] == s for r in t.values())
        if n:
            lines.append(f"| {s} | {n} |")
    lines += [f"| **all targets taken on** | **{len(t)}** |", "",
              "Targets that were tried and not proved stay in the total.", "",
              "## How the proved ones were found", "", "| Route | Proved | Merged upstream |", "|---|---|---|"]
    for route, label in ROUTE_NAMES.items():
        mine = [r for r in done if r.get("route") == route]
        if mine:
            lines.append(f"| {label} | {len(mine)} | {sum(r['state'] == 'merged' for r in mine)} |")
    compiles = [x for x in att if x.get("type") == "compile"]
    passes = [x for x in att if x.get("type") == "model-pass"]
    usage = [f"usage before {x.get('usage_before', 'unmeasured')}" for x in passes]
    notes = [x for x in att if x.get("type") == "usage"]
    lines += ["", "## Cost", "",
              f"- Lean runs with no model call: {len(compiles)}, {sum(x.get('secs', 0) for x in compiles) / 60:.0f} minutes, "
              f"{sum(x.get('attempts', 0) for x in compiles)} proof attempts.",
              f"- Model passes: {len(passes)}"
              + (" (" + "; ".join(f"{x['tier']} {x['model']}: {u}" for x, u in zip(passes, usage)) + ")" if passes else "") + ".",
              *[f"- Usage read off the meter, {x['ts'][:16]}: {x['note']}" for x in notes],
              "- A usage figure of `unmeasured` means nobody read the meter; it is not zero.", "",
              "## Targets", "", "| Issue | Declaration | State | Route | PR | Axioms |", "|---|---|---|---|---|---|"]
    for d, r in sorted(t.items(), key=lambda kv: kv[1].get("issue") or 0):
        ax = ", ".join(r.get("axioms") or []) if r.get("axioms") is not None else ""
        lines.append(f"| {('#' + str(r['issue'])) if r.get('issue') else ''} | `{d}` | {r['state']} | "
                     f"{ROUTE_NAMES.get(r.get('route'), '')} | {('#' + str(r['pr'])) if r.get('pr') else ''} | {ax} |")
    (rv.STATE / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"REPORT.md written: {len(t)} targets, {len(done)} proved, {len(passes)} model passes")


def cmd_check(a) -> None:
    problems = []
    t = rv.load_targets()
    att = rv.read_jsonl("attempts.jsonl")
    rv.read_jsonl("sessions.jsonl")
    for d, r in t.items():
        if r["state"] not in rv.STATES:
            problems.append(f"{d}: unknown state {r['state']}")
        if r["state"] in ("pr-open", "merged") and not r.get("pr"):
            problems.append(f"{d}: state {r['state']} without a PR number")
        if r["state"] in ("proved-local", "pr-open", "merged"):
            if r.get("route") not in rv.ROUTES:
                problems.append(f"{d}: proved without a route")
            if not any(x.get("type") == "apply" and rv.same_decl(x.get("decl"), d) and x.get("result") == "win" for x in att):
                problems.append(f"{d}: marked proved, but the ledger has no accepted `gate.py apply` for it")
        if r["state"] in ("stuck", "finding") and not r.get("note"):
            problems.append(f"{d}: {r['state']} without a note for the next person")
    cur = lock_info()
    if cur and hours_since(cur["since"]) > rv.cfg().get("turn_stale_hours", 4):
        problems.append(f"turn lock held by {cur['agent']} is stale")
    for p in problems:
        print("  " + p)
    print(f"check: {len(t)} targets, {len(att)} ledger rows, {len(problems)} problems")
    sys.exit(1 if problems else 0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    p = sub.add_parser("turn"); p.add_argument("action", choices=["start", "end", "steal"])
    p.add_argument("--agent"); p.add_argument("--did"); p.add_argument("--next"); p.add_argument("--needs"); p.add_argument("--why")
    p.set_defaults(fn=cmd_turn)
    p = sub.add_parser("preflight"); p.add_argument("file"); p.add_argument("--add", action="store_true"); p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("scout"); p.add_argument("--min-free", type=int, default=2); p.add_argument("-n", type=int, default=15)
    p.set_defaults(fn=cmd_scout)
    p = sub.add_parser("add"); p.add_argument("--issue", type=int); p.add_argument("--decl", required=True)
    p.add_argument("--file", required=True); p.add_argument("--group"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("set"); p.add_argument("decl", nargs="+"); p.add_argument("--state", choices=rv.STATES)
    p.add_argument("--claimed", action="store_true", help="record a `Claiming` comment seen upstream; keeps the state")
    p.add_argument("--pr", type=int); p.add_argument("--note"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("show"); p.add_argument("decl"); p.add_argument("-n", type=int, default=12); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("model-pass"); p.add_argument("--model", required=True); p.add_argument("--tier", required=True, choices=["mid", "strong"])
    p.add_argument("--targets", required=True); p.add_argument("--purpose", required=True); p.add_argument("--lemma")
    p.add_argument("--usage-before"); p.add_argument("--operator-ok", action="store_true")
    p.set_defaults(fn=cmd_model_pass)
    p = sub.add_parser("usage"); p.add_argument("note"); p.set_defaults(fn=cmd_usage)
    p = sub.add_parser("draft"); p.add_argument("kind", choices=["claim", "release", "pr"]); p.add_argument("decl", nargs="*"); p.set_defaults(fn=cmd_draft)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = ap.parse_args()
    if a.cmd == "turn":
        need = {"start": ["agent"], "steal": ["agent", "why"], "end": ["did", "next"]}[a.action]
        missing = [n for n in need if not getattr(a, n)]
        if missing:
            rv.die(f"turn {a.action} needs " + ", ".join("--" + m for m in missing))
    a.fn(a)


if __name__ == "__main__":
    main()
