from __future__ import annotations

from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .recognizers import CompanyTermsRecognizer, EmployeeRecognizer

_SUPPORTED_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "IP_ADDRESS",
    "DOMAIN_NAME",
    "URL",
    "ORGANIZATION",
    "LOCATION",
    "COMPANY",
    "CREDIT_CARD",
]

# Additional entity types active only in redact mode.
_REDACT_EXTRA_ENTITIES = ["MONEY", "IBAN_CODE", "MAC_ADDRESS"]

# Map Presidio entity type names to our internal token-type names.
_ENTITY_TYPE_MAP: dict[str, str] = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IP_ADDRESS": "IP",
    "DOMAIN_NAME": "DOMAIN",
    "URL": "URL",
    "ORGANIZATION": "ORG",
    "LOCATION": "LOC",
    "COMPANY": "COMPANY",
    "CREDIT_CARD": "CREDIT_CARD",
    "MONEY":       "AMOUNT",
    "IBAN_CODE":   "IBAN_CODE",
    "MAC_ADDRESS": "MAC_ADDRESS",
}


@dataclass
class DetectedEntity:
    entity_type: str  # internal token type, e.g. "PERSON", "EMAIL"
    text: str         # original text span
    start: int
    end: int
    score: float


def _build_engine(config: dict, redact_mode: bool = False) -> AnalyzerEngine:
    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    })
    nlp_engine = provider.create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    company_terms = config.get("company_terms", [])
    if company_terms:
        engine.registry.add_recognizer(CompanyTermsRecognizer(company_terms))

    employees = config.get("employees", [])
    if employees:
        engine.registry.add_recognizer(EmployeeRecognizer(employees))

    if redact_mode:
        from .recognizers import AmountRecognizer
        engine.registry.add_recognizer(AmountRecognizer())

    return engine


class Detector:
    """Wraps Presidio AnalyzerEngine. Call analyze(text) to get detected entities."""

    def __init__(self, config: dict, redact_mode: bool = False) -> None:
        self._engine = _build_engine(config, redact_mode=redact_mode)
        self._exclude: set[str] = {
            t.lower() for t in config.get("exclude_terms", [])
        }
        self._entities = (
            _SUPPORTED_ENTITIES + _REDACT_EXTRA_ENTITIES if redact_mode else _SUPPORTED_ENTITIES
        )

    def analyze(self, text: str) -> list[DetectedEntity]:
        raw = self._engine.analyze(
            text=text,
            language="en",
            entities=self._entities,
            allow_list=list(self._exclude) if self._exclude else None,
        )

        # Remove overlapping spans: keep highest-score winner for each character position.
        raw_sorted = sorted(raw, key=lambda r: (r.score, r.end - r.start), reverse=True)
        accepted: list = []
        covered: set[int] = set()
        for result in raw_sorted:
            span = set(range(result.start, result.end))
            if span & covered:
                continue
            accepted.append(result)
            covered |= span

        entities: list[DetectedEntity] = []
        for result in accepted:
            internal_type = _ENTITY_TYPE_MAP.get(result.entity_type, result.entity_type)
            span_text = text[result.start:result.end]
            if span_text.lower() in self._exclude:
                continue
            entities.append(
                DetectedEntity(
                    entity_type=internal_type,
                    text=span_text,
                    start=result.start,
                    end=result.end,
                    score=result.score,
                )
            )

        return entities
