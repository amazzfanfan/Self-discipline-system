from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def app_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().APP_TIMEZONE)


def local_now() -> datetime:
    return datetime.now(app_timezone())


def local_today() -> date:
    return local_now().date()


def seconds_until_local_midnight() -> int:
    now = local_now()
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((tomorrow - now).total_seconds()))
