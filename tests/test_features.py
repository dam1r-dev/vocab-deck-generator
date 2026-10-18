import io
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from app import main
from app.deck import to_apkg
from app.extractor import _youtube_id
from app.llm import Card
from app.pipeline import DeckResult
from app.ratelimit import RateLimiter


def cards(n=3):
    return [Card(word=f"w{i}", part_of_speech="noun", definition_en="def <b>", translation_ru="пер",
                 example="An example.", image_prompt="a picture") for i in range(n)]


def test_apkg_is_valid_anki_package(tmp_path):
    data = to_apkg(cards(3), "My <Deck>")
    z = zipfile.ZipFile(io.BytesIO(data))
    assert "collection.anki2" in z.namelist()
    path = tmp_path / "collection.db"
    path.write_bytes(z.read("collection.anki2"))
    db = sqlite3.connect(path)
    assert db.execute("select count(*) from notes").fetchone()[0] == 3
    assert "&lt;b&gt;" in db.execute("select flds from notes").fetchone()[0]  # HTML экранирован
    db.close()


def test_youtube_id_variants():
    assert _youtube_id("https://www.youtube.com/watch?v=abc123&t=5") == "abc123"
    assert _youtube_id("https://youtu.be/abc123?si=x") == "abc123"
    assert _youtube_id("https://youtube.com/shorts/abc123") == "abc123"
    assert _youtube_id("https://example.com/watch?v=abc123") is None


def test_rate_limiter_blocks_after_limit():
    rl = RateLimiter(limit=2, window_sec=60)
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a")
    assert rl.allow("b")


def make_client(monkeypatch):
    monkeypatch.setattr(main.settings, "service_api_key", "secret")
    monkeypatch.setattr(main, "limiter", RateLimiter(limit=2, window_sec=60))
    monkeypatch.setattr(main, "auth_fail_limiter", RateLimiter(limit=2, window_sec=60))
    monkeypatch.setattr(main, "build_deck", lambda url, count, level: DeckResult(
        title="T", cards=cards(), anki_csv="a", quizlet_txt="q", full_csv="c", apkg=b"zip"))
    return TestClient(main.app)


def test_api_auth_and_limits(monkeypatch):
    c = make_client(monkeypatch)
    body = {"url": "https://example.com/a"}
    assert c.post("/api/generate", json=body).status_code == 401
    assert c.post("/api/generate", json=body, headers={"x-api-key": "bad"}).status_code == 401
    assert c.post("/api/generate", json=body, headers={"x-api-key": "bad"}).status_code == 429  # перебор ключа
    h = {"x-api-key": "secret"}
    r = c.post("/api/generate", json=body, headers=h)
    assert r.status_code == 200 and r.json()["count"] == 3 and r.json()["apkg_base64"] == "emlw"
    assert c.post("/api/generate", json=body, headers=h).status_code == 200
    assert c.post("/api/generate", json=body, headers=h).status_code == 429  # общий лимит


def test_demo_deck_is_public_and_complete(monkeypatch):
    c = make_client(monkeypatch)
    r = c.get("/demo.json")  # без X-API-Key
    d = r.json()
    assert r.status_code == 200 and d["demo"] is True
    assert d["count"] == len(d["cards"]) >= 10
    assert all(card["translation_ru"] and card["definition_en"] for card in d["cards"])
    zipfile.ZipFile(io.BytesIO(__import__("base64").b64decode(d["apkg_base64"]))).testzip()


def test_telegram_webhook_security_and_dispatch(monkeypatch):
    from app import tg
    c = make_client(monkeypatch)
    handled = []
    monkeypatch.setattr(tg, "safe_handle", lambda msg: handled.append(msg["text"]))
    monkeypatch.setattr(main.settings, "telegram_bot_token", "123:abc")
    secret = tg.webhook_secret()
    upd = {"update_id": 1, "message": {"text": "hi", "chat": {"id": 5}, "from": {"id": 5}}}

    monkeypatch.setattr(main.settings, "telegram_webhook", False)
    assert c.post("/telegram/webhook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": secret}).status_code == 404

    monkeypatch.setattr(main.settings, "telegram_webhook", True)
    assert c.post("/telegram/webhook", json=upd).status_code == 403
    assert c.post("/telegram/webhook", json=upd, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}).status_code == 403
    assert handled == []

    ok = {"X-Telegram-Bot-Api-Secret-Token": secret}
    assert c.post("/telegram/webhook", json=upd, headers=ok).status_code == 200
    assert c.post("/telegram/webhook", json=upd, headers=ok).status_code == 200  # повтор доставки
    assert handled == ["hi"]  # обработано один раз


def test_telegram_handle_access_and_help(monkeypatch):
    from app import tg
    sent = []
    monkeypatch.setattr(tg, "send", lambda chat, text: sent.append(text))
    monkeypatch.setattr(tg.settings, "telegram_allowed_ids", "42")
    tg.handle({"text": "hello", "chat": {"id": 1}, "from": {"id": 7}})
    assert "Нет доступа" in sent[-1]
    tg.handle({"text": "hello", "chat": {"id": 1}, "from": {"id": 42}})
    assert "Пришли ссылку" in sent[-1]


def test_index_page_served(monkeypatch):
    c = make_client(monkeypatch)
    r = c.get("/")
    assert r.status_code == 200 and "Создать колоду" in r.text
