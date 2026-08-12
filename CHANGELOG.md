# Changelog

All notable changes to this project are documented here. The version at the
top of this file is the single source of truth - releases are cut from it by
`.github/workflows/release.yml`.

## [Unreleased]

### Added
- `--stdin` non-interactive mode for `--decide`/`--revise`/`--resolve`: the
  answers (DECISION/REASON/FILES/STATUS[,SUPERSEDES]) are read from piped
  stdin, one per line, with no prompts; required fields and invalid input
  fail loudly with no partial entry; optional fields default as if Enter
  were pressed (family finding: interactive scaffolds abort on truncated
  piped stdin).
- `--version` flag prints the tool version and exits 0 (family finding #1
  closed - all four family tools now support it).

### Fixed
- CI commit-message gate now gates the authored PR tip (HEAD^2)
  on GitHub merge commits, so master stops showing a red X on
  `gh pr merge --merge` merges (family finding, all four repos)
- `--init` scaffold ships only LOCKED/REVISED example decisions, never an
  OPEN one, so a fresh adopter passes `--has-open` out of the box (family
  finding #4 closed).


## [0.5.0] - 2026-08-11

### Added
- Professional packaging: `pyproject.toml` (version derived from the git tag via
  setuptools-scm - no drift), a global `decision-log` console script, zero
  runtime dependencies.
- Installed-mode defaults guard (`_default_base`): pip-installed runs resolve
  default paths against the current directory; in-place copies keep resolving
  against the file's folder.
- CI `packaging` job: builds the wheel, installs it into a fresh venv, and
  smoke-tests the console script + module import.
- `publish.yml`: trusted publishing to PyPI, gated behind the `PUBLISH_TO_PYPI`
  repository variable (skipped until enabled).


### Fixed
- Typed entries: `parse_entries()` now returns `DecisionEntry` dataclasses (dict-compatible via `__getitem__`), full type hints on all functions, and a small exception vocabulary (`AgentLogError` / `ValidationError` / `LockTimeoutError`) — same behavior, same exit codes.
- stdin reconfigured to UTF-8 on Windows: piped unicode no longer double-encodes into decisions.txt (stdout-only reconfigure bug).
- L10: `load()` no longer crashes on a locked/unreadable log file (graceful `OSError` fallback; regression tests added).


### Docs


### Fixed

- Concurrent `--decide`/`--revise`/`--resolve` appends no longer lose
  entries: the append is serialized by a cross-process lock file
  (`<log>.lock`, stdlib-only, atomic `O_CREAT|O_EXCL` create with 5s wait
  and stale-lock recovery) and the log is re-read inside the lock before
  writing (lost-update fix).

- Document the PR-based push workflow in the README (branch -> PR ->
  squash merge with the `(AREA: <logged decision>)` marker) now that
  branch protection blocks direct pushes to `master`.

## [0.4.0] - 2026-08-09

### Fixed

- `_extract_area()` marker semantics documented and pinned by tests:
  the CI gate matches the hooks (first matching line, last
  `AREA:`/`LOG:` marker on it).
- `status_token()` strips the en-dash as well as the em-dash (`OPEN–` ->
  `OPEN`).
- `cmd_revise()` / `cmd_resolve()` use the already-read `text` instead of
  re-reading the log (one read, no stale-write window).
- `load()` reads with `utf-8-sig` so a BOM-prefixed log is parsed.

### Added

- `--review` proposals now quote each reversal's REASON, so the draft
  shows why the decision kept changing.
- Robustness tests: 100-decision fuzz, BOM / invalid UTF-8, en-dash
  statuses, multi-marker precedence in `--check-commit`, and the manual
  LOCKED + SUPERSEDES path through `--decide`.
- `--stats` analytics command: status mix, current/superseded counts,
  reversal rate, average time from LOCKED to REVISED, and the most
  volatile topics.

### Docs

- Document the `_topic_of` grouping heuristic (`--review` / `--stats`):
  first `FILES` basename, else first 3 title words; same basename in
  different dirs merges.

## [0.3.0] - 2026-08-09

### Added

- `_check_readme_count.py` + a `README test-count drift guard` CI job:
  any push or PR where the README-stated test count differs from the
  actual suite fails CI (now a required check) - the stale-count bug
  class is mechanically prevented.
- README Development section now states the test count explicitly
  (104) instead of a vague "100% pass expected".

## [0.2.0] - 2026-08-09

### Added

- `--check-commit FILE` gate: exit 0 only if the commit message names a
  logged decision (AREA:/LOG: marker), mechanically enforced by a new
  `commit-message gate (log-before-fix)` CI job - the AREA marker is now
  enforced in CI, mirroring agent-error-log.
- Companion badge in the README badge row linking agent-error-log - the
  ecosystem cross-link is visible at the top of the page, not only in the
  bottom Companion section.
- AGENTS.md section 7 (Committing): the AREA-marker gate is documented
  for AI agents, matching the enforced reality.
- Branch protection on master: direct pushes are rejected (GH006 verified
  live), so changes ship via the PR flow like the sibling.
- 7 new unit tests (104 total).



## [0.1.0] - 2026-08-09

### Added

- Initial release of **agent-decision-log**: decisions.txt + rules.txt +
  notes.txt, check_decisions.py (validate / `--decide` / `--revise` /
  `--resolve` / `--has-open` / `--recent` / `--review` / `--init`),
  start.py boot-time recall, 97 unit tests, CI (Linux + Windows, Python
  3.9-3.12), release workflow, full community standards.
