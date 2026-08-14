import re

# Single source of truth for sensitive-field name detection.
# Used by:
#   - redact._is_sensitive_key (dict key redaction)
#   - tools.interaction._SENSITIVE_FIELD_RE (type_text confirmation gate)
#   - logging_jsonl._SENSITIVE_FIELD_RE (log line sanitizer)
SENSITIVE_FIELD_RE = re.compile(
    r"password|passwd|secret|token|api[_\-\s]?key|auth(?:orization)?|"
    r"bearer|cookie|session|ssn|dob|pin\b",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

_SENSITIVE_KEY_PATTERNS = [
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "session",
    "ssn",
    "dob",
    "pin",
]


def _is_sensitive_key(key: str) -> bool:
    """Return True if any sensitive substring appears (case-insensitive) in key."""
    lowered = key.lower()
    return any(pattern in lowered for pattern in _SENSITIVE_KEY_PATTERNS)


def _redact_str(value: str) -> str:
    value = _EMAIL_RE.sub("<email>", value)
    value = _PHONE_RE.sub("<phone>", value)
    value = _SSN_RE.sub("<ssn>", value)
    value = _CC_RE.sub("<cc>", value)
    return value


def redact(value):
    """Return a copy of value with PII masked and sensitive fields hidden."""
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, dict):
        result = {}
        for key, val in value.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                result[key] = "<redacted>"
            else:
                result[key] = redact(val)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
