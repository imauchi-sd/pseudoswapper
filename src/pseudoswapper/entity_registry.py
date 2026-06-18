from __future__ import annotations

from collections import defaultdict
from typing import Optional


class EntityRegistry:
    """In-memory store of value → token mappings for a single session."""

    def __init__(self) -> None:
        self._forward: dict[str, str] = {}  # original value → token
        self._reverse: dict[str, str] = {}  # token → original value
        self._counters: dict[str, int] = defaultdict(int)

    def register(self, value: str, entity_type: str) -> str:
        """Return the token for *value*, creating one if not yet seen."""
        if value in self._forward:
            return self._forward[value]

        self._counters[entity_type] += 1
        token = f"[{entity_type}_{self._counters[entity_type]}]"
        self._forward[value] = token
        self._reverse[token] = value
        return token

    def lookup(self, value: str) -> Optional[str]:
        return self._forward.get(value)

    def reverse_lookup(self, token: str) -> Optional[str]:
        return self._reverse.get(token)

    def register_alias(self, alias: str, token: str) -> None:
        """Map *alias* to an already-assigned *token* (e.g. first/last name surface forms)."""
        self._forward[alias] = token
        # Reverse map keeps the first mapping only (canonical → token is already set).
        self._reverse.setdefault(token, alias)

    def allocate_counter(self, entity_type: str) -> int:
        """Increment and return the counter for entity_type without creating a token."""
        self._counters[entity_type] += 1
        return self._counters[entity_type]

    def register_mask(self, value: str, masked_form: str) -> str:
        """Store value → masked_form in the forward map only (masked values are not restorable)."""
        self._forward[value] = masked_form
        return masked_form

    def to_dict(self) -> dict:
        return {
            "forward": dict(self._forward),
            "reverse": dict(self._reverse),
            "counters": dict(self._counters),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EntityRegistry":
        registry = cls()
        registry._forward = data.get("forward", {})
        registry._reverse = data.get("reverse", {})
        registry._counters = defaultdict(int, data.get("counters", {}))
        return registry
