"""Логика Telegram-бота: общая для polling (bot.py) и webhook (FastAPI на сервере)."""
import hashlib
import re
from collections import OrderedDict
from threading import Lock

import httpx

from .config import settings
from .extractor import ExtractionError
from .llm import LLMError
from .pipeline import build_deck
from .ratelimit import RateLimiter

limiter = RateLimiter(limit=settings.bot_rate_limit_per_hour, window_sec=3600)
URL_RE = re.compile(r"https?://\S+")
HELP = (
    "Привет! Пришли ссылку на статью на английском — через ~20 секунд "
    "получишь колоду из 15 слов уровня B2/C1.\n"
    "Можно указать количество слов: https://... 20\n\n"
    "Файлы: deck.apkg (Anki, двойной клик), anki.txt (импорт CSV), quizlet.txt (Quizlet → Import), cards.csv (Excel)."
)


def _api() -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}"


def tg(method: str, **kw) -> dict:
    return httpx.post(f"{_api()}/{method}", timeout=60, **kw).json()


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


def safe_handle(msg: dict):
    """Для фоновой обработки: одно сломанное сообщение не должно ронять сервер."""
    try:
        handle(msg)
    except Exception as e:
        print("telegram handle error:", repr(e))


# --- webhook ---

def webhook_secret() -> str:
    """Секрет, по которому сервер узнаёт, что запрос пришёл от Telegram. Выводится из токена бота."""
    return hashlib.sha256(("wh:" + settings.telegram_bot_token).encode()).hexdigest()[:48]


_seen: OrderedDict[int, None] = OrderedDict()
_seen_lock = Lock()


def mark_new_update(update_id: int | None) -> bool:
    """True, если это обновление мы ещё не обрабатывали (Telegram может повторять доставку)."""
    if update_id is None:
        return True
    with _seen_lock:
        if update_id in _seen:
            return False
        _seen[update_id] = None
        while len(_seen) > 500:
            _seen.popitem(last=False)
    return True


def register_webhook(base_url: str) -> bool:
    r = tg("setWebhook", data={
        "url": base_url.rstrip("/") + "/telegram/webhook",
        "secret_token": webhook_secret(),
        "allowed_updates": '["message"]',
    })
    print("setWebhook:", r.get("ok"), r.get("description"))
    return bool(r.get("ok"))
