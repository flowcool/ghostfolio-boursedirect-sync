import sys

from ghostfolio_boursedirect_sync.app import main
from ghostfolio_boursedirect_sync.notify import NOTIFY_WORKER_FLAG, notify_worker

raise SystemExit(notify_worker() if sys.argv[1:] == [NOTIFY_WORKER_FLAG] else main())
