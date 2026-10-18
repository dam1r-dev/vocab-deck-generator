import pytest

from app import extractor, llm
from app.deck import to_anki_csv, to_full_csv, to_quizlet_txt
from app.extractor import ExtractionError
from app.llm import Card


def card(**kw):
    base = dict(word="ubiquitous", part_of_speech="adj", definition_en="found everywhere",
                translation_ru="вездесущий", example='He said "it\'s\tubiquitous".', image_prompt="a crowd of phones")
    return Card(**{**base, **kw})


def test_anki_format_and_escaping():
    out = to_anki_csv([card(word="<b>x</b>")])
    assert out.startswith("#separator:tab")
    row = out.strip().split("\n")[-1].split("\t")
    assert len(row) == 5 and "&lt;b&gt;" in row[0]


def test_quizlet_one_line_per_card():
    out = to_quizlet_txt([card(), card(word="ephemeral")])
    assert len(out.strip().split("\n")) == 2 and "\t" in out.split("\n")[0]


def test_full_csv_has_bom_and_header():
    assert to_full_csv([card()]).startswith("﻿word,")


def test_json_extraction_from_fenced_block():
    assert llm._extract_json('```json\n{"cards": []}\n```') == {"cards": []}


def test_dedup_and_limit(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_api_key", "x")
    monkeypatch.setattr(llm.settings, "llm_provider", "gemini")
    payload = '{"cards":[%s]}' % ",".join(
        '{"word":"%s","definition_en":"d","translation_ru":"т","example":"e","image_prompt":"p"}' % w
        for w in ["Alpha", "alpha", "beta", "gamma"])
    monkeypatch.setattr(llm, "_call_gemini", lambda s, u: payload)
    cards = llm.generate_cards("text", count=2)
    assert [c.word for c in cards] == ["Alpha", "beta"]


def test_bad_json_retries_then_fails(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_api_key", "x")
    monkeypatch.setattr(llm.settings, "llm_provider", "gemini")
    calls = []
    monkeypatch.setattr(llm, "_call_gemini", lambda s, u: calls.append(1) or "not json")
    with pytest.raises(llm.LLMError):
        llm.generate_cards("text")
    assert len(calls) == 2


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost:8000", "http://169.254.169.254/", "ftp://x.com"])
def test_ssrf_blocked(url):
    with pytest.raises(ExtractionError):
        extractor._assert_public_url(url)
