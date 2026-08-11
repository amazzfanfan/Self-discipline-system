from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.assessment_generation_service import generation_payload


def test_generation_payload_exposes_progress_without_internal_details():
    run = SimpleNamespace(
        id="assessment-id",
        generation_status="running",
        generation_stage="daily_tasks",
        generation_error=None,
        care_suggestions=["温和清洁"],
        generation_started_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
        generation_completed_at=None,
    )

    assert generation_payload(run) == {
        "assessment_id": "assessment-id",
        "status": "running",
        "stage": "daily_tasks",
        "error": None,
        "care_suggestions": ["温和清洁"],
        "started_at": "2026-08-12T00:00:00+00:00",
        "completed_at": None,
    }
