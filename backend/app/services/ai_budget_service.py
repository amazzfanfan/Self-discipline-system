from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.time import local_today, seconds_until_local_midnight
from app.services.cache_service import _get_redis
from app.services.metrics_service import increment_metric


settings = get_settings()


class AIBudgetExceeded(RuntimeError):
    def __init__(self, scope: str, resource: str):
        super().__init__(f"AI {resource} budget exceeded for {scope}")
        self.scope = scope
        self.resource = resource


@dataclass(frozen=True)
class AIBudgetReservation:
    user_key: str
    global_key: str
    reserved_tokens: int


_RESERVE_SCRIPT = """
local user_key = KEYS[1]
local global_key = KEYS[2]
local tokens = tonumber(ARGV[1])
local user_calls_limit = tonumber(ARGV[2])
local global_calls_limit = tonumber(ARGV[3])
local user_tokens_limit = tonumber(ARGV[4])
local global_tokens_limit = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])
local user_calls = tonumber(redis.call('HGET', user_key, 'calls') or '0')
local global_calls = tonumber(redis.call('HGET', global_key, 'calls') or '0')
local user_tokens = tonumber(redis.call('HGET', user_key, 'tokens') or '0')
local global_tokens = tonumber(redis.call('HGET', global_key, 'tokens') or '0')
if user_calls + 1 > user_calls_limit then return 1 end
if global_calls + 1 > global_calls_limit then return 2 end
if user_tokens + tokens > user_tokens_limit then return 3 end
if global_tokens + tokens > global_tokens_limit then return 4 end
redis.call('HINCRBY', user_key, 'calls', 1)
redis.call('HINCRBY', global_key, 'calls', 1)
redis.call('HINCRBY', user_key, 'tokens', tokens)
redis.call('HINCRBY', global_key, 'tokens', tokens)
redis.call('EXPIRE', user_key, ttl)
redis.call('EXPIRE', global_key, ttl)
return 0
"""


_SETTLE_SCRIPT = """
local delta = tonumber(ARGV[1])
for _, key in ipairs(KEYS) do
  local current = tonumber(redis.call('HGET', key, 'tokens') or '0')
  local next_value = math.max(0, current + delta)
  redis.call('HSET', key, 'tokens', next_value)
end
return 1
"""


def _keys(user_id: str | None) -> tuple[str, str]:
    day = local_today().isoformat()
    identity = (user_id or "system")[:80]
    return (
        f"system-agent:ai-budget:user:{identity}:{day}",
        f"system-agent:ai-budget:global:{day}",
    )


async def reserve_ai_budget(
    user_id: str | None,
    estimated_tokens: int,
) -> AIBudgetReservation | None:
    if not settings.AI_BUDGET_ENFORCEMENT:
        return None
    tokens = max(1, int(estimated_tokens))
    user_key, global_key = _keys(user_id)
    result = int(
        await _get_redis().eval(
            _RESERVE_SCRIPT,
            2,
            user_key,
            global_key,
            tokens,
            settings.AI_USER_DAILY_CALL_LIMIT,
            settings.AI_GLOBAL_DAILY_CALL_LIMIT,
            settings.AI_USER_DAILY_TOKEN_LIMIT,
            settings.AI_GLOBAL_DAILY_TOKEN_LIMIT,
            max(60, seconds_until_local_midnight() + 300),
        )
    )
    if result:
        scope = "user" if result in {1, 3} else "global"
        resource = "calls" if result in {1, 2} else "tokens"
        await increment_metric(f"ai_budget:{scope}:{resource}:rejected")
        raise AIBudgetExceeded(scope, resource)
    await increment_metric("ai_budget:reserved")
    return AIBudgetReservation(user_key, global_key, tokens)


async def settle_ai_budget(
    reservation: AIBudgetReservation | None,
    actual_tokens: int,
) -> None:
    if reservation is None or actual_tokens <= 0:
        return
    delta = int(actual_tokens) - reservation.reserved_tokens
    if delta:
        await _get_redis().eval(
            _SETTLE_SCRIPT,
            2,
            reservation.user_key,
            reservation.global_key,
            delta,
        )


async def global_budget_snapshot() -> dict:
    _, global_key = _keys(None)
    raw = await _get_redis().hgetall(global_key)
    return {
        "calls": int(raw.get("calls", 0)),
        "call_limit": settings.AI_GLOBAL_DAILY_CALL_LIMIT,
        "tokens": int(raw.get("tokens", 0)),
        "token_limit": settings.AI_GLOBAL_DAILY_TOKEN_LIMIT,
    }
