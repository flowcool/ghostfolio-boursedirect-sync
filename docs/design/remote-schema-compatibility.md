# Saved Ghostfolio schema compatibility

The real destination runs Ghostfolio 3.81.0. A complete GET-only capture could not
be normalized because legitimate nullable fields were treated as missing evidence.
The official Order schema permits nullable account assignment and currency. The
activities service retains original numeric fields and resolves currency using
`order.currency ?? order.SymbolProfile.currency`. These pinned sources justify
compatibility handling; they do not authorize exchange-rate or date guesses.

Sources at commit `920d0787541a8568920fc11f978aa01e5a52c581`:

- [Order schema](https://github.com/ghostfolio/ghostfolio/blob/920d0787541a8568920fc11f978aa01e5a52c581/prisma/schema.prisma).
- [Activities response construction](https://github.com/ghostfolio/ghostfolio/blob/920d0787541a8568920fc11f978aa01e5a52c581/apps/api/src/app/activities/activities.service.ts).

An explicit `currency: null` inherits the current asset profile's nonempty currency.
An absent key, absent profile currency or invalid value still fails. Current
`assetProfile` takes precedence over the legacy profile, including when invalid.
No derived converted price or fee substitutes for original numeric values.

Explicit `accountId: null` and `account: null` form a valid unassigned pair. The
record remains inspectable, with inactive target context. Missing or contradictory
account assignment fails. Unassigned records cannot cover target holdings or be
owned/adopted as target activities.

An explicitly different price/profile currency or zero price is retained with
`financial_context_verified=false`. Ownership, matching manual candidates,
chronological target holdings and positive uncertain-write readback require this
flag. Negative price, nonpositive quantity and negative fee remain invalid trades.
Unsupported unrelated records do not invalidate a complete multi-account capture.
The UTC-midnight comparison policy remains unchanged.

All verification uses synthetic inputs without sockets, plus private evaluation
of the immutable GET capture. No remote write exists in this change. Rollback is
reverting the scoped compatibility commit; original private captures remain intact.
