"""Settings from the environment: SMTP is read at start, fail loud on half a configuration."""

from __future__ import annotations

import pytest

from lasteverlm_account.config import ConfigError, Settings
from lasteverlm_account.mail import SmtpConfig

REQUIRED = {
    "DATABASE_URL": "postgresql://unused",
    "AUTH_JWT_SECRET": "test-secret-not-for-production-0123456789",
    "PUBLIC_BASE_URL": "https://lasteverlm.test/",
    "VOUCHER_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
}


def test_smtp_comes_from_the_environment() -> None:
    settings = Settings.from_env(
        {
            **REQUIRED,
            "SMTP_HOST": "mail.test",
            "SMTP_PORT": "465",
            "SMTP_USERNAME": "u",
            "SMTP_PASSWORD": "p",
            "SMTP_FROM_ADDRESS": "noreply@mail.test",
            "SMTP_STARTTLS": "false",
        }
    )
    assert settings.smtp == SmtpConfig("mail.test", 465, "u", "p", "noreply@mail.test", False)
    assert settings.public_base_url == "https://lasteverlm.test"


def test_without_smtp_host_there_is_no_smtp() -> None:
    assert Settings.from_env({**REQUIRED, "SMTP_FROM_ADDRESS": "x@y.test"}).smtp is None


def test_smtp_host_without_from_address_fails_at_start() -> None:
    with pytest.raises(ConfigError, match="SMTP_FROM_ADDRESS"):
        Settings.from_env({**REQUIRED, "SMTP_HOST": "mail.test"})


def test_judge_models_come_from_the_environment() -> None:
    import base64

    env = {**REQUIRED, "VOUCHER_KEY": base64.b64encode(b"k" * 32).decode()}
    defaults = Settings.from_env(env).judge_models
    assert set(defaults) == {"low", "medium", "high"}
    custom = Settings.from_env({**env, "JUDGE_MODELS": '{"high": "special-model"}'}).judge_models
    assert custom["high"] == "special-model" and custom["low"] == defaults["low"]
