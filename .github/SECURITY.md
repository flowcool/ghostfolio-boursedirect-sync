# Security

Report suspected credential leaks or security vulnerabilities privately using
[GitHub private vulnerability reporting](https://github.com/flowcool/ghostfolio-boursedirect-sync/security/advisories/new).
Do not include Bourse Direct credentials or one-time codes, Ghostfolio tokens,
account identifiers, statements or contract notes in public issues or pull
requests.

Security fixes target the current `main` branch. Older revisions do not receive
separate backports. Dependency checks run on pull requests and weekly. Tagged
releases publish a scanned AMD64 connector image to GHCR and a Compose archive;
they never deploy it to an operator environment.
