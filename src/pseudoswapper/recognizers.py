from __future__ import annotations

import re
from typing import Optional

from presidio_analyzer import PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


class CompanyTermsRecognizer(PatternRecognizer):
    """Exact-match recognizer for company_terms from config. Highest priority."""

    ENTITY_TYPE = "COMPANY"

    def __init__(self, terms: list[str]) -> None:
        self._terms = terms
        # PatternRecognizer requires at least one pattern; supply a placeholder
        # that will never match — actual detection happens in load_predefined_patterns_and_deny_list.
        super().__init__(
            supported_entity=self.ENTITY_TYPE,
            deny_list=terms,
            deny_list_score=0.99,
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> list[RecognizerResult]:
        if self.ENTITY_TYPE not in entities:
            return []
        results: list[RecognizerResult] = []
        for term in self._terms:
            if not term:
                continue
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for m in pattern.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY_TYPE,
                        start=m.start(),
                        end=m.end(),
                        score=0.99,
                    )
                )
        return results


class EmployeeRecognizer(PatternRecognizer):
    """Exact-match recognizer for employee full names and usernames from config."""

    ENTITY_TYPE = "PERSON"

    def __init__(self, employees: list[dict]) -> None:
        self._terms: list[str] = []
        for emp in employees:
            if emp.get("full_name"):
                self._terms.append(emp["full_name"])
            if emp.get("username"):
                self._terms.append(emp["username"])
        super().__init__(
            supported_entity=self.ENTITY_TYPE,
            deny_list=self._terms or ["__NEVER_MATCH__"],
            deny_list_score=0.95,
        )

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> list[RecognizerResult]:
        if self.ENTITY_TYPE not in entities:
            return []
        results: list[RecognizerResult] = []
        for term in self._terms:
            if not term:
                continue
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            for m in pattern.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type=self.ENTITY_TYPE,
                        start=m.start(),
                        end=m.end(),
                        score=0.95,
                    )
                )
        return results
