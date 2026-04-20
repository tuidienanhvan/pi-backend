"""Unit tests for prompt parsing — no network / no DB needed."""

import pytest

from app.pi_seo.prompts import parse_seo_bot_output


def test_parses_clean_json() -> None:
    raw = '{"variants":[{"title":"T1","description":"D1"}]}'
    out = parse_seo_bot_output(raw, expected=1)
    assert len(out) == 1
    assert out[0].title == "T1"
    assert out[0].description == "D1"


def test_parses_fenced_json() -> None:
    raw = '```json\n{"variants":[{"title":"T1","description":"D1"}]}\n```'
    out = parse_seo_bot_output(raw, expected=1)
    assert out[0].title == "T1"


def test_parses_multiple_variants() -> None:
    raw = (
        '{"variants":['
        '{"title":"T1","description":"D1"},'
        '{"title":"T2","description":"D2"}]}'
    )
    out = parse_seo_bot_output(raw, expected=2)
    assert len(out) == 2
    assert out[1].title == "T2"


def test_raises_on_invalid_json() -> None:
    with pytest.raises(ValueError):
        parse_seo_bot_output("not json at all", expected=1)


def test_raises_on_missing_variants_key() -> None:
    with pytest.raises(ValueError):
        parse_seo_bot_output('{"foo":"bar"}', expected=1)


def test_skips_variants_with_empty_fields() -> None:
    raw = (
        '{"variants":['
        '{"title":"","description":"D1"},'
        '{"title":"T2","description":"D2"}]}'
    )
    out = parse_seo_bot_output(raw, expected=2)
    assert len(out) == 1
    assert out[0].title == "T2"


def test_hard_caps_long_title() -> None:
    long = "x" * 200
    raw = f'{{"variants":[{{"title":"{long}","description":"D"}}]}}'
    out = parse_seo_bot_output(raw, expected=1)
    assert len(out[0].title) <= 70
