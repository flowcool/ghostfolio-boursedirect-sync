"""Run one sync with the IBKR CLI logging and private worker dispatch."""

import logging
import os
import sys

from ghostfolio_boursedirect_sync.app import main
from ghostfolio_boursedirect_sync.notify import NOTIFY_WORKER_FLAG, notify_worker


def run() -> int:
    # IBKR f9a2b11 __main__.py:11-26.
    stdout = logging.StreamHandler(sys.stdout)
    stdout.addFilter(lambda record: record.levelno < logging.WARNING)
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setLevel(logging.WARNING)
    logging.basicConfig(
        level=logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "INFO"), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[stdout, stderr],
    )
    # HTTP request DEBUG lines can contain URL credentials and query tokens.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if sys.argv[1:] == [NOTIFY_WORKER_FLAG]:
        return notify_worker()
    return main(invalid_schedule=sys.argv[1:] == ["--invalid-cron"])


if __name__ == "__main__":
    sys.exit(run())
