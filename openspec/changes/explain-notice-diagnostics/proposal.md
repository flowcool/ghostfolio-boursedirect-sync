# Proposal

## Why

A successful run reports ignored custody fees as warnings. It also reports disabled review as unavailable and gives no specific reason for a coupon without an ISIN.

## What Changes

- Report ignored custody fees at INFO.
- Distinguish disabled review, unavailable results, and measured zero counts.
- Report a fixed `missing_isin` reason for a recognized coupon without an ISIN. Keep `notice_unreadable` and all write protections.

The scope below uses operation types observed in retained original notices.

| Operation | In scope | Out of scope |
| --- | --- | --- |
| Custody fee | Message level | Fee import |
| Coupon without ISIN | Safe diagnostic reason | Security inference or import |
| Valid coupon | Summary status | Amount, identity, or date changes |
| Domestic or foreign BUY/SELL | Summary status | Financial changes |
| Charged TTF | Summary status | Attribution changes |
| Division | Existing messages | Split conversion or waiver |
| Subscription right detachment | Existing messages | Support for rights |
| Taxable security withdrawal | Existing messages | Support for withdrawals |
| Free share attribution | Existing messages | Support for attribution |
| Compensation or cash on corporate action | Existing messages | Classification or import |

## Non-goals

No new operation support, historical conversion, financial correction, ENV setting, dependency, notification policy, or production action.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `notice-import`: clarify informational messages, review status, and the missing-ISIN diagnostic.

## Impact

Update existing parser and logging paths. Reuse the current error code and source protections. Add focused tests from existing anonymized notice fixtures. No new runtime mechanism is needed.
