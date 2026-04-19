import json

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_TITLE: str = "Spitex Leistungskontrolle"
    SECRET_KEY: str
    TOKEN_EXPIRE_MINUTES: int = 120
    USERS_JSON: str
    MAX_UPLOAD_MB: int = 50

    @property
    def users(self) -> list[dict]:
        return json.loads(self.USERS_JSON)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
