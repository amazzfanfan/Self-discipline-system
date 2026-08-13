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
        "RATE_LIMIT_STORAGE_URI": "redis://redis:6379/0",
        "OPS_METRICS_TOKEN": "m" * 32,
        "SCHEDULER_PERSIST_JOBS": True,
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
        ({"RATE_LIMIT_STORAGE_URI": ""}, "RATE_LIMIT_STORAGE_URI"),
        ({"TRUSTED_PROXY_CIDRS": []}, "TRUSTED_PROXY_CIDRS"),
        ({"OPS_METRICS_TOKEN": "short"}, "OPS_METRICS_TOKEN"),
        ({"AI_BUDGET_ENFORCEMENT": False}, "AI_BUDGET_ENFORCEMENT"),
        ({"WORKER_CONCURRENCY": 1, "WORKER_AI_CONCURRENCY": 2}, "WORKER_AI_CONCURRENCY"),
        ({"AI_USER_DAILY_TOKEN_LIMIT": 0}, "AI budget"),
        (
            {"AI_USER_DAILY_CALL_LIMIT": 6000, "AI_GLOBAL_DAILY_CALL_LIMIT": 5000},
            "User AI call budget",
        ),
        ({"SCHEDULER_PERSIST_JOBS": False}, "persistent jobs"),
    ],
)
def test_insecure_production_settings_are_rejected(overrides, message):
    with pytest.raises(RuntimeError, match=message):
        production_settings(**overrides).validate_runtime_security()
