# Генератор учебных колод (Make.com + FastAPI + Telegram)

Учитель отправляет ссылку на англоязычную статью и получает колоду: 15 слов уровня B2/C1 с определением (EN),
переводом (RU), примером и промптом для картинки. Готовые форматы: **`.apkg`** (Anki, двойной клик), CSV для Anki,
текст для импорта в Quizlet, полный CSV для Excel.

```
Telegram ──► Make.com ──► POST /api/generate (этот сервис) ──► Groq / Gemini / любой OpenAI-совместимый ИИ
   ▲            │                 │ trafilatura: текст статьи
   └────────────┴── файлы колоды ◄┘
Браузер ──► GET /  (веб-форма) ──► тот же /api/generate
```

Три способа пользоваться, один движок:
- **Telegram-бот** `bot.py`: работает сам, без Make (быстрый старт).
- **Make.com**: принимает сообщение из Telegram, вызывает API, возвращает файлы (раздел 3).
- **Веб-страница** `/`: вставил ссылку и код доступа, скачал файлы.

## 1. Запуск локально

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Заполни `.env`:

| Переменная | Что это |
|---|---|
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | ИИ. Сейчас Groq (бесплатно, https://console.groq.com/keys): `openai_compatible`, `https://api.groq.com/openai/v1`, `openai/gpt-oss-120b`. Список моделей Groq меняется, актуальный: `GET {LLM_BASE_URL}/models` |
| `SERVICE_API_KEY` | Код доступа к API и веб-форме. Длинная случайная строка |
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather |
| `TELEGRAM_ALLOWED_IDS` | id учителей через запятую (свой id: @userinfobot). Пусто = бот открыт всем |

```bash
python bot.py                      # Telegram-бот
uvicorn app.main:app --port 8000   # API + веб-форма на http://localhost:8000
python -m pytest                   # тесты
```

Лимиты (меняются в `.env`): `API_RATE_LIMIT_PER_HOUR=60` запросов в час на весь API,
`BOT_RATE_LIMIT_PER_HOUR=10` колод в час на одного пользователя бота. 10 неверных кодов доступа за 10 минут с одного IP блокируют подбор.

## 2. Выложить в интернет (нужно для Make и чтобы бот работал без твоего компьютера)

Подготовлены `Dockerfile` и `render.yaml`. На **Render.com**:
1. Залей проект в GitHub (файл `.env` не попадёт: он в `.gitignore`).
2. Render → New → **Blueprint** → выбери репозиторий.
3. Укажи секрет `LLM_API_KEY`. `SERVICE_API_KEY` Render сгенерирует сам, скопируй его из Environment.
4. Бесплатный сервис «засыпает», первый запрос идёт 30–60 секунд. В Make ставь таймаут 120 секунд.

Автономный бот `bot.py` на Render free не запустится постоянно (это не веб-сервис). Либо держи его на своём компьютере,
либо используй Make (раздел 3), который принимает сообщения Telegram сам.

## 3. Сценарий в Make.com

Модулей 6; бесплатного тарифа хватает (~6 операций на колоду, порядка 150 колод в месяц).
**Важно:** пока работает `bot.py` с тем же токеном, Make не получит сообщения (Telegram отдаёт апдейты одному потребителю). Останови бота перед включением сценария.

1. **Telegram Bot → Watch Updates**. Подключение: токен от BotFather. Работает мгновенно, через webhook.
2. **Фильтр** после модуля 1: `message.text` *Contains* `http`.
3. **Text parser → Match pattern**. Pattern `https?://\S+`, Text `{{1.message.text}}`. Результат: `{{3.0}}`.
4. **HTTP → Make a request**:
   - URL `https://ТВОЙ-СЕРВИС.onrender.com/api/generate`, Method POST
   - Headers: `X-API-Key` = значение `SERVICE_API_KEY`
   - Body type Raw, Content type JSON: `{"url": "{{3.0}}", "count": 15}`
   - Parse response: **Yes**, Timeout: 120
5. **Telegram → Send a Text Message**: chat id `{{1.message.chat.id}}`, текст `Готово! «{{4.data.title}}» — {{4.data.count}} карточек`.
6. **Telegram → Send a Document** (по модулю на файл): File name `anki.txt`, Data `{{4.data.anki_csv}}`; второй `quizlet.txt`, Data `{{4.data.quizlet_txt}}`.
   Файл `.apkg` приходит как `apkg_base64`. Для Make его нужно декодировать (функция `toBinary({{4.data.apkg_base64}}; "base64")`), в Data выбери этот результат, имя `deck.apkg`.

**Обработка ошибок.** Правый клик на модуль 4 → *Add error handler* → Telegram *Send a Text Message*: `Не получилось: {{4.data.detail}}`. Сервис возвращает понятные причины (платная страница, лимит ИИ и т.д.).

## 4. Как импортировать

- **Anki**: открой `deck.apkg` двойным кликом. Или File → Import → `anki.txt` (разделитель и HTML заданы в самом файле).
- **Quizlet**: Create → Import → вставить содержимое `quizlet.txt` (между термином и определением Tab).
- **Excel / Google Таблицы**: `cards.csv`, все поля включая промпты для картинок.

## Ограничения

- Работают статьи, открытые без логина и оплаты. Wikipedia блокирует анонимных ботов (403).
- **YouTube** в коде есть (`youtube-transcript-api`), но YouTube блокирует запросы с домашних и облачных IP, поэтому на практике не работает. Бот честно сообщает об этом.
- Картинки не генерируются: промпт попадает в колоду как поле.
- Бесплатные лимиты ИИ ограничены по запросам и токенам в минуту; сервис сообщает об этом понятным текстом.
- Статья обрезается до 12 000 символов.
