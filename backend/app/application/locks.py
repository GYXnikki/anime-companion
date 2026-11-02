class SessionLocks:
    """In-process guard against concurrent generation in one session.

    `try_begin` performs no await, so the check-and-set is atomic on the single
    event loop this app runs on. P0 is explicitly single-process; a second
    worker would need a DB-backed lease instead.
    """

    def __init__(self) -> None:
        self._active: set[str] = set()

    def try_begin(self, session_id: str) -> bool:
        if session_id in self._active:
            return False
        self._active.add(session_id)
        return True

    def end(self, session_id: str) -> None:
        self._active.discard(session_id)

    def is_busy(self, session_id: str) -> bool:
        return session_id in self._active
