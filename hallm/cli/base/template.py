"""Text template rendering with ##KEY## placeholder substitution."""

import re

_PLACEHOLDER_RE = re.compile(r"##(\w+)##")


def render(text: str, subs: dict[str, str]) -> str:
    """Expand ##KEY## placeholders; raises ValueError for unknown keys."""
    unknown: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in subs:
            unknown.append(key)
            return match.group(0)
        return subs[key]

    rendered = _PLACEHOLDER_RE.sub(_replace, text)
    if unknown:
        raise ValueError(f"Unknown placeholders: {', '.join(f'##{k}##' for k in unknown)}")
    return rendered
