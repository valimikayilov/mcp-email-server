from __future__ import annotations

import datetime
import os
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from mcp_email_server.logger import logger

DEFAILT_CONFIG_PATH = "~/.config/zerolib/mcp_email_server/config.toml"

CONFIG_PATH = Path(os.getenv("MCP_EMAIL_SERVER_CONFIG_PATH", DEFAILT_CONFIG_PATH)).expanduser().resolve()


class EmailServer(BaseModel):
    user_name: str
    password: str
    host: str
    port: int
    ssl: bool = True


class AccountAttributes(BaseModel):
    account_name: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.now)

    @model_validator(mode="after")
    @classmethod
    def update_updated_at(cls, obj: AccountAttributes) -> AccountAttributes:
        """Update updated_at field."""
        # must disable validation to avoid infinite loop
        obj.model_config["validate_assignment"] = False

        # update updated_at field
        obj.updated_at = datetime.datetime.now()

        # enable validation again
        obj.model_config["validate_assignment"] = True
        return obj

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AccountAttributes):
            return NotImplemented
        return self.model_dump(exclude={"created_at", "updated_at"}) == other.model_dump(
            exclude={"created_at", "updated_at"}
        )


class EmailSettings(AccountAttributes):
    full_name: str
    email_address: str
    incoming: EmailServer
    outgoing: EmailServer

    @classmethod
    def init(
        cls,
        account_name: str,
        full_name: str,
        email_address: str,
        user_name: str,
        password: str,
        imap_host: str,
        smtp_host: str,
        imap_user_name: str | None = None,
        imap_password: str | None = None,
        imap_port: int = 993,
        imap_ssl: bool = True,
        smtp_port: int = 587,
        smtp_ssl: bool = True,
        smtp_user_name: str | None = None,
        smtp_password: str | None = None,
    ) -> EmailSettings:
        return cls(
            account_name=account_name,
            full_name=full_name,
            email_address=email_address,
            incoming=EmailServer(
                user_name=imap_user_name or user_name,
                password=imap_password or password,
                host=imap_host,
                port=imap_port,
                ssl=imap_ssl,
            ),
            outgoing=EmailServer(
                user_name=smtp_user_name or user_name,
                password=smtp_password or password,
                host=smtp_host,
                port=smtp_port,
                ssl=smtp_ssl,
            ),
        )


class ProviderSettings(AccountAttributes):
    provider_name: str
    api_key: str


class Settings(BaseSettings):
    emails: list[EmailSettings] = []
    providers: list[ProviderSettings] = []

    model_config = SettingsConfigDict(toml_file=CONFIG_PATH)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (TomlConfigSettingsSource(settings_cls),)

    def _to_toml(self) -> str:
        data = self.model_dump()
        return tomli_w.dumps(data)

    def store(self) -> None:
        toml_file = self.model_config["toml_file"]
        toml_file.parent.mkdir(parents=True, exist_ok=True)
        toml_file.write_text(self._to_toml())
        logger.info(f"Settings stored in {toml_file}")


_settings = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if not _settings or reload:
        logger.info(f"Loading settings from {CONFIG_PATH}")
        _settings = Settings()
    return _settings


def store_settings(settings: Settings | None = None) -> None:
    if not settings:
        settings = get_settings()
    settings.store()
    return


def delete_settings() -> None:
    if not CONFIG_PATH.exists():
        logger.info(f"Settings file {CONFIG_PATH} does not exist")
        return
    CONFIG_PATH.unlink()
    logger.info(f"Deleted settings file {CONFIG_PATH}")
