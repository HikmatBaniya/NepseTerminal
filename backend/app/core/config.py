from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    allowed_origins: str = ""
    database_url: str
    groq_api_key: str | None = None
    groq_model: str = "llama3-8b-8192"
    use_crewai: bool = True
    scrape_user_agent: str = "SellrClubBot/1.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()