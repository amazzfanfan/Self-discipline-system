import json
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import web_push_service


def test_web_push_requires_all_vapid_settings(monkeypatch):
    monkeypatch.setattr(web_push_service, "webpush", MagicMock())
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "public")
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_EMAIL", "mailto:a@example.com")

    assert web_push_service.web_push_configured() is False
    assert web_push_service.web_push_public_config() == {
        "enabled": False,
        "public_key": None,
    }


def test_web_push_payload_contains_link_and_uses_subscription_keys(monkeypatch):
    sender = MagicMock()
    monkeypatch.setattr(web_push_service, "webpush", sender)
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_PUBLIC_KEY", "public")
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_PRIVATE_KEY", "private")
    monkeypatch.setattr(web_push_service.settings, "WEB_PUSH_VAPID_EMAIL", "mailto:a@example.com")
    subscription = SimpleNamespace(endpoint="https://push.example/1", p256dh="p-key", auth="a-key")
    notification = SimpleNamespace(
        id="notification-id",
        title="任务提醒",
        message="该开始训练了",
        kind="task_reminder",
        payload={"link": "/tasks"},
    )

    web_push_service._send(subscription, notification)

    kwargs = sender.call_args.kwargs
    assert kwargs["subscription_info"]["keys"] == {"p256dh": "p-key", "auth": "a-key"}
    assert json.loads(kwargs["data"])["link"] == "/tasks"


def test_quiet_hours_support_ranges_across_midnight():
    assert web_push_service.within_quiet_hours(time(23, 0), time(22, 30), time(7, 30))
    assert web_push_service.within_quiet_hours(time(7, 0), time(22, 30), time(7, 30))
    assert not web_push_service.within_quiet_hours(time(12, 0), time(22, 30), time(7, 30))
    assert web_push_service.within_quiet_hours(time(12, 0), time(9, 0), time(18, 0))


def test_push_retry_backoff_is_bounded():
    now = datetime(2026, 8, 12, tzinfo=timezone.utc)
    assert web_push_service.next_retry_at(1, now=now).minute == 1
    assert web_push_service.next_retry_at(2, now=now).minute == 5
    assert web_push_service.next_retry_at(99, now=now).minute == 15
