"""Job worker + reconciliation loop. Run:  python -m novacloud.worker"""
import logging
import time

from novacloud.api.container import build
from novacloud.core.config import Settings
from novacloud.core.logging import configure_logging

log = logging.getLogger("novacloud.worker")


def main(poll: float = 1.0, reconcile_every: float = 60.0) -> None:
    configure_logging()
    c = build(Settings())
    w, last = c.worker(), 0.0
    while True:
        if not w.run_once():
            time.sleep(poll)
        if time.monotonic() - last > reconcile_every:
            last = time.monotonic()
            try:
                drift = c.compute.reconcile()
                if drift:
                    log.warning("drift detected", extra={"fields": {"count": len(drift)}})
            except Exception:  # noqa: BLE001
                log.exception("reconcile failed")


if __name__ == "__main__":
    main()
