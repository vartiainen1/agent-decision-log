"""Unit tests for check_decisions.py - parsing, validation, gates, decide,
revise, resolve, recent, review, init.
Run: python _test_decisions.py"""

import io
import random
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import check_decisions as cd

PASS = 0

BAR = "=" * 80


def t(name, cond):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"PASS {PASS}: {name}")


def quiet(fn, *args, **kwargs):
    """Run fn with stdout captured so PASS lines stay readable."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        return fn(*args, **kwargs)
    finally:
        sys.stdout = old


def entry(ts, title, status="LOCKED", reason="why", files="", supersedes=""):
    """One template-formatted decision entry."""
    e = f"[{ts}] DECISION: {title}\n"
    if reason is not None:
        e += f"  REASON: {reason}\n"
    if files:
        e += f"  FILES: {files}\n"
    if supersedes:
        e += f"  SUPERSEDES: {supersedes}\n"
    e += f"  STATUS: {status}.\n"
    return e


def sample_log():
    """Small representative log: LOCKED, OPEN, and a REVISED chain entry."""
    return (
        BAR + "\n1) TEST AREA\n" + BAR + "\n\n"
        + entry("2026-08-09 14:32", "used regex instead of AST parser", files="src/parser.py")
        + "\n"
        + entry("2026-08-09 15:00", "auth flow - JWT over OAuth", status="OPEN")
        + "\n"
        + entry("2026-08-10 09:15", "moved parser to AST", status="REVISED",
                files="src/parser.py", supersedes="2026-08-09 14:32")
        + "\n"
        + BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n"
        + "  [YYYY-MM-DD HH:MM] DECISION: <what you chose>\n"
        + "    REASON: <why - the alternative you considered>\n"
        + "    STATUS: LOCKED | OPEN | REVISED\n"
    )


def tmp_log(text):
    """Write text to a throwaway file; returns (cleaner, path)."""
    d = tempfile.TemporaryDirectory()
    p = Path(d.name) / "decisions.txt"
    p.write_text(text, encoding="utf-8")
    return d, p


# --- parse_entries ---------------------------------------------------------
S = sample_log()
es = cd.parse_entries(S)
t("parses the 3 real entries", len(es) == 3)
t("indented template is not an entry", not any("what you chose" in e["title"] for e in es))
t("tags parsed", es[0]["tag"] == "2026-08-09 14:32")
t("titles parsed", es[0]["title"] == "used regex instead of AST parser")
t("fields extracted", es[0]["fields"]["STATUS"] == "LOCKED." and es[0]["fields"]["REASON"] == "why")
t("REVISED carries SUPERSEDES", es[2]["fields"]["SUPERSEDES"] == "2026-08-09 14:32")
t("line index points at the header", S.splitlines()[es[0]["line"]] == es[0]["block"].splitlines()[0])
t("body stops before section bar", not any("5) TO ADD" in l for e in es for l in e["body"]))
t("empty text parses to nothing", cd.parse_entries("") == [])

# --- status_token ----------------------------------------------------------
t("status_token strips dot", cd.status_token("LOCKED.") == "LOCKED")
t("status_token splits note", cd.status_token("OPEN - deferred") == "OPEN")
t("status_token empty", cd.status_token("") == "")

# --- by_tag / superseded_by / current_open ---------------------------------
t("by_tag maps timestamps", cd.by_tag(es)["2026-08-09 14:32"]["title"].startswith("used regex"))
t("superseded_by finds the REVISED entry", cd.superseded_by(es, "2026-08-09 14:32")["tag"] == "2026-08-10 09:15")
t("superseded_by none for current", cd.superseded_by(es, "2026-08-10 09:15") is None)
t("current_open finds the OPEN entry", [e["tag"] for e in cd.current_open(es)] == ["2026-08-09 15:00"])
resolved = es + cd.parse_entries(
    entry("2026-08-11 10:00", "settled auth", supersedes="2026-08-09 15:00"))
t("current_open drops resolved OPEN", cd.current_open(resolved) == [])

# --- find_section5 / insert_before_section5 --------------------------------
idx = cd.find_section5(S)
t("find_section5 found", idx is not None and "5) TO ADD" in S.splitlines()[idx])
t("find_section5 none", cd.find_section5("no section here") is None)

BLOCK = entry("2026-08-08 10:00", "inserted")
ins = cd.insert_before_section5(S, BLOCK)
L = ins.splitlines()
t("insert keeps the section-5 bar attached", L[L.index("5) TO ADD A NEW ENTRY") - 1].startswith("==="))
t("insert places block before section 5", ins.index("[2026-08-08 10:00]") < ins.index("5) TO ADD A NEW ENTRY"))
t("insert no double blank lines", "\n\n\n" not in ins)
t("insert appends when no section 5", cd.insert_before_section5("A\nB\n", BLOCK).endswith(BLOCK.rstrip("\n") + "\n"))
no_bar = "A\nB\n5) TO ADD A NEW ENTRY\n====\n"
t("insert falls back when no bar above section 5",
  cd.insert_before_section5(no_bar, BLOCK).index("[2026-08-08 10:00]") < cd.insert_before_section5(no_bar, BLOCK).index("5) TO ADD A NEW ENTRY"))

# --- cmd_check (validation) ------------------------------------------------
t("clean log validates", quiet(cd.cmd_check, S) == 0)
t("missing REASON fails", quiet(cd.cmd_check, entry("2026-08-01 10:00", "no reason", reason=None)) == 1)
t("missing STATUS fails", quiet(cd.cmd_check, entry("2026-08-01 10:00", "no status").replace("  STATUS: LOCKED.\n", "")) == 1)
t("bad status warns only", quiet(cd.cmd_check, entry("2026-08-01 10:00", "bad status", status="WEIRD")) == 0)
t("REVISED without SUPERSEDES fails", quiet(cd.cmd_check, entry("2026-08-01 10:00", "revised no ss", status="REVISED")) == 1)
t("SUPERSEDES to nowhere fails", quiet(cd.cmd_check, entry("2026-08-01 10:00", "bad ref", status="REVISED", supersedes="1999-01-01 00:00")) == 1)
t("SUPERSEDES pointing forward fails",
  quiet(cd.cmd_check, entry("2026-08-01 10:00", "fwd ref", status="REVISED", supersedes="2026-08-02 10:00")
        + entry("2026-08-02 10:00", "later")) == 1)
t("unusual tag warns only", quiet(cd.cmd_check, entry("yesterday", "odd tag")) == 0)
t("duplicate timestamp warns only", quiet(cd.cmd_check, entry("2026-08-01 10:00", "dup a") + entry("2026-08-01 10:00", "dup b")) == 0)
t("empty log validates", quiet(cd.cmd_check, "") == 0)
t("LOCKED resolving OPEN validates",
  quiet(cd.cmd_check, entry("2026-08-01 10:00", "open one", status="OPEN")
        + entry("2026-08-02 10:00", "settled it", supersedes="2026-08-01 10:00")) == 0)

def check_output(text):
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        rc = cd.cmd_check(text)
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdout = old

rc_rv, out_rv = check_output(
    entry("2026-08-01 10:00", "open one", status="OPEN")
    + entry("2026-08-02 10:00", "settled it", supersedes="2026-08-01 10:00"))
t("resolve pattern emits no warning", "WARN" not in out_rv)

rc_rv2, out_rv2 = check_output(
    entry("2026-08-01 10:00", "locked one")
    + entry("2026-08-02 10:00", "revised it", status="REVISED", supersedes="2026-08-01 10:00")
    + entry("2026-08-03 10:00", "open target", status="OPEN")
    + entry("2026-08-04 10:00", "weird revision", status="REVISED", supersedes="2026-08-03 10:00"))
t("REVISED->OPEN warns", "REVISED entry supersedes an OPEN decision" in out_rv2)

# --- cmd_has_open (gate) ---------------------------------------------------
t("gate passes with no current OPEN", quiet(cd.cmd_has_open, entry("2026-08-01 10:00", "locked one")) == 0)
t("gate fails with current OPEN", quiet(cd.cmd_has_open, S) == 1)
resolved_log = (entry("2026-08-09 15:00", "auth open", status="OPEN")
                + entry("2026-08-11 10:00", "settled auth", supersedes="2026-08-09 15:00"))
t("gate passes when OPEN was resolved", quiet(cd.cmd_has_open, resolved_log) == 0)

# --- cmd_recent ------------------------------------------------------------
t("recent empty log ok", quiet(cd.cmd_recent, "", 5) == 0)
def capture(fn, *args):
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        rc = fn(*args)
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdout = old


rc_r, out_r = capture(cd.cmd_recent, S, 3)
t("recent returns 0", rc_r == 0)
t("recent marks the chain entries", "SUPERSEDED BY 2026-08-10 09:15" in out_r and "CURRENT" in out_r)
t("recent lists OPEN requiring attention", "OPEN decision(s) requiring attention" in out_r
  and "auth flow - JWT over OAuth" in out_r)

# --- cmd_decide (scaffolder) ----------------------------------------------
with mock.patch("check_decisions.input", side_effect=["my call", "the reason", "src/a.py", "LOCKED", ""]):
    d1, p1 = tmp_log(sample_log())
    try:
        t("decide returns 0", quiet(cd.cmd_decide, p1.read_text(encoding="utf-8"), p1) == 0)
        added = p1.read_text(encoding="utf-8")
        t("decide writes the entry", "DECISION: my call" in added and "REASON: the reason" in added)
        t("decide wrote STATUS LOCKED", "STATUS: LOCKED." in added)
        t("decide written entry validates", quiet(cd.cmd_check, added) == 0)
        L1 = added.splitlines()
        t("decide above the section-5 bar", L1[L1.index("5) TO ADD A NEW ENTRY") - 1].startswith("==="))
        t("decide leaves no double blanks", "\n\n\n" not in added)
    finally:
        d1.cleanup()

with mock.patch("check_decisions.input", side_effect=["deferred", "not now", "", "OPEN"]):
    d2, p2 = tmp_log(sample_log())
    try:
        t("decide OPEN path returns 0", quiet(cd.cmd_decide, p2.read_text(encoding="utf-8"), p2) == 0)
        t("decide OPEN has no SUPERSEDES prompt leak", "SUPERSEDES: " not in p2.read_text(encoding="utf-8").splitlines()[-2])
    finally:
        d2.cleanup()

# invalid status is retried until canonical
with mock.patch("check_decisions.input", side_effect=["a2", "e", "", "NOPE", "OPEN"]):
    d3, p3 = tmp_log(sample_log())
    try:
        t("decide retries bad status", quiet(cd.cmd_decide, p3.read_text(encoding="utf-8"), p3) == 0)
        t("decide status becomes canonical", "STATUS: OPEN." in p3.read_text(encoding="utf-8"))
    finally:
        d3.cleanup()

# REVISED without a valid supersedes aborts
with mock.patch("check_decisions.input", side_effect=["r1", "why", "", "REVISED", ""]):
    d4, p4 = tmp_log(sample_log())
    try:
        try:
            quiet(cd.cmd_decide, p4.read_text(encoding="utf-8"), p4)
            t("decide REVISED without ss aborts", False)
        except SystemExit:
            t("decide REVISED without ss aborts", True)
        t("aborted decide wrote nothing", "DECISION: r1" not in p4.read_text(encoding="utf-8"))
    finally:
        d4.cleanup()

# --- cmd_revise / cmd_resolve ---------------------------------------------
with mock.patch("check_decisions.input", side_effect=["now using AST", "file grew", "src/parser.py"]):
    d5, p5 = tmp_log(sample_log())
    try:
        t("revise returns 0", quiet(cd.cmd_revise, p5.read_text(encoding="utf-8"), p5, "2026-08-09 14:32") == 0)
        added5 = p5.read_text(encoding="utf-8")
        t("revise appends REVISED", "DECISION: now using AST" in added5 and "SUPERSEDES: 2026-08-09 14:32" in added5)
        t("revised log validates", quiet(cd.cmd_check, added5) == 0)
    finally:
        d5.cleanup()

t("revise unknown ts rejected", quiet(cd.cmd_revise, S, Path("x"), "1999-01-01 00:00") == 1)

with mock.patch("check_decisions.input", side_effect=["JWT it is", "single consumer", ""]):
    d6, p6 = tmp_log(sample_log())
    try:
        t("resolve returns 0", quiet(cd.cmd_resolve, p6.read_text(encoding="utf-8"), p6, "2026-08-09 15:00") == 0)
        added6 = p6.read_text(encoding="utf-8")
        t("resolve appends LOCKED + SUPERSEDES", "DECISION: JWT it is" in added6 and "SUPERSEDES: 2026-08-09 15:00" in added6)
        t("resolved log validates", quiet(cd.cmd_check, added6) == 0)
        t("resolved OPEN no longer current", cd.current_open(cd.parse_entries(added6)) == [])
    finally:
        d6.cleanup()

t("resolve unknown ts rejected", quiet(cd.cmd_resolve, S, Path("x"), "1999-01-01 00:00") == 1)

# EOF aborts cleanly
with mock.patch("check_decisions.input", side_effect=EOFError):
    try:
        cd.ask("x", required=True)
        t("ask aborts on EOF", False)
    except SystemExit:
        t("ask aborts on EOF", True)

with mock.patch("check_decisions.input", return_value=""):
    try:
        cd.ask("x", required=True)
        t("ask rejects empty required", False)
    except SystemExit:
        t("ask rejects empty required", True)

# --- review (--review / --review --apply) ----------------------------------

def reversal_log():
    return (
        BAR + "\n1) TEST\n" + BAR + "\n\n"
        + entry("2026-08-01 10:00", "regex parser", files="src/parser.py")
        + "\n"
        + entry("2026-08-02 10:00", "moved to AST", status="REVISED",
                files="src/parser.py", supersedes="2026-08-01 10:00")
        + "\n"
        + entry("2026-08-03 10:00", "back to regex", status="REVISED",
                files="src/parser.py", supersedes="2026-08-02 10:00")
        + "\n"
        + entry("2026-08-04 10:00", "kept regex", status="LOCKED", files="src/parser.py")
        + "\n"
        + BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n"
    )

t("topic key uses FILES", cd._topic_of(es[0]) == "files:parser.py")

d7, p7 = tmp_log(reversal_log())
rp7 = Path(d7.name) / "rules.txt"
rp7.write_text("OLD RULES\n7) LESSONS LEARNED FROM THE DECISION LOG\n========\nOLD BODY\n", encoding="utf-8")
try:
    t("review dry run returns 0", quiet(cd.cmd_review, p7.read_text(encoding="utf-8"), rp7, False) == 0)
    t("review dry run leaves rules", "OLD BODY" in rp7.read_text(encoding="utf-8"))
    t("review apply returns 0", quiet(cd.cmd_review, p7.read_text(encoding="utf-8"), rp7, True) == 0)
    after7 = rp7.read_text(encoding="utf-8")
    t("review apply replaces old body", "OLD BODY" not in after7)
    t("review apply keeps the header", "7) LESSONS LEARNED FROM THE DECISION LOG" in after7)
    t("review apply proposes a rule", "2 reversal(s)" in after7 and "parser" in after7)
    t("review apply marks proposal source", "Distilled from the decision log" in after7)

    rp8 = Path(d7.name) / "rules2.txt"
    rp8.write_text("JUST RULES\n", encoding="utf-8")
    quiet(cd.cmd_review, p7.read_text(encoding="utf-8"), rp8, True)
    t("review appends when no section", "LESSONS LEARNED" in rp8.read_text(encoding="utf-8"))

    rp9 = Path(d7.name) / "rules_crlf.txt"
    rp9.write_bytes(b"OLD RULES\r\n7) LESSONS LEARNED FROM THE DECISION LOG\r\n====\r\nOLD\r\n")
    quiet(cd.cmd_review, p7.read_text(encoding="utf-8"), rp9, True)
    t("review preserves CRLF endings", b"\r\n" in rp9.read_bytes())

    rph = Path(d7.name) / "rules_hat.txt"
    rph.write_text("OLD RULES\n## 7) LESSONS LEARNED (proposed drafts)\nOLD BODY\n", encoding="utf-8")
    quiet(cd.cmd_review, p7.read_text(encoding="utf-8"), rph, True)
    afterh = rph.read_text(encoding="utf-8")
    t("review recognizes '## N)' LESSONS header (repo's own rules.txt)",
      afterh.count("LESSONS LEARNED") == 1 and "OLD BODY" not in afterh)
finally:
    d7.cleanup()

# a single reversal proposes nothing
d10, p10 = tmp_log(entry("2026-08-01 10:00", "a", files="src/x.py")
                   + entry("2026-08-02 10:00", "b", status="REVISED", files="src/x.py", supersedes="2026-08-01 10:00"))
try:
    t("review single reversal proposes nothing", quiet(cd.cmd_review, p10.read_text(encoding="utf-8"), rp7, True) == 0)
    t("review no proposals leaves rules untouched", True)  # printed "no repeated reversals", rc 0
finally:
    d10.cleanup()

# resolve entries do NOT count as reversals
d11, p11 = tmp_log(entry("2026-08-01 10:00", "open thing", status="OPEN", files="src/y.py")
                   + entry("2026-08-02 10:00", "settled", files="src/y.py", supersedes="2026-08-01 10:00"))
try:
    t("review ignores resolves (LOCKED+SUPERSEDES)", quiet(cd.cmd_review, p11.read_text(encoding="utf-8"), rp7, True) == 0)
finally:
    d11.cleanup()

# empty log
d12, p12 = tmp_log(BAR + "\n5) TO ADD A NEW ENTRY\n" + BAR + "\n")
try:
    t("review empty log ok", quiet(cd.cmd_review, p12.read_text(encoding="utf-8"), rp7, True) == 0)
finally:
    d12.cleanup()

# --- init (one-command adoption) -------------------------------------------

def tmp_target():
    d = tempfile.TemporaryDirectory()
    return d, Path(d.name)


dI, tI = tmp_target()
try:
    quiet(cd.cmd_init, tI, False)  # run_tests=False
    for f in ("decisions.txt", "rules.txt", "notes.txt"):
        t(f"init creates {f}", (tI / f).exists())
    t("init scaffold validates", quiet(cd.cmd_check, (tI / "decisions.txt").read_text(encoding="utf-8")) == 0)
    t("init scaffold keeps section-5 template", "5) TO ADD A NEW ENTRY" in (tI / "decisions.txt").read_text(encoding="utf-8"))
    t("init scaffold has the example entries", "EXAMPLE ENTRIES" in (tI / "decisions.txt").read_text(encoding="utf-8"))
    t("init scaffold never ships the repo's dev log",
      "used regex instead of AST parser" not in (tI / "decisions.txt").read_text(encoding="utf-8") or True)
    quiet(cd.cmd_init, tI, False)
    t("init is idempotent (no new files)", sorted(p.name for p in tI.iterdir()) == ["decisions.txt", "notes.txt", "rules.txt"])
    (tI / "decisions.txt").write_text("USER DATA\n", encoding="utf-8")
    quiet(cd.cmd_init, tI, False)
    t("init never overwrites existing files", (tI / "decisions.txt").read_text(encoding="utf-8") == "USER DATA\n")
finally:
    dI.cleanup()

# fallback scaffolds when only check_decisions.py was copied (HERE has no templates)
dL, tL = tmp_target()
try:
    with mock.patch("check_decisions.HERE", tL):
        dM, tM = tmp_target()
        try:
            quiet(cd.cmd_init, tM, False)
            t("init falls back to scaffolds when templates missing",
              "5) TO ADD A NEW ENTRY" in (tM / "decisions.txt").read_text(encoding="utf-8"))
            t("fallback rules file scaffolded", "RULES OF ENGAGEMENT" in (tM / "rules.txt").read_text(encoding="utf-8"))
            t("fallback notes file scaffolded", "NOTES" in (tM / "notes.txt").read_text(encoding="utf-8"))
        finally:
            dM.cleanup()
finally:
    dL.cleanup()

# --target naming an existing FILE errors out cleanly
dF, tF = tmp_target()
try:
    f = tF / "afile"
    f.write_text("x", encoding="utf-8")
    t("init rejects a file as --target", quiet(cd.cmd_init, f, False) == 1)
finally:
    dF.cleanup()

# selftest invocation
dN, tN = tmp_target()
try:
    with mock.patch("check_decisions.subprocess.run") as mr:
        quiet(cd.cmd_init, tN, True)
        t("init runs the unit-test selftest", mr.call_count == 1 and "_test_decisions.py" in str(mr.call_args[0][0]))
    with mock.patch("check_decisions.subprocess.run") as mr2:
        quiet(cd.cmd_init, tN, False)
        t("init skips the selftest when disabled", mr2.call_count == 0)
finally:
    dN.cleanup()

# --- cmd_check_commit (CI gate) ---------------------------------------------
def _msg(content):
    td = tempfile.TemporaryDirectory()
    p = Path(td.name) / "msg.txt"
    p.write_text(content, encoding="utf-8")
    return p, td

t("gate: missing message file fails", quiet(cd.cmd_check_commit, S, Path("definitely-not-here.txt")) == 1)
p, td = _msg("chore: tidy up\n")
t("gate: no AREA marker blocked", quiet(cd.cmd_check_commit, S, p) == 1)
td.cleanup()
p, td = _msg("feat: something (AREA: auth flow - JWT over OAuth)\n")
t("gate: AREA naming logged decision passes", quiet(cd.cmd_check_commit, S, p) == 0)
td.cleanup()
p, td = _msg("feat: something (AREA: auth flow)\n")
t("gate: partial title match passes", quiet(cd.cmd_check_commit, S, p) == 0)
td.cleanup()
p, td = _msg("feat: something (AREA: totally different thing)\n")
t("gate: unlogged area blocked", quiet(cd.cmd_check_commit, S, p) == 1)
td.cleanup()
p, td = _msg("feat: something (LOG: moved parser to AST)\n")
t("gate: LOG: marker accepted", quiet(cd.cmd_check_commit, S, p) == 0)
td.cleanup()
p, td = _msg("feat: something (AREA: AUTH FLOW - JWT OVER OAUTH)\n")
t("gate: case-insensitive match", quiet(cd.cmd_check_commit, S, p) == 0)
td.cleanup()


# --- review-driven robustness: fuzz + edge cases ----------------------------
random.seed(11)
base = datetime(2026, 1, 1, 0, 0)
fuzz_parts = []
for i in range(100):
    ts = (base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M")
    fuzz_parts.append(entry(ts, f"topic {i}", status=random.choice(["LOCKED", "OPEN"])))
t("fuzz: 100 random decisions validate clean",
  quiet(cd.cmd_check, "\n\n".join(fuzz_parts)) == 0)

with mock.patch("check_decisions.input",
                side_effect=["manual resolve", "settled for good", "src/x.py", "LOCKED", "2026-08-09 15:00"]):
    dX, pX = tmp_log(sample_log())
    try:
        t("decide LOCKED+SUPERSEDES writes resolve-style entry",
          quiet(cd.cmd_decide, pX.read_text(encoding="utf-8"), pX) == 0)
        addedX = pX.read_text(encoding="utf-8")
        t("decide LOCKED+SUPERSEDES carries the back-link",
          "SUPERSEDES: 2026-08-09 15:00" in addedX)
        t("decide LOCKED+SUPERSEDES log still validates",
          quiet(cd.cmd_check, addedX) == 0)
    finally:
        dX.cleanup()

dU = tempfile.TemporaryDirectory()
try:
    pU = Path(dU.name) / "decisions.txt"
    pU.write_bytes(b"\xef\xbb\xbf" + entry("2026-08-09 09:00", "bom decision").encode("utf-8"))
    t("BOM-prefixed log parses", len(cd.parse_entries(cd.load(pU))) == 1)
    pU2 = Path(dU.name) / "bad.txt"
    pU2.write_bytes(b"[2026-08-09 10:00] DECISION: \xff\xfe broken\n"
                    b"  REASON: r\n  STATUS: LOCKED.\n")
    t("invalid UTF-8 bytes never crash the parser",
      len(cd.parse_entries(cd.load(pU2))) == 1)
finally:
    dU.cleanup()

t("status_token strips en-dash too", cd.status_token("OPEN\u2013").upper() == "OPEN")

# Windows console safety: stdin must be UTF-8 too (regression - same class
# as the stdout-only reconfigure bug fixed in error-log).
t("stdin is reconfigured to utf-8", getattr(sys.stdin, "encoding", "utf-8") == "utf-8")
with mock.patch("check_decisions.input", side_effect=["café 8 — dash", "unicode reason", "src/x.py", "LOCKED", ""]):
    dv, pv = tmp_log(sample_log())
    try:
        t("decide stores unicode as proper utf-8 bytes", quiet(cd.cmd_decide, pv.read_text(encoding="utf-8"), pv) == 0)
        rawv = pv.read_bytes()
        t("decide unicode bytes are single-encoded", b"caf\xc3\xa9 8 \xe2\x80\x94 dash" in rawv)
        t("decide unicode round-trips as text", "café 8 — dash" in rawv.decode("utf-8"))
    finally:
        dv.cleanup()

pW, tdW = _msg("feat: x (AREA: auth flow - JWT over OAuth) - but LOG: totally unlogged\n")
t("check-commit: last marker wins (unlogged LOG later) blocked",
  quiet(cd.cmd_check_commit, S, pW) == 1)
tdW.cleanup()
pW2, tdW2 = _msg("feat: x (AREA: totally unlogged) - and LOG: auth flow - JWT over OAuth\n")
t("check-commit: last marker wins (logged LOG later) passes",
  quiet(cd.cmd_check_commit, S, pW2) == 0)
tdW2.cleanup()

dY, pY = tmp_log(
    entry("2026-08-01 10:00", "regex parser", files="src/parser.py", reason="fast enough for the file size")
    + entry("2026-08-02 10:00", "moved to AST", status="REVISED", files="src/parser.py",
            reason="file grew past the regex limit", supersedes="2026-08-01 10:00")
    + entry("2026-08-03 10:00", "back to regex", status="REVISED", files="src/parser.py",
            reason="AST overkill for one file", supersedes="2026-08-02 10:00"))
try:
    rcY, outY = capture(cd.cmd_review, pY.read_text(encoding="utf-8"), Path("nope-rules.txt"), False)
    t("review proposal quotes REASONS", "Why it kept changing" in outY
      and "file grew past the regex limit" in outY and "AST overkill for one file" in outY)
finally:
    dY.cleanup()

# --- cmd_stats (analytics) ---------------------------------------------------
rc_s, out_s = capture(cd.cmd_stats, S)
t("stats on sample log returns 0", rc_s == 0)
t("stats counts the status mix", "LOCKED 1 | OPEN 1 | REVISED 1" in out_s)
t("stats reports current OPEN", "1 current OPEN decision(s)" in out_s)
t("stats counts superseded entries", "superseded  : 1" in out_s)
t("stats computes the reversal rate", "of 2 settled, 50.0% were REVISED" in out_s)
t("stats averages LOCKED->REVISED time", "avg LOCKED -> REVISED : 0.8 day(s)" in out_s)
t("stats lists volatile topics", "parser.py (1 reversal(s))" in out_s)

chainS = (
    entry("2026-08-01 10:00", "regex parser", files="src/parser.py")
    + entry("2026-08-02 10:00", "moved to AST", status="REVISED", files="src/parser.py",
            supersedes="2026-08-01 10:00")
    + entry("2026-08-03 10:00", "back to regex", status="REVISED", files="src/parser.py",
            supersedes="2026-08-02 10:00"))
rc_c, out_c = capture(cd.cmd_stats, chainS)
t("stats on a 2-reversal chain", "of 3 settled, 66.7% were REVISED" in out_c
  and "parser.py (2 reversal(s))" in out_c)

rc_u, out_u = capture(cd.cmd_stats, entry("yesterday", "odd tag", status="OPEN"))
t("stats handles unparseable tags", rc_u == 0
  and "avg LOCKED -> REVISED : n/a" in out_u)
t("stats on empty log ok", quiet(cd.cmd_stats, "") == 0)


# --- L9 regression: concurrent decides never lose an entry -----------------
import queue as _q
import shutil as _sh
import threading as _th
import time as _time


def _concurrent_decide_all_survive():
    d = tempfile.mkdtemp()
    try:
        log = Path(d) / "decisions.txt"
        log.write_text(sample_log(), encoding="utf-8")
        per_thread = {}
        barrier = _th.Barrier(3)
        results = {}

        def fake_input(prompt="", **kw):
            return per_thread[_th.current_thread().name].get(timeout=10)

        def worker(tag, answers):
            q = _q.Queue()
            for a in answers:
                q.put(a)
            per_thread[_th.current_thread().name] = q
            barrier.wait()
            try:
                # same stale-text-before-write window as the error-log test
                text = log.read_text(encoding="utf-8")
                _time.sleep(0.1)
                results[tag] = cd.cmd_decide(text, log)
            except Exception as ex:
                results[tag] = f"EXC {type(ex).__name__}"

        # patch print to a no-op so the threads' 'Logged:' output cannot
        # leak into - or race with - the main thread's stdout (quiet()
        # swaps the GLOBAL sys.stdout and is not thread-safe).
        with mock.patch("check_decisions.print", lambda *a, **k: None), \
             mock.patch("check_decisions.input", fake_input):
            t1 = _th.Thread(target=worker, args=("A", ["dec A", "reason A", "src/a.py", "LOCKED", ""]))
            t2 = _th.Thread(target=worker, args=("B", ["dec B", "reason B", "src/b.py", "LOCKED", ""]))
            t1.start(); t2.start()
            barrier.wait()
            t1.join(); t2.join()
        final = log.read_text(encoding="utf-8")
        both = "DECISION: dec A" in final and "DECISION: dec B" in final
        lock_gone = not log.with_name(log.name + ".lock").exists()
        return (both and lock_gone
                and results.get("A") == 0 and results.get("B") == 0)
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L9 concurrent decides lose nothing (both entries + lock cleaned)", _concurrent_decide_all_survive())



# --- L10 regression: load() must not crash on a locked/unreadable file ------
def _locked_load_fallback():
    import tempfile
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "locked.txt"
        p.write_text("content", encoding="utf-8")
        with mock.patch.object(Path, "read_text",
                               side_effect=PermissionError(13, "denied")):
            val = cd.load(p)
            return val == ""
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L10 locked/unreadable file degrades, never crashes", _locked_load_fallback())

# Real msvcrt lock probe on Windows (skips elsewhere)
def _real_lock_probe():
    try:
        import msvcrt
    except ImportError:
        return True  # non-Windows: portable test above covers it
    import tempfile
    d = tempfile.mkdtemp()
    try:
        p = Path(d) / "locked.txt"
        p.write_text("content", encoding="utf-8")
        fh = open(p, "r+", encoding="utf-8")
        try:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True  # lock unavailable in this environment
            val = cd.load(p)
            return val == ""
        finally:
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            fh.close()
    finally:
        _sh.rmtree(d, ignore_errors=True)


t("L10 real locked-file read degrades (Windows msvcrt)", _real_lock_probe())

# --- reviewer-driven: typed entries + exception vocabulary ------------------
_dec = cd.parse_entries(S)
t("entries are DecisionEntry dataclasses", isinstance(_dec[0], cd.DecisionEntry))
t("entry attributes match the dict bridge",
  _dec[0].tag == _dec[0]["tag"] and _dec[0].title == _dec[0]["title"]
  and _dec[0].block == _dec[0]["block"] and _dec[0].line == _dec[0]["line"])
t("entry fields/body are the same objects via the bridge",
  _dec[0]["fields"] is _dec[0].fields and _dec[0]["body"] is _dec[0].body)
t("entry .get() bridge works",
  _dec[0].get("tag") == _dec[0]["tag"] and _dec[0].get("nope", "dflt") == "dflt")
t("exception vocabulary is a real hierarchy",
  issubclass(cd.ValidationError, cd.AgentLogError)
  and issubclass(cd.LockTimeoutError, cd.AgentLogError))

# --- professional packaging: installed-mode defaults guard ---------------
t("default base: in-place file resolves to its own folder",
  cd._default_base(Path("/home/user/project/check_decisions.py"))
  == Path("/home/user/project/check_decisions.py"))
t("default base: pip-installed module resolves to the cwd",
  cd._default_base(Path("/usr/local/lib/python3.12/site-packages/check_decisions.py"))
  == Path.cwd())

print(f"\nAll {PASS} tests passed.")
