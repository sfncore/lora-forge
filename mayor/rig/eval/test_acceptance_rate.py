"""Tests for offline acceptance rate evaluation."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch

from mayor.rig.eval.acceptance_rate import (
    AcceptanceResult,
    EvalReport,
    EvalSample,
    compute_acceptance_greedy,
    compute_acceptance_stochastic,
    evaluate_acceptance_rate,
    load_eval_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_eval_data(tmp_path: Path) -> Path:
    """Create a temporary eval JSONL file."""
    samples = [
        {
            "input_ids": [1, 2, 3],
            "target_token_ids": [4, 5, 6],
            "target_logprobs": None,
            "role": "mayor",
            "sample_id": "s001",
        },
        {
            "input_ids": [10, 20],
            "target_token_ids": [30, 40, 50],
            "role": "witness",
            "sample_id": "s002",
        },
        {
            "input_ids": [7, 8, 9],
            "target_token_ids": [10, 11],
            "target_logprobs": [
                [0.0] * 100,  # uniform-ish logprobs
                [0.0] * 100,
            ],
            "role": "mayor",
            "sample_id": "s003",
        },
    ]
    path = tmp_path / "eval.jsonl"
    with open(path, "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")
    return path


@pytest.fixture
def eval_samples() -> list[EvalSample]:
    return [
        EvalSample(
            input_ids=[1, 2, 3],
            target_token_ids=[4, 5, 6],
            target_logprobs=None,
            role="mayor",
            sample_id="s001",
        ),
        EvalSample(
            input_ids=[10, 20],
            target_token_ids=[30, 40],
            target_logprobs=None,
            role="witness",
            sample_id="s002",
        ),
    ]


# ---------------------------------------------------------------------------
# Tests: Data loading
# ---------------------------------------------------------------------------

class TestLoadEvalData:
    def test_loads_all_samples(self, sample_eval_data: Path) -> None:
        samples = load_eval_data(sample_eval_data)
        assert len(samples) == 3

    def test_preserves_fields(self, sample_eval_data: Path) -> None:
        samples = load_eval_data(sample_eval_data)
        assert samples[0].role == "mayor"
        assert samples[0].sample_id == "s001"
        assert samples[0].input_ids == [1, 2, 3]
        assert samples[0].target_token_ids == [4, 5, 6]

    def test_handles_missing_optional_fields(self, tmp_path: Path) -> None:
        path = tmp_path / "minimal.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({
                "input_ids": [1],
                "target_token_ids": [2],
            }) + "\n")
        samples = load_eval_data(path)
        assert samples[0].role == "unknown"
        assert samples[0].sample_id == "sample_0000"
        assert samples[0].target_logprobs is None

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "blanks.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"input_ids": [1], "target_token_ids": [2]}) + "\n")
            f.write("\n")
            f.write(json.dumps({"input_ids": [3], "target_token_ids": [4]}) + "\n")
        samples = load_eval_data(path)
        assert len(samples) == 2


# ---------------------------------------------------------------------------
# Tests: Greedy acceptance
# ---------------------------------------------------------------------------

class TestGreedyAcceptance:
    def test_perfect_match(self) -> None:
        result = compute_acceptance_greedy([1, 2, 3], [1, 2, 3])
        assert result.acceptance_rate == 1.0
        assert result.n_accepted == 3
        assert all(result.per_token_accepted)

    def test_no_match(self) -> None:
        result = compute_acceptance_greedy([1, 2, 3], [4, 5, 6])
        assert result.acceptance_rate == 0.0
        assert result.n_accepted == 0

    def test_partial_match(self) -> None:
        result = compute_acceptance_greedy([1, 2, 3], [1, 5, 3])
        assert result.acceptance_rate == pytest.approx(2 / 3)
        assert result.n_accepted == 2
        assert result.per_token_accepted == [True, False, True]

    def test_different_lengths_uses_minimum(self) -> None:
        result = compute_acceptance_greedy([1, 2], [1, 2, 3, 4])
        assert result.n_draft_tokens == 2
        assert result.acceptance_rate == 1.0

    def test_empty_returns_zero(self) -> None:
        result = compute_acceptance_greedy([], [])
        assert result.acceptance_rate == 0.0
        assert result.n_draft_tokens == 0


# ---------------------------------------------------------------------------
# Tests: Stochastic acceptance
# ---------------------------------------------------------------------------

class TestStochasticAcceptance:
    def test_identical_distributions_high_acceptance(self) -> None:
        """When draft and target agree perfectly, acceptance should be ~1.0."""
        n_tokens = 100
        vocab_size = 10
        rng = np.random.default_rng(42)

        # Same logits for draft and target
        logits = torch.randn(n_tokens, vocab_size)
        target_logprobs = torch.log_softmax(logits, dim=-1).tolist()
        draft_tokens = logits.argmax(dim=-1).tolist()

        result = compute_acceptance_stochastic(
            logits, target_logprobs, draft_tokens, rng,
        )
        # With identical distributions and greedy tokens, acceptance should be 1.0
        assert result.acceptance_rate == 1.0

    def test_divergent_distributions_lower_acceptance(self) -> None:
        """Divergent distributions should yield lower acceptance."""
        n_tokens = 200
        vocab_size = 10
        rng = np.random.default_rng(42)

        draft_logits = torch.randn(n_tokens, vocab_size) * 2
        # Target has very different distribution
        target_logits = torch.randn(n_tokens, vocab_size) * 2
        target_logprobs = torch.log_softmax(target_logits, dim=-1).tolist()
        draft_tokens = draft_logits.argmax(dim=-1).tolist()

        result = compute_acceptance_stochastic(
            draft_logits, target_logprobs, draft_tokens, rng,
        )
        # With divergent distributions, acceptance should be noticeably below 1.0
        assert result.acceptance_rate < 0.9

    def test_reproducible_with_seed(self) -> None:
        """Same seed should give same result."""
        n_tokens = 50
        vocab_size = 10
        logits = torch.randn(n_tokens, vocab_size)
        target_logprobs = torch.log_softmax(
            torch.randn(n_tokens, vocab_size), dim=-1,
        ).tolist()
        draft_tokens = logits.argmax(dim=-1).tolist()

        r1 = compute_acceptance_stochastic(
            logits, target_logprobs, draft_tokens, np.random.default_rng(123),
        )
        r2 = compute_acceptance_stochastic(
            logits, target_logprobs, draft_tokens, np.random.default_rng(123),
        )
        assert r1.acceptance_rate == r2.acceptance_rate
        assert r1.per_token_accepted == r2.per_token_accepted


# ---------------------------------------------------------------------------
# Tests: Evaluate acceptance rate (integration)
# ---------------------------------------------------------------------------

class TestEvaluateAcceptanceRate:
    def _mock_model(self, output_tokens: list[int], vocab_size: int = 100):
        """Create a mock model that produces deterministic outputs."""
        model = MagicMock()
        model.parameters.side_effect = lambda: iter([torch.tensor([0.0])])

        call_count = [0]

        def forward_fn(input_tensor):
            idx = call_count[0] % len(output_tokens)
            logits = torch.zeros(1, input_tensor.shape[1], vocab_size)
            # Make the target token have high logit
            logits[0, -1, output_tokens[idx]] = 10.0
            call_count[0] += 1
            return MagicMock(logits=logits)

        model.side_effect = forward_fn
        model.eval = MagicMock()
        return model

    def test_perfect_draft_model(self) -> None:
        """Model that predicts target tokens exactly should get 100% acceptance."""
        samples = [
            EvalSample(
                input_ids=[1],
                target_token_ids=[4, 5, 6],
                target_logprobs=None,
                role="mayor",
                sample_id="s001",
            ),
        ]
        model = self._mock_model([4, 5, 6])

        report = evaluate_acceptance_rate(
            model, samples, seed=42, use_stochastic=False,
        )
        assert report.overall_acceptance_rate == 1.0
        assert report.per_role_acceptance_rate["mayor"] == 1.0

    def test_wrong_draft_model(self) -> None:
        """Model that predicts wrong tokens should get 0% acceptance."""
        samples = [
            EvalSample(
                input_ids=[1],
                target_token_ids=[4, 5, 6],
                target_logprobs=None,
                role="mayor",
                sample_id="s001",
            ),
        ]
        model = self._mock_model([7, 8, 9])

        report = evaluate_acceptance_rate(
            model, samples, seed=42, use_stochastic=False,
        )
        assert report.overall_acceptance_rate == 0.0

    def test_per_role_breakdown(self) -> None:
        """Report should separate acceptance rates by role."""
        samples = [
            EvalSample([1], [4, 5], None, "mayor", "s001"),
            EvalSample([2], [4, 5], None, "witness", "s002"),
        ]
        # Model always predicts token 4
        model = self._mock_model([4])

        report = evaluate_acceptance_rate(
            model, samples, seed=42, use_stochastic=False,
        )
        # Token 4 matches first target for both roles, token 4 != 5 for second
        assert report.per_role_acceptance_rate["mayor"] == 0.5
        assert report.per_role_acceptance_rate["witness"] == 0.5
        assert report.per_role_sample_count["mayor"] == 1
        assert report.per_role_sample_count["witness"] == 1

    def test_skips_empty_target(self) -> None:
        """Samples with empty target should be skipped."""
        samples = [
            EvalSample([1], [], None, "mayor", "s001"),
            EvalSample([2], [4], None, "mayor", "s002"),
        ]
        model = self._mock_model([4])

        report = evaluate_acceptance_rate(
            model, samples, seed=42, use_stochastic=False,
        )
        assert report.total_samples == 1


# ---------------------------------------------------------------------------
# Tests: EvalReport
# ---------------------------------------------------------------------------

class TestEvalReport:
    def test_to_dict(self) -> None:
        report = EvalReport(
            overall_acceptance_rate=0.75,
            per_role_acceptance_rate={"mayor": 0.8, "witness": 0.7},
            per_role_sample_count={"mayor": 10, "witness": 5},
            total_samples=15,
            total_tokens_drafted=300,
            total_tokens_accepted=225,
        )
        d = report.to_dict()
        assert d["overall_acceptance_rate"] == 0.75
        assert d["per_role_acceptance_rate"]["mayor"] == 0.8
        assert "results" not in d  # results excluded from dict
