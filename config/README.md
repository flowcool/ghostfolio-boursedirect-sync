# Optional symbol mappings

Set `MAPPING_FILE=/config/mappings.yaml` to use a private mapping file.
Compose mounts this directory read only at `/config`. Keep the private file
outside Git. Set its mode to `0600`.

The file must contain `symbol_mapping`. Use an ISIN as each key and a verified
EUR Yahoo ticker as its value. See [mappings.example.yaml](mappings.example.yaml).

```yaml
symbol_mapping:
  FR0000000002: VERIFIED.PA
```

These values are synthetic. Verify the ticker before use. An explicit mapping
takes priority over lookup. With `MAPPING_FILE` empty, the connector uses
Ghostfolio lookup. It accepts exactly one EUR YAHOO result for each ISIN.
An unresolved security is skipped and reported. Independent operations continue.

The legacy mapping formats remain in Git history. They do not configure the
v1 package. See the [README](../README.md) for current settings.
