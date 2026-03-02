"""Unit tests for CostTracker."""
from decimal import Decimal

import pytest

from app.utils.cost_tracker import CostTracker


class TestCostTracker:
    def test_initial_cost_zero(self):
        tracker = CostTracker("test-run-id")
        assert tracker.total_usd == Decimal("0")

    def test_add_gpt4o_cost(self):
        tracker = CostTracker("test-run-id")
        cost = tracker.add_gpt4o(prompt_tokens=1000, completion_tokens=500)
        # 1000 * 0.000005 + 500 * 0.000015 = 0.005 + 0.0075 = 0.0125
        assert cost == Decimal("0.0125")
        assert tracker.total_usd == Decimal("0.0125")

    def test_add_dalle3_cost(self):
        tracker = CostTracker("test-run-id")
        cost = tracker.add_dalle3(count=3)
        assert cost == Decimal("0.120")
        assert tracker.total_usd == Decimal("0.120")

    def test_add_tts_cost(self):
        tracker = CostTracker("test-run-id")
        cost = tracker.add_tts(char_count=1000)
        # 1000 * 0.000015 = 0.015
        assert cost == Decimal("0.015")
        assert tracker.total_usd == Decimal("0.015")

    def test_add_raw_cost(self):
        tracker = CostTracker("test-run-id")
        cost = tracker.add_raw(Decimal("0.05"), label="test")
        assert cost == Decimal("0.05")
        assert tracker.total_usd == Decimal("0.05")

    def test_accumulates_multiple_costs(self):
        tracker = CostTracker("test-run-id")
        tracker.add_gpt4o(1000, 500)  # 0.0125
        tracker.add_dalle3(2)          # 0.080
        tracker.add_tts(500)           # 0.0075
        expected = Decimal("0.0125") + Decimal("0.080") + Decimal("0.0075")
        assert tracker.total_usd == expected

    def test_dalle3_single_image_cost(self):
        tracker = CostTracker("test-run-id")
        cost = tracker.add_dalle3(count=1)
        assert cost == Decimal("0.040")
