import asyncio
from collections.abc import AsyncIterator

from app.domain.ports import LlmRequest


class MockLlm:
    """Deterministic stand-in until a real provider adapter exists.

    It reports zero token usage on purpose: inventing numbers would make the
    stored metrics lie.
    """

    def __init__(self, reply: str = "我在这儿，你慢慢说。", *, chunk_size: int = 4) -> None:
        self._reply = reply
        self._chunk_size = max(1, chunk_size)

    @property
    def model(self) -> str:
        return "mock-companion-v1"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        await asyncio.sleep(0)
        for start in range(0, len(self._reply), self._chunk_size):
            yield self._reply[start : start + self._chunk_size]
            await asyncio.sleep(0)
