"""Application configuration, driven entirely by environment variables.

The reward rule (`n` and `x` in the README) and the admin boundary live here so
behaviour is reproducible and no business value is hard-coded in handlers.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://uniblox:uniblox@db:5432/uniblox"

    # Reward rule: every `coupon_order_interval`-th order makes one coupon for
    # `coupon_percent`% off available. README example: n=5, x=10.
    coupon_order_interval: int = 5  # n
    coupon_percent: int = 10        # x

    # Admin boundary. Auth is intentionally not implemented (see DECISIONS.md);
    # this token only *marks* which operations are administrative.
    admin_token: str = "dev-admin-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
