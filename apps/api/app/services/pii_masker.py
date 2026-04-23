"""PII 마스킹 서비스 — regex + NER (klue/bert-base)"""

import asyncio
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from app.config import get_settings


@dataclass
class PIIEntity:
    type: str
    original: str
    masked: str
    start: int
    end: int


@dataclass
class MaskResult:
    masked_text: str
    entities: list[PIIEntity] = field(default_factory=list)


_REGEX_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("SSN",   re.compile(r"\d{6}-[1-4]\d{6}"),                              "[주민번호]"),
    ("CARD",  re.compile(r"\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}"),          "[카드번호]"),
    ("BRN",   re.compile(r"\d{3}-\d{2}-\d{5}"),                             "[사업자번호]"),
    ("PHONE", re.compile(r"(?:02|0[3-9]\d)-\d{3,4}-\d{4}"),                 "[전화번호]"),
    ("PHONE", re.compile(r"01[016789]-\d{3,4}-\d{4}"),                      "[전화번호]"),
    ("EMAIL", re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[이메일]"),
]

_NER_TAG_MAP = {
    "PS": ("[이름]",   "NAME"),
    "LC": ("[주소]",   "ADDRESS"),
    "OG": ("[기관명]", "ORG"),
}


class PIIMasker:
    _pipeline_instance: Any = None
    _pipeline_loaded: bool = False

    def _get_pipeline(self) -> Any:
        if not PIIMasker._pipeline_loaded:
            try:
                from transformers import pipeline  # type: ignore
                settings = get_settings()
                PIIMasker._pipeline_instance = pipeline(
                    "token-classification",
                    model=settings.pii_ner_model,
                    device=settings.pii_ner_device,
                    aggregation_strategy="simple",
                )
            except Exception:
                PIIMasker._pipeline_instance = None
            PIIMasker._pipeline_loaded = True
        return PIIMasker._pipeline_instance

    def _apply_regex(
        self,
        text: str,
        enabled_types: list[str] | None,
    ) -> tuple[str, list[PIIEntity]]:
        entities: list[PIIEntity] = []
        offset = 0
        result = text

        for ptype, pattern, label in _REGEX_PATTERNS:
            if enabled_types is not None and ptype not in enabled_types:
                continue
            new_result = ""
            new_offset = 0
            for m in pattern.finditer(result):
                start_in_result = m.start()
                end_in_result = m.end()
                original = m.group()
                abs_start = offset + start_in_result
                abs_end = offset + end_in_result
                entities.append(PIIEntity(
                    type=ptype,
                    original=original,
                    masked=label,
                    start=abs_start,
                    end=abs_end,
                ))
                new_result += result[new_offset:start_in_result] + label
                shift = len(label) - (end_in_result - start_in_result)
                new_offset = end_in_result
            new_result += result[new_offset:]
            result = new_result if new_offset else result

        return result, entities

    def _apply_regex_v2(
        self,
        text: str,
        enabled_types: list[str] | None,
    ) -> tuple[str, list[PIIEntity]]:
        """Single-pass replacement tracking absolute positions in original text."""
        # Collect all matches with original-text positions
        matches: list[tuple[int, int, str, str, str]] = []  # start, end, original, label, type
        for ptype, pattern, label in _REGEX_PATTERNS:
            if enabled_types is not None and ptype not in enabled_types:
                continue
            for m in pattern.finditer(text):
                matches.append((m.start(), m.end(), m.group(), label, ptype))

        # Sort by start position, resolve overlaps (first match wins)
        matches.sort(key=lambda x: x[0])
        non_overlapping: list[tuple[int, int, str, str, str]] = []
        last_end = 0
        for m in matches:
            if m[0] >= last_end:
                non_overlapping.append(m)
                last_end = m[1]

        entities: list[PIIEntity] = []
        result_parts: list[str] = []
        cursor = 0
        for start, end, original, label, ptype in non_overlapping:
            result_parts.append(text[cursor:start])
            result_parts.append(label)
            entities.append(PIIEntity(
                type=ptype,
                original=original,
                masked=label,
                start=start,
                end=end,
            ))
            cursor = end
        result_parts.append(text[cursor:])

        return "".join(result_parts), entities

    def _apply_ner(
        self,
        text: str,
        enabled_types: list[str] | None,
    ) -> tuple[str, list[PIIEntity]]:
        pipeline = self._get_pipeline()
        if pipeline is None:
            return text, []

        raw_entities = pipeline(text)
        if not raw_entities:
            return text, []

        # Filter by enabled_types
        ner_type_keys = set(_NER_TAG_MAP.keys())
        filtered = []
        for ent in raw_entities:
            tag = ent.get("entity_group", "")
            if tag not in ner_type_keys:
                continue
            _, mapped_type = _NER_TAG_MAP[tag]
            if enabled_types is not None and mapped_type not in enabled_types:
                continue
            filtered.append(ent)

        if not filtered:
            return text, []

        # Sort by start descending for safe in-place replacement
        filtered.sort(key=lambda x: x["start"], reverse=True)
        entities: list[PIIEntity] = []
        result = text
        for ent in filtered:
            tag = ent["entity_group"]
            label, mapped_type = _NER_TAG_MAP[tag]
            start: int = ent["start"]
            end: int = ent["end"]
            original = ent["word"]
            result = result[:start] + label + result[end:]
            entities.append(PIIEntity(
                type=mapped_type,
                original=original,
                masked=label,
                start=start,
                end=end,
            ))

        entities.sort(key=lambda e: e.start)
        return result, entities

    def mask_sync(
        self,
        text: str,
        enabled_types: list[str] | None = None,
    ) -> MaskResult:
        if not text:
            return MaskResult(masked_text=text, entities=[])

        regex_text, regex_entities = self._apply_regex_v2(text, enabled_types)

        ner_enabled = enabled_types is None or bool(
            {"NAME", "ADDRESS"} & set(enabled_types)
        )
        if ner_enabled:
            final_text, ner_entities = self._apply_ner(regex_text, enabled_types)
        else:
            final_text, ner_entities = regex_text, []

        return MaskResult(
            masked_text=final_text,
            entities=regex_entities + ner_entities,
        )

    async def mask(
        self,
        text: str,
        enabled_types: list[str] | None = None,
    ) -> MaskResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.mask_sync(text, enabled_types)
        )
