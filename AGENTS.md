# AGENTS.md - instructions for AI coding agents

This repo gives the agent a **decision log**: what was CHOSEN and WHY, so the
next session starts from "we already decided X" instead of re-exploring it.

## 1) Read first (in this order)

1. `rules.txt` - behavior rules (how to behave)
2. `decisions.txt` - decisions and their reasons (don't re-explore)
3. `notes.txt` - session notes and context

## 2) THE FORK RULE (when to log a decision)

> Log a decision when reversing it would cost time, or when you actively
> considered an alternative and picked one.

That is the whole rule. No checklist: "cost time" is judged in context, and
"actively considered an alternative" covers the classic tradeoffs (regex vs
AST, OAuth vs JWT, library vs hand-rolled). Log it:

    python check_decisions.py --decide

## 3) The discipline

- **Never repeat exploration.** If a decision is LOCKED, honor it unless the
  context genuinely changed - then log a REVISED entry, never edit the old one.
- **Never rewrite history.** The log is append-only. Corrections are new
  entries that point back with `SUPERSEDES: <timestamp>`.
- **Settle OPEN decisions** early in a session, or say explicitly why they
  stay deferred.
- **Run `python start.py` at session start** - it surfaces the last decisions
  and anything still OPEN. Start from that state.

## 4) Status lifecycle (exactly three states)

| STATUS   | Meaning                                  | SUPERSEDES?                    |
|----------|------------------------------------------|--------------------------------|
| LOCKED   | the decision stands                       | optional (resolving an OPEN)   |
| OPEN     | deferred; needs a call next session       | no                             |
| REVISED  | changed your mind (append-only)           | required - points back         |

## 5) The compounding loop

`python check_decisions.py --review` distills repeated reversals into
**proposed** additions to rules.txt section 7 (LESSONS). `--review --apply`
writes them as drafts. A human confirms them. Failures teach rules
(agent-error-log `--lessons`); decisions teach rules (this `--review`).

## 6) Companion tool

`agent-error-log` (errors.txt) records what BROKE - reactive memory. This log
records what was CHOSEN - proactive memory. Use both.

## 7) Committing (the AREA-marker gate)

Every commit or PR title must carry an `AREA: <text>` marker naming a
**logged decision**:

    git commit -m "feat: <thing> (AREA: <decision topic>)"

The CI workflow enforces this on master: a `commit-message gate` job re-runs
`python check_decisions.py --check-commit` on every pushed commit and fails
the push unless the marker names a decision already in `decisions.txt`. This
repo has no local commit hook — CI is the gate. Log the decision first
(`python check_decisions.py --decide`), then commit.
