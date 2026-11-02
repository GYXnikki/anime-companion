from datetime import UTC, datetime


def utc_now_iso() -> str:
    """Return the current UTC time as ISO8601 with milliseconds and a Z suffix."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
