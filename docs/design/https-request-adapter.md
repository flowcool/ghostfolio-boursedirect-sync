# Bounded Ghostfolio request adapter

`make_ghostfolio_request(allowed_origin, max_bytes, timeout)` returns the existing
single-event callback signature `(method,path,body)`. The factory validates limits,
canonical exact HTTPS origin/GHOST_HOST equality and privately captures the existing
environment GHOST_SESSION_BEARER. It never connects; it does not exchange a Security
Token, renew credentials, use a proxy/netrc or confer execution authority.

Only GET /api/v1/activities withNonebody and POST /api/v1/import with boundedbytes
are permitted. POST JSON/numeric shape is bounded before canonical reconstruction,
then must contain exactly one canonical strict activity. No arbitrary URL/path,
query, DELETE/PUT/authPOST or multi-event request can reach a connection.

Each invocation creates a fresh HTTPSConnection with verified systemTLS and an
explicit integer1–120 second per-operation socket timeout. Bearer/json/identity
headers are fixed. GET200/POST201 and uncompressed application/json are required;
read budget is max_bytes+1. Raw(status,bytes) goes to the existing core, whose exact
acceptance/full readback checks establish outcomes; transport status alone does not.
No redirect, retry, remote body logging or snapshot publication occurs.

Connection creation/send/response/header/read faults produce fixed codes without
private exception chaining; every created connection is closed once. Close failure
also produces a fixed failure, retaining any earlier safe failure. Lost POST
responses, including close errors, cannot authorize retry under the core's already
persisted uncertainty fence. The adapter has no public execution route yet and the
existing snapshot command remains unchanged. Ordinary tests forbid sockets and
prove composition with the real core through fakeHTTPS, not live acceptance.

Rollback scoped implementation revert. New external HTTP/credential code still
requires the project's pre-merge security review; design/CI are not that approval.
[Approved packageB](../plans/2026-10-09-operator-application.md).
