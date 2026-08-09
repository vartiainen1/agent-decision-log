# Changelog

All notable changes to this project are documented here. The version at the
top of this file is the single source of truth - releases are cut from it by
`.github/workflows/release.yml`.

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
