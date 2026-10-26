import sys

from ghostfolio_boursedirect_sync.app import main
from ghostfolio_boursedirect_sync.notify import NOTIFY_WORKER_FLAG, notify_worker

# Reuse the pinned IBKR worker dispatch to route schedule rejection through the
# same configuration-failure finalizer. This internal flag never runs a sync.
raise SystemExit(notify_worker() if sys.argv[1:] == [NOTIFY_WORKER_FLAG]
                 else main(invalid_schedule=sys.argv[1:] == ["--invalid-cron"]))
