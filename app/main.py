import base64
import hmac
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, HttpUrl

from . import tg
from .config import settings
from .extractor import ExtractionError
from .llm import Card, LLMError
from .pipeline import build_deck
from .ratelimit import RateLimiter

@asynccontextmanager
async def lifespan(_: FastAPI):
    """На сервере (TELEGRAM_WEBHOOK=true) сам сообщает Telegram, куда присылать сообщения."""
    base = settings.public_url or settings.render_external_url
    if settings.telegram_webhook and settings.telegram_bot_token and base:
        threading.Thread(target=tg.register_webhook, args=(base,), daemon=True).start()
    yield


app = FastAPI(title="Vocab Deck Generator", lifespan=lifespan)
STATIC = Path(__file__).parent / "static"
limiter = RateLimiter(limit=settings.api_rate_limit_per_hour, window_sec=3600)
auth_fail_limiter = RateLimiter(limit=10, window_sec=600)  # подбор ключа: 10 ошибок / 10 минут с одного IP


def require_key(request: Request, x_api_key: str = Header(default="")):
    ip = request.client.host if request.client else "?"
    if not settings.service_api_key or not hmac.compare_digest(x_api_key, settings.service_api_key):
        if not auth_fail_limiter.allow(ip):
            raise HTTPException(429, "Слишком много неверных попыток. Подожди 10 минут.")
        raise HTTPException(401, "Неверный код доступа")
    if not limiter.allow("global"):
        raise HTTPException(429, "Достигнут лимит запросов в час. Попробуй позже.")


class GenerateRequest(BaseModel):
    url: HttpUrl
    count: int = Field(default=15, ge=5, le=30)
    level: str = Field(default="B2/C1", max_length=10)


class GenerateResponse(BaseModel):
    title: str
    count: int
    cards: list[Card]
    anki_csv: str
    quizlet_txt: str
    full_csv: str
    apkg_base64: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/demo.json")
def demo():
    """Готовая демо-колода: без кода доступа и без запросов к ИИ."""
    return FileResponse(STATIC / "demo.json", media_type="application/json")


@app.post("/telegram/webhook")
def telegram_webhook(
    update: dict,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """Сюда Telegram присылает сообщения. Отвечаем сразу, а колоду собираем в фоне (это ~20 секунд)."""
    if not (settings.telegram_webhook and settings.telegram_bot_token):
        raise HTTPException(404)
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, tg.webhook_secret()):
        raise HTTPException(403)
    msg = update.get("message")
    if msg and "from" in msg and tg.mark_new_update(update.get("update_id")):
        background.add_task(tg.safe_handle, msg)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/generate", response_model=GenerateResponse, dependencies=[Depends(require_key)])
def generate(req: GenerateRequest):
    try:
        d = build_deck(str(req.url), req.count, req.level)
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    except LLMError as e:
        raise HTTPException(502, str(e))
    return GenerateResponse(
        title=d.title, count=len(d.cards), cards=d.cards,
        anki_csv=d.anki_csv, quizlet_txt=d.quizlet_txt, full_csv=d.full_csv,
        apkg_base64=base64.b64encode(d.apkg).decode(),
    )
