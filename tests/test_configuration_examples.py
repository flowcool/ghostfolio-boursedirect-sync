"""The published ENV example covers every Compose interpolation key."""
import re
from pathlib import Path


def test_env_example_covers_all_operator_compose_keys():
    root = Path(__file__).resolve().parents[1]
    settings = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", (root / ".env.example").read_text(), re.M))
    required = set()
    for path in root.glob("compose*.yaml"):
        required.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text()))
    assert required <= settings, "Missing settings: " + ", ".join(sorted(required - settings))
