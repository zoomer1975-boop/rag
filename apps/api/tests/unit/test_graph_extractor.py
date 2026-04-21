"""Phase 2 RED: GraphExtractor — LLM으로 청크에서 엔티티/관계를 추출.

LLM은 모킹한다. 실제 LLM 호출은 E2E에서 검증.
"""

import json
from unittest.mock import AsyncMock

import pytest


@pytest.mark.unit
class TestExtractionDataclasses:
    def test_extracted_entity_is_immutable(self):
        from app.services.graph_extractor import ExtractedEntity

        e = ExtractedEntity(name="서울시청", entity_type="organization", description="서울의 행정기관")
        with pytest.raises((AttributeError, Exception)):
            e.name = "다른값"  # type: ignore[misc]

    def test_extracted_relationship_has_keywords_tuple(self):
        from app.services.graph_extractor import ExtractedRelationship

        r = ExtractedRelationship(
            source="A",
            target="B",
            description="A는 B의 상위 기관이다",
            keywords=("계층", "행정"),
            weight=0.9,
        )
        assert r.keywords == ("계층", "행정")
        assert r.weight == 0.9


@pytest.mark.unit
class TestGraphExtractorHappyPath:
    @pytest.mark.asyncio
    async def test_extracts_entities_and_relationships_from_text(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = json.dumps(
            {
                "entities": [
                    {"name": "서울시청", "type": "organization", "description": "서울의 행정 본청"},
                    {"name": "박원순", "type": "person", "description": "전 서울시장"},
                ],
                "relationships": [
                    {
                        "source": "박원순",
                        "target": "서울시청",
                        "description": "박원순은 서울시청의 시장이었다",
                        "keywords": ["리더십", "행정"],
                        "weight": 0.9,
                    }
                ],
            },
            ensure_ascii=False,
        )

        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("박원순은 서울시청의 시장이었다.")

        assert len(result.entities) == 2
        names = {e.name for e in result.entities}
        assert names == {"서울시청", "박원순"}
        assert all(e.entity_type in {"organization", "person"} for e in result.entities)

        assert len(result.relationships) == 1
        rel = result.relationships[0]
        assert rel.source == "박원순"
        assert rel.target == "서울시청"
        assert rel.keywords == ("리더십", "행정")
        assert 0.0 <= rel.weight <= 1.0

    @pytest.mark.asyncio
    async def test_llm_called_with_json_instruction(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = json.dumps({"entities": [], "relationships": []})

        extractor = GraphExtractor(llm_client=llm)
        await extractor.extract("샘플 텍스트")

        call_args = llm.chat.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        combined = " ".join(m.get("content", "") for m in messages).lower()
        assert "json" in combined
        assert "샘플 텍스트" in " ".join(m.get("content", "") for m in messages)


@pytest.mark.unit
class TestGraphExtractorTolerance:
    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty_result(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = "이건 JSON이 아니다 {broken"

        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("아무 텍스트")

        assert result.entities == ()
        assert result.relationships == ()

    @pytest.mark.asyncio
    async def test_json_wrapped_in_code_fence_is_parsed(self):
        from app.services.graph_extractor import GraphExtractor

        payload = {
            "entities": [{"name": "A", "type": "concept", "description": "desc"}],
            "relationships": [],
        }
        llm = AsyncMock()
        llm.chat.return_value = f"```json\n{json.dumps(payload)}\n```"

        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("x")

        assert len(result.entities) == 1
        assert result.entities[0].name == "A"

    @pytest.mark.asyncio
    async def test_empty_text_skips_llm_call(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("   ")

        assert result.entities == ()
        assert result.relationships == ()
        llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_fields_use_defaults(self):
        """LLM이 일부 필드를 누락해도 추출이 실패하지 않는다."""
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = json.dumps(
            {
                "entities": [
                    {"name": "A", "type": "concept"},
                    {"name": "B", "type": "concept"},
                ],
                "relationships": [
                    {"source": "A", "target": "B", "description": "관계"},
                ],
            }
        )
        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("텍스트")

        assert len(result.entities) == 2
        assert result.entities[0].description == ""

        assert len(result.relationships) == 1
        assert result.relationships[0].keywords == ()
        assert result.relationships[0].weight == 1.0  # 기본값

    @pytest.mark.asyncio
    async def test_invalid_relationship_refs_are_dropped(self):
        """relationships의 source/target이 entities에 없으면 제외된다."""
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = json.dumps(
            {
                "entities": [
                    {"name": "A", "type": "concept", "description": "a"},
                    {"name": "B", "type": "concept", "description": "b"},
                ],
                "relationships": [
                    {"source": "A", "target": "B", "description": "valid"},
                    {"source": "A", "target": "UNKNOWN", "description": "dangling"},
                ],
            }
        )
        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("x")

        assert len(result.entities) == 2
        assert len(result.relationships) == 1
        assert result.relationships[0].description == "valid"

    @pytest.mark.asyncio
    async def test_llm_exception_returns_empty_result(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.side_effect = RuntimeError("LLM down")

        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("텍스트")

        assert result.entities == ()
        assert result.relationships == ()

    @pytest.mark.asyncio
    async def test_duplicate_entity_names_are_merged_by_name_type(self):
        from app.services.graph_extractor import GraphExtractor

        llm = AsyncMock()
        llm.chat.return_value = json.dumps(
            {
                "entities": [
                    {"name": "서울", "type": "location", "description": "대한민국 수도"},
                    {"name": "서울", "type": "location", "description": "중복"},
                ],
                "relationships": [],
            }
        )
        extractor = GraphExtractor(llm_client=llm)
        result = await extractor.extract("x")

        assert len(result.entities) == 1
