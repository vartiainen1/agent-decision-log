## What & why

<!-- What does this change do, and why? One or two sentences. -->

- [ ] Linked issue (if any): #

## Decision-log discipline (dogfooding)

This repo is a decision log - the change itself should follow the rules:

- [ ] I logged the decision with `python check_decisions.py --decide` (or the
      change is a trivial fix already covered by an existing decision)
- [ ] `python _test_decisions.py` passes (all tests green)
- [ ] `python check_decisions.py` exits 0 on the repo's own log
- [ ] CHANGELOG.md has a bullet under `## [Unreleased]`
- [ ] Added/updated tests for any behavior change

## Checklist

- [ ] Zero new dependencies (stdlib only)
- [ ] Runs on Windows and Unix (CI proves it)
