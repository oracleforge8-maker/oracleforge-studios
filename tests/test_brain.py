"""Tests for The Brain AI processing agents."""

from __future__ import annotations

import pytest

from src.agents.brain import (
    fallback_analysis,
    fallback_social_posts,
    load_prompt,
    safe_json,
)


def test_load_prompt_exists():
    """All required prompt templates should exist in prompts.yaml."""
    required = [
        "chadsatoshi_system",
        "trend_analysis",
        "social_content",
        "reply_generation",
        "newsletter",
        "celebrity_engagement",
        "linkedin_post",
        "voice_reprompt",
        "forge_business_prompt",
        "forge_meme_prompt",
        "forge_brand_prompt",
    ]
    for name in required:
        assert load_prompt(name), f"Missing prompt: {name}"


def test_fallback_analysis(sample_trends):
    """fallback_analysis() should return narratives from top movers."""
    result = fallback_analysis(sample_trends)
    assert "narratives" in result
    assert "red_flags" in result
    assert "summary" in result
    assert len(result["narratives"]) > 0
    # MOON has the highest change (145%) so it should be first
    assert result["narratives"][0]["tokens"] == ["MOON"]


def test_fallback_social_posts(sample_trends):
    """fallback_social_posts() should return up to 3 posts."""
    posts = fallback_social_posts(sample_trends)
    assert 1 <= len(posts) <= 3
    # Posts should mention a token symbol
    assert any("$" in p for p in posts)


def test_safe_json_extracts_from_markdown():
    """safe_json() should extract JSON from markdown fences."""
    text = '```json\n{"narratives": [], "summary": "ok"}\n```'
    parsed = safe_json(text)
    assert parsed is not None
    assert parsed["summary"] == "ok"


def test_safe_json_returns_none_on_garbage():
    """safe_json() should return None for unparseable text."""
    assert safe_json("this is not json at all") is None