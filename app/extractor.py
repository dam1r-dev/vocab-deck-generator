"""Скачивает страницу и достаёт из неё текст статьи (с защитой от SSRF)."""
import ipaddress
import socket
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
import trafilatura

from .config import settings

MAX_BYTES = 3_000_000
MAX_REDIRECTS = 5
# Одни сайты пускают только браузер, другие (Wikipedia) — только честного бота. Пробуем по очереди при 403.
HEADER_SETS = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    },
    {"User-Agent": "VocabDeckBot/1.0 (educational flashcard tool; reads single articles on teacher request)"},
]


class ExtractionError(Exception):
    """Ошибка, текст которой можно показывать учителю."""


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ExtractionError("Нужна ссылка вида https://...")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror:
        raise ExtractionError("Не удалось найти сайт по этой ссылке.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ExtractionError("Эта ссылка недоступна (внутренний адрес).")


def _get(url: str, headers: dict) -> tuple[int, str]:
    """GET с ручной обработкой редиректов: каждый адрес проверяется на SSRF."""
    with httpx.Client(timeout=15, headers=headers, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _assert_public_url(url)
            try:
                with client.stream("GET", url) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("location", ""))
                        continue
                    if r.status_code >= 400:
                        return r.status_code, ""
                    data = b""
                    for chunk in r.iter_bytes():
                        data += chunk
                        if len(data) > MAX_BYTES:
                            break
                    return r.status_code, data.decode(r.encoding or "utf-8", errors="replace")
            except httpx.HTTPError:
                raise ExtractionError("Не удалось загрузить страницу.")
    raise ExtractionError("Слишком много перенаправлений.")


def fetch_html(url: str) -> str:
    status = 0
    for headers in HEADER_SETS:
        status, body = _get(url, headers)
        if status < 400:
            return body
        if status != 403:
            break
    raise ExtractionError(f"Сайт ответил ошибкой {status}.")


def _youtube_id(url: str) -> str | None:
    p = urlparse(url)
    host = (p.hostname or "").removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return p.path.strip("/") or None
    if host in ("youtube.com", "music.youtube.com"):
        if p.path == "/watch":
            return parse_qs(p.query).get("v", [None])[0]
        parts = p.path.strip("/").split("/")
        if parts[0] in ("shorts", "embed", "live") and len(parts) > 1:
            return parts[1]
    return None


def extract_youtube(video_id: str, url: str) -> tuple[str, str]:
    from youtube_transcript_api import IpBlocked, RequestBlocked, YouTubeTranscriptApi

    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
        text = " ".join(s.text for s in fetched)
    except (IpBlocked, RequestBlocked):
        raise ExtractionError(
            "YouTube блокирует запросы с этого сервера, видео сейчас не поддерживаются. Пришли ссылку на статью."
        )
    except Exception:
        raise ExtractionError("У видео нет английских субтитров или YouTube не отдал их.")
    text = " ".join(text.split())
    if len(text) < settings.min_article_chars:
        raise ExtractionError("В субтитрах слишком мало текста.")
    title = "YouTube " + video_id
    try:
        r = httpx.get("https://www.youtube.com/oembed", params={"url": url, "format": "json"}, timeout=8)
        if r.status_code == 200:
            title = r.json().get("title", title)
    except httpx.HTTPError:
        pass
    return title, text[: settings.max_article_chars]


def extract_article(url: str) -> tuple[str, str]:
    """Возвращает (заголовок, текст). Понимает статьи и ссылки на YouTube."""
    video_id = _youtube_id(url)
    if video_id:
        return extract_youtube(video_id, url)
    html = fetch_html(url)
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text or len(text) < settings.min_article_chars:
        raise ExtractionError(
            "Не удалось извлечь текст статьи (возможно, платная страница или слишком короткий текст)."
        )
    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else urlparse(url).netloc)
    return title, text[: settings.max_article_chars]
