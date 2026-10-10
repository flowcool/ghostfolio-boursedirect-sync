# Bourse Direct document acquisition

Vocabulary for obtaining broker documents and preparing their import.

## Language

**Broker vault item**:
The unique live login item named `boursedirect.fr` whose login URI identifies
Bourse Direct and whose fields provide the broker authentication material.
_Avoid_: Ghostfolio account, vault account

**Vault access capability**:
The reusable project capability for obtaining the broker vault item through an
independent vault session.
_Avoid_: Broker authentication, document acquisition
