from __future__ import annotations

import re

from .detector import DetectedEntity
from .entity_registry import EntityRegistry

# These types are always tokenized or masked — no passthrough config or CLI flag can bypass them.
PROTECTED_TYPES: frozenset[str] = frozenset({"PERSON", "EMAIL", "COMPANY", "ORG", "CREDIT_CARD"})


class Tokenizer:
    """Converts DetectedEntity spans into token or mask assignments, owning the person entity model."""

    def __init__(
        self,
        registry: EntityRegistry,
        passthrough_types: set[str] | None = None,
        masking_rules: dict | None = None,
    ) -> None:
        self._registry = registry
        # Silently drop any attempt to passthrough a protected type.
        self._passthrough: frozenset[str] = frozenset(
            t for t in (passthrough_types or set()) if t not in PROTECTED_TYPES
        )
        self._masking_rules: dict = masking_rules or {}

    def assign(self, entities: list[DetectedEntity]) -> dict[str, str]:
        """Return a mapping of original text → token/mask for all detected entities.

        Entities whose type is in the passthrough set are left unreplaced.
        """
        token_map: dict[str, str] = {}
        for entity in entities:
            if entity.entity_type in self._passthrough:
                continue
            token_map[entity.text] = self._assign_one(entity)
        return token_map

    def _assign_one(self, entity: DetectedEntity) -> str:
        if entity.entity_type == "PERSON":
            return self._assign_person(entity.text)
        if entity.entity_type == "CREDIT_CARD" and "CREDIT_CARD" in self._masking_rules:
            return self._mask_credit_card(entity.text, self._masking_rules["CREDIT_CARD"])
        existing = self._registry.lookup(entity.text)
        if existing:
            return existing
        return self._registry.register(entity.text, entity.entity_type)

    def _assign_person(self, name: str) -> str:
        if "PERSON" in self._masking_rules:
            return self._assign_person_masked(name)
        return self._assign_person_tokenized(name)

    def _assign_person_tokenized(self, name: str) -> str:
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

    def _assign_person_masked(self, name: str) -> str:
        """Mask a person name as {n}_{initials}, e.g. 'John Doe' → '5_J.D.'"""
        existing = self._registry.lookup(name)
        if existing:
            return existing

        n = self._registry.allocate_counter("PERSON")
        parts = name.split()
        initials = ".".join(p[0].upper() for p in parts) + "."
        masked = f"{n}_{initials}"
        self._registry.register_mask(name, masked)

        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            if not self._registry.lookup(first):
                self._registry.register_mask(first, f"{n}_{first[0].upper()}.")
            if not self._registry.lookup(last):
                self._registry.register_mask(last, f"{n}_{last[0].upper()}.")

        return masked

    def _mask_credit_card(self, pan: str, rule: dict) -> str:
        """Mask a PAN keeping first/last digits, e.g. '4111111111111111' → '411111XXXXXX1111'."""
        existing = self._registry.lookup(pan)
        if existing:
            return existing

        digits = re.sub(r"\D", "", pan)
        keep_first: int = rule.get("keep_first", 6)
        keep_last: int = rule.get("keep_last", 4)
        fill_char: str = rule.get("fill_char", "X")

        total = len(digits)
        middle = max(0, total - keep_first - keep_last)
        if total <= keep_first + keep_last:
            masked = fill_char * total
        else:
            masked = digits[:keep_first] + fill_char * middle + digits[-keep_last:]

        self._registry.register_mask(pan, masked)
        return masked

    def assign_correlated(self, email: str, person_n: int) -> str:
        """Register an email correlated to a specific person entity (structured mode)."""
        token = f"[EMAIL_PERSON_{person_n}]"
        self._registry.register_alias(email, token)
        return token
