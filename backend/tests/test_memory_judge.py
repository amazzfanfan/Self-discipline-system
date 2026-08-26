"""Tests for the memory judgment system.

Covers rule filtering, importance scoring, decay, and the hybrid LLM path.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

from app.services.memory_judge import RuleBasedFilter, LLMBasedJudge, HybridMemoryJudge
from app.services.memory_scorer import MemoryImportanceScorer
from app.services.memory_decay import MemoryDecay
from app.services.prompt_service import prompt_service


# ============================================================
# TestRuleBasedFilter
# ============================================================

class TestRuleBasedFilter:
    """Test the rule-based quick filter."""

    def setup_method(self):
        self.f = RuleBasedFilter()

    # -- High priority patterns (should_remember=True) --

    @pytest.mark.parametrize("text, expected_type", [
        ("我的目标是明年学会弹钢琴", "goal"),
        ("计划要减肥十公斤", "goal"),
        ("打算去日本旅游", "goal"),
        ("准备开始学画画", "goal"),
        ("想要成为一个作家", "goal"),
    ])
    def test_high_priority_goal(self, text, expected_type):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert importance >= 0.8
        assert mem_type == expected_type

    @pytest.mark.parametrize("text", [
        "我喜欢吃火锅",
        "我最爱的颜色是蓝色",
        "我讨厌早起",
        "我的习惯是每天跑步",
    ])
    def test_high_priority_preference(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert mem_type == "preference"
        assert importance >= 0.7

    @pytest.mark.parametrize("text", [
        "我的生日是三月五号",
        "我的名字是张三",
        "我工作于腾讯",
        "我家住在北京",
    ])
    def test_high_priority_fact(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert mem_type == "fact"
        assert importance >= 0.85

    @pytest.mark.parametrize("text", [
        "我养了一只狗狗",
        "我养的一只狗叫可乐",
        "我的狗名字是可乐",
    ])
    def test_high_priority_pet_fact(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert importance >= 0.9
        assert mem_type == "personal"

    @pytest.mark.parametrize("text", [
        "我的体重是七十公斤",
        "我每天运动一小时",
        "我的血压有点高",
        "我最近失眠了",
    ])
    def test_high_priority_health(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert mem_type == "health"
        assert importance >= 0.75

    def test_high_priority_emotion(self):
        result = self.f.filter("我最近很难过")
        assert result is not None
        should, importance, mem_type = result
        assert should is True
        assert mem_type == "emotion"
        assert importance >= 0.7

    # -- Low priority patterns (should_remember=False) --

    @pytest.mark.parametrize("text", [
        "你能做什么",
        "你是谁",
        "你好",
        "你好呀",
        "测试",
        "嗯",
        "ok",
    ])
    def test_low_priority_returns_false(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, importance, mem_type = result
        assert should is False
        assert importance <= 0.2
        assert mem_type == "conversation"

    @pytest.mark.parametrize("text", [
        "什么是量子力学",
        "如何学习编程",
    ])
    def test_low_priority_question(self, text):
        result = self.f.filter(text)
        assert result is not None
        should, _, mem_type = result
        assert should is False
        assert mem_type == "conversation"

    # -- Edge cases --

    def test_empty_text(self):
        result = self.f.filter("")
        assert result == (False, 0.0, "conversation")

    def test_whitespace_only(self):
        result = self.f.filter("   ")
        assert result == (False, 0.0, "conversation")

    def test_ambiguous_text_returns_none(self):
        """Random text that doesn't match any pattern returns None."""
        result = self.f.filter("今天天气不错，适合散步")
        assert result is None

    def test_system_role(self):
        """Low priority pattern with system role."""
        result = self.f.filter("你好", role="system")
        assert result is not None
        should, _, _ = result
        assert should is False

    def test_high_priority_importance_values(self):
        """Verify specific importance values for different categories."""
        _, imp_goal, _ = self.f.filter("我的目标是学画画")
        _, imp_pref, _ = self.f.filter("我喜欢游泳")
        _, imp_fact, _ = self.f.filter("我的生日是元旦")
        # Facts should score highest, then goals, then preferences
        assert imp_fact >= imp_goal >= imp_pref


# ============================================================
# TestMemoryImportanceScorer
# ============================================================

class TestMemoryImportanceScorer:
    """Test the importance scoring module."""

    def setup_method(self):
        self.scorer = MemoryImportanceScorer()

    def test_empty_content_returns_zero(self):
        assert self.scorer.score("") == 0.0
        assert self.scorer.score("   ") == 0.0

    def test_high_importance_goal_scores_high(self):
        score = self.scorer.score("我的目标是明年学会弹钢琴")
        assert score >= 0.7

    def test_low_importance_ai_question(self):
        """Matches first low-importance pattern (index 0), safe path."""
        score = self.scorer.score("你能做什么")
        assert score <= 0.3

    def test_low_importance_names(self):
        """Matches second low-importance pattern (index 1), safe path."""
        score = self.scorer.score("你是谁")
        assert score <= 0.3

    def test_low_importance_simple_request(self):
        """Matches low-importance pattern (index 2), safe path."""
        score = self.scorer.score("帮我翻译一下")
        assert score <= 0.3

    def test_low_importance_explain(self):
        """Matches low-importance pattern (index 3), safe path."""
        score = self.scorer.score("解释一下这个概念")
        assert score <= 0.3

    def test_low_importance_what_is(self):
        """Matches low-importance pattern (index 4), safe path."""
        score = self.scorer.score("什么是人工智能")
        assert score <= 0.3

    def test_neutral_text_returns_bounded_score(self):
        score = self.scorer.score("今天天气不错，适合出去走走")
        assert 0.0 <= score <= 1.0

    def test_short_greeting_scores_low(self):
        assert self.scorer.score("你好") <= 0.3

    def test_rule_score_with_safe_input(self):
        """Test _rule_score with text that matches low-importance pattern (safe path)."""
        assert self.scorer._rule_score("你能做什么") <= 0.2

    def test_behavior_score_defaults(self):
        """Test _behavior_score with empty context."""
        score = self.scorer._behavior_score({})
        assert 0.4 <= score <= 0.6

    def test_behavior_score_question_flag(self):
        score_q = self.scorer._behavior_score({"has_question": True})
        score_no_q = self.scorer._behavior_score({"has_question": False})
        assert score_q >= score_no_q


# ============================================================
# TestMemoryDecay
# ============================================================

class TestMemoryDecay:
    """Test the memory decay calculator."""

    def setup_method(self):
        self.decay = MemoryDecay()

    def test_no_decay_for_recent_memory(self):
        """Memory created just now should have minimal decay."""
        now = datetime.now(timezone.utc)
        result = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=now,
            last_accessed=now,
            access_count=1,
        )
        assert result >= 0.9

    def test_decay_for_old_memory(self):
        """Memory created 100 days ago should decay significantly."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=100)
        result = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old,
            last_accessed=old,
            access_count=0,
        )
        assert result < 0.5

    def test_recent_access_reduces_decay(self):
        """Recently accessed memory decays less than never-accessed."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=30)

        never_accessed = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old,
            last_accessed=None,
            access_count=0,
        )
        recently_accessed = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old,
            last_accessed=now,
            access_count=5,
        )
        assert recently_accessed > never_accessed

    def test_high_access_count_slows_decay(self):
        """More access counts should slow the decay."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)

        low_access = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old,
            last_accessed=old,
            access_count=1,
        )
        high_access = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old,
            last_accessed=old,
            access_count=20,
        )
        assert high_access > low_access

    def test_minimum_importance_floor(self):
        """Decayed importance should never go below MIN_IMPORTANCE."""
        now = datetime.now(timezone.utc)
        very_old = now - timedelta(days=10000)
        result = self.decay.calculate_importance(
            original_importance=0.01,
            created_at=very_old,
            last_accessed=very_old,
            access_count=0,
        )
        assert result >= self.decay.MIN_IMPORTANCE

    def test_naive_datetime_handled(self):
        """Naive datetime (no tzinfo) should be auto-converted to UTC."""
        naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.decay.calculate_importance(
            original_importance=0.8,
            created_at=naive_now,
            last_accessed=None,
            access_count=0,
        )
        assert result > 0.0

    def test_preserves_original_importance_scaling(self):
        """Higher original importance should result in higher decayed value."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=30)

        low = self.decay.calculate_importance(
            original_importance=0.3, created_at=old, last_accessed=old, access_count=1
        )
        high = self.decay.calculate_importance(
            original_importance=0.9, created_at=old, last_accessed=old, access_count=1
        )
        assert high > low

    def test_decay_rate_constant(self):
        """Verify the decay rate is reasonable."""
        assert 0.0 < self.decay.DECAY_RATE < 1.0

    def test_access_boost_factor(self):
        """Verify the access boost factor is reasonable."""
        assert 0.0 < self.decay.ACCESS_BOOST_FACTOR < 1.0

    def test_zero_original_importance(self):
        """Zero original importance stays at MIN_IMPORTANCE."""
        now = datetime.now(timezone.utc)
        result = self.decay.calculate_importance(
            original_importance=0.0,
            created_at=now,
            last_accessed=now,
            access_count=1,
        )
        assert result >= self.decay.MIN_IMPORTANCE


# ============================================================
# TestHybridMemoryJudge
# ============================================================

class TestHybridMemoryJudge:
    """Test the hybrid memory judge integration."""

    def _run(self, coro):
        """Helper to run async in sync test."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_rule_layer_high_priority(self):
        """High priority text should be caught by rule layer."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge("我的目标是学会弹钢琴"))
        assert result["should_remember"] is True
        assert result["source"] == "rule"
        assert result["importance"] > 0.0

    def test_rule_layer_low_priority(self):
        """Low priority text should be caught by rule layer."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge("你好"))
        assert result["should_remember"] is False
        assert result["source"] == "rule"

    def test_empty_text(self):
        judge = HybridMemoryJudge()
        result = self._run(judge.judge(""))
        assert result["should_remember"] is False
        assert result["importance"] == 0.0

    def test_ambiguous_text_without_llm_or_scorer(self):
        """Without LLM or scorer, ambiguous text uses default (0.5)."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge("今天天气不错，适合出去走走"))
        assert result["source"] == "hybrid"
        assert result["should_remember"] is True  # 0.5 >= 0.5

    def test_apply_decay_without_decay_module(self):
        """Without MemoryDecay configured, apply_decay returns original."""
        judge = HybridMemoryJudge()
        result = judge.apply_decay(
            original_importance=0.8,
            created_at=datetime.now(timezone.utc),
        )
        assert result == 0.8

    def test_apply_decay_with_decay_module(self):
        """With MemoryDecay configured, apply_decay should reduce importance."""
        decay = MemoryDecay()
        judge = HybridMemoryJudge(memory_decay=decay)
        old = datetime.now(timezone.utc) - timedelta(days=90)
        result = judge.apply_decay(
            original_importance=1.0,
            created_at=old,
            last_accessed=old,
            access_count=0,
        )
        assert result < 1.0
        assert result >= MemoryDecay.MIN_IMPORTANCE

    def test_llm_judge_parses_valid_response(self):
        mock_client = AsyncMock()
        mock_client.chat.return_value = (
            '{"should_remember": true, "importance": 0.85, '
            '"memory_type": "fact", "reason": "test"}'
        )
        judge = LLMBasedJudge(mock_client)
        result = self._run(judge.judge("昨天去了一个有意思的展览"))
        assert result == (True, 0.85, "fact")
        mock_client.chat.assert_awaited_once()

    def test_llm_prompt_formats_json_example(self):
        prompt = prompt_service.build_judge_prompt("test")
        assert '"should_remember": true/false' in prompt
        assert "test" in prompt

    def test_llm_judge_normalizes_invalid_fields(self):
        mock_client = AsyncMock()
        mock_client.chat.return_value = (
            '{"should_remember": true, "importance": 5, '
            '"memory_type": "unknown"}'
        )
        judge = LLMBasedJudge(mock_client)
        result = self._run(judge.judge("值得记忆的内容"))
        assert result == (True, 1.0, "conversation")

    def test_hybrid_without_llm_no_scorer(self):
        """Hybrid judge with no LLM and no scorer defaults to 0.5."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge("今天天气不错"))
        assert result["source"] == "hybrid"
        assert result["importance"] == 0.5

    def test_llm_path_normalizes_active_weights(self):
        mock_client = AsyncMock()
        mock_client.chat.return_value = (
            '{"should_remember": true, "importance": 0.9, "memory_type": "fact"}'
        )
        scorer = AsyncMock()
        scorer.score = lambda *_args, **_kwargs: 0.8
        judge = HybridMemoryJudge(llm_client=mock_client, importance_scorer=scorer)

        result = self._run(judge.judge("这是一条规则未覆盖但稳定的个人事实"))

        assert result["should_remember"] is True
        assert result["importance"] > 0.8

    def test_rule_result_structure(self):
        """Verify the result dict has all expected keys."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge("我的目标是学会弹钢琴"))
        expected_keys = {
            "should_remember", "importance", "memory_type", "source",
            "rule_result", "llm_result", "scorer_score",
        }
        assert expected_keys.issubset(result.keys())

    def test_judge_with_decay_integration(self):
        """Test judge_with_decay combines judge + decay."""
        decay = MemoryDecay()
        judge = HybridMemoryJudge(memory_decay=decay)
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=60)
        result = self._run(judge.judge_with_decay(
            text="我的目标是学会弹钢琴",
            created_at=old,
            last_accessed=old,
            access_count=1,
        ))
        assert result["should_remember"] is True
        # importance should be less than the rule-based importance (decayed)
        rule_importance = judge.rule_filter.filter("我的目标是学会弹钢琴")[1]
        assert result["importance"] < rule_importance

    def test_judge_with_decay_no_memory_decay(self):
        """judge_with_decay without decay module returns undecayed result."""
        judge = HybridMemoryJudge()
        result = self._run(judge.judge_with_decay(
            text="我的目标是学会弹钢琴",
            created_at=datetime.now(timezone.utc),
        ))
        rule_importance = judge.rule_filter.filter("我的目标是学会弹钢琴")[1]
        # Without decay, importance should equal rule importance
        assert result["importance"] == rule_importance

    def test_rule_weight_constants(self):
        """Verify hybrid judge weight constants sum to reasonable values."""
        total = HybridMemoryJudge.RULE_WEIGHT + HybridMemoryJudge.LLM_WEIGHT + HybridMemoryJudge.SCORER_WEIGHT
        assert 0.9 <= total <= 1.1  # approximately 1.0
