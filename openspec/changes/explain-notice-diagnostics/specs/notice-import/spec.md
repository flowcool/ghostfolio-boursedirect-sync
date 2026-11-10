# Spec Delta

## ADDED Requirements

### Requirement: Clear diagnostic status

The connector SHALL log `custody_fee_ignored` at INFO. The message SHALL keep the document reference and row count. Import selection, exit status, and notification rules SHALL stay unchanged.

When `ACTIVITY_RECONCILIATION=off` and `ACTIVITY_REVIEW_FILE` is unset, the reconciliation and review summaries SHALL state `disabled`. They SHALL NOT present unavailable review counts as measured zeros.

When review is configured but no result is available, the summaries SHALL state `unavailable`. Measured results SHALL retain their exact counts, including zero, and the overlap information. A profile set to `off` with a review file SHALL NOT be reported as disabled: manual review remains available.

#### Scenario: Informational custody fee

- **WHEN** a run reads a retained custody-fee notice
- **THEN** it logs `custody_fee_ignored` at INFO, with the document reference and row count; activity selection and exit status stay unchanged.

#### Scenario: Review disabled

- **WHEN** a run uses profile `off` without a review file
- **THEN** both summaries state `disabled`; they do not present review counts as measured zeros.

#### Scenario: Review result unavailable

- **WHEN** a run has a review file but fails before review produces counts
- **THEN** both summaries state `unavailable`; the existing failure remains visible.

#### Scenario: Measured review result

- **WHEN** review completes with a review file, including with profile `off`
- **THEN** the summaries report the measured counts and overlap information; a measured zero stays zero.

### Requirement: Safe reason for a coupon without an ISIN

For a recognized `COUPONS` row with no ISIN, the connector SHALL retain `notice_unreadable` and add the fixed local diagnostic `reason=missing_isin` with the document reference. The reason SHALL contain no source text, holder data, account reference, or inferred security.

All existing unreadable-source protections SHALL remain in effect. A historical Paperless notice with a reliably proved date before the creation cut-off SHALL remain excluded from normal writes. Coverage SHALL still report incomplete evidence. Other unreadable inputs SHALL retain their existing diagnostic and write protection. Notification content and grouping SHALL stay unchanged.

#### Scenario: Historical coupon without an ISIN

- **WHEN** a run reads the retained coupon without an ISIN and proves its date precedes the creation cut-off
- **THEN** it reports `notice_unreadable`, `reason=missing_isin`, and the document reference; it excludes that notice and preserves eligibility for independent recent activities.

#### Scenario: Coupon without a safe historical date

- **WHEN** the same coupon has no reliable date or a date at or after the creation cut-off
- **THEN** the run reports the fixed reason and retains the existing activity-write block and failure status.

#### Scenario: Other unreadable source

- **WHEN** an input is unreadable for another reason
- **THEN** the run does not claim `missing_isin`; it keeps the existing failure and write protection.
