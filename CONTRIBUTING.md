# Contributing

Thanks for considering a contribution to **agent-decision-log**. It is a
small, deliberate project - every file earns its place.

## Principles

- **Zero dependencies, stdlib only.** Nothing may be added to `requirements`.
- **Windows + Unix.** Every script runs on both; CI proves it.
- **Append-only by design.** The log format and the tooling never rewrite
  history - keep it that way.

## Workflow

1. **Decide before you code.** This is a decision log - dogfood it:
   `python check_decisions.py --decide` before changing behavior.
2. **Log before fixing.** If you find a bug, log it in `decisions.txt` (or
   `notes.txt`) first, then fix.
3. **Tests.** Add or update `_test_decisions.py` for any behavior change.
   Run `python _test_decisions.py` - all tests must pass.
4. **Validate.** `python check_decisions.py` must exit 0 on the repo's own log.
5. **Changelog.** Add a bullet under `## [Unreleased]` in CHANGELOG.md.
6. **Branch + PR.** Create a branch, open a pull request, keep the diff
   focused. PRs are squash-merged with the changelog area in the title
   (e.g. `feat: ... (AREA: new command)` - the log-before-fix discipline).
7. **Release.** The maintainer bumps `[Unreleased]` to a version; the
   release workflow tags it and drafts the GitHub Release.

## Code of conduct

Be kind and constructive. The Contributor Covenant
([CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)) applies to all spaces.
