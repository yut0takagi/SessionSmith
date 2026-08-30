"""`SessionSmith.tracer.AlgorithmTracer` のテスト"""

import json
import types

import pytest

from SessionSmith.tracer import AlgorithmTracer


def _run_traced_loop(tracer):
    """トレース対象の簡単な処理"""
    with tracer:
        total = 0
        for i in range(3):
            total += i
    return total


class TestConstructor:
    def test_defaults(self):
        tracer = AlgorithmTracer()

        assert tracer.track_all is True
        assert tracer.target_variables is None
        assert tracer.trace_data == []
        assert types.ModuleType in tracer.exclude_types

    def test_custom_exclude_types_replace_the_defaults(self):
        tracer = AlgorithmTracer(exclude_types=[int])

        assert tracer.exclude_types == [int]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"max_depth": -1},
            {"max_array_size": -1},
            {"max_string_length": -1},
        ],
    )
    def test_negative_parameters_are_rejected(self, kwargs):
        with pytest.raises(ValueError):
            AlgorithmTracer(**kwargs)


class TestSerializeValue:
    def test_primitives_pass_through(self):
        tracer = AlgorithmTracer()

        assert tracer._serialize_value(1) == 1
        assert tracer._serialize_value("abc") == "abc"
        assert tracer._serialize_value(None) is None
        assert tracer._serialize_value(True) is True

    def test_long_strings_are_truncated(self):
        tracer = AlgorithmTracer(max_string_length=10)

        result = tracer._serialize_value("x" * 100)

        assert len(result) < 100
        assert result.startswith("x" * 10)

    def test_large_lists_are_sampled(self):
        tracer = AlgorithmTracer(max_array_size=5)

        result = tracer._serialize_value(list(range(100)))

        # 全要素をそのまま保持しない
        assert result != list(range(100))

    def test_nested_structures_are_serialized(self):
        tracer = AlgorithmTracer()

        result = tracer._serialize_value({"a": [1, 2], "b": {"c": 3}})

        assert result["a"] == [1, 2]
        assert result["b"]["c"] == 3

    def test_depth_limit_is_respected(self):
        tracer = AlgorithmTracer(max_depth=1)

        deep = {"l1": {"l2": {"l3": {"l4": "bottom"}}}}
        result = tracer._serialize_value(deep)

        # 最下層までそのままは展開されない
        assert result != deep

    def test_unserializable_object_does_not_raise(self):
        class Weird:
            def __repr__(self):
                raise RuntimeError("boom")

        tracer = AlgorithmTracer()

        # 例外を投げずに何かを返す
        tracer._serialize_value(Weird())


class TestTracing:
    def test_context_manager_records_steps(self):
        tracer = AlgorithmTracer()

        assert _run_traced_loop(tracer) == 3
        assert len(tracer.get_trace_data()) > 0

    def test_tracing_stops_after_the_context(self):
        tracer = AlgorithmTracer()
        _run_traced_loop(tracer)

        recorded = len(tracer.get_trace_data())
        _ = sum(range(10))  # トレース対象外

        assert len(tracer.get_trace_data()) == recorded

    def test_start_and_stop_directly(self):
        tracer = AlgorithmTracer()

        tracer.start()
        _ = 1 + 1
        tracer.stop()

        assert isinstance(tracer.get_trace_data(), list)

    def test_clear_resets_the_data(self):
        tracer = AlgorithmTracer()
        _run_traced_loop(tracer)
        assert tracer.get_trace_data()

        tracer.clear()

        assert tracer.get_trace_data() == []

    def test_target_variables_limits_what_is_recorded(self):
        tracer = AlgorithmTracer(target_variables=["total"], track_all=False)

        _run_traced_loop(tracer)

        recorded = set()
        for step in tracer.get_trace_data():
            recorded.update(step.get("variables", {}).keys())

        assert recorded <= {"total"}


class TestSummary:
    def test_empty_summary(self):
        summary = AlgorithmTracer().get_summary()

        assert summary == {
            "total_steps": 0,
            "variables_tracked": [],
            "line_range": None,
            "functions_called": [],
        }

    def test_summary_after_tracing(self):
        tracer = AlgorithmTracer()
        _run_traced_loop(tracer)

        summary = tracer.get_summary()

        assert summary["total_steps"] == len(tracer.get_trace_data())
        assert summary["line_range"] is not None
        assert summary["line_range"][0] <= summary["line_range"][1]
        assert isinstance(summary["variables_tracked"], list)
        assert isinstance(summary["functions_called"], list)


class TestSaveAndLoad:
    def test_json_roundtrip(self, tmp_path):
        tracer = AlgorithmTracer()
        _run_traced_loop(tracer)
        original = tracer.get_trace_data()

        path = tmp_path / "trace.json"
        tracer.save(path, format="json")
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8"))

        restored = AlgorithmTracer()
        restored.load(path, format="json")

        assert len(restored.get_trace_data()) == len(original)

    def test_pickle_roundtrip(self, tmp_path):
        tracer = AlgorithmTracer()
        _run_traced_loop(tracer)

        path = tmp_path / "trace.pkl"
        tracer.save(path, format="pickle")

        restored = AlgorithmTracer()
        restored.load(path, format="pickle")

        assert len(restored.get_trace_data()) == len(tracer.get_trace_data())

    def test_unknown_format_raises(self, tmp_path):
        tracer = AlgorithmTracer()

        with pytest.raises(ValueError):
            tracer.save(tmp_path / "trace.xyz", format="xyz")

    def test_loading_a_missing_file_raises(self, tmp_path):
        tracer = AlgorithmTracer()

        with pytest.raises((FileNotFoundError, OSError)):
            tracer.load(tmp_path / "nope.json", format="json")
