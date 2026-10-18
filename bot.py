"""Автономный Telegram-бот (long polling). Работает без Make.com — удобно для проверки.
Запуск: python bot.py
"""
import re
import time

import httpx

from app.config import settings
from app.extractor import ExtractionError
from app.llm import LLMError
from app.pipeline import build_deck
from app.ratelimit import RateLimiter

limiter = RateLimiter(limit=settings.bot_rate_limit_per_hour, window_sec=3600)
API = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
URL_RE = re.compile(r"https?://\S+")
HELP = (
    "Привет! Пришли ссылку на статью на английском — через ~20 секунд "
    "получишь колоду из 15 слов уровня B2/C1.\n"
    "Можно указать количество слов: https://... 20\n\n"
    "Файлы: deck.apkg (Anki, двойной клик), anki.txt (импорт CSV), quizlet.txt (Quizlet → Import), cards.csv (Excel)."
)


def tg(method: str, **kw):
    r = httpx.post(f"{API}/{method}", timeout=60, **kw)
    return r.json()


def send(chat_id: int, text: str):
    tg("sendMessage", data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})


def send_doc(chat_id: int, name: str, content: str | bytes, caption: str = ""):
    data = content.encode("utf-8") if isinstance(content, str) else content
    tg("sendDocument", data={"chat_id": chat_id, "caption": caption},
       files={"document": (name, data, "application/octet-stream")})


def allowed(user_id: int) -> bool:
    ids = [i.strip() for i in settings.telegram_allowed_ids.split(",") if i.strip()]
    return not ids or str(user_id) in ids


def handle(msg: dict):
    chat_id, user_id = msg["chat"]["id"], msg["from"]["id"]
    text = msg.get("text", "")
    if not allowed(user_id):
        return send(chat_id, f"Нет доступа. Твой id: {user_id}")
    m = URL_RE.search(text)
    if not m:
        return send(chat_id, HELP)
    rest = text[m.end():].strip()
    count = int(rest) if rest.isdigit() and 5 <= int(rest) <= 30 else 15
    if not limiter.allow(str(user_id)):
        return send(chat_id, f"Лимит: {settings.bot_rate_limit_per_hour} колод в час. Попробуй чуть позже.")
    send(chat_id, "Читаю материал и подбираю слова…")
    try:
        d = build_deck(m.group(0), count=count)
    except (ExtractionError, LLMError) as e:
        return send(chat_id, f"Не получилось: {e}")
    except Exception:
        return send(chat_id, "Что-то пошло не так. Попробуй другую ссылку.")
    send(chat_id, f"Готово! «{d.title}» — {len(d.cards)} карточек.")
    send_doc(chat_id, "deck.apkg", d.apkg, "Anki: открой файл двойным кликом")
    send_doc(chat_id, "anki.txt", d.anki_csv, "Anki: File → Import (если нужен CSV)")
    send_doc(chat_id, "quizlet.txt", d.quizlet_txt, "Quizlet: Create → Import")
    send_doc(chat_id, "cards.csv", d.full_csv, "Все поля + промпты для картинок")


def main():
    if not settings.telegram_bot_token:
        raise SystemExit("Задай TELEGRAM_BOT_TOKEN в .env")
    print("Бот запущен")
    offset = 0
    while True:
        try:
            res = httpx.get(f"{API}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=45).json()
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    try:
                        handle(u["message"])
                    except Exception as e:  # один сбойный апдейт не должен ронять бота
                        print("error:", e)
        except httpx.HTTPError:
            time.sleep(5)


if __name__ == "__main__":
    main()
