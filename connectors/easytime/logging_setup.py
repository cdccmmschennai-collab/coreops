"""Structured, redacted logging for a scheduled unattended process.

Nobody watches a connector that runs every five minutes. The log IS the
observability surface, so it has three properties:

* **Every line carries the run id.** A 5-minute schedule interleaves nothing
  (the run lock serializes it), but a manual backfill and a scheduled run in
  the same file would otherwise be indistinguishable after the fact.
* **One file per day, not per run.** 288 runs a day for a year is 105,000
  files if each run gets its own; a dated file stays greppable and stays
  inside any reasonable retention policy.
* **Every handler redacts.** ``redaction.sanitize_text`` runs over the
  formatted message on its way out, in addition to nothing secret being passed
  in. See redaction.py for why both.

The format is deliberately the same ``key=value`` style the backend's
ingestion logger uses, so an operator reading both ends of one batch reads the
same shape twice.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from redaction import sanitize_text

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s run=%(run_id)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RunIdFilter(logging.Filter):
    """Stamp the run id onto every record, including ones from httpx."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


class RedactingFormatter(logging.Formatter):
    """The last thing that touches a log line before it is written.

    Applied to the FULLY formatted message, including any exception traceback,
    because a traceback frame can carry a local variable's repr.
    """

    def format(self, record: logging.LogRecord) -> str:
        return sanitize_text(super().format(record))


def configure_logging(
    *,
    run_id: str,
    log_dir: Path | None,
    verbose: bool = False,
    console: bool = True,
) -> Path | None:
    """Install the connector's handlers. Returns the log file path, if any.

    A log directory that cannot be created is a WARNING, not a failure: losing
    the ability to write a log file must never stop punches from being
    ingested. The run continues with console output only.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Replace handlers rather than adding: --status followed by a sync in one
    # process (the tests do exactly that) must not double every line.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = RedactingFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    run_filter = RunIdFilter(run_id)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        stream.addFilter(run_filter)
        root.addHandler(stream)

    log_path: Path | None = None
    if log_dir is not None:
        try:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"sync-{_today()}.log"
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.addFilter(run_filter)
            root.addHandler(file_handler)
        except OSError as exc:
            log_path = None
            root.warning(
                "could not open the log directory %s (%s); continuing with console "
                "output only",
                log_dir,
                type(exc).__name__,
            )

    # httpx logs one INFO line per request, including the full URL. The URL
    # carries no secret (the token is a header, by design) but at INFO it
    # doubles the log volume for no operational value.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return log_path


def _today() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d")
