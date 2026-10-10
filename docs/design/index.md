# Design contracts

Before changing importer, acquisition, review or application behavior, read the
owning contract below. Beads owns active work and acceptance evidence. Summaries
are generated from each contract's first non-heading line.

| Contract | Purpose |
| --- | --- |
| [Offline acquisition bundle qualification](acquisition-bundles.md) | `qualify-captures` checks one completed saved acquisition bundle and writes a |
| [Durable acquisition authority core (offline)](acquisition-core.md) | The approved A scope is implemented in `collector/core.mjs`. This is a functional |
| [Conservative offline historical sale coverage](chronological-holdings.md) | `verify_chronological_holdings` consumes prepared strict trades, raw complete |
| [Portable owned disposable acceptance runner](disposable-acceptance.md) | This development-only runner reproduces the supported three-trade fixture chain |
| [Frozen owned-lab sequence](frozen-lab-sequence.md) | `dispatch_frozen_lab_review(state_root, binding, review_raw, review_sha256, |
| [Frozen review validation](frozen-review-validation.md) | The callable `compute_offline_review(config_raw, captures, max_bytes)` computes the |
| [Disposable Ghostfolio 3.81.0 parity evidence](ghostfolio-381-parity.md) | Observed on 2026-10-09 (Europe/Zurich), under the approved G5 scope. This repeats |
| [Pinned isolated Ghostfolio API observations](ghostfolio-api-lab.md) | Verified on 2026-10-08 against Ghostfolio **3.80.2**, official source commit |
| [Isolated delayed-write recovery evidence](ghostfolio-recovery-lab.md) | Observed2026-10-08 on the same pinned Ghostfolio3.80.2 image/source and isolated |
| [Bounded Ghostfolio request adapter](https-request-adapter.md) | `make_ghostfolio_request(allowed_origin, max_bytes, timeout)` returns the existing |
| [Internal trade conversion contract](internal-trade-conversion.md) | Florent accepted the strict BUY/SELL initial scope, existing Ghostfolio opening |
| [Ledger identity and revision contract](ledger-identity.md) | The reviewed plan's v1 identity candidate is implemented as pure offline helpers. |
| [Offline existing-activity adoption contract](offline-adoption.md) | Florent confirms that earlier acquisitions already exist in Ghostfolio. Import |
| [Offline compensation association candidates](offline-compensation-candidates.md) | `rollback-plan` inspects one retained intent against a saved complete activity |
| [Saved-input diagnosis contract](offline-diagnosis.md) | `diagnose --config FILE --input-root DIR --max-bytes N` describes uncertainty |
| [Saved retained-intent observation command](offline-intent-verification.md) | `verify` compares a retained write journal with a saved complete activity snapshot. |
| [Offline preparation contract](offline-preparation.md) | `prepare --config FILE --input-root DIR --max-bytes N --max-depth N` reads only |
| [Offline statement inspection contract](offline-probe.md) | Florent authorized implementation with “Carte blanche” on 2026-10-08 after |
| [Saved-snapshot review command](offline-review-cli.md) | `review --config FILE --input-root DIR --max-bytes N` is entirely offline. Its |
| [Offline reviewed wire and acceptance contract](offline-wire.md) | `build_wire_payload(keyed_activities)` produces private deterministic UTF-8 JSON |
| [Interactive source acquisition amendment](online-source-inspection.md) | On 2026-10-08 Florent replaced manual-only source acquisition with direct online |
| [Operator application preview](operator-application.md) | `apply --config FILE --review FILE --review-sha256 HEX --input-root DIR |
| [Pure preparation source replay](preparation-source-replay.md) | `compute_prepared_sources(config_raw, documents, max_bytes, max_depth)` returns |
| [Qualified operator application](qualified-application.md) | The `apply` command defaults to offline preview/export. Remote application exists |
| [GET-only saved activity snapshot acquisition](readonly-snapshot.md) | `snapshot` is a narrowly scoped acquisition command. It sends exactly one |
| [Saved Ghostfolio schema compatibility](remote-schema-compatibility.md) | The real destination runs Ghostfolio 3.81.0. A complete GET-only capture could not |
| [Single-event laboratory dispatch core](single-event-lab-dispatch.md) | `dispatch_single_lab_intent` is a reusable lab-only orchestration helper, with a |
| [Synthetic document-to-import lifecycle on Ghostfolio 3.81.0](synthetic-import-lifecycle.md) | Observed on 2026-10-09 (Europe/Zurich), under reviewed G5/G6. This joins the |
| [Local durable write intents and replay fences](write-intents.md) | The offline journal boundary complements [reviewed wire bytes](offline-wire.md). |
