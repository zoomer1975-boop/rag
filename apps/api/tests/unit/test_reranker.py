"""RerankerService 단위 테스트"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.reranker import RerankerService, get_reranker_service


def _make_chunks(scores_and_contents: list[tuple[float, str]]) -> list[dict]:
    return [
        {"id": i, "content": content, "score": 1.0, "metadata": {}}
        for i, (_, content) in enumerate(scores_and_contents)
    ]


@pytest.fixture()
def mock_cross_encoder():
    with patch("app.services.reranker.RerankerService.__init__", return_value=None):
        svc = RerankerService.__new__(RerankerService)
        svc._model = MagicMock()
        svc._model_name = "test-model"
        yield svc


def test_compute_sorts_descending(mock_cross_encoder):
    chunks = _make_chunks([(0.9, "best"), (0.2, "worst"), (0.6, "mid")])
    mock_cross_encoder._model.predict.return_value = np.array([0.9, 0.2, 0.6])

    result = mock_cross_encoder._compute("query", chunks, top_n=3)

    assert [r["content"] for r in result] == ["best", "mid", "worst"]


def test_compute_returns_actual_scores(mock_cross_encoder):
    chunks = _make_chunks([(0.8, "a"), (0.3, "b")])
    mock_cross_encoder._model.predict.return_value = np.array([0.8, 0.3])

    result = mock_cross_encoder._compute("q", chunks, top_n=2)

    assert abs(result[0]["score"] - 0.8) < 1e-6
    assert abs(result[1]["score"] - 0.3) < 1e-6


def test_compute_truncates_to_top_n(mock_cross_encoder):
    chunks = _make_chunks([(0.9, "a"), (0.7, "b"), (0.5, "c"), (0.3, "d")])
    mock_cross_encoder._model.predict.return_value = np.array([0.9, 0.7, 0.5, 0.3])

    result = mock_cross_encoder._compute("q", chunks, top_n=2)

    assert len(result) == 2
    assert result[0]["content"] == "a"
    assert result[1]["content"] == "b"


def test_compute_replaces_original_score(mock_cross_encoder):
    chunks = [{"id": 0, "content": "text", "score": 1.0, "metadata": {}}]
    mock_cross_encoder._model.predict.return_value = np.array([0.42])

    result = mock_cross_encoder._compute("q", chunks, top_n=1)

    assert abs(result[0]["score"] - 0.42) < 1e-6


def test_compute_preserves_other_fields(mock_cross_encoder):
    chunks = [{"id": 7, "content": "hello", "score": 1.0, "metadata": {"title": "doc"}}]
    mock_cross_encoder._model.predict.return_value = np.array([0.55])

    result = mock_cross_encoder._compute("q", chunks, top_n=1)

    assert result[0]["id"] == 7
    assert result[0]["metadata"] == {"title": "doc"}


@pytest.mark.asyncio
async def test_rerank_empty_returns_empty(mock_cross_encoder):
    result = await mock_cross_encoder.rerank("q", [], top_n=3)
    assert result == []
    mock_cross_encoder._model.predict.assert_not_called()


@pytest.mark.asyncio
async def test_rerank_calls_compute_in_executor(mock_cross_encoder):
    chunks = _make_chunks([(0.9, "a"), (0.5, "b")])
    mock_cross_encoder._model.predict.return_value = np.array([0.9, 0.5])

    result = await mock_cross_encoder.rerank("q", chunks, top_n=2)

    assert len(result) == 2
    assert result[0]["score"] > result[1]["score"]


def test_get_reranker_service_returns_none_when_disabled():
    mock_settings = MagicMock()
    mock_settings.reranker_enabled = False
    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.services.reranker._load_reranker") as mock_load,
    ):
        result = get_reranker_service()

    assert result is None
    mock_load.assert_not_called()


def test_get_reranker_service_loads_model_when_enabled():
    mock_settings = MagicMock()
    mock_settings.reranker_enabled = True
    mock_settings.reranker_model = "test-model"
    mock_settings.reranker_device = "cpu"
    with (
        patch("app.config.get_settings", return_value=mock_settings),
        patch("app.services.reranker._load_reranker") as mock_load,
    ):
        mock_load.return_value = MagicMock(spec=RerankerService)
        result = get_reranker_service()

    mock_load.assert_called_once_with("test-model", "cpu")
    assert result is mock_load.return_value
