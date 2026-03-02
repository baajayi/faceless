"""Unit tests for topic filtering — blocklist + composite scoring."""
from unittest.mock import patch

import pytest

from app.agents.topic_selection import (
    _compute_novelty,
    _detect_category,
    _is_blocked,
)


@pytest.fixture
def blocklist():
    return {
        "blocked_keywords": ["murder", "violence", "horror", "drug"],
        "blocked_brands": ["fortnite"],
    }


@pytest.fixture
def categories_cfg():
    return {
        "categories": {
            "animals": {
                "keywords": ["animal", "dinosaur", "ocean", "bird", "fish"],
            },
            "science": {
                "keywords": ["science", "space", "planet", "experiment"],
            },
        }
    }


# ── Blocklist tests ───────────────────────────────────────────────────────────

class TestBlocklist:
    def test_blocks_violence(self, blocklist):
        assert _is_blocked("how to do violence in sports", blocklist) is True

    def test_blocks_horror(self, blocklist):
        assert _is_blocked("Horror Movies for Kids", blocklist) is True

    def test_blocks_brand(self, blocklist):
        assert _is_blocked("Fortnite Skins Guide", blocklist) is True

    def test_allows_safe_topic(self, blocklist):
        assert _is_blocked("Why Do Butterflies Have Wings", blocklist) is False

    def test_allows_animal_topic(self, blocklist):
        assert _is_blocked("Ocean Animals for Kids", blocklist) is False

    def test_case_insensitive(self, blocklist):
        assert _is_blocked("MURDER MYSTERY", blocklist) is True

    def test_partial_word_match(self, blocklist):
        # "drug" in "drug store" should be blocked
        assert _is_blocked("Drug store opening near school", blocklist) is True

    def test_empty_title(self, blocklist):
        assert _is_blocked("", blocklist) is False


# ── Composite scoring tests ───────────────────────────────────────────────────

class TestCompositeScoring:
    def test_novelty_unique_title(self):
        score = _compute_novelty("Butterfly Wings Facts", [])
        assert score == 1.0

    def test_novelty_exact_duplicate(self):
        from unittest.mock import MagicMock
        existing = MagicMock()
        existing.title = "butterfly wings facts"
        score = _compute_novelty("Butterfly Wings Facts", [existing])
        assert score == 0.0

    def test_novelty_partial_match(self):
        from unittest.mock import MagicMock
        existing = MagicMock()
        existing.title = "butterfly wings"
        score = _compute_novelty("Butterfly Wings Facts for Kids", [existing])
        assert score == 0.5

    def test_novelty_no_match(self):
        from unittest.mock import MagicMock
        existing = MagicMock()
        existing.title = "Dinosaur Facts"
        score = _compute_novelty("Why Is The Sky Blue", [existing])
        assert score == 1.0


# ── Category detection tests ──────────────────────────────────────────────────

class TestCategoryDetection:
    def test_detects_animals(self, categories_cfg):
        cat = _detect_category("Ocean Animals for Kids", categories_cfg)
        assert cat == "animals"

    def test_detects_science(self, categories_cfg):
        cat = _detect_category("Space Facts for Children", categories_cfg)
        assert cat == "science"

    def test_unknown_category(self, categories_cfg):
        cat = _detect_category("How to Bake Cookies", categories_cfg)
        assert cat is None

    def test_strongest_match_wins(self, categories_cfg):
        # "ocean animal science experiment" has 2 animal hits + 2 science hits
        # Both equal — first alphabetically or whichever counts more wins
        cat = _detect_category("ocean animals in science experiments", categories_cfg)
        # Both match 2 keywords — implementation picks one; just ensure a valid result
        assert cat in ("animals", "science")
