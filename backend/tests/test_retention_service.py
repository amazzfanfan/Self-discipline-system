import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import retention_service


class _Scalars:
    def __init__(self, items):
        self.items = items

    def scalars(self):
        return self

    def all(self):
        return self.items


def test_cleanup_upload_files_removes_only_old_orphans(tmp_path, monkeypatch):
    db = SimpleNamespace(execute=AsyncMock(side_effect=[_Scalars([]), _Scalars([])]))
    monkeypatch.setattr(retention_service, "UPLOAD_DIRECTORY", tmp_path.resolve())
    monkeypatch.setattr(retention_service.get_settings(), "TEMP_UPLOAD_RETENTION_HOURS", 24)
    monkeypatch.setattr(retention_service.get_settings(), "PHOTO_RETENTION_DAYS", 365)
    old_file = tmp_path / "old.jpg"
    recent_file = tmp_path / "recent.jpg"
    old_file.write_bytes(b"old")
    recent_file.write_bytes(b"recent")
    now = datetime.now(timezone.utc)
    old_timestamp = (now - timedelta(hours=25)).timestamp()
    os.utime(old_file, (old_timestamp, old_timestamp))

    result = asyncio.run(retention_service.cleanup_upload_files(db, now=now))

    assert result["orphan_uploads_deleted"] == 1
    assert not old_file.exists()
    assert recent_file.exists()
