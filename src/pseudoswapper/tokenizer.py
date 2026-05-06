from __future__ import annotations

from .detector import DetectedEntity
from .entity_registry import EntityRegistry


class Tokenizer:
    """Converts DetectedEntity spans into token assignments, owning the person entity model."""

    def __init__(self, registry: EntityRegistry) -> None:
        self._registry = registry

    def assign(self, entities: list[DetectedEntity]) -> dict[str, str]:
        """Return a mapping of original text → token for all detected entities."""
        token_map: dict[str, str] = {}
        for entity in entities:
            token = self._assign_one(entity)
            token_map[entity.text] = token
        return token_map

    def _assign_one(self, entity: DetectedEntity) -> str:
        if entity.entity_type == "PERSON":
            return self._assign_person(entity.text)
        existing = self._registry.lookup(entity.text)
        if existing:
            return existing
        return self._registry.register(entity.text, entity.entity_type)

    def _assign_person(self, name: str) -> str:
        existing = self._registry.lookup(name)
        if existing:
            return existing

        parts = name.split()
        if len(parts) >= 2:
            token = self._registry.register(name, "PERSON")
            # Derive surface-form tokens from the canonical token, e.g. [PERSON_1] → [PERSON_1_FIRST]
            base = token[:-1]  # strip trailing "]"
            first, last = parts[0], parts[-1]
            if not self._registry.lookup(first):
                self._registry.register_alias(first, f"{base}_FIRST]")
            if not self._registry.lookup(last):
                self._registry.register_alias(last, f"{base}_LAST]")
        else:
            token = self._registry.register(name, "PERSON")

        return token

    def assign_correlated(self, email: str, person_n: int) -> str:
        """Register an email correlated to a specific person entity (structured mode)."""
        token = f"[EMAIL_PERSON_{person_n}]"
        self._registry.register_alias(email, token)
        return token
