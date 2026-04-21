"""LLM 스트리밍 버퍼 처리 테스트"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.llm import LLMClient, strip_thinking_tokens


@pytest.mark.asyncio
async def test_chat_stream_no_thinking_blocks():
    """thinking 블록이 없는 일반 응답을 정상 처리"""
    client = LLMClient()

    # Mock streaming response chunks
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content=" "))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="world"))]),
    ]

    with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        async def async_iter(items):
            for item in items:
                yield item

        mock_create.return_value = async_iter(mock_chunks)

        # Collect streamed tokens
        tokens = []
        async for token in client.chat_stream([{"role": "user", "content": "test"}]):
            tokens.append(token)

        # All tokens should be yielded without buffering delay
        assert len(tokens) > 0
        result = "".join(tokens)
        assert "Hello" in result
        assert "world" in result


@pytest.mark.asyncio
async def test_chat_stream_short_response():
    """짧은 응답도 모두 전송되는지 확인"""
    client = LLMClient()

    # Short response that's smaller than THINKING_START marker length
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Yes"))]),
    ]

    with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        async def async_iter(items):
            for item in items:
                yield item

        mock_create.return_value = async_iter(mock_chunks)

        tokens = []
        async for token in client.chat_stream([{"role": "user", "content": "test"}]):
            tokens.append(token)

        # Short response must be received
        result = "".join(tokens)
        assert result == "Yes", f"Expected 'Yes' but got '{result}'"


@pytest.mark.asyncio
async def test_chat_stream_with_thinking_block():
    """thinking 블록이 있는 응답에서 블록 제거"""
    client = LLMClient()

    # Response with thinking block
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="<|channel>"))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="thought\nI think"))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="<channel|>"))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="The answer is yes"))]),
    ]

    with patch.object(client._client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
        async def async_iter(items):
            for item in items:
                yield item

        mock_create.return_value = async_iter(mock_chunks)

        tokens = []
        async for token in client.chat_stream([{"role": "user", "content": "test"}]):
            tokens.append(token)

        result = "".join(tokens)
        # Thinking block should be removed
        assert "<|channel>" not in result
        assert "<channel|>" not in result
        assert "I think" not in result
        # Only actual answer remains
        assert "The answer is yes" in result


def test_strip_thinking_tokens():
    """thinking 블록 제거 함수 테스트"""
    text_with_thinking = "<|channel>thought\nthinking here\n<channel|>\nActual response"
    result = strip_thinking_tokens(text_with_thinking)

    assert "thinking" not in result
    assert "Actual response" in result
