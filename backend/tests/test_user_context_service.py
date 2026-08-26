from app.services.user_context_service import select_context


def test_context_selection_is_query_aware():
    exercise = select_context("根据我最近的完成情况，今天适合做什么运动？")

    assert exercise.dimensions == ("exercise",)
    assert exercise.include_behavior is True
    assert exercise.include_today is True
    assert exercise.include_constraints is True
    assert exercise.include_skin is False


def test_weight_context_does_not_load_unrelated_skin_data():
    weight = select_context("我最近30天体重变化怎么样？")

    assert weight.include_weight is True
    assert weight.include_skin is False
    assert weight.dimensions == ("diet",)


def test_small_talk_keeps_context_minimal():
    selection = select_context("你好")

    assert selection.labels() == ["identity"]
