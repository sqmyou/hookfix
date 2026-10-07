"""Plain-text reporter, an alternative to the JSON one."""


def render(payload: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in payload.items())
