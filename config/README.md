# Optional symbol mappings

Set `MAPPING_FILE=/config/mappings.yaml` to use a private mapping file.
Compose mounts this directory read only at `/config`. Keep the private file
outside Git. The container runs as UID and GID `10001`. Give that user read
access to the file and traversal access to the directory. From the repository
root, use group access while retaining the host owner's access:

```sh
sudo chgrp 10001 config config/mappings.yaml
chmod 0750 config
chmod 0640 config/mappings.yaml
```

Only the owner and members of group `10001` can read the file. The container
mount remains read only.

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
