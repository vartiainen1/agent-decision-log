# agent-decision-log

Your agent's decisions survive the session.

A tiny, dependency-free system for anyone who works with AI coding assistants
or builds their own agent loops. `decisions.txt` records what your agent
CHOSE and WHY - so the next session starts from *"we already decided X"*
[agent-error-log](https://github.com/vartiainen1/agent-error-log) (which
records what broke); together they give an agent a memory for both its
mistakes and its choices.

[![CI](https://github.com/vartiainen1/agent-decision-log/actions/workflows/ci.yml/badge.svg)](https://github.com/vartiainen1/agent-decision-log/actions/workflows/ci.yml)
[![checks on master](https://img.shields.io/github/checks-status/vartiainen1/agent-decision-log/master)](https://github.com/vartiainen1/agent-decision-log/actions)
[![release](https://img.shields.io/github/v/release/vartiainen1/agent-decision-log)](https://github.com/vartiainen1/agent-decision-log/releases)
[![license](https://img.shields.io/github/license/vartiainen1/agent-decision-log)](https://github.com/vartiainen1/agent-decision-log/blob/master/LICENSE)
[![python](https://img.shields.io/badge/python-3.9%20%7C%203.11%20%7C%203.12-3776AB)](https://github.com/vartiainen1/agent-decision-log/actions)
[![dependencies-0](https://img.shields.io/badge/dependencies-0-brightgreen)](https://github.com/vartiainen1/agent-decision-log)
[![Visitors](https://visitor-badge.laobi.icu/badge?page_id=vartiainen1.agent-decision-log&left_text=Visitors&right_color=2F80ED)](https://github.com/vartiainen1/agent-decision-log)
[![companion-error](https://img.shields.io/badge/companion-agent--error--log-2ea44f)](https://github.com/vartiainen1/agent-error-log)
[![companion-log-ai](https://img.shields.io/badge/companion-agent--log--ai-2ea44f)](https://github.com/vartiainen1/agent-log-ai)
[![companion-diff-gate](https://img.shields.io/badge/companion-agent--diff--gate-2ea44f)](https://github.com/vartiainen1/agent-diff-gate)

## Why this exists

An agent repeats bad decisions far more often than it repeats crashes. A bug
has a stack trace - it forces itself to be noticed. A bad decision is
invisible: *"I used regex instead of an AST parser"* works, nothing flags it,
and the next session re-makes the same choice in the dark.

The pain is at **session start**: a new chat has no context, so it re-asks
questions the last session already answered and re-explores tradeoffs the
last session already settled. This log fixes recall at boot time.

## Quick start

```bash
# 1. One-command adoption (scaffolds decisions.txt / rules.txt / notes.txt)
python check_decisions.py --init

# 2. Start each session with boot-time recall
python start.py            # or double-click start.bat (Windows)

# 3. Log decisions at forks in the road
python check_decisions.py --decide

# 4. Validate the log
python check_decisions.py
```

## What a decision looks like

```text
[2026-08-09 14:32] DECISION: used regex instead of AST parser
  REASON: faster for the simple case, file was small
  FILES: src/parser.py
  STATUS: LOCKED
```

Three states, one mental model:

| STATUS  | Meaning                            | SUPERSEDES?                |
|---------|------------------------------------|----------------------------|
| LOCKED  | the decision stands                | optional (resolving OPEN)  |
| OPEN    | deferred; needs a call next session| no                         |
| REVISED | changed your mind (append-only)    | required - points back     |

History is never rewritten. A correction is a new entry pointing back:

```text
[2026-08-10 09:15] DECISION: moved parser to AST
  REASON: file grew past 200 lines; regex became unmaintainable
  FILES: src/parser.py
  SUPERSEDES: 2026-08-09 14:32
  STATUS: REVISED
```

## The fork rule (when to log)

> Log a decision when reversing it would cost time, or when you actively
> considered an alternative and picked one.

That's the whole rule. `start.py` enforces it by *embarrassment*: it shows
the last session's decisions at boot, so picking a different path now without
a REVISED entry is visibly inconsistent - not blocked, just accountable.

## Tooling reference

| Command | What it does |
|---|---|
| `python check_decisions.py` | validate the log (exit 0 = healthy) |
| `--decide` | scaffold a new decision (interactive; LOCKED + SUPERSEDES is the manual form of `--resolve`) |
| `--revise <ts>` | change a decision: append REVISED superseding `ts` |
| `--resolve <ts>` | settle an OPEN decision: append LOCKED superseding `ts` |
| `--has-open` | gate: exit 1 if any OPEN decision is still current |
| `--recent [N]` | show the last N decisions with currency |
| `--stats` | show analytics: status mix, reversal rate, volatility |
| `--review` | distill repeated reversals into proposed rule drafts |
| `--review --apply` | write the proposals into rules.txt §7 (LESSONS) |
| `--init [--target DIR]` | one-command adoption + health check + self-test |
| `--check-commit FILE` | gate: exit 0 only if the commit message in FILE names a logged decision |

## How the currency rule works

An entry is **current** unless a *newer* entry's `SUPERSEDES` points at it.
Append-only means that check is deterministic and free: a LOCKED decision
whose timestamp appears in a later entry's `SUPERSEDES` is shown as
`SUPERSEDED BY <ts>` at boot. Resolving an OPEN decision uses the same move -
append a LOCKED entry with `SUPERSEDES` - so three states need exactly one
append rule.

## The compounding loop

`--review` looks for decisions that were LOCKED and then changed (reversals).
Two or more reversals on the same topic produce a **proposed** rule:

```text
Proposal: default to the most recent decision on <topic> unless the
context genuinely changed; when it does, log a REVISED entry that says why.
```

`--review --apply` writes proposals into `rules.txt` §7 (LESSONS) as drafts.
A human confirms them. Failures teach rules (agent-error-log `--lessons`);
decisions teach rules (this `--review`) - both feed the same permanent memory.

Each proposal also quotes the REASON behind every reversal, so the draft
shows *why* the decision kept changing - not just that it did.

Grouping is by heuristic, not taxonomy: the first `FILES` basename when a
decision names files, else the first three words of its title. Two entries
on the same basename in different folders merge into one topic - fine for
spotting volatility, not a perfect classification.

## FAQ

**Why not just use a NOTES.md?** A notes file is where decisions go to be
forgotten - nothing parses it, nothing gates on it, nothing surfaces it at
boot. This log is a structured, validated, append-only record that `start.py`
reads and `check_decisions.py` keeps honest.

**Isn't this just ADRs (Architecture Decision Records)?** It's the same
instinct applied to *agent sessions*: ADRs have no boot-time recall, no
currency rule, and no compounding loop that turns repeated reversals into
rules. The format is the easy part; recall is the product.

**Why soft enforcement?** A bug without a log entry is clearly wrong; a
decision without a log entry is usually *correct* - most choices are trivial.
So there is no local git hook (unlike the sibling repo); the mechanical
backstop is the CI commit-message gate on `master` merges, and the
accountability loop is boot-time recall: the agent's own history is shown
back at session start.

**Does it work with any agent?** Yes - any agent that can read text and run
shell commands. Point it at the repo in AGENTS.md, or paste rules.txt into a
system prompt.
**I copied the tool to a scratch folder — will it touch my real repo?** No.
Default paths resolve relative to the script location (`HERE`), so a scratch
copy logs next to itself. Point at your real log from anywhere with
`--log path/to/decisions.txt`.
**Can I log unicode (café, em-dash) on Windows?** Yes — `stdin` is
reconfigured to UTF-8 like `stdout`, so piped unicode decision text is
stored as-is, never double-encoded.

## Development

```bash
python _test_decisions.py          # run the unit tests (139, 100% pass expected)
python check_decisions.py          # validate the log
python -m py_compile check_decisions.py start.py
```

CI runs tests + linter on Ubuntu and Windows across Python 3.9 / 3.11 / 3.12.
Releases are cut from CHANGELOG.md by a workflow that creates the tag and a
draft GitHub Release - see `CHANGELOG.md` and the workflow in
`.github/workflows/release.yml`.

### Shipping a change (PR workflow)

With branch protection live, **direct pushes to `master` are rejected** -
`GH006: Protected branch update failed ... N of N required status checks are
expected` - because a fresh commit has no CI checks yet. Every change lands
via pull request:

1. **Branch off `master`** and commit with the `(AREA: <logged decision>)`
   marker in the message (matching a decision in `decisions.txt`):
   `git commit -m "feat: ... (AREA: add a --stats analytics command)"`.
2. **Push the branch, open a PR** against `master`. The six
   `tests + linter` matrix jobs run on the PR head.
3. **Squash-merge** once checks are green, keeping the `(AREA: ...)` marker in
   the squash title. The merge push re-runs CI **and the commit-message
   gate** on `master` - a missing marker leaves the gate red.

This repo ships no local commit-msg hook (deliberate: most decisions are
trivial, so boot-time recall is the discipline). The CI gate is the
mechanical backstop for the marker - which is why it must survive into the
squash title. The gate job skips PR events on purpose: PRs are gated when
the merge lands, so the squash title is exactly what gets re-checked on
`master`.

## Security

- The decision log may contain sensitive context (architecture details,
  tradeoff analysis). **Never log credentials or secrets** — keep the repo
  private if in doubt.
- Stdlib only; default paths resolve next to the script, so a scratch copy
  never touches your real log.
- To report a vulnerability, use the private advisory path in
  [`SECURITY.md`](SECURITY.md) — never a public issue.

## Companion tools

The agent-memory family — same shape, same lifecycle verbs, four layers:

| Repo | What it remembers | How it works |
|---|---|---|
| [agent-error-log](https://github.com/vartiainen1/agent-error-log) | what BROKE | text log + linter + git gate |
| **agent-decision-log (this)** | what was CHOSEN and why | append-only decisions + currency chain |
| [agent-log-ai](https://github.com/vartiainen1/agent-log-ai) | *why* it kept happening | heuristics select → LLM reasons |
| [agent-diff-gate](https://github.com/vartiainen1/agent-diff-gate) | what must never be COMMITTED | pre-commit diff scan + gate |

Same shape, same lifecycle verbs across all four layers: agent-error-log
prevents repeating failures, this one prevents repeating exploration,
agent-log-ai explains why both keep happening, and agent-diff-gate catches
the results before they land.

## Installing with pip (optional)

The single-file adoption story is unchanged - copy `check_decisions.py` into
your project and you are done. The tool is *also* pip-installable with zero
runtime dependencies:

```sh
pip install agent-decision-log
decision-log --help
```

- The package version is derived from the git tag (setuptools-scm), which the
  release workflow creates from CHANGELOG.md - there is no version to drift.
- Run from the installed package, default paths (`decisions.txt`, `rules.txt`)
  resolve against your current directory; an in-place copy keeps resolving
  against the file's folder.
- `--init` works identically from an installed copy (built-in templates).


## Dogfood ledger

This repo is reviewed by its own family gate — **agent-diff-gate**, a
pre-commit diff analyzer that flags risky patterns in added code. The
ledger below is the gate's output over this repo's entire history
(initial commit → `HEAD`), recorded so the tool's claims are backed by
its own findings.

The gate numbers its rules R1–R14 (`python check_diff.py --list-rules`
prints the full list). The classes that appear in this repo's history:

- **R2** — silent failure: an exception swallowed without a trace
- **R4** — duplicate logic: near-identical lines added in the same diff


| | |
|---|---|
| Commits scanned | 39 (~1,900 diff lines) |
| Findings | **12** — 5 HIGH · 7 MEDIUM |
| Classes | R2 ×5 (HIGH) · R4 ×7 (MEDIUM) |
| Suppressed | **none** — every finding is fixed, tracked in `decisions.txt`, or documented here |

- **R2 (HIGH)** — best-effort lock-cleanup swallows in `check_decisions.py`
  (stale lock-file unlink). Deliberate by intent — cleanup failure is
  non-fatal — and documented here as the accepted class.
- **R4 (MEDIUM)** — the documented test-fixture duplication class.

Reproduce from this repo:

```sh
git diff $(git rev-list --max-parents=0 HEAD) HEAD \
  | python <path-to>/agent-diff-gate/check_diff.py --stdin --json
```

## License

MIT - see [LICENSE](LICENSE).
