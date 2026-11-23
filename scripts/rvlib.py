"""Shared helpers for the riemann-verified scripts. Standard library only.

Nothing in here calls a model. Every function either reads/writes the ledgers, parses Lean
source text, or runs `lake` under a single-build lock.
"""
from __future__ import annotations

import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Where ledgers, runs, drafts and the turn lock live. Only the self-test points this elsewhere.
STATE = pathlib.Path(os.environ.get("RV_STATE") or ROOT)
LEDGER = STATE / "ledger"

STATES = [
    "open",          # known upstream, nothing of ours on it
    "claimed",       # we commented `Claiming`
    "proved-local",  # proof applied in the worktree, module builds, axioms recorded
    "pr-open",       # in an open pull request
    "merged",        # upstream merged it
    "stuck",         # tried, neither proved nor refuted; note written
    "finding",       # a problem with the statement was reported
    "released",      # claim given back
    "taken",         # someone else claimed or proved it first
]
ROUTES = ["lean-only", "model", "private", "human"]


# ---------------------------------------------------------------- config and paths

def cfg() -> dict:
    return json.loads((ROOT / "config" / "project.json").read_text())


def worktree() -> pathlib.Path:
    p = pathlib.Path(os.environ.get("RV_WORKTREE") or cfg()["worktree"])
    return p if p.is_absolute() else ROOT / p


def scratch_dir(wt: pathlib.Path) -> pathlib.Path:
    d = wt / ".agent" / "rv"          # upstream's .gitignore ignores .agent/
    d.mkdir(parents=True, exist_ok=True)
    return d


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- ledgers

def append(name: str, row: dict) -> None:
    """Append one JSON line. Ledgers are append-only; never rewrite a line."""
    LEDGER.mkdir(exist_ok=True)
    with open(LEDGER / name, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(name: str) -> list[dict]:
    p = LEDGER / name
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                die(f"ledger/{name} line {i} is not JSON: {e}")
    return rows


def load_targets() -> dict:
    p = LEDGER / "targets.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def ledger_key(name: str, file: str | None = None) -> str:
    """The ledger key for a declaration found under its short name (e.g. `foo_false` for
    `Printed.foo_false`), so attempts and the target row use the same name."""
    ts = load_targets()
    if name in ts:
        return name
    hits = [k for k, v in ts.items() if k.split(".")[-1] == name and (file is None or v.get("file") == file)]
    return hits[0] if len(hits) == 1 else name


def same_decl(logged: str | None, key: str) -> bool:
    """An attempt row logged as `logged` belongs to ledger target `key` (short or full name)."""
    return logged == key or (logged is not None and "." not in logged and logged == key.split(".")[-1])


def save_targets(t: dict) -> None:
    LEDGER.mkdir(exist_ok=True)
    tmp = LEDGER / "targets.json.tmp"
    tmp.write_text(json.dumps(t, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, LEDGER / "targets.json")


def set_target(decl: str, **fields) -> dict:
    """Update the current-state row of one declaration and log the transition."""
    t = load_targets()
    row = t.get(decl, {"decl": decl, "state": "open"})
    before = row.get("state")
    row.update({k: v for k, v in fields.items() if v is not None})
    if row["state"] not in STATES:
        die(f"unknown state {row['state']!r}; one of {', '.join(STATES)}")
    row["updated"] = now()
    t[decl] = row
    save_targets(t)
    if before != row["state"]:
        append("attempts.jsonl", {"ts": now(), "type": "state", "decl": decl,
                                  "from": before, "to": row["state"], "note": fields.get("note")})
    return row


# ---------------------------------------------------------------- running Lean

@contextlib.contextmanager
def build_lock(wt: pathlib.Path):
    """One Lean build or check per worktree at a time (a build uses every core)."""
    path = scratch_dir(wt) / "build.lock"
    f = open(path, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        die(f"another Lean check is running in this worktree ({f.read().strip() or 'unknown'}). "
            "Wait for it; never start a second one.", 75)
    f.seek(0); f.truncate(); f.write(f"pid {os.getpid()} since {now()}: {' '.join(sys.argv[:3])}"); f.flush()
    try:
        yield
    finally:
        f.seek(0); f.truncate(); f.close()


def run(cmd: list[str], cwd: pathlib.Path, timeout: int) -> tuple[int, str, float, bool]:
    """Run a command with empty stdin and a hard wall-clock limit. Kills the whole process group."""
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out, time.time() - t0, False
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return -9, out, time.time() - t0, True


def lake_lean(wt: pathlib.Path, rel: str, timeout: int):
    """`lake lean <file> -- --json`: one file with the project's options (never `lake env lean`)."""
    return run(["lake", "lean", rel, "--", "--json"], wt, timeout)


_TEXT_MSG = re.compile(r"^(?:error: |warning: |info: )?(.+?\.lean):(\d+):(\d+): (error|warning|info\w*): ?(.*)$")


def parse_messages(out: str, only: str | None = None) -> list[dict]:
    """Lean messages as {file, line, end, sev, text}. Reads --json output, falls back to text output.

    `only` keeps the messages of one file (path suffix). Use it for a `lake lean` run: Lake also
    replays the warnings of every dependency as text, with line numbers of those other files.
    """
    msgs: list[dict] = []
    for raw in out.splitlines():
        s = raw.strip()
        if s.startswith("{") and '"severity"' in s:
            try:
                j = json.loads(s)
                sev = {"information": "info"}.get(j["severity"], j["severity"])
                line = j["pos"]["line"]
                end = (j.get("endPos") or {}).get("line", line)
                msgs.append({"file": j.get("fileName", ""), "line": line, "end": end, "sev": sev,
                             "text": j.get("data", ""), "kind": j.get("kind", "")})
                continue
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        m = _TEXT_MSG.match(raw)
        if m:
            sev = "info" if m.group(4).startswith("info") else m.group(4)
            msgs.append({"file": m.group(1), "line": int(m.group(2)), "end": int(m.group(2)), "sev": sev,
                         "text": m.group(5), "kind": ""})
        elif msgs and not s.startswith("{"):
            msgs[-1]["text"] += "\n" + raw
    if only:
        msgs = [m for m in msgs if m["file"].endswith(only)]
    return msgs


def other_output(out: str) -> str:
    """What `lake` printed that is not a Lean message (setup failures show up here)."""
    keep = [l for l in out.splitlines() if not (l.strip().startswith("{") and '"severity"' in l)]
    return "\n".join(keep).strip()


def git_sha(wt: pathlib.Path) -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=wt, capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def module_name(rel: str) -> str:
    return rel[:-5].replace("/", ".") if rel.endswith(".lean") else rel.replace("/", ".")


def short(s: str, n: int = 240) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- Lean source text

_HEADER = r"^(?P<mods>(?:(?:private|protected|nonrec)[ \t]+)*)(?P<kw>theorem|lemma)[ \t]+(?P<name>{name})(?=[\s({{\[:])"
_DECL_START = re.compile(
    r"^(?:(?:private|protected|nonrec|noncomputable|public|scoped|local)[ \t]+)*"
    r"(?:theorem|lemma|def|abbrev|instance|structure|class|inductive|example|namespace|section|end|"
    r"variable|open|notation|macro|syntax|attribute|universe)\b", re.M)
_BARE = re.compile(r":=\s*(?:by\s+)?sorry[ \t]*(?:--[^\n]*)?(?=\n\s*\n|\n?\Z|\n(?=\S))")
_IN_LINE = re.compile(r"^(omit|include|open|set_option)\b.*\bin$")


class Target:
    """One theorem whose proof is exactly `sorry`, located in a file's text."""

    def __init__(self, name, start, head, tail_start, end, mods, kept_prefix):
        self.name = name
        self.start = start            # offset of the block start (docstring / attributes / `… in` lines)
        self.head = head              # offset of the `theorem` line
        self.tail_start = tail_start  # offset of the `:=` that precedes `sorry`
        self.end = end                # offset just past `sorry`
        self.mods = mods
        self.kept_prefix = kept_prefix  # `omit … in` style lines, kept on copies


def _block_start(text: str, head: int) -> tuple[int, str]:
    """Walk back from the theorem line over its docstring, attributes and `… in` lines."""
    lines_before = text[:head].split("\n")[:-1]
    i = len(lines_before)
    kept: list[str] = []
    while i > 0:
        s = lines_before[i - 1].strip()
        if s.endswith("-/"):
            j = i - 1
            while j >= 0 and "/-" not in lines_before[j]:
                j -= 1
            if j < 0 or "/--" not in lines_before[j]:
                break
            i = j
        elif s.startswith("@["):
            i -= 1
        elif _IN_LINE.match(s):
            kept.insert(0, lines_before[i - 1])
            i -= 1
        else:
            break
    start = len("\n".join(lines_before[:i])) + (1 if i > 0 else 0)
    return start, ("\n".join(kept) + "\n" if kept else "")


def find_target(text: str, name: str) -> Target | str:
    """Locate a bare-`sorry` theorem. Returns a Target, or a string saying why it is not one."""
    base = name.split(".")[-1]
    pat = re.compile(_HEADER.format(name=r"(?:[\w.']+\.)?" + re.escape(base)), re.M)
    m = pat.search(text)
    if not m:
        return "no theorem or lemma with this name in the file"
    nxt = _DECL_START.search(text, m.end())
    limit = nxt.start() if nxt else len(text)
    b = _BARE.search(text, m.end(), limit)
    if not b:
        return "its proof is not a bare `sorry` (already proved, split, or edited)"
    start, kept = _block_start(text, m.start())
    sorry_end = text.index("sorry", b.start()) + len("sorry")
    return Target(base, start, m.start(), b.start(), sorry_end, m.group("mods"), kept)


def bare_sorries(text: str) -> list[str]:
    """Names of every theorem/lemma in the file whose proof is exactly `sorry`."""
    names = []
    for m in re.finditer(_HEADER.format(name=r"[\w.']+"), text, re.M):
        if isinstance(find_target(text, m.group("name")), Target):
            names.append(m.group("name"))
    return names


def statement_as_example(text: str, t: Target) -> str:
    """The target's statement up to (not including) `:=`, restated as an `example`.

    An `example` is not added to the environment, so no later search can use it.
    """
    header = text[t.head:t.tail_start]
    header = re.sub(r"^(?:(?:private|protected|nonrec)[ \t]+)*(?:theorem|lemma)[ \t]+[\w.']+", "example",
                    header, count=1)
    return t.kept_prefix + header


def namespace_at(text: str, pos: int) -> str:
    """The namespace open at an offset, e.g. `RiemannMasullo`."""
    stack: list[tuple[str, str]] = []
    for m in re.finditer(r"^(namespace|section|end)\b[ \t]*([\w.']*)", text[:pos], re.M):
        kind, name = m.group(1), m.group(2)
        if kind == "end":
            if stack:
                stack.pop()
        else:
            stack.append((kind, name))
    return ".".join(n for k, n in stack if k == "namespace" and n)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def outline(text: str) -> list[tuple[int, str, str, bool]]:
    """(line, keyword, name, is_bare_sorry) for each declaration: a cheap map of a file."""
    rows = []
    sorry_names = set(bare_sorries(text))
    for m in re.finditer(r"^(?:(?:private|protected|nonrec|noncomputable)[ \t]+)*"
                         r"(theorem|lemma|def|abbrev|instance|structure)[ \t]+([\w.']+)", text, re.M):
        rows.append((line_of(text, m.start()), m.group(1), m.group(2), m.group(2) in sorry_names))
    return rows
