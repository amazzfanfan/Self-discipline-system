import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from app.services import cache_service
from scripts import worker


def test_claim_stale_jobs_returns_claimed_messages(monkeypatch):
    client = MagicMock()
    client.xgroup_create = AsyncMock(side_effect=RuntimeError("BUSYGROUP Consumer Group name already exists"))
    claimed = [("1-0", {"kind": "index_goal", "payload": "{}"})]
    client.xautoclaim = AsyncMock(return_value=["0-0", claimed, []])
    monkeypatch.setattr(cache_service, "_get_redis", lambda: client)

    result = asyncio.run(
        cache_service.claim_stale_background_jobs("worker-1", min_idle_ms=1_000)
    )

    assert result == claimed
    client.xautoclaim.assert_awaited_once()


def test_worker_status_reports_heartbeat_and_backlog(monkeypatch):
    client = MagicMock()
    client.get = AsyncMock(
        return_value=json.dumps({"consumer": "worker-1", "seen_at": "2026-08-12T00:00:00+00:00"})
    )
    client.xinfo_groups = AsyncMock(
        return_value=[{"name": cache_service.BACKGROUND_JOB_GROUP, "pending": 2, "lag": 4}]
    )
    monkeypatch.setattr(cache_service, "_get_redis", lambda: client)

    result = asyncio.run(cache_service.get_background_worker_status())

    assert result == {
        "ready": True,
        "consumer": "worker-1",
        "last_seen": "2026-08-12T00:00:00+00:00",
        "pending": 2,
        "lag": 4,
    }


def test_failed_job_is_left_pending_for_retry(monkeypatch):
    monkeypatch.setattr(worker, "process_job", AsyncMock(side_effect=RuntimeError("temporary")))
    failure = AsyncMock(return_value=1)
    dead_letter = AsyncMock()
    acknowledge = AsyncMock()
    monkeypatch.setattr(worker, "record_background_job_failure", failure)
    monkeypatch.setattr(worker, "move_background_job_to_dead_letter", dead_letter)
    monkeypatch.setattr(worker, "acknowledge_background_job", acknowledge)

    asyncio.run(worker.handle_message("1-0", {"kind": "index_goal", "payload": "{}"}))

    failure.assert_awaited_once_with("1-0")
    dead_letter.assert_not_awaited()
    acknowledge.assert_not_awaited()


def test_repeated_failure_moves_job_to_dead_letter(monkeypatch):
    monkeypatch.setattr(worker, "process_job", AsyncMock(side_effect=RuntimeError("permanent")))
    monkeypatch.setattr(
        worker,
        "record_background_job_failure",
        AsyncMock(return_value=worker.MAX_JOB_ATTEMPTS),
    )
    dead_letter = AsyncMock()
    acknowledge = AsyncMock()
    monkeypatch.setattr(worker, "move_background_job_to_dead_letter", dead_letter)
    monkeypatch.setattr(worker, "acknowledge_background_job", acknowledge)
    fields = {"kind": "index_goal", "payload": "{}"}

    asyncio.run(worker.handle_message("1-0", fields))

    dead_letter.assert_awaited_once_with(
        "1-0",
        fields,
        attempts=worker.MAX_JOB_ATTEMPTS,
        error_type="RuntimeError",
    )
    acknowledge.assert_not_awaited()


def test_successful_job_is_acknowledged(monkeypatch):
    monkeypatch.setattr(worker, "process_job", AsyncMock())
    acknowledge = AsyncMock()
    monkeypatch.setattr(worker, "acknowledge_background_job", acknowledge)

    asyncio.run(worker.handle_message("1-0", {"kind": "index_goal", "payload": "{}"}))

    acknowledge.assert_awaited_once_with("1-0")


def test_assessment_generation_job_is_dispatched(monkeypatch):
    generate = AsyncMock()
    monkeypatch.setattr(worker, "process_assessment_generation", generate)

    asyncio.run(
        worker.process_job(
            "generate_assessment_extras",
            {"assessment_run_id": "assessment-id", "user_id": "user-id"},
        )
    )

    generate.assert_awaited_once_with(
        assessment_run_id="assessment-id",
        user_id="user-id",
    )


def test_deduplicated_enqueue_uses_short_lived_marker(monkeypatch):
    client = MagicMock()
    client.set = AsyncMock(return_value=True)
    client.xadd = AsyncMock(return_value="1-0")
    monkeypatch.setattr(cache_service, "_get_redis", lambda: client)

    result = asyncio.run(
        cache_service.enqueue_background_job_once(
            "generate_assessment_extras",
            {"assessment_run_id": "assessment-id"},
            dedupe_key="assessment:assessment-id",
        )
    )

    assert result == "1-0"
    client.set.assert_awaited_once()
    client.xadd.assert_awaited_once()
