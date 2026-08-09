# Security Policy

## Reporting a vulnerability

Please do **not** open a public issue for a security vulnerability. Instead,
report it privately to the maintainer via GitHub's security advisory feature:
**Security → Report a vulnerability** on this repository.

You should receive a response within 7 days. If the issue is confirmed, a fix
and (if warranted) a security release will be prepared before the details are
made public.

## Scope

This project is stdlib-only tooling with no network surface and no secrets.
The realistic risks are:

- **Log spoofing** - a tool that validates text cannot verify the *truth* of
  what is logged. The linter checks format, not honesty; that is true of any
  documentation system.
- **Self-modification** - if an agent can edit its own tooling or the log,
  it can defeat validation. Keep the repo read-only for agents.

## Supported versions

Security fixes land in the latest release and are backported on request.
