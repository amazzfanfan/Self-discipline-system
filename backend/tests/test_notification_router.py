import pytest
from fastapi import HTTPException

from app.modules.notification.router import _validate_push_endpoint


def test_push_endpoint_accepts_trusted_provider():
    _validate_push_endpoint("https://fcm.googleapis.com/fcm/send/example-token")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/token",
        "https://localhost/internal",
        "https://googleapis.com.attacker.example/push",
    ],
)
def test_push_endpoint_rejects_untrusted_or_insecure_hosts(endpoint):
    with pytest.raises(HTTPException) as exc_info:
        _validate_push_endpoint(endpoint)
    assert exc_info.value.status_code == 422
