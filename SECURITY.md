# Security policy

Agentic OS is a local, single-user tool. It has no hosted service and no accounts. The threat model, the guarantees it
tries to keep and its honest limits are described in [docs/security.md](docs/security.md).

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately, with steps to reproduce: use
"Report a vulnerability" (GitHub private security advisories) on the repository's Security tab. Reports are handled on
a best-effort basis; this project is provided as is.

## In scope

- a way to make an agent or the server write, execute or send something outside the documented rules
- a way to reach the local server from another origin or host, or without the token
- secrets or note content leaking into logs, answers or generated files
