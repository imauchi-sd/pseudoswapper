from __future__ import annotations

import re


def replace(text: str, token_map: dict[str, str]) -> str:
    """Return *text* with every key in *token_map* replaced by its token value.

    Keys are matched longest-first so full names are caught before their parts.
    All occurrences are replaced, not just the first.
    """
    if not token_map:
        return text

    sorted_keys = sorted(token_map, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(k) for k in sorted_keys))
    return pattern.sub(lambda m: token_map[m.group(0)], text)
