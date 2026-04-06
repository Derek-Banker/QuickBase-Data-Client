import atexit
import datetime
import logging
import threading
from typing import Dict, List

from quickbase_sdk.exceptions import QuickbaseValidationError, format_error_message
from quickbase_sdk.parsers.requests import QuickBaseRequest
from quickbase_sdk.quickbase_api import Auth, QuickBaseAPI

DEFAULT_BATCH_SIZE = 20
DEFAULT_DT_FMT = "%Y-%m-%d %H:%M:%S"
REQUIRED_FID_KEYS = frozenset({"date_time", "level", "message"})


class QuickBaseHandler(logging.Handler):
    """Optional logging utility that batches log records into a Quickbase table."""

    def __init__(
        self,
        auth: Auth,
        table_id: str,
        fids: Dict[str, str],
        batch_size: int = DEFAULT_BATCH_SIZE,
        level: int = logging.NOTSET,
    ):
        """
        `fids` must include:
          - `date_time`
          - `level`
          - `message`

        Optional mappings:
          - `source`
          - `link`
        """
        missing_fids = sorted(REQUIRED_FID_KEYS.difference(fids))
        if missing_fids:
            raise QuickbaseValidationError(
                format_error_message(
                    "QuickBaseHandler requires field ids for date_time, level, and message.",
                    operation="QuickBaseHandler.__init__",
                    missing_fids=missing_fids,
                )
            )

        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise QuickbaseValidationError(
                format_error_message(
                    "batch_size must be a positive integer.",
                    operation="QuickBaseHandler.__init__",
                    batch_size=batch_size,
                )
            )

        super().__init__(level)
        self.client = QuickBaseAPI(auth)
        self.table_id = table_id
        self.fids = fids
        self.batch_size = batch_size

        self.buffer: List[logging.LogRecord] = []
        self._lock = threading.Lock()

        # Flush any remaining logs on process exit.
        atexit.register(self.close)

    def _record_to_payload(self, record: logging.LogRecord) -> Dict[str, Dict[str, object]]:
        record_timestamp = datetime.datetime.fromtimestamp(record.created).strftime(
            DEFAULT_DT_FMT
        )
        payload: Dict[str, Dict[str, object]] = {
            self.fids["date_time"]: {"value": record_timestamp},
            self.fids["level"]: {"value": record.levelname},
            self.fids["message"]: {"value": record.getMessage()},
        }

        source_field_id = self.fids.get("source")
        if source_field_id:
            payload[source_field_id] = {"value": getattr(record, "source", "")}

        link_field_id = self.fids.get("link")
        if link_field_id:
            payload[link_field_id] = {"value": getattr(record, "resource_link", "")}

        return payload

    def emit(self, record: logging.LogRecord):
        need_flush = False
        with self._lock:
            self.buffer.append(record)
            if len(self.buffer) >= self.batch_size or record.levelno >= logging.WARNING:
                need_flush = True

        if need_flush:
            self.flush()

    def flush(self):
        with self._lock:
            if not self.buffer:
                return
            records = list(self.buffer)
            self.buffer.clear()

        try:
            QuickBaseRequest.upsert_records(
                self.client,
                self.table_id,
                [self._record_to_payload(record) for record in records],
                [],
            )
        except Exception:
            self.handleError(records[-1])

    def close(self):
        """Flush any pending logs, then clean up the handler."""
        try:
            self.flush()
        finally:
            super().close()
