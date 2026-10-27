# Security Policy

## Supported versions

Only the latest release of PortPilot receives security fixes.

## Reporting a vulnerability

Please **do not** open a public issue. Instead, use GitHub's
[private vulnerability reporting](https://github.com/cyber-emreclskn/portpilot/security/advisories/new)
for this repository.

You can expect an initial response within 7 days. Once a fix is available we
will publish a GitHub Security Advisory and credit you unless you prefer
otherwise.

## Scope notes

PortPilot terminates processes on the local machine with the privileges of the
user running it. It never elevates privileges on its own, and it does not open
network connections.
