#!/usr/bin/env python3
"""check_decisions.py - Agent decision-log tooling (stdlib only, Windows-safe).

Keeps the decision log healthy and turns the FORK RULE into tooling so it
does not rely on memory. Companion to agent-error-log (check_errors.py):
that log records what BROKE (reactive memory); this one records what was
CHOSEN and WHY (proactive memory). Run from the folder holding this script
(or point --log at any decision log):

    python check_decisions.py                              validate every entry
    python check_decisions.py --decide                     scaffold a new decision
    python check_decisions.py --revise <ts>                change a decision: append
                                                           a REVISED entry superseding ts
    python check_decisions.py --resolve <ts>               settle an OPEN decision:
                                                           append LOCKED + SUPERSEDES
    python check_decisions.py --has-open                   gate: exit 1 if any OPEN
                                                           decision is still current
    python check_decisions.py --recent [N]                 show the last N decisions
                                                           with their currency
    python check_decisions.py --stats                      show analytics: status
                                                           mix, reversals, volatility
    python check_decisions.py --review                     distill repeated reversals
                                                           into proposed rules drafts
    python check_decisions.py --review --apply             write the drafts into
                                                           rules.txt section 7
    python check_decisions.py --init [--target DIR]        one-command adoption:
                                                           scaffold the templates,
                                                           health-check, self-test
    python check_decisions.py --check-commit FILE          gate: the commit message
                                                           in FILE must name a
                                                           logged decision

Exit codes: 0 = ok / gate passed, 1 = validation errors or gate failed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stdin and hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
# Default decision log filename. Rename to match your project, or pass --log PATH.
LOG = HERE / "decisions.txt"

STATUSES: tuple[str, ...] = ("LOCKED", "OPEN", "REVISED")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
ENTRY_RE = re.compile(r"^\[(?P<tag>[^\]]+)\] DECISION: (?P<title>.+)$")
FIELD_RE = re.compile(r"^  (?P<field>REASON|FILES|SUPERSEDES|STATUS):\s*(?P<value>.*)$")
SEP_RE = re.compile(r"^={10,}$")
SECTION5 = "5) TO ADD A NEW ENTRY"
RULES = HERE / "rules.txt"            # rules file holding the LESSONS section
LESSONS_HEADER = "LESSONS LEARNED"


# --- Error vocabulary -------------------------------------------------------
class AgentLogError(Exception):
    """Base class for tooling errors (validation / locking / usage)."""


class ValidationError(AgentLogError):
    """The log (or an argument) failed validation."""


class LockTimeoutError(AgentLogError):
    """Could not acquire the cross-process log lock within the deadline."""


# --- Data model ---------------------------------------------------------------
@dataclass
class DecisionEntry:
    """One parsed decision-log entry.

    Dict-compatible on purpose: ``entry["tag"]`` still works (see
    __getitem__), so tests, start.py and any external caller that indexed
    parse_entries() results keep working unchanged. New code should use
    attribute access (entry.tag, entry.title, entry.fields).
    """

    tag: str
    title: str
    line: int
    body: list[str]
    fields: dict[str, str]
    block: str

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)

    def get(self, key: str, default: object = None) -> object:
        return getattr(self, key, default)


def load(path: Path) -> str:
    """Read a text file with UTF-8 fallback (BOM-safe).

    Returns "" if the file cannot be read (e.g. locked by another
    process on Windows) instead of crashing - a locked log degrades to
    empty, never raises (L10).
    """
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def parse_entries(text: str) -> list[DecisionEntry]:
    """Return a list of DecisionEntry objects, in file order.

    An entry starts at a column-0 "[ts] DECISION: ..." line (the template in
    section 5 is indented, so it never matches) and runs until the next entry
    header or a "====" section separator. Each dict has:
      tag, title, line, body, fields, block
    fields may hold REASON / FILES / SUPERSEDES / STATUS.
    """
    lines = text.splitlines()
    entries = []
    for i, line in enumerate(lines):
        m = ENTRY_RE.match(line)
        if not m:
            continue
        j = i + 1
        body = []
        while j < len(lines) and not (ENTRY_RE.match(lines[j]) or SEP_RE.match(lines[j])):
            body.append(lines[j])
            j += 1
        fields = {}
        for bl in body:
            fm = FIELD_RE.match(bl)
            if fm:
                fields.setdefault(fm.group("field"), fm.group("value").strip())
        entries.append(DecisionEntry(
            tag=m.group("tag"),
            title=m.group("title"),
            line=i,
            body=body,
            fields=fields,
            block="\n".join([line] + body),
        ))
    return entries


def status_token(status: str) -> str:
    """First word of a STATUS value, punctuation stripped ('LOCKED.' -> 'LOCKED')."""
    if not status:
        return ""
    return re.split(r"\s", status.strip())[0].rstrip(".,;—–-")


def by_tag(entries: list[DecisionEntry]) -> dict[str, DecisionEntry]:
    """Map tag -> entry (timestamps are unique; first wins)."""
    out = {}
    for e in entries:
        out.setdefault(e["tag"], e)
    return out


def superseded_by(entries: list[DecisionEntry], tag: str) -> Optional[DecisionEntry]:
    """The entry that supersedes `tag`, or None.

    Append-only means "later" == later in the list: parse_entries preserves
    file order, so list index is chronological. Index-based (not raw line
    numbers) so the check stays correct across any parsed list.
    """
    order = {e["tag"]: i for i, e in enumerate(entries)}
    if tag not in order:
        return None
    for e in entries:
        if e["fields"].get("SUPERSEDES") == tag and order[e["tag"]] > order[tag]:
            return e
    return None


def current_open(entries: list[DecisionEntry]) -> list[DecisionEntry]:
    """OPEN decisions that no later entry supersedes (i.e. still need a call)."""
    out = []
    for e in entries:
        if status_token(e["fields"].get("STATUS", "")).upper() != "OPEN":
            continue
        if superseded_by(entries, e["tag"]) is not None:
            continue
        out.append(e)
    return out


def find_section5(text: str) -> Optional[int]:
    """Line index of the section-5 header, or None."""
    for i, l in enumerate(text.splitlines()):
        if l.strip() == SECTION5:
            return i
    return None


def _with_log_lock(log_path: Path, fn: Callable[[], int]) -> int:
    """Serialize a read-modify-write on log_path across processes.

    Creates a sibling '<name>.lock' file atomically (O_CREAT|O_EXCL, which
    fails if the lock already exists) and retries for up to 5s; the lock is
    removed in a finally block. A stale lock older than 30s (crashed writer)
    is broken and reclaimed. Returns fn()'s result; raises LockTimeoutError
    on timeout.
    """
    lock_path = log_path.with_name(log_path.name + ".lock")
    deadline = time.time() + 5.0
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 30:
                    # Atomically claim the stale lock by renaming it
                    # aside: only one contender can win the rename, so
                    # nobody can ever unlink a lock another process has
                    # just created (TOCTOU hardening). The .stale file
                    # is garbage by definition - unlinking it is safe.
                    stale = lock_path.with_name(lock_path.name + ".stale")
                    try:
                        stale.unlink()
                    except OSError:
                        pass
                    os.rename(lock_path, stale)
                    try:
                        stale.unlink()
                    except OSError:
                        pass
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise LockTimeoutError(f"timed out waiting for log lock: {lock_path}")
            time.sleep(0.05)
    try:
        return fn()
    finally:
        try:
            lock_path.unlink()
        except OSError:
            pass


def _locked_append(log_path: Path, block: str,
                    validate: Optional[Callable[[str], tuple[bool, str]]] = None) -> int:
    """Append a block under the log lock, re-reading inside the lock.

    The read-modify-write (load -> insert_before_section5 -> write) is not
    atomic; two concurrent appends could both read the same text and one
    entry would be silently lost. Locking and re-reading inside the lock
    makes concurrent appends safe (lost-update fix, L9).

    `validate(text) -> (ok, msg)` is optional and runs against the FRESH
    text inside the lock, so validation and the write can never disagree
    under concurrency (caller-passed text may be stale by write time).
    """
    def do_write() -> int:
        text = load(log_path)
        if validate is not None:
            ok, msg = validate(text)
            if not ok:
                print(msg)
                return 1
        log_path.write_text(insert_before_section5(text, block), encoding="utf-8")
        return 0
    try:
        return _with_log_lock(log_path, do_write)
    except LockTimeoutError as e:
        print(e)
        return 1


def insert_before_section5(text: str, block: str) -> str:
    """Insert a block (already formatted) directly above section 5's bar.

    The block goes between the last live content and the separator bar that
    belongs to section 5, so the bar stays attached to its header and no
    stray bar or blank line is left behind.
    """
    idx = find_section5(text)
    lines = text.splitlines()
    if idx is None:
        return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    k = idx
    while k > 0 and not SEP_RE.match(lines[k]):
        k -= 1
    if k == 0 and not SEP_RE.match(lines[0]):
        k = idx  # no bar above section 5 - insert directly above the header
    before, after = lines[:k], lines[k:]
    while before and before[-1].strip() == "":
        before.pop()
    while after and after[0].strip() == "":
        after.pop(0)
    return "\n".join(before) + "\n\n" + block.rstrip("\n") + "\n\n" + "\n".join(after) + "\n"


def cmd_check(text: str) -> int:
    """Validate every entry: fields present, status vocabulary, chain integrity."""
    errors, warnings = [], []
    seen = set()
    entries = parse_entries(text)
    if not entries:
        print("No decisions found in the decision log.")
        return 0
    table = by_tag(entries)
    for e in entries:
        tag = e["tag"]
        loc = f"line {e['line'] + 1} [{tag}] DECISION: {e['title']}"
        if not DATE_RE.match(tag):
            warnings.append(f"{loc}: unusual timestamp (expected 'YYYY-MM-DD HH:MM')")
        if not e["fields"].get("REASON", ""):
            errors.append(f"{loc}: missing REASON field (why did you pick this?)")
        st = status_token(e["fields"].get("STATUS", ""))
        if not st:
            errors.append(f"{loc}: missing STATUS field")
        elif st.upper() not in STATUSES:
            warnings.append(f"{loc}: STATUS '{st}' not in {STATUSES}")
        ss = e["fields"].get("SUPERSEDES", "")
        if st.upper() == "REVISED" and not ss:
            errors.append(f"{loc}: REVISED entry must carry SUPERSEDES: <timestamp>")
        if ss:
            target = table.get(ss)
            if target is None:
                errors.append(f"{loc}: SUPERSEDES '{ss}' points at no existing entry")
            elif target["line"] >= e["line"]:
                errors.append(f"{loc}: SUPERSEDES must point at an EARLIER entry "
                              f"(history is append-only - never point forward)")
            elif (status_token(target["fields"].get("STATUS", "")).upper() == "OPEN"
                  and st.upper() == "REVISED"):
                # LOCKED + SUPERSEDES->OPEN is the intended --resolve pattern;
                # only a REVISED entry superseding an OPEN one is contradictory.
                warnings.append(f"{loc}: REVISED entry supersedes an OPEN decision - "
                                f"use --resolve to settle OPEN decisions")
            elif st.upper() == "OPEN":
                warnings.append(f"{loc}: an OPEN decision should not supersede - use "
                                f"REVISED when changing your mind")
        if tag in seen:
            warnings.append(f"{loc}: duplicate timestamp")
        seen.add(tag)
    for msg in errors:
        print(f"ERROR: {msg}")
    for msg in warnings:
        print(f"WARN : {msg}")
    print(f"{len(entries)} decision(s): {len(errors)} error(s), {len(warnings)} warning(s).")
    open_ = current_open(entries)
    if open_:
        print(f"{len(open_)} OPEN decision(s) still awaiting a call:")
        for e in open_:
            print(f"  [{e['tag']}] {e['title']}")
    return 1 if errors else 0


def cmd_has_open(text: str) -> int:
    """Mechanical gate: exit 1 if any OPEN decision is still current."""
    open_ = current_open(parse_entries(text))
    if not open_:
        print("GATE PASSED - no OPEN decisions awaiting a call.")
        return 0
    for e in open_:
        print(f"OPEN: [{e['tag']}] {e['title']}")
    print(f"GATE FAILED - {len(open_)} OPEN decision(s) need a call.")
    print("settle them early, or say explicitly why they stay deferred.")
    return 1


def ask(prompt: str, required: bool = False, default: Optional[str] = None) -> str:
    """Single-line interactive prompt (Ctrl-C/EOF aborts cleanly)."""
    if default:
        prompt += f" [{default}]"
    try:
        val = input(prompt + ": ").strip()
    except EOFError:
        print("\n(aborted)")
        raise SystemExit(1)
    if not val and default:
        val = default
    if required and not val:
        print("Required - aborting.")
        raise SystemExit(1)
    return val


def now_ts() -> str:
    """Current timestamp in the log's format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def format_block(title: str, reason: str, files: str, supersedes: str, status: str) -> str:
    """Render one entry block in the template format."""
    lines = [f"[{now_ts()}] DECISION: {title}",
             f"  REASON: {reason}"]
    if files:
        lines.append(f"  FILES: {files}")
    if supersedes:
        lines.append(f"  SUPERSEDES: {supersedes}")
    lines.append(f"  STATUS: {status}.")
    return "\n".join(lines) + "\n"


def _validate_ss(text: str, ss: str) -> tuple[bool, str]:
    """Return (ok, msg) for a SUPERSEDES value against the current log."""
    if not ss:
        return True, ""
    for e in parse_entries(text):
        if e["tag"] == ss:
            return True, ""
    return False, f"no entry with timestamp '{ss}' - check decisions.txt"


def cmd_decide(text: str, log_path: Path) -> int:
    """Scaffold a decision entry in the template format, then append it."""
    title = ask("DECISION (what you chose)", required=True)
    reason = ask("REASON (why - the alternative you considered)", required=True)
    files = ask("FILES (files affected, optional)", default="")
    supersedes = ""
    while True:
        st = ask("STATUS", default="LOCKED").upper()
        if st in STATUSES:
            break
        print(f"Status must be one of: {STATUSES}")
    if st == "REVISED" or st == "LOCKED":
        supersedes = ask("SUPERSEDES (ts this replaces/resolves, optional)", default="")
        if supersedes:
            ok, msg = _validate_ss(text, supersedes)
            if not ok:
                print(msg)
                supersedes = ask("SUPERSEDES (re-enter a valid ts, or leave blank)", default="")
    if st == "REVISED" and not supersedes:
        print("A REVISED entry must supersede an earlier decision - aborting.")
        raise SystemExit(1)
    block = format_block(title, reason, files, supersedes, st)
    rc = _locked_append(log_path, block,
                        validate=lambda t: _validate_ss(t, supersedes))
    if rc:
        return rc
    print("Logged:")
    print(block.rstrip("\n"))
    return 0


def cmd_revise(text: str, log_path: Path, target_ts: str) -> int:
    """Change a decision: append a REVISED entry superseding target_ts."""
    if target_ts not in by_tag(parse_entries(text)):
        print(f"no entry with timestamp '{target_ts}' - check decisions.txt")
        return 1
    title = ask("DECISION (what you now chose)", required=True)
    reason = ask("REASON (why the change)", required=True)
    files = ask("FILES (files affected, optional)", default="")
    block = format_block(title, reason, files, target_ts, "REVISED")
    def _check(t: str) -> tuple[bool, str]:
        if target_ts not in by_tag(parse_entries(t)):
            return False, f"no entry with timestamp '{target_ts}' - check decisions.txt"
        return True, ""
    # write under the cross-process log lock with a fresh re-read inside
    # the lock, so a concurrent append can never be clobbered (L9), and
    # validate the target against that FRESH text, not the stale param.
    rc = _locked_append(log_path, block, validate=_check)
    if rc:
        return rc
    print("Logged (REVISED, supersedes " + target_ts + "):")
    print(block.rstrip("\n"))
    return 0


def cmd_resolve(text: str, log_path: Path, target_ts: str) -> int:
    """Settle an OPEN decision: append a LOCKED entry superseding it."""
    entries = by_tag(parse_entries(text))
    target = entries.get(target_ts)
    if target is None:
        print(f"no entry with timestamp '{target_ts}' - check decisions.txt")
        return 1
    if status_token(target["fields"].get("STATUS", "")).upper() != "OPEN":
        print(f"WARN : '{target_ts}' is not OPEN - resolving a non-OPEN decision is odd")
    title = ask("DECISION (the call you made)", required=True)
    reason = ask("REASON (why now / why this)", required=True)
    files = ask("FILES (files affected, optional)", default="")
    block = format_block(title, reason, files, target_ts, "LOCKED")
    def _check(t: str) -> tuple[bool, str]:
        if target_ts not in by_tag(parse_entries(t)):
            return False, f"no entry with timestamp '{target_ts}' - check decisions.txt"
        return True, ""
    # write under the cross-process log lock with a fresh re-read inside
    # the lock, so a concurrent append can never be clobbered (L9), and
    # validate the target against that FRESH text, not the stale param.
    rc = _locked_append(log_path, block, validate=_check)
    if rc:
        return rc
    print("Logged (LOCKED, resolves " + target_ts + "):")
    print(block.rstrip("\n"))
    return 0


def cmd_recent(text: str, n: int) -> int:
    """Show the last N decisions with currency (CURRENT vs SUPERSEDED)."""
    entries = parse_entries(text)
    if not entries:
        print("No decisions logged yet.")
        return 0
    for e in entries[-n:]:
        st = status_token(e["fields"].get("STATUS", "")).upper()
        ss = e["fields"].get("SUPERSEDES", "")
        sub = superseded_by(entries, e["tag"])
        state = f"SUPERSEDED BY {sub['tag']}" if sub else "CURRENT"
        chain = f" (supersedes {ss})" if ss else ""
        print(f"[{e['tag']}] {st} - {state}{chain}: {e['title']}")
    open_ = current_open(entries)
    if open_:
        print(f"\n{len(open_)} OPEN decision(s) requiring attention:")
        for e in open_:
            print(f"  [{e['tag']}] {e['title']}")
    return 0


def cmd_stats(text: str) -> int:
    """Analytics over the decision log: status mix, reversals, volatility."""
    entries = parse_entries(text)
    if not entries:
        print("No decisions in the decision log - nothing to summarize.")
        return 0
    counts = {}
    statuses = {}
    for e in entries:
        st = status_token(e["fields"].get("STATUS", "")).upper()
        statuses[e["tag"]] = st
        counts[st] = counts.get(st, 0) + 1
    open_now = len(current_open(entries))
    superseded = sum(1 for e in entries if superseded_by(entries, e["tag"]) is not None)
    table = by_tag(entries)
    revs = [e for e in entries
            if statuses.get(e["tag"]) == "REVISED"
            and e["fields"].get("SUPERSEDES") in table]

    def _ts(tag):
        try:
            return datetime.strptime(tag, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    deltas = []
    for e in revs:
        base = table[e["fields"]["SUPERSEDES"]]
        t0, t1 = _ts(base["tag"]), _ts(e["tag"])
        if t0 is not None and t1 is not None and t1 >= t0:
            deltas.append((t1 - t0).total_seconds() / 86400.0)
    avg_days = sum(deltas) / len(deltas) if deltas else 0.0

    locked = counts.get("LOCKED", 0)
    settled = locked + counts.get("REVISED", 0)
    rate = (len(revs) / settled * 100.0) if settled else 0.0

    rev_by_topic = {}
    for e in revs:
        rev_by_topic.setdefault(_topic_of(e), []).append(e)
    volatile = sorted(rev_by_topic.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]

    mix = " | ".join(f"{k} {counts[k]}" for k in ("LOCKED", "OPEN", "REVISED") if k in counts)
    print(f"DECISION LOG STATS - {len(entries)} decision(s)")
    print(f"  status mix  : {mix}")
    print(f"  open now    : {open_now} current OPEN decision(s) still awaiting a call")
    print(f"  superseded  : {superseded} decision(s) no longer current")
    print(f"  reversals   : {len(revs)} (of {settled} settled, {rate:.1f}% were REVISED)")
    if deltas:
        print(f"  avg LOCKED -> REVISED : {avg_days:.1f} day(s)")
    else:
        print("  avg LOCKED -> REVISED : n/a")
    if volatile:
        print("  most volatile topics:")
        for topic, rs in volatile:
            print(f"    - {topic.split(':', 1)[1]} ({len(rs)} reversal(s))")
    return 0


# --- Review distillation (--review) ----------------------------------------

def _topic_of(e: DecisionEntry) -> str:
    """Grouping key for --review/--stats: first FILES basename when present,
    else the first 3 title words.

    Deterministic by design, not a taxonomy: two entries touching the same
    basename in different directories merge into one topic.
    """
    files = e["fields"].get("FILES", "")
    if files:
        return "files:" + Path(files.split(",")[0].strip()).name.lower()
    return "title:" + " ".join(e["title"].lower().split()[:3])


def cmd_review(text: str, rules_path: Path, apply: bool) -> int:
    """Distill repeated reversals into proposed rules; --apply writes §7."""
    entries = parse_entries(text)
    if not entries:
        print("No decisions in the decision log - nothing to distill.")
        return 0
    table = by_tag(entries)
    rev_by_topic = {}
    for e in entries:
        ss = e["fields"].get("SUPERSEDES", "")
        if not ss or ss not in table:
            continue
        if status_token(e["fields"].get("STATUS", "")).upper() != "REVISED":
            continue  # only REVISED entries are reversals; --resolve entries settle
        rev_by_topic.setdefault(_topic_of(e), []).append(e)
    proposals = []
    for topic in sorted(rev_by_topic):
        revs = rev_by_topic[topic]
        if len(revs) < 2:
            continue
        dates = ", ".join(sorted(r["tag"] for r in revs))
        label = topic.split(":", 1)[1]
        reasons = "\n".join(
            f"   - {r['tag']}: {r['fields'].get('REASON', '').strip()}"
            for r in sorted(revs, key=lambda r: r["tag"])
            if r["fields"].get("REASON", "").strip()
        )
        proposals.append(
            f"{len(proposals) + 1}. {label}\n"
            f"   {len(revs)} reversal(s) - decisions on '{label}' were LOCKED then changed\n"
            f"   (supersedes on {dates})\n"
            f"   Why it kept changing:\n{reasons}\n"
            f"   Proposal: default to the most recent decision on {label} unless the\n"
            f"   context genuinely changed; when it does, log a REVISED entry that says why.\n"
        )
    if not proposals:
        print("No repeated reversals found (need 2+ changes on the same topic).")
        print("Nothing to propose - the log is stable or too young.")
        return 0
    body = (
        "Distilled from the decision log by: python check_decisions.py --review [--apply]\n"
        f"Generated: {datetime.now():%Y-%m-%d}  |  source: {len(entries)} decision(s).\n"
        "\n"
        + "\n".join(p.strip() for p in proposals).rstrip("\n")
        + "\n"
    )
    print(body, end="")
    print(f"{len(proposals)} proposed rule(s) from {len(entries)} decision(s).")
    if not apply:
        print("Dry run - nothing changed. Re-run with --apply to write these")
        print("proposals into the rules file (rules.txt section 7).")
        return 0
    if not rules_path.exists():
        print(f"WARN : rules file not found: {rules_path} (creating it)")
    rules_path.write_bytes(_patch_rules_lessons(rules_path, body).encode("utf-8"))
    print(f"Proposals written to: {rules_path}")
    return 0


def _patch_rules_lessons(rules_path: Path, body: str) -> str:
    """Replace the LESSONS section in rules.txt with body; append if absent.

    The header is anchored to a real section title (a numbered section line
    or exactly 'LESSONS LEARNED'), so a stray mention of the words in the
    body is never mistaken for the section. Original line endings are
    preserved (CRLF in, CRLF out).
    """
    raw = rules_path.read_bytes() if rules_path.exists() else b""
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8", errors="replace")
    bar = "=" * 80
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines)
                if LESSONS_HEADER in l
                and (re.match(r"^\s*(##\s*)?\d+\)", l) or l.strip() == LESSONS_HEADER)), None)
    if idx is not None:
        head = "\n".join(lines[: idx + 1])
        out = head + "\n" + bar + "\n" + body
    else:
        block = f"{bar}\n{LESSONS_HEADER}\n{bar}\n{body}"
        out = block if not text.strip() else text.rstrip("\r\n") + "\n\n" + block
    return out.replace("\n", "\r\n") if crlf else out


# --- One-command adoption (--init) ------------------------------------------
# --init scaffolds the three template files (decisions / rules / notes),
# health-checks the log, and runs the tooling's own unit tests. Templates are
# copied from the folder holding this script; when only check_decisions.py was
# copied into a project (no templates), built-in minimal scaffolds are used
# instead. Existing files are NEVER overwritten.
#
# decisions.txt is a STATIC scaffold, never a copy of this repo's live log:
# the repo's log legitimately accumulates this project's own dev entries, and
# pre-seeding a consumer's log with them would fake a decision history the
# consumer never made. NOTE: every continuation line starts with '+' so
# adjacent string literals are never implicitly concatenated.

MINIMAL_DECISIONS = (
    "=" * 80 + "\n"
    + "DECISION LOG - scaffolded by check_decisions.py --init\n"
    + "=" * 80 + "\n"
    + "\n"
    + "What the agent CHOSE and WHY - proactive memory (\"I chose this\"), the\n"
    + "companion to an error log (\"I broke this\"). Append-only: history is never\n"
    + "rewritten - corrections are new entries that point back with SUPERSEDES.\n"
    + "\n"
    + "THE FORK RULE (when to log): log a decision when reversing it would cost\n"
    + "time, or when you actively considered an alternative and picked one.\n"
    + "\n"
    + "STATUS: LOCKED (stands) | OPEN (deferred, needs a call) | REVISED (changed;\n"
    + "carries SUPERSEDES: <ts> pointing back at what it replaced).\n"
    + "\n"
    + "=" * 80 + "\n"
    + "EXAMPLE ENTRIES (replace with your own; delete this section header)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "[2026-08-09 14:32] DECISION: used regex instead of AST parser\n"
    + "  REASON: faster for the simple case, file was small\n"
    + "  FILES: src/parser.py\n"
    + "  STATUS: LOCKED.\n"
    + "\n"
    + "[2026-08-09 15:00] DECISION: auth flow - JWT over OAuth\n"
    + "  REASON: single API consumer, no third-party login needed yet\n"
    + "  FILES: auth.py\n"
    + "  STATUS: OPEN.\n"
    + "\n"
    + "[2026-08-10 09:15] DECISION: moved parser to AST\n"
    + "  REASON: file grew past 200 lines; regex became unmaintainable\n"
    + "  FILES: src/parser.py\n"
    + "  SUPERSEDES: 2026-08-09 14:32\n"
    + "  STATUS: REVISED.\n"
    + "\n"
    + "=" * 80 + "\n"
    + "5) TO ADD A NEW ENTRY\n"
    + "=" * 80 + "\n"
    + "  [YYYY-MM-DD HH:MM] DECISION: <what you chose>\n"
    + "    REASON: <why - the alternative you considered>\n"
    + "    FILES: <files affected, optional>\n"
    + "    SUPERSEDES: <ts this replaces/resolves, REVISED only>\n"
    + "    STATUS: LOCKED | OPEN | REVISED\n"
)

MINIMAL_RULES = (
    "=" * 80 + "\n"
    + "<YOUR PROJECT NAME> - RULES OF ENGAGEMENT\n"
    + "(scaffolded by check_decisions.py --init)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "1. THE FORK RULE: log a decision when reversing it would cost time, or\n"
    + "   when you actively considered an alternative and picked one. Use:\n"
    + "       python check_decisions.py --decide\n"
    + "2. NEVER REPEAT EXPLORATION: if a decision is LOCKED, honor it unless the\n"
    + "   context genuinely changed (then log a REVISED entry, never edit).\n"
    + "3. BOOT RECALL: run `python start.py` at session start - it surfaces the\n"
    + "   last decisions and anything still OPEN. Start from that state.\n"
    + "4. SETTLE OPEN DECISIONS early, or say explicitly why they stay deferred.\n"
)

MINIMAL_NOTES = (
    "=" * 80 + "\n"
    + "<YOUR PROJECT NAME> - NOTES\n"
    + "(scaffolded by check_decisions.py --init)\n"
    + "=" * 80 + "\n"
    + "\n"
    + "SESSION NOTE (YYYY-MM-DD): <title>\n"
    + "- what happened this session, decisions taken, and the next step\n"
)


def _template_text(name: str, fallback: str) -> str:
    """Content for a template file: the real template next to this script, or a
    minimal built-in scaffold when it is missing (e.g. only check_decisions.py
    was copied into the target project).

    NOTE: decisions.txt does NOT go through here - it is always the static
    MINIMAL_DECISIONS scaffold, so a consumer never inherits this repo's dev
    log. rules.txt / notes.txt are copied from HERE only because they are
    verified generic templates; keep them free of project-specific content."""
    p = HERE / name
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return fallback


def cmd_init(target: str, run_tests: bool = True) -> int:
    """One-command adoption: scaffold the templates, health-check the log,
    and (optionally) run the unit tests. Existing files are never overwritten."""
    target = Path(target)
    if target.exists() and not target.is_dir():
        print(f"--init target is not a directory: {target}")
        return 1
    target.mkdir(parents=True, exist_ok=True)
    print(f"--init target: {target}")
    for name, content in (("decisions.txt", MINIMAL_DECISIONS),
                          ("rules.txt", _template_text("rules.txt", MINIMAL_RULES)),
                          ("notes.txt", _template_text("notes.txt", MINIMAL_NOTES))):
        dest = target / name
        if dest.exists():
            print(f"  exists: {name} (left untouched)")
            continue
        dest.write_text(content, encoding="utf-8")
        print(f"  created: {name}")
    log = target / "decisions.txt"
    if log.exists():
        rc = cmd_check(load(log))
        print(f"  health check: decision log {'OK' if rc == 0 else 'HAS PROBLEMS (see above)'}")
    else:
        print("  WARN: no decisions.txt to health-check")
    selftest = HERE / "_test_decisions.py"
    if run_tests and selftest.exists():
        print(f"  self-test: running the tooling's unit tests ({selftest}) ...")
        ret = subprocess.run([sys.executable, str(selftest)], check=False)
        if ret.returncode != 0:
            print(f"  self-test FAILED (exit {ret.returncode}) - the tooling is broken")
            print("  in this environment; adoption continues but fix it before relying on")
            print("  the log.")
            return 1
        print("  self-test: all tests passed")
    else:
        print("  self-test: skipped (run_tests off, or no _test_decisions.py next to")
        print("             check_decisions.py)")
    print("  NEXT: python check_decisions.py to validate; start.py for the session")
    print("        bootstrap. Behavior rules live in rules.txt.")
    return 0

def _extract_area(msg: str) -> Optional[str]:
    """Marker value from a commit message, or None.

    Matches the shell hooks exactly: the first line that carries an
    AREA:/LOG: marker, then the LAST marker on that line (the hooks use
    'grep -m1' for the line and a greedy 'sed s/^.*(AREA|LOG):' for the
    marker). The CI gate and the local hook therefore gate on the same text.
    """
    for line in msg.splitlines():
        marks = list(re.finditer(r"(?:AREA|LOG)\s*:", line, re.IGNORECASE))
        if not marks:
            continue
        area = line[marks[-1].end():]
        area = re.sub(r"[),.;:]+\s*$", "", area)
        return re.sub(r"\s+", " ", area).strip()
    return None


def cmd_check_commit(text: str, msg_path: Path) -> int:
    """Gate on a commit message file: exit 0 only if it names a logged decision.

    Server-side twin of the log-before-change rule so the AREA-marker
    convention is mechanically enforced in CI (this repo has no local commit
    hook). The message must carry an 'AREA:' (or 'LOG:') marker naming a
    decision that is already logged in decisions.txt.
    """
    if not msg_path.exists():
        print(f"commit-gate: message file not found: {msg_path}")
        return 1
    area = _extract_area(load(msg_path))
    if not area:
        print("commit-gate BLOCKED: no 'AREA:' marker in the commit message.")
        print("  Log the decision first:  python check_decisions.py --decide")
        print('  Then commit with:         git commit -m "... (AREA: <decision topic>)"')
        return 1
    # Mirrors the --has-entry search: the marker must name a logged decision.
    needle = area.lower()
    found = [e for e in parse_entries(text)
             if needle in (e["title"] + " " + e["tag"]).lower()]
    if found:
        print(f'commit-gate OK: "{area}" names a logged decision - change may land.')
        return 0
    print(f'commit-gate BLOCKED: "{area}" matches no logged decision.')
    print("  LOG BEFORE CHANGING: add the decision first (python check_decisions.py --decide),")
    print("  then commit again.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate and maintain the decision log (stdlib only). "
                    "Exit 0 = ok / gate passed, 1 = validation errors / gate failed.")
    ap.add_argument("--log", metavar="PATH",
                    help="decision log to use (default: decisions.txt in this folder)")
    ap.add_argument("--decide", action="store_true",
                    help="scaffold a new decision entry (interactive)")
    ap.add_argument("--revise", metavar="TS",
                    help="change a decision: append a REVISED entry superseding TS")
    ap.add_argument("--resolve", metavar="TS",
                    help="settle an OPEN decision: append a LOCKED entry superseding TS")
    ap.add_argument("--has-open", action="store_true",
                    help="gate: exit 1 if any OPEN decision is still current")
    ap.add_argument("--recent", nargs="?", const=5, type=int, metavar="N",
                    help="show the last N decisions (default 5) with currency")
    ap.add_argument("--stats", action="store_true",
                    help="show analytics: status mix, reversal rate, volatility")
    ap.add_argument("--review", action="store_true",
                    help="distill repeated reversals into proposed rule drafts "
                         "(preview; --apply writes rules.txt section 7)")
    ap.add_argument("--apply", action="store_true",
                    help="with --review: write the proposals into rules.txt")
    ap.add_argument("--rules", metavar="PATH",
                    help="rules file to update with --review --apply "
                         "(default: rules.txt in this folder)")
    ap.add_argument("--init", action="store_true",
                    help="one-command adoption: scaffold decisions/rules/notes, "
                         "health-check, self-test")
    ap.add_argument("--target", metavar="DIR",
                    help="with --init: directory to adopt (default: current directory)")
    ap.add_argument("--no-tests", action="store_true",
                    help="with --init: skip the tooling's unit-test run")
    ap.add_argument("--check-commit", metavar="FILE",
                    help="gate: exit 0 only if the commit message in FILE names "
                         "a logged decision (AREA:/LOG: marker)")
    args = ap.parse_args()

    if args.init:
        return cmd_init(args.target or ".", run_tests=not args.no_tests)

    log_path = Path(args.log) if args.log else LOG
    try:
        if not log_path.exists():
            raise ValidationError(f"missing decision log: {log_path}")
        text = load(log_path)

        if args.check_commit:
            return cmd_check_commit(text, Path(args.check_commit))

        if args.decide:
            return cmd_decide(text, log_path)
        if args.revise:
            return cmd_revise(text, log_path, args.revise)
        if args.resolve:
            return cmd_resolve(text, log_path, args.resolve)
        if args.has_open:
            return cmd_has_open(text)
        if args.recent is not None:
            return cmd_recent(text, args.recent)
        if args.stats:
            return cmd_stats(text)
        if args.review:
            rules_path = Path(args.rules) if args.rules else RULES
            return cmd_review(text, rules_path, args.apply)
        return cmd_check(text)
    except AgentLogError as e:
        print(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
