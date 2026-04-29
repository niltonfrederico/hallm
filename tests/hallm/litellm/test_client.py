"""Tests for hallm.litellm.client — unit (mocked) and integration (real APIs)."""

from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from hallm.litellm.client import complete
from hallm.litellm.client import stream
from hallm.litellm.models import CLAUDE_OPUS
from hallm.litellm.models import CLAUDE_SONNET
from hallm.litellm.models import GEMINI_FLASH
from hallm.litellm.models import GEMINI_PRO
from hallm.litellm.models import GITHUB_COPILOT_GPT4O
from hallm.litellm.models import GITHUB_COPILOT_O1_REASONING
from hallm.litellm.models import ModelConfig

MESSAGES = [{"role": "user", "content": "ping"}]

ALL_MODELS = [
    pytest.param(GEMINI_FLASH, id="gemini-flash"),
    pytest.param(GEMINI_PRO, id="gemini-pro"),
    pytest.param(CLAUDE_SONNET, id="claude-sonnet"),
    pytest.param(CLAUDE_OPUS, id="claude-opus"),
    pytest.param(GITHUB_COPILOT_GPT4O, id="copilot-gpt4o"),
    pytest.param(GITHUB_COPILOT_O1_REASONING, id="copilot-o1"),
]


def _make_response(content: str = "pong") -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = content
    return response


def _make_stream_chunk(content: str | None) -> MagicMock:
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    return chunk


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ALL_MODELS)
class TestComplete:
    async def test_calls_acompletion_with_correct_model(self, model: ModelConfig) -> None:
        mock_response = _make_response()
        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await complete(MESSAGES, model=model)

        mock.assert_awaited_once()
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == model.model
        assert result is mock_response

    async def test_passes_api_key_from_env(self, model: ModelConfig, monkeypatch) -> None:
        monkeypatch.setenv(model.api_key_env, "test-key-123")
        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = _make_response()
            await complete(MESSAGES, model=model)

        assert mock.call_args.kwargs["api_key"] == "test-key-123"

    async def test_passes_api_base_when_set(self, model: ModelConfig) -> None:
        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = _make_response()
            await complete(MESSAGES, model=model)

        call_kwargs = mock.call_args.kwargs
        if model.api_base:
            assert call_kwargs["api_base"] == model.api_base
        else:
            assert "api_base" not in call_kwargs

    async def test_forwards_extra_kwargs(self, model: ModelConfig) -> None:
        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = _make_response()
            await complete(MESSAGES, model=model, temperature=0.5, max_tokens=100)

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 100


async def test_uses_settings_model_when_no_model_given(monkeypatch) -> None:
    monkeypatch.setattr("hallm.litellm.client.settings.litellm_model", "openai/gpt-4o-mini")
    with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value = _make_response()
        await complete(MESSAGES)

    assert mock.call_args.kwargs["model"] == "openai/gpt-4o-mini"


@pytest.mark.parametrize("model", ALL_MODELS)
class TestStream:
    async def test_calls_acompletion_with_stream_true(self, model: ModelConfig) -> None:
        chunks = [_make_stream_chunk("po"), _make_stream_chunk("ng"), _make_stream_chunk(None)]

        async def _fake_aiter():
            for chunk in chunks:
                yield chunk

        mock_response = _fake_aiter()

        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            _ = [chunk async for chunk in stream(MESSAGES, model=model)]

        assert mock.call_args.kwargs["stream"] is True

    async def test_yields_non_none_deltas(self, model: ModelConfig) -> None:
        chunks = [_make_stream_chunk("po"), _make_stream_chunk("ng"), _make_stream_chunk(None)]

        async def _fake_aiter():
            for chunk in chunks:
                yield chunk

        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = _fake_aiter()
            result = [chunk async for chunk in stream(MESSAGES, model=model)]

        assert result == ["po", "ng"]

    async def test_passes_correct_model_and_api_key(self, model: ModelConfig, monkeypatch) -> None:
        monkeypatch.setenv(model.api_key_env, "stream-key")

        async def _fake_aiter():
            return
            yield  # make it an async generator

        with patch("hallm.litellm.client.litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.return_value = _fake_aiter()
            _ = [c async for c in stream(MESSAGES, model=model)]

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == model.model
        assert call_kwargs["api_key"] == "stream-key"


# ---------------------------------------------------------------------------
# Integration tests  (skipped unless -m integration)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("model", ALL_MODELS)
class TestCompleteIntegration:
    async def test_returns_non_empty_response(self, model: ModelConfig) -> None:
        result = await complete(MESSAGES, model=model)
        content = result.choices[0].message.content
        assert isinstance(content, str) and content.strip()

    async def test_extra_kwargs_accepted(self, model: ModelConfig) -> None:
        result = await complete(MESSAGES, model=model, max_tokens=200)
        assert result.choices[0].message.content


@pytest.mark.integration
@pytest.mark.parametrize("model", ALL_MODELS)
class TestStreamIntegration:
    async def test_yields_chunks(self, model: ModelConfig) -> None:
        chunks: list[str] = []
        async for chunk in stream(MESSAGES, model=model):
            chunks.append(chunk)
        assert chunks, "expected at least one streamed chunk"

    async def test_chunks_are_strings(self, model: ModelConfig) -> None:
        async for chunk in stream(MESSAGES, model=model):
            assert isinstance(chunk, str)
