"""Failure notifications: summaries and the isolated Apprise worker process."""

import json
import logging
import os
import signal
import subprocess
import sys

from ghostfolio_boursedirect_sync.config import (
    APPRISE_URLS_MAX,
    NOTIFY_PAYLOAD_MAX,
    NotificationConfigDict,
)

NOTIFY_WORKER_FLAG = "--notify-worker"
# The worker inherits only what Apprise needs to reach a destination: never the
# IBKR or Ghostfolio credentials.
NOTIFY_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                        "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy")
# Worker exit code -> delivery status reported by send_notification.  Kept clear
# of the interpreter's own codes (1 uncaught error, 2 cannot open the script).
NOTIFY_EXIT_STATUS = {0: "sent", 10: "invalid_payload", 11: "unavailable", 12: "failed",
                      13: "invalid_destination"}


def notify_worker() -> int:
    """Worker process entry: deliver one notification read from stdin.

    Never runs the sync.  Apprise is imported here only, so the sync never
    loads it.  Exit codes: see NOTIFY_EXIT_STATUS.
    """
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.read(NOTIFY_PAYLOAD_MAX + 1)
    try:
        payload = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("urls"), list) or not payload["urls"]
            or not all(isinstance(u, str) for u in payload["urls"])
            or not isinstance(payload.get("title"), str)
            or not isinstance(payload.get("body"), str)):
        return 10
    try:
        import apprise
    except ImportError:
        return 11
    notifier = apprise.Apprise()
    # One entry may hold several space- or comma-separated URLs: bound the
    # destinations Apprise actually expanded, not the list entries
    if (not all(notifier.add(url) for url in payload["urls"])
            or len(notifier) > APPRISE_URLS_MAX):
        return 13
    try:
        sent = notifier.notify(title=payload["title"], body=payload["body"])
    except Exception:
        return 12
    return 0 if sent else 12


def _notify_worker_argv() -> list[str]:
    # -I: ignore PYTHON* variables, user site-packages and the current directory;
    # the installed package is found through site-packages.
    return [sys.executable, "-I", "-m", "ghostfolio_boursedirect_sync", NOTIFY_WORKER_FLAG]


def _stop_worker(proc: subprocess.Popen[bytes]) -> None:
    """Kill the worker (and anything it started) if still running, then reap it."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    proc.wait()


def send_notification(settings: NotificationConfigDict, title: str, body: str) -> str:
    """Deliver one notification through an isolated Apprise worker.

    Apprise plugins can block past any library timeout and can print their
    destination URL.  So the URLs travel on stdin, the worker gets an
    allowlisted environment and no output channel, and one deadline covers its
    whole life (import, setup, send, exit); on expiry it is killed and reaped.
    No retry: a timed-out send may still have been delivered.  Returns a fixed
    status string; SystemExit/KeyboardInterrupt propagate after the kill.
    """
    payload = json.dumps({"urls": settings["urls"], "title": title, "body": body}).encode()
    if len(payload) > NOTIFY_PAYLOAD_MAX:
        return "payload_too_large"
    env = {k: os.environ[k] for k in NOTIFY_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(_notify_worker_argv(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, close_fds=True, start_new_session=True)
    except (OSError, ValueError):
        return "spawn_failed"
    try:
        proc.communicate(payload, timeout=settings["timeout"])
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "failed"
    finally:
        _stop_worker(proc)
    return NOTIFY_EXIT_STATUS.get(proc.returncode, "failed")


NOTIFY_TITLE = "ghostfolio-boursedirect-sync: run failed"
