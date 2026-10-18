"""Форматы колод: CSV для импорта в Anki и текст для импорта в Quizlet."""
import csv
import hashlib
import html
import io
import os
import tempfile

import genanki

from .llm import Card

_CSS = """.card{font-family:Arial,sans-serif;font-size:22px;text-align:center;color:#222;background:#fff}
.pos{color:#888;font-size:16px}.tr{color:#0a6;font-weight:bold;margin-top:10px}
.ex{color:#555;font-style:italic;font-size:18px;margin-top:14px}"""

_MODEL = genanki.Model(
    1607392319,
    "Vocab B2C1 (word)",
    fields=[{"name": "Word"}, {"name": "POS"}, {"name": "Definition"}, {"name": "Translation"},
            {"name": "Example"}, {"name": "ImagePrompt"}],
    templates=[{
        "name": "Word → meaning",
        "qfmt": '<div><b>{{Word}}</b></div><div class="pos">{{POS}}</div>',
        "afmt": '{{FrontSide}}<hr id="answer"><div>{{Definition}}</div><div class="tr">{{Translation}}</div>'
                '<div class="ex">{{Example}}</div>',
    }],
    css=_CSS,
)


def to_apkg(cards: list[Card], deck_name: str) -> bytes:
    """Готовая колода Anki (.apkg): открывается двойным кликом."""
    deck_id = int(hashlib.sha1(deck_name.encode()).hexdigest()[:8], 16)
    deck = genanki.Deck(deck_id, f"Vocab: {deck_name}"[:80])
    e = lambda s: html.escape(" ".join(s.split()))
    for c in cards:
        deck.add_note(genanki.Note(
            model=_MODEL,
            fields=[e(c.word), e(c.part_of_speech), e(c.definition_en), e(c.translation_ru),
                    e(c.example), e(c.image_prompt)],
            guid=genanki.guid_for(deck_name, c.word),
        ))
    fd, path = tempfile.mkstemp(suffix=".apkg")
    os.close(fd)
    try:
        genanki.Package(deck).write_to_file(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


def _clean(s: str) -> str:
    return " ".join(s.replace("\t", " ").split())


def to_anki_csv(cards: list[Card], deck_name: str = "") -> str:
    """Tab-separated файл с директивами Anki (File → Import).
    Колонки: Front, Back, Example, ImagePrompt, Tags. HTML включён."""
    buf = io.StringIO()
    buf.write("#separator:tab\n#html:true\n#tags column:5\n")
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    for c in cards:
        pos = f" <i>({html.escape(c.part_of_speech)})</i>" if c.part_of_speech else ""
        front = f"<b>{html.escape(c.word)}</b>{pos}"
        back = (
            f"{html.escape(_clean(c.definition_en))}<br>"
            f"<b>{html.escape(_clean(c.translation_ru))}</b>"
        )
        example = html.escape(_clean(c.example))
        w.writerow([front, back, example, html.escape(_clean(c.image_prompt)), "vocab_b2c1"])
    return buf.getvalue()


def to_quizlet_txt(cards: list[Card]) -> str:
    """Quizlet Import: между термином и определением — таб, между карточками — перевод строки."""
    lines = []
    for c in cards:
        term = _clean(c.word)
        definition = f"{_clean(c.definition_en)} — {_clean(c.translation_ru)}. E.g.: {_clean(c.example)}"
        lines.append(f"{term}\t{definition}")
    return "\n".join(lines) + "\n"


def to_full_csv(cards: list[Card]) -> str:
    """Универсальный CSV со всеми полями (для Excel/Google Таблиц), UTF-8 с BOM."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["word", "part_of_speech", "definition_en", "translation_ru", "example", "image_prompt"])
    for c in cards:
        w.writerow([c.word, c.part_of_speech, c.definition_en, c.translation_ru, c.example, c.image_prompt])
    return "﻿" + buf.getvalue()
