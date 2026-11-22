import json
import logging
import re
from datetime import datetime, timezone

SENSITIVE_KEYS = re.compile(r"(pass(word)?|token|secret|authorization|cookie|api[_-]?key|csrf)", re.I)
REDACTED = "[REDACTED]"


def redact(value):
    """Recursively redact values whose key looks sensitive."""
    if isinstance(value, dict):
        return {k: (REDACTED if SENSITIVE_KEYS.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            data.update(redact(extra))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(data, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)
