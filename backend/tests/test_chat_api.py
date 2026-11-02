import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.application.chat import FALLBACK_REPLY
from app.application.safety import SAFETY_RESPONSE
from app.config import settings
from app.domain.ports import LlmRequest
from tests.helpers import parse_sse


class EmptyLlm:
    @property
    def model(self) -> str:
        return "empty"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        return
        yield ""  # pragma: no cover


class ExplodingLlm:
    @property
    def model(self) -> str:
        return "exploding"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        raise AssertionError("LLM must not be called on the safety path")
        yield ""  # pragma: no cover


class FailingLlm:
    @property
    def model(self) -> str:
        return "failing"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        raise RuntimeError("provider down")
        yield ""  # pragma: no cover


class HangingLlm:
    @property
    def model(self) -> str:
        return "hanging"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        await asyncio.sleep(5)
        yield "never"


class CapturingLlm:
    def __init__(self) -> None:
        self.requests: list[LlmRequest] = []

    @property
    def model(self) -> str:
        return "capturing"

    async def stream(self, request: LlmRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        yield "嗯"


async def create_session(client: AsyncClient) -> str:
    response = await client.post("/api/sessions")
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def send(client: AsyncClient, session_id: str, text: str) -> Any:
    return await client.post(f"/api/sessions/{session_id}/messages", json={"text": text})


async def replay(client: AsyncClient, session_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/sessions/{session_id}/events")
    assert response.status_code == 200, response.text
    return list(response.json()["events"])


async def test_create_session_returns_201_and_records_started(client: AsyncClient) -> None:
    response = await client.post("/api/sessions")

    assert response.status_code == 201
    body = response.json()
    assert body["character_id"] == "default"
    assert body["character_version"] == "v1"

    events = await replay(client, body["id"])
    assert [event["type"] for event in events] == ["session.started"]
    assert events[0]["seq"] == 1


async def test_message_streams_deltas_then_done_and_persists_events(client: AsyncClient) -> None:
    session_id = await create_session(client)

    response = await send(client, session_id, "今天有点累")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = parse_sse(response.text)
    names = [name for name, _ in stream]
    assert "delta" in names
    assert names[-1] == "done"
    reply = "".join(data["text"] for name, data in stream if name == "delta")
    assert reply == "我在这儿，你慢慢说。"

    events = await replay(client, session_id)
    assert [event["type"] for event in events] == [
        "session.started",
        "user.text",
        "assistant.completed",
    ]
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert events[1]["turn_id"] == events[2]["turn_id"] is not None
    completed = events[2]["payload"]
    assert completed["content"] == reply
    assert completed["model"] == "mock-companion-v1"
    assert completed["prompt_version"] == "v1"
    assert stream[-1][1]["message_id"] == events[2]["id"]


async def test_safety_path_skips_llm_and_writes_fixed_response(app_factory: Any) -> None:
    app = app_factory(ExplodingLlm())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await create_session(client)
        response = await send(client, session_id, "我不想活了")

        stream = parse_sse(response.text)
        assert [name for name, _ in stream] == ["delta", "done"]
        assert stream[0][1]["text"] == SAFETY_RESPONSE

        events = await replay(client, session_id)

    assert [event["type"] for event in events] == [
        "session.started",
        "user.text",
        "safety.triggered",
        "safety.responded",
    ]
    assert events[2]["payload"] == {"category": "self_harm", "matched_keyword": "不想活"}
    assert events[3]["payload"] == {"content": SAFETY_RESPONSE, "hotline_shown": True}
    assert {events[1]["turn_id"], events[2]["turn_id"], events[3]["turn_id"]} == {
        events[1]["turn_id"]
    }


async def test_llm_error_streams_error_and_persists_failed(
    app_factory: Any,
) -> None:
    app = app_factory(FailingLlm())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await create_session(client)
        response = await send(client, session_id, "你在吗")

        stream = parse_sse(response.text)
        assert stream[-1][0] == "error"
        assert stream[-1][1]["code"] == "llm_error"

        events = await replay(client, session_id)

    assert [event["type"] for event in events] == [
        "session.started",
        "user.text",
        "assistant.failed",
    ]
    assert events[-1]["payload"]["code"] == "llm_error"


async def test_empty_llm_reply_falls_back_to_apology(app_factory: Any) -> None:
    app = app_factory(EmptyLlm())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await create_session(client)
        response = await send(client, session_id, "你在吗")

        stream = parse_sse(response.text)
        deltas = "".join(data["text"] for name, data in stream if name == "delta")
        assert deltas == FALLBACK_REPLY

        events = await replay(client, session_id)

    assert events[-1]["type"] == "assistant.completed"
    assert events[-1]["payload"]["content"] == FALLBACK_REPLY


async def test_context_keeps_only_the_last_twenty_turns(app_factory: Any) -> None:
    llm = CapturingLlm()
    app = app_factory(llm)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await create_session(client)
        for index in range(21):
            assert (await send(client, session_id, f"u{index}")).status_code == 200

    last_request = llm.requests[-1]
    assert last_request.messages[0].role == "system"
    # 20 turns counting the current one: 19 completed turns plus the in-flight user message.
    assert len(last_request.messages) == 1 + 19 * 2 + 1
    assert last_request.messages[1].content == "u1"
    assert last_request.messages[-1].role == "user"
    assert last_request.messages[-1].content == "u20"


async def test_llm_timeout_is_reported(
    app_factory: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(settings, "llm_timeout_seconds", 0.05)
    app = app_factory(HangingLlm())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = await create_session(client)
        response = await send(client, session_id, "你在吗")

        stream = parse_sse(response.text)
        assert stream[-1][0] == "error"
        assert stream[-1][1]["code"] == "llm_timeout"

        events = await replay(client, session_id)

    assert events[-1]["payload"]["code"] == "llm_timeout"


async def test_unknown_session_returns_404(client: AsyncClient) -> None:
    assert (await client.get("/api/sessions/missing/events")).status_code == 404
    assert (await send(client, "missing", "你好")).status_code == 404


async def test_invalid_text_returns_422(client: AsyncClient) -> None:
    session_id = await create_session(client)

    assert (await send(client, session_id, "")).status_code == 422
    assert (await send(client, session_id, "   ")).status_code == 422
    assert (await send(client, session_id, "x" * 2001)).status_code == 422


async def test_second_request_while_generating_returns_409(
    client: AsyncClient, app: FastAPI
) -> None:
    session_id = await create_session(client)
    assert app.state.session_locks.try_begin(session_id) is True

    response = await send(client, session_id, "你好")

    assert response.status_code == 409
    app.state.session_locks.end(session_id)
    assert (await send(client, session_id, "你好")).status_code == 200
