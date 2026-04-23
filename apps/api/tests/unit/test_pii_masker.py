"""PII 마스킹 서비스 단위 테스트 (TDD)"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.pii_masker import MaskResult, PIIEntity, PIIMasker


@pytest.fixture
def masker():
    return PIIMasker()


# ─── Regex: 전화번호 ──────────────────────────────────────────────────────────


class TestRegexPhone:
    def test_landline_seoul(self, masker):
        result = masker.mask_sync("02-1234-5678로 연락주세요")
        assert "[전화번호]" in result.masked_text
        assert "02-1234-5678" not in result.masked_text

    def test_landline_gyeonggi(self, masker):
        result = masker.mask_sync("031-999-8888에 전화하세요")
        assert "[전화번호]" in result.masked_text
        assert "031-999-8888" not in result.masked_text

    def test_landline_4digit(self, masker):
        result = masker.mask_sync("051-1234-5678 부산 번호입니다")
        assert "[전화번호]" in result.masked_text

    def test_mobile_010(self, masker):
        result = masker.mask_sync("010-9876-5432로 문자주세요")
        assert "[전화번호]" in result.masked_text
        assert "010-9876-5432" not in result.masked_text

    def test_mobile_011(self, masker):
        result = masker.mask_sync("구번호 011-123-4567입니다")
        assert "[전화번호]" in result.masked_text

    def test_mobile_016(self, masker):
        result = masker.mask_sync("016-777-8888로 연락")
        assert "[전화번호]" in result.masked_text

    def test_mobile_3digit_local(self, masker):
        result = masker.mask_sync("010-123-4567 단문형")
        assert "[전화번호]" in result.masked_text

    def test_entity_type_is_phone(self, masker):
        result = masker.mask_sync("010-1234-5678")
        assert any(e.type == "PHONE" for e in result.entities)

    def test_entity_original_preserved(self, masker):
        result = masker.mask_sync("010-1234-5678")
        phone_entity = next(e for e in result.entities if e.type == "PHONE")
        assert phone_entity.original == "010-1234-5678"


# ─── Regex: 이메일 ────────────────────────────────────────────────────────────


class TestRegexEmail:
    def test_basic_email(self, masker):
        result = masker.mask_sync("user@example.com으로 보내세요")
        assert "[이메일]" in result.masked_text
        assert "user@example.com" not in result.masked_text

    def test_email_with_dots(self, masker):
        result = masker.mask_sync("john.doe@company.co.kr")
        assert "[이메일]" in result.masked_text

    def test_email_with_plus(self, masker):
        result = masker.mask_sync("user+tag@gmail.com")
        assert "[이메일]" in result.masked_text

    def test_email_entity_type(self, masker):
        result = masker.mask_sync("test@test.com")
        assert any(e.type == "EMAIL" for e in result.entities)


# ─── Regex: 주민등록번호 ──────────────────────────────────────────────────────


class TestRegexSSN:
    def test_ssn_male(self, masker):
        result = masker.mask_sync("주민번호는 900101-1234567입니다")
        assert "[주민번호]" in result.masked_text
        assert "900101-1234567" not in result.masked_text

    def test_ssn_female(self, masker):
        result = masker.mask_sync("850315-2987654")
        assert "[주민번호]" in result.masked_text

    def test_ssn_entity_type(self, masker):
        result = masker.mask_sync("750101-1234567")
        assert any(e.type == "SSN" for e in result.entities)


# ─── Regex: 신용카드 ──────────────────────────────────────────────────────────


class TestRegexCard:
    def test_card_with_dashes(self, masker):
        result = masker.mask_sync("카드번호 1234-5678-9012-3456")
        assert "[카드번호]" in result.masked_text
        assert "1234-5678-9012-3456" not in result.masked_text

    def test_card_with_spaces(self, masker):
        result = masker.mask_sync("1234 5678 9012 3456")
        assert "[카드번호]" in result.masked_text

    def test_card_entity_type(self, masker):
        result = masker.mask_sync("1234-5678-9012-3456")
        assert any(e.type == "CARD" for e in result.entities)


# ─── Regex: 사업자등록번호 ────────────────────────────────────────────────────


class TestRegexBRN:
    def test_brn_basic(self, masker):
        result = masker.mask_sync("사업자번호 123-45-67890")
        assert "[사업자번호]" in result.masked_text
        assert "123-45-67890" not in result.masked_text

    def test_brn_entity_type(self, masker):
        result = masker.mask_sync("123-45-67890")
        assert any(e.type == "BRN" for e in result.entities)


# ─── 복합 PII ──────────────────────────────────────────────────────────────


class TestMixedPII:
    def test_phone_and_email_together(self, masker):
        result = masker.mask_sync("010-1111-2222 또는 user@test.com으로 연락")
        assert "[전화번호]" in result.masked_text
        assert "[이메일]" in result.masked_text
        assert "010-1111-2222" not in result.masked_text
        assert "user@test.com" not in result.masked_text

    def test_multiple_entities_counted(self, masker):
        result = masker.mask_sync("02-111-2222 그리고 031-333-4444")
        assert result.masked_text.count("[전화번호]") == 2

    def test_surrounding_text_preserved(self, masker):
        result = masker.mask_sync("안녕하세요. 010-1234-5678입니다. 감사합니다.")
        assert "안녕하세요" in result.masked_text
        assert "감사합니다" in result.masked_text


# ─── PII 없는 텍스트 ──────────────────────────────────────────────────────────


class TestNoPII:
    def test_clean_text_unchanged(self, masker):
        text = "RAG 시스템에서 문서를 검색하는 방법을 알려주세요."
        result = masker.mask_sync(text)
        assert result.masked_text == text

    def test_empty_entities_when_no_pii(self, masker):
        result = masker.mask_sync("이것은 일반 질문입니다.")
        assert result.entities == []

    def test_empty_string(self, masker):
        result = masker.mask_sync("")
        assert result.masked_text == ""
        assert result.entities == []


# ─── 타입 필터링 ──────────────────────────────────────────────────────────────


class TestTypeFiltering:
    def test_disabled_email_type_not_masked(self, masker):
        result = masker.mask_sync(
            "user@test.com",
            enabled_types=["PHONE", "SSN"],
        )
        assert "user@test.com" in result.masked_text
        assert "[이메일]" not in result.masked_text

    def test_only_phone_type_enabled(self, masker):
        result = masker.mask_sync(
            "010-1234-5678 그리고 user@test.com",
            enabled_types=["PHONE"],
        )
        assert "[전화번호]" in result.masked_text
        assert "user@test.com" in result.masked_text

    def test_none_types_masks_all(self, masker):
        result = masker.mask_sync(
            "010-1234-5678 그리고 user@test.com",
            enabled_types=None,
        )
        assert "[전화번호]" in result.masked_text
        assert "[이메일]" in result.masked_text


# ─── NER (이름·주소) — pipeline mock ────────────────────────────────────────
# monologg/koelectra-base-finetuned-naver-ner 모델은 HuggingFace pipeline을
# aggregation_strategy 없이(비집계 모드) 사용한다.
# 따라서 pipeline 반환값의 각 토큰은 "entity_group"(집계 모드)이 아닌
# "entity" 키를 가지며, 값은 BIO 태깅 형식이다:
#   B-<TAG> : 엔티티 시작 토큰 (Begin)
#   I-<TAG> : 엔티티 연속 토큰 (Inside)
# NAVER NER 태그 예시: PS(인물), LC(장소), OG(기관), DT(날짜) ...
# _apply_ner()는 B- 토큰에서 새 스팬을 열고, I- 토큰에서 스팬을 이어붙인다.
# 모든 mock은 이 형식을 따라야 한다 — entity_group 키를 쓰면 마스킹이 동작하지 않는다.


class TestNERMasking:
    def test_person_name_masked(self, masker):
        mock_pipeline = MagicMock()
        # B-PS: 인물(Person) 엔티티 시작 토큰 1개 (단일 토큰 이름)
        mock_pipeline.return_value = [
            {"entity": "B-PS", "word": "홍길동", "start": 5, "end": 8, "score": 0.99}
        ]
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("저는 홍길동입니다.")
        assert "[이름]" in result.masked_text
        assert "홍길동" not in result.masked_text

    def test_location_address_masked(self, masker):
        mock_pipeline = MagicMock()
        # 장소명이 2개 토큰으로 분리됨: B-LC(시작) + I-LC(연속)
        # 집계 모드였다면 entity_group="LC" 토큰 1개이지만,
        # 비집계 모드에서는 서브워드/어절 단위로 나뉘어 각각 B-/I- 태그를 갖는다.
        mock_pipeline.return_value = [
            {"entity": "B-LC", "word": "서울시", "start": 3, "end": 6, "score": 0.97},
            {"entity": "I-LC", "word": "강남구", "start": 7, "end": 10, "score": 0.96},
        ]
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("저는 서울시 강남구에 삽니다.")
        assert "[주소]" in result.masked_text

    def test_ner_entity_type_name(self, masker):
        mock_pipeline = MagicMock()
        # B-PS → _NER_TAG_MAP["PS"] → type="NAME" 으로 변환됨을 검증
        mock_pipeline.return_value = [
            {"entity": "B-PS", "word": "김철수", "start": 0, "end": 3, "score": 0.95}
        ]
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("김철수가 질문합니다.")
        assert any(e.type == "NAME" for e in result.entities)

    def test_ner_entity_original_preserved(self, masker):
        mock_pipeline = MagicMock()
        # MaskResult.entities 각 항목의 .original 필드에 마스킹 전 원문이 보존되는지 확인
        # (감사 로그, UI 표시 등에서 원문 복원이 필요한 경우를 위해)
        mock_pipeline.return_value = [
            {"entity": "B-PS", "word": "이영희", "start": 0, "end": 3, "score": 0.98}
        ]
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("이영희 고객님")
        name_entity = next(e for e in result.entities if e.type == "NAME")
        assert name_entity.original == "이영희"

    def test_ner_empty_result_no_mask(self, masker):
        mock_pipeline = MagicMock()
        # pipeline이 빈 리스트를 반환하면 원문 그대로 통과해야 한다
        mock_pipeline.return_value = []
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("일반 질문입니다.")
        assert result.masked_text == "일반 질문입니다."

    def test_ner_disabled_type_not_masked(self, masker):
        mock_pipeline = MagicMock()
        mock_pipeline.return_value = [
            {"entity": "B-PS", "word": "홍길동", "start": 0, "end": 3, "score": 0.99}
        ]
        # enabled_types에 NAME이 없으면 이름이 감지되어도 마스킹하지 않아야 한다
        with patch.object(masker, "_get_pipeline", return_value=mock_pipeline):
            result = masker.mask_sync("홍길동입니다", enabled_types=["PHONE", "EMAIL"])
        assert "홍길동" in result.masked_text


# ─── MaskResult 데이터 구조 ───────────────────────────────────────────────────


class TestMaskResultStructure:
    def test_mask_result_has_masked_text(self, masker):
        result = masker.mask_sync("010-1234-5678")
        assert hasattr(result, "masked_text")

    def test_mask_result_has_entities(self, masker):
        result = masker.mask_sync("010-1234-5678")
        assert hasattr(result, "entities")

    def test_pii_entity_fields(self, masker):
        result = masker.mask_sync("010-1234-5678")
        entity = result.entities[0]
        assert hasattr(entity, "type")
        assert hasattr(entity, "original")
        assert hasattr(entity, "masked")
        assert hasattr(entity, "start")
        assert hasattr(entity, "end")


# ─── async mask() ─────────────────────────────────────────────────────────────


class TestAsyncMask:
    @pytest.mark.asyncio
    async def test_async_mask_returns_mask_result(self, masker):
        result = await masker.mask("010-1234-5678")
        assert isinstance(result, MaskResult)

    @pytest.mark.asyncio
    async def test_async_mask_same_result_as_sync(self, masker):
        text = "user@example.com"
        sync_result = masker.mask_sync(text)
        async_result = await masker.mask(text)
        assert sync_result.masked_text == async_result.masked_text
