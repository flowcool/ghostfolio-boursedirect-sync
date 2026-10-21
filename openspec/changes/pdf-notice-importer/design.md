# Design

## Context

Use the installed Python 3.14 package `ghostfolio_boursedirect_sync`.
Keep functions and typed records, with strict mypy and Ruff.
This permits selective reuse without the old single-file constraint.
The application package stays within 2 500 lines.

Source: `ghostfolio-ibkr-sync` commit
`a9bd0b92e4783ff1f42a089eb9547b27ba40f9bd`.
Module paths below are under `ghostfolio_ibkr_sync/`.
Preparation can precede IBKR stable. Review later source changes separately.
Do not add a shared library or automatic core projection.

## Reused parts

| Part | Source |
| --- | --- |
| ENV | `config.py:95` |
| Token exchange, account lookup | `ghostfolio.py:116,189` |
| Complete activity read | `ghostfolio.py:208` |
| Account-scoped identity | `ghostfolio.py:64,76` |
| Mapping, manual match, dividend proximity | `sync.py:58,546,718` |
| Holdings and accepted-buy guard | `sync.py:580,960`, `app.py:343` |
| Import and accepted response | `ghostfolio.py:398,459` |
| Failure codes, notification | `outcome.py:49`, `notify.py:81`, `app.py:400` |
| Package, image, CRON | `pyproject.toml`, `Dockerfile`, `entrypoint.sh` |

## Adaptations

Keep the BD spec:

- Require one exact target account and one labelled source account.
- Accept only absent `DRY_RUN`, `0` or `1`; never notify in simulation.
- Use Decimal throughout money and position decisions; do not inherit float tolerances.
- Require exact manual quantity and price. Coupon proximity compares net amounts.
- Apply the chronological sell guard, with SELL first on equal dates.
  Advance real holdings only from confirmed activities.
- Require complete exact readback; partial acceptance fails without retry.
- Log fixed error codes, HTTP status and Paperless document ID, never response bodies.
- Keep `BD#v3#<account>:<KIND>:<row key>` and legacy matching.
  The key includes the broker reference or original-PDF hash, row content
  and identical-row rank.

Do not copy Flex parsing, cash updates, gross dividends or maintenance tools.

## Source-specific parts

Previously approved:

- Paperless originals and missing-Source search: paperless-ngx
  `docs/api.md:121-134`, commit `2b00cf6`; view-only token.
- PDF extraction: `pdftotext -layout` from `poppler-utils`.
- Row parsing: selected legacy parser functions at `legacy-wip`.
- ISIN lookup: decision of 2026-10-14.

## Limits and rollback

Other PDF types need real evidence. Keep TTF outside Ghostfolio.
Stop on DIVISION; split-adjusted holdings remain unverified (#115).
Revert the adoption commit for code rollback. This does not undo financial writes.
