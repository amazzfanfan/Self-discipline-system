import pytest

from app.core.config import Settings


def production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "SECRET_KEY": "a" * 64,
        "AUTH_COOKIE_SECURE": True,
        "AI_API_KEY": "configured",
        "CORS_ORIGINS": ["https://example.com"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_secure_production_settings_are_accepted():
    production_settings().validate_runtime_security()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SECRET_KEY": "zengfan"}, "SECRET_KEY"),
        ({"AUTH_COOKIE_SECURE": False}, "AUTH_COOKIE_SECURE"),
        ({"CORS_ORIGINS": ["http://localhost:5174"]}, "CORS"),
        ({"DEBUG": True}, "DEBUG"),
        ({"AI_API_KEY": ""}, "AI_API_KEY"),
    ],
)
def test_insecure_production_settings_are_rejected(overrides, message):
    with pytest.raises(RuntimeError, match=message):
        production_settings(**overrides).validate_runtime_security()
