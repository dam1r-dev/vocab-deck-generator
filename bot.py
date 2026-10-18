"""Автономный Telegram-бот (long polling) для локального запуска: python bot.py

Не запускай его одновременно с webhook на сервере или сценарием Make:
Telegram отдаёт сообщения только одному получателю.
"""
import time

import httpx

from app.config import settings
from app.tg import _api, safe_handle


def main():
    if not settings.telegram_bot_token:
        raise SystemExit("Задай TELEGRAM_BOT_TOKEN в .env")
    print("Бот запущен")
    offset = 0
    while True:
        try:
            res = httpx.get(f"{_api()}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=45).json()
            if not res.get("ok"):
                print("Telegram:", res.get("description"))
                if res.get("error_code") == 409:
                    print("Подсказка: у бота включён webhook (сервер или Make). Для polling его нужно отключить.")
                time.sleep(10)
                continue
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                if "message" in u:
                    safe_handle(u["message"])
        except httpx.HTTPError:
            time.sleep(5)


if __name__ == "__main__":
    main()
