from dataclasses import dataclass

from .deck import to_anki_csv, to_apkg, to_full_csv, to_quizlet_txt
from .extractor import extract_article
from .llm import Card, generate_cards


@dataclass
class DeckResult:
    title: str
    cards: list[Card]
    anki_csv: str
    quizlet_txt: str
    full_csv: str
    apkg: bytes


def build_deck(url: str, count: int = 15, level: str = "B2/C1") -> DeckResult:
    title, text = extract_article(url)
    cards = generate_cards(text, count=count, level=level)
    return DeckResult(
        title=title,
        cards=cards,
        anki_csv=to_anki_csv(cards),
        quizlet_txt=to_quizlet_txt(cards),
        full_csv=to_full_csv(cards),
        apkg=to_apkg(cards, title),
    )
