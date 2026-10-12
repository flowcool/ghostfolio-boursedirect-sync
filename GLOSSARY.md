# Glossary

Terms used by the released Bourse Direct acquisition and preview.

**Account binding**
: The retained pairing of one Bourse Direct account and one existing Ghostfolio
  account. A conflicting later configuration stops rather than silently changing
  the destination.

**Broker vault item**
: The unique Bitwarden-compatible Login item that contains the Bourse Direct
  login, password, and TOTP setup. Its default name is `boursedirect.fr`.

**Dry run / preview**
: The report produced after saving and comparing source notices and a Ghostfolio
  snapshot. It never creates, updates, or deletes financial records.

**Operation notice**
: A Bourse Direct document describing an operation. The connector reads notices
  made available during its rolling 90-day window; this is not a full account
  history.

**Safety journal**
: Private state that records account bindings and unfinished or uncertain
  attempts. It prevents an operator from bypassing a stopped attempt by simply
  rerunning the connector.

**Security mapping**
: An explicit operator-provided mapping from a verified ISIN to the Ghostfolio
  symbol and currency. Missing or ambiguous mappings stay visible in the report.

**Vault access capability**
: The connector's temporary, isolated access to the vault item. It does not mean
  broker authentication has succeeded.
