"""greeting 자동 번역 서비스 단위 테스트 (TDD - RED 단계)"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.greeting_translator import GreetingTranslator


class TestGreetingTranslatorCacheHit:
    """Redis 캐시에 번역이 있으면 LLM을 호출하지 않는다."""

    @pytest.mark.asyncio
    async def test_returns_cached_translation(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "Hello! How can I help you?"
        mock_llm = AsyncMock()

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(
            text="안녕하세요! 무엇을 도와드릴까요?",
            target_lang="en",
        )

        assert result == "Hello! How can I help you?"
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_key_includes_text_hash_and_lang(self):
        """캐시 키는 원문 해시 + target_lang 조합이어야 한다."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "Bonjour!"
        mock_llm = AsyncMock()

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        await translator.translate(text="안녕하세요!", target_lang="fr")

        called_key = mock_redis.get.call_args[0][0]
        assert "fr" in called_key
        assert called_key.startswith("greeting:translate:")


class TestGreetingTranslatorCacheMiss:
    """캐시 미스 시 LLM으로 번역하고 결과를 캐싱한다."""

    @pytest.mark.asyncio
    async def test_calls_llm_when_cache_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "Hello! How can I help you?"

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(
            text="안녕하세요! 무엇을 도와드릴까요?",
            target_lang="en",
        )

        assert result == "Hello! How can I help you?"
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_stores_translation_in_cache(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "Bonjour!"

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        await translator.translate(text="안녕하세요!", target_lang="fr")

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        # key, value, ex= 형태 확인
        assert call_args[0][1] == "Bonjour!"
        assert "ex" in call_args[1]  # TTL 설정됨

    @pytest.mark.asyncio
    async def test_llm_prompt_contains_target_language(self):
        """LLM 프롬프트에 target_lang 이름이 포함되어야 한다."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "こんにちは！"

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        await translator.translate(text="Hello!", target_lang="ja")

        messages = mock_llm.chat.call_args[0][0]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "ja" in full_prompt.lower() or "japan" in full_prompt.lower()

    @pytest.mark.asyncio
    async def test_llm_prompt_contains_original_text(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "Hola!"

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        await translator.translate(text="Hello!", target_lang="es")

        messages = mock_llm.chat.call_args[0][0]
        full_prompt = " ".join(m["content"] for m in messages)
        assert "Hello!" in full_prompt


class TestGreetingTranslatorSameLang:
    """원문과 target_lang이 같으면 번역 없이 원문을 반환한다."""

    @pytest.mark.asyncio
    async def test_same_lang_returns_original(self):
        mock_redis = AsyncMock()
        mock_llm = AsyncMock()

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(
            text="안녕하세요!",
            target_lang="ko",
            source_lang="ko",
        )

        assert result == "안녕하세요!"
        mock_llm.chat.assert_not_called()
        mock_redis.get.assert_not_called()


class TestGreetingTranslatorFallback:
    """LLM 오류나 Redis 오류 시 원문을 반환한다."""

    @pytest.mark.asyncio
    async def test_llm_error_returns_original(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = None
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM unavailable")

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(text="안녕하세요!", target_lang="en")

        assert result == "안녕하세요!"

    @pytest.mark.asyncio
    async def test_redis_error_still_calls_llm(self):
        """Redis 오류 시 캐시 없이 LLM 번역을 시도한다."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "Hello!"

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(text="안녕하세요!", target_lang="en")

        assert result == "Hello!"
        mock_llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self):
        mock_redis = AsyncMock()
        mock_llm = AsyncMock()

        translator = GreetingTranslator(redis=mock_redis, llm=mock_llm)
        result = await translator.translate(text="", target_lang="en")

        assert result == ""
        mock_llm.chat.assert_not_called()
