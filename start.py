"""start.py — Agent session bootstrap: boot-time decision recall.

Run at the start of every working session to start from the last session's
state instead of re-exploring it:
    python start.py          (Windows: double-click start.bat)

Prints, from the folder holding this script:
  0. a decision-log health check (runs check_decisions.py),
  1. the reading order (rules -> decisions -> notes),
  2. the FORK RULE (when to log a decision),
  3. the last few decisions with their currency (CURRENT / SUPERSEDED),
  4. OPEN decisions that still need a call this session,
  5. the latest session note from the notes file.

Stdlib only.
"""

import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import check_decisions  # sibling tool: validates the decision log
except ImportError:
    check_decisions = None

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- CONFIG: point these at your own files ---------------------------------
# Rename the example files and set the names here. All files are read from
# the folder that contains this script.
HERE = Path(__file__).resolve().parent
RULES_FILE = "rules.txt"       # the RULES file (how the agent should behave)
DECISIONS_FILE = "decisions.txt"  # the DECISION LOG (must match check_decisions.py's)
NOTES_FILE = "notes.txt"       # the NOTES file (general text + session notes)
# --------------------------------------------------------------------------

BAR = "=" * 80
SUB = "-" * 80


def load(name):
    """Read a file from this folder, or None if it is missing."""
    p = HERE / name
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def last_session_note(text):
    """Return the most recent SESSION NOTE block (and its date line)."""
    blocks = re.split(r"(?m)^(?=SESSION NOTE\s*\()", text)
    if len(blocks) < 2:
        return "(no session notes yet)"
    return "\n".join(l for l in blocks[-1].splitlines() if l.strip())


def main():
    decisions = load(DECISIONS_FILE)
    rules = load(RULES_FILE)
    notes = load(NOTES_FILE)

    print(BAR)
    print("AGENT SESSION BOOTSTRAP - DECISION RECALL")
    print(f"when       : {datetime.now():%Y-%m-%d %H:%M}")
    print(f"workspace  : {HERE}")
    print(BAR)

    print(f"\n{SUB}")
    print("STEP 0 - DECISION-LOG HEALTH CHECK (check_decisions.py):")
    log_path = HERE / DECISIONS_FILE
    if check_decisions is None:
        print("  (check_decisions.py not found - skipping health check)")
    elif not log_path.exists():
        print(f"  (missing file: {log_path})")
    else:
        rc = check_decisions.cmd_check(check_decisions.load(log_path))
        if rc == 0:
            print("  RESULT: log healthy - safe to code.")
        else:
            print("  RESULT: PROBLEMS FOUND - fix the log before coding")
            print("  (run: python check_decisions.py to see the details)")

    print("\nREADING ORDER (before doing anything):")
    print(f"  1. {RULES_FILE}     -> the RULES (how to behave)")
    print(f"  2. {DECISIONS_FILE} -> what was decided and why (don't re-explore)")
    print(f"  3. {NOTES_FILE}     -> notes + session context")
    print("\nTHE FORK RULE (when to log a decision):")
    print("  Log a decision when reversing it would cost time, or when you")
    print("  actively considered an alternative and picked one.")

    entries = check_decisions.parse_entries(decisions) if (decisions and check_decisions) else []
    print(f"\n{SUB}")
    print("LAST DECISIONS (3) - with currency:")
    if not entries:
        print("  (no decisions logged yet - run python check_decisions.py --decide")
        print("   at the first fork in the road)")
    else:
        for e in entries[-3:]:
            st = check_decisions.status_token(e["fields"].get("STATUS", "")).upper()
            ss = e["fields"].get("SUPERSEDES", "")
            sub = check_decisions.superseded_by(entries, e["tag"])
            state = f"SUPERSEDED BY {sub['tag']}" if sub else "CURRENT"
            chain = f" (supersedes {ss})" if ss else ""
            print(f"  [{e['tag']}] {st} - {state}{chain}: {e['title']}")

    print(f"\n{SUB}")
    print("OPEN DECISIONS REQUIRING ATTENTION:")
    open_ = check_decisions.current_open(entries) if entries else []
    if not open_:
        print("  (none - nothing is deferred; all calls are made)")
    else:
        for e in open_:
            print(f"  [{e['tag']}] {e['title']}")

    print(f"\n{SUB}")
    print(f"LATEST SESSION NOTE (from {NOTES_FILE}):")
    if notes is None:
        print(f"  (missing file: {HERE / NOTES_FILE})")
    else:
        for line in last_session_note(notes).splitlines():
            print(f"  {line}")

    print(f"\n{SUB}")
    print("Tips: log decisions at forks (python check_decisions.py --decide);")
    print("settle OPEN decisions early or say why they stay deferred; end")
    print(f"sessions with a dated SESSION NOTE (YYYY-MM-DD): TITLE in {NOTES_FILE}.")
    print("Run 'python check_decisions.py' to validate the log (--review")
    print("distills repeated reversals into proposed rules).")
    print(BAR)


if __name__ == "__main__":
    main()
