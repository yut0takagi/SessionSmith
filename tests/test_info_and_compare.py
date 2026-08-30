"""`SessionSmith.info` と `SessionSmith.compare` のテスト"""

import gzip
import pickle

import pytest

from SessionSmith.compare import compare_sessions, print_comparison
from SessionSmith.info import (
    get_session_info,
    list_session_variables,
    print_session_info,
)


def _write_pickle(path, data, compress=None):
    if compress == "gzip":
        with gzip.open(path, "wb") as f:
            pickle.dump(data, f)
    else:
        with open(path, "wb") as f:
            pickle.dump(data, f)
    return path


@pytest.fixture
def session_a(tmp_path):
    return _write_pickle(tmp_path / "a.pkl", {"x": 1, "y": [1, 2, 3], "shared": "same"})


@pytest.fixture
def session_b(tmp_path):
    return _write_pickle(tmp_path / "b.pkl", {"y": [9, 9], "z": {"k": 1}, "shared": "same"})


class TestGetSessionInfo:
    def test_basic_fields(self, session_a):
        info = get_session_info(session_a)

        assert info["file_path"] == str(session_a)
        assert info["file_size"] > 0
        assert info["variable_count"] == 3
        assert info["total_data_size"] > 0
        assert info["compression"] is None
        assert info["metadata"] is None
        assert "modified_time" in info

    def test_variables_are_sorted_with_type_and_size(self, session_a):
        info = get_session_info(session_a)

        names = [v["name"] for v in info["variables"]]
        assert names == sorted(names) == ["shared", "x", "y"]

        by_name = {v["name"]: v for v in info["variables"]}
        assert by_name["x"]["type"] == "int"
        assert by_name["y"]["type"] == "list"
        assert by_name["shared"]["size"] > 0

    def test_metadata_is_extracted_and_not_counted_as_a_variable(self, tmp_path):
        path = _write_pickle(
            tmp_path / "meta.pkl",
            {"a": 1, "__metadata__": {"saved_at": "2026-01-01", "version": "2.2.0"}},
        )

        info = get_session_info(path)

        assert info["metadata"] == {"saved_at": "2026-01-01", "version": "2.2.0"}
        assert info["variable_count"] == 1
        assert [v["name"] for v in info["variables"]] == ["a"]

    def test_compression_is_reported(self, tmp_path):
        """圧縮形式が報告されること（issue #58 の回帰テスト）

        修正前は _load_session_file() が compression を None で初期化したまま
        一度も代入しておらず、常に None を返していた。
        """
        path = _write_pickle(tmp_path / "c.pkl.gz", {"a": 1}, compress="gzip")

        assert get_session_info(path)["compression"] == "gzip"

    def test_uncompressed_reports_none(self, session_a):
        assert get_session_info(session_a)["compression"] is None

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises((FileNotFoundError, OSError)):
            get_session_info(tmp_path / "nope.pkl")


class TestListSessionVariables:
    def test_returns_sorted_names(self, session_a):
        assert list_session_variables(session_a) == ["shared", "x", "y"]

    def test_empty_session(self, tmp_path):
        path = _write_pickle(tmp_path / "empty.pkl", {})
        assert list_session_variables(path) == []


class TestPrintSessionInfo:
    def test_prints_the_summary(self, session_a, capsys):
        print_session_info(session_a)

        out = capsys.readouterr().out
        assert str(session_a) in out
        assert "shared" in out and "x" in out and "y" in out


class TestCompareSessions:
    def test_added_removed_and_common(self, session_a, session_b):
        result = compare_sessions(session_a, session_b)

        assert result["common_variables"] == ["shared", "y"]
        assert result["added_variables"] == ["z"]
        assert result["removed_variables"] == ["x"]

    def test_detailed_detects_changed_values(self, session_a, session_b):
        """値が変わった変数を検出できること（issue #57 の回帰テスト）

        修正前は load_session() を既定の use_ssm=True で呼んでいたため、
        一時的な名前空間に何も読み込まれず、常に空のリストを返していた。
        """
        result = compare_sessions(session_a, session_b, detailed=True)

        # y は両方にあるが値が違う / shared は同じ
        assert "y" in result["changed_variables"]
        assert "shared" not in result["changed_variables"]

    def test_detailed_does_not_create_an_ssm_repository(
        self, session_a, session_b, tmp_path, monkeypatch
    ):
        """比較しただけで .ssm にコミットが作られないこと（issue #57）

        修正前は use_ssm=True の経路で「ファイルを SSM にインポートして
        コミットする」動作になっていた。比較は読み取り専用の分析機能なので、
        リポジトリを書き換えてはいけない。
        """
        import SessionSmith.ssm as ssm_module

        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)
        # SSM のシングルトンは最初に生成された時点の CWD を握るため、
        # このテストの CWD が使われるようにリセットする
        monkeypatch.setattr(ssm_module, "_ssm_instance", None)

        compare_sessions(session_a, session_b, detailed=True)

        assert not (work / ".ssm").exists()

    def test_without_detailed_there_is_no_changed_list(self, session_a, session_b):
        result = compare_sessions(session_a, session_b)
        assert "changed_variables" not in result

    def test_identical_sessions(self, tmp_path):
        a = _write_pickle(tmp_path / "same1.pkl", {"a": 1})
        b = _write_pickle(tmp_path / "same2.pkl", {"a": 1})

        result = compare_sessions(a, b, detailed=True)

        assert result["common_variables"] == ["a"]
        assert result["added_variables"] == []
        assert result["removed_variables"] == []
        assert result["changed_variables"] == []

    def test_missing_file_raises(self, session_a, tmp_path):
        with pytest.raises(FileNotFoundError, match="not found"):
            compare_sessions(session_a, tmp_path / "nope.pkl")

        with pytest.raises(FileNotFoundError, match="not found"):
            compare_sessions(tmp_path / "nope.pkl", session_a)


class TestPrintComparison:
    def test_prints_each_section(self, session_a, session_b, capsys):
        print_comparison(session_a, session_b)

        out = capsys.readouterr().out
        assert "Common variables" in out
        assert "shared" in out
        assert "z" in out  # added
        assert "x" in out  # removed

    def test_reports_the_error_and_reraises(self, session_a, tmp_path, capsys):
        with pytest.raises(FileNotFoundError):
            print_comparison(session_a, tmp_path / "nope.pkl")

        assert "Error comparing sessions" in capsys.readouterr().out
