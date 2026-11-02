import json
from typing import Any


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    parsed: list[tuple[str, dict[str, Any]]] = []
    name: str | None = None
    data: list[str] = []
    for line in body.splitlines():
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            data.append(line[len("data: ") :])
        elif line == "":
            if name is not None:
                parsed.append((name, json.loads("".join(data))))
            name = None
            data = []
    return parsed
