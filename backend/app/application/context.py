from collections.abc import Sequence

from app.domain.character import Character, render_system_prompt
from app.domain.events import Event
from app.domain.ports import LlmMessage

DEFAULT_MAX_CONTEXT_TURNS = 20


def build_context(
    events: Sequence[Event],
    character: Character,
    *,
    max_turns: int = DEFAULT_MAX_CONTEXT_TURNS,
) -> list[LlmMessage]:
    """Rebuild the LLM context from the event log.

    A turn starts at `user.text` and ends at the assistant reply, whether that
    is a normal completion or a fixed safety response. Failed turns keep the
    user message but contribute no assistant message.
    """
    turns: list[list[str | None]] = []
    for event in events:
        if event.type == "user.text":
            turns.append([str(event.payload.get("text", "")), None])
        elif event.type in ("assistant.completed", "safety.responded"):
            content = str(event.payload.get("content", ""))
            if turns and turns[-1][1] is None:
                turns[-1][1] = content

    recent = turns[-max_turns:] if max_turns > 0 else []
    messages = [LlmMessage(role="system", content=render_system_prompt(character))]
    for user_text, reply in recent:
        if user_text:
            messages.append(LlmMessage(role="user", content=user_text))
        if reply:
            messages.append(LlmMessage(role="assistant", content=reply))
    return messages
