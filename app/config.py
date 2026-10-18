from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "gemini"  # gemini | openai_compatible
    llm_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    llm_base_url: str = "https://api.groq.com/openai/v1"

    service_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_allowed_ids: str = ""
    telegram_webhook: bool = False  # true на сервере: бот принимает сообщения через webhook
    public_url: str = ""  # адрес сервиса; на Render берётся из RENDER_EXTERNAL_URL
    render_external_url: str = ""

    api_rate_limit_per_hour: int = 60
    bot_rate_limit_per_hour: int = 10

    max_article_chars: int = 12000
    min_article_chars: int = 400


settings = Settings()
