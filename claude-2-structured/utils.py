"""Small shared helpers."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    Stored naive (but always UTC) so behaviour is consistent across SQLite
    which does not preserve timezone information on DateTime columns.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_iso_utc(dt: datetime) -> str:
    """Serialise a stored (naive, UTC) datetime as an ISO-8601 string with a
    trailing 'Z' to make the UTC offset explicit."""
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
