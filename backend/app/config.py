from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EA Control Center"
    database_url: str = "postgresql+psycopg://ea_user:change_this_password@postgres:5432/ea_control"
    ea_api_token: str = "change_this_ea_token"
    admin_api_token: str = "change_this_admin_token"
    ea_offline_seconds: int = 60
    command_timeout_seconds: int = 120
    max_manual_order_volume: float = 10.0
    allowed_trade_symbols: str = "XAUUSD"
    jwt_secret: str = "change_this_jwt_secret"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    first_admin_bootstrap: bool = False
    first_admin_username: str | None = None
    first_admin_password: str | None = None
    allow_public_dashboard_preview: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()