from ulid import ULID


def new_ulid() -> str:
    """Return a new time-ordered ULID as TEXT."""
    return str(ULID())
