class DomainError(Exception):
    """Base class for errors raised by the domain/application core."""


class SessionNotFound(DomainError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"session not found: {session_id}")
        self.session_id = session_id


class SessionBusy(DomainError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"session is already generating: {session_id}")
        self.session_id = session_id
