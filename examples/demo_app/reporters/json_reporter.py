"""Output reporters, loaded dynamically by name."""


def render(payload: dict) -> str:
    import json

    return json.dumps(payload, indent=2)
