# Optional security mappings

Place the existing verified per-ISIN mappings in `mappings.yaml` here. Compose
mounts this directory read-only at `/config`. This file is private and ignored
by Git. Missing mappings remain visible in the dry run; they never cause a
security, symbol or execution currency to be guessed.

Source and destination accounts are configured through the documented Compose
ENV fields, or selected once during `connect`. They are retained in the private
persistent state volume. A configured value conflicting with retained state
refuses instead of silently changing the route.
