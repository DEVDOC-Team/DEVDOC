import logging
import re
import sys

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(postgres(?:ql)?(?:\+[a-z0-9_]+)?://[^:]+:)([^@]+)(@)", re.IGNORECASE),
    re.compile(r"((?:nebius|api[_-]?key|secret|password|token|auth)\s*[:=]\s*['\"]?)([^'\"\s&]+)", re.IGNORECASE),
]


class SecretRedactingFilter(logging.Filter):
    """Redacts authorization tokens, credentials, and sensitive parameters from logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pattern in _SECRET_PATTERNS:
                if "Bearer" in pattern.pattern:
                    msg = pattern.sub(r"\1[REDACTED]", msg)
                elif "postgres" in pattern.pattern:
                    msg = pattern.sub(r"\1[REDACTED]\3", msg)
                else:
                    msg = pattern.sub(r"\1[REDACTED]", msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("devdoc")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.addFilter(SecretRedactingFilter())
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = setup_logging()
