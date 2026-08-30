"""テキストファイル入出力のエンコーディングに関するテスト（issue #48）

`open()` / `Path.read_text()` / `Path.write_text()` は `encoding` を省略すると
ロケール依存のエンコーディングを使う。Windows（cp1252 / cp932）では UTF-8 で
書かれたファイルを読めず、`SSM._write_json()` が `ensure_ascii=False` で
書いた日本語のコミットメッセージが壊れる。

`locale.getpreferredencoding` を monkeypatch しても `open()` の既定は変わらないため、
Linux 上ではロケール依存の挙動を再現できない。そこでソースレベルのガードを併用する。
"""

import ast
import pathlib

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent.parent / "SessionSmith"

# `RemoteBackend.read_text()` / `write_text()` は Path のメソッドではなく、
# 内部で明示的に UTF-8 へエンコード/デコードしているため対象外。
_NON_PATH_RECEIVERS = {"backend", "self"}


def _python_files():
    return sorted(PACKAGE_DIR.glob("*.py"))


def _is_binary_mode(node: ast.Call) -> bool:
    """open() の mode 引数がバイナリモードか"""
    mode = None
    if len(node.args) >= 2:
        mode = node.args[1]
    for kw in node.keywords:
        if kw.arg == "mode":
            mode = kw.value
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value


def _has_encoding_kwarg(node: ast.Call) -> bool:
    return any(kw.arg == "encoding" for kw in node.keywords)


def _find_violations(path: pathlib.Path):
    """encoding を指定していないテキストI/Oの (行番号, 内容) を返す"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # 組み込みの open()
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            if not _is_binary_mode(node) and not _has_encoding_kwarg(node):
                violations.append((node.lineno, "open()"))
            continue

        # Path.read_text() / Path.write_text()
        if isinstance(node.func, ast.Attribute) and node.func.attr in ("read_text", "write_text"):
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and receiver.id in _NON_PATH_RECEIVERS:
                continue
            if not _has_encoding_kwarg(node):
                violations.append((node.lineno, f"{node.func.attr}()"))
    return violations


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_text_io_specifies_encoding(path):
    """テキストI/Oが必ず encoding を指定していること（issue #48 の回帰ガード）"""
    violations = _find_violations(path)
    assert not violations, (
        f"{path.name} でロケール依存のテキストI/Oが見つかりました: "
        + ", ".join(f"L{line} {what}" for line, what in violations)
        + "\nWindows で壊れるため encoding='utf-8' を明示してください。"
    )


class TestNonAsciiCommitMessages:
    """非ASCIIのコミットメッセージがロケールに関係なく扱えること"""

    def _make_repo_with_japanese_commit(self, tmp_path):
        from SessionSmith.ssm import SSM

        ssm = SSM(path=tmp_path, globals_dict={"データ": [1, 2, 3]})
        ssm.init()
        commit_hash = ssm.commit("初期コミット", author="高木")
        return ssm, commit_hash

    def test_commit_and_log_roundtrip(self, tmp_path):
        ssm, commit_hash = self._make_repo_with_japanese_commit(tmp_path)

        entries = ssm.log(limit=1)
        assert entries[0]["message"] == "初期コミット"
        assert entries[0]["author"] == "高木"

    def test_commit_file_is_utf8_on_disk(self, tmp_path):
        """コミットJSONが UTF-8 の生バイト列で保存されていること

        `_write_json()` は `ensure_ascii=False` なので、読む側が encoding を
        省略するとロケール依存になる。この前提が変わったら気付けるようにする。
        """
        ssm, commit_hash = self._make_repo_with_japanese_commit(tmp_path)

        commit_file = tmp_path / ".ssm" / "commits" / f"{commit_hash}.json"
        raw = commit_file.read_bytes()
        assert "初期コミット".encode() in raw

    def test_resource_manager_cleanup_handles_japanese_commit(self, tmp_path):
        """日本語コミットがあっても ResourceManager のクリーンアップが動くこと

        修正前は Windows で2つの理由からクリーンアップが黙ってスキップされていた。

        1. コミットJSONを encoding 未指定で読むため `UnicodeDecodeError`
           （`ValueError` のサブクラス）になり、except 節に握りつぶされていた
        2. `unlink()` を `with open(...)` の内側で呼んでいたため、開いたままの
           ファイルを削除できず `WinError 32` になっていた（エンコーディングとは無関係で、
           Windows ではコミットのクリーンアップが全く機能していなかった）
        """
        import json

        resource_manager = pytest.importorskip(
            "SessionSmith.resource_manager", reason="ResourceManager is optional"
        )

        ssm, commit_hash = self._make_repo_with_japanese_commit(tmp_path)
        commit_file = tmp_path / ".ssm" / "commits" / f"{commit_hash}.json"
        assert commit_file.exists()

        # タイムスタンプを十分過去に書き換える。
        # 「作成直後のコミットを commits_days=0 で消す」形にすると、時計の分解能が
        # 粗い環境（Windows）で commit_time == cutoff_time になり `<` が成立しない。
        # 日本語メッセージは残したまま、_write_json() と同じ書き方で保存し直す。
        commit_data = json.loads(commit_file.read_text(encoding="utf-8"))
        commit_data["timestamp"] = "2000-01-01T00:00:00"
        with open(commit_file, "w", encoding="utf-8") as f:
            json.dump(commit_data, f, indent=2, ensure_ascii=False, default=str)
        assert "初期コミット".encode() in commit_file.read_bytes()

        manager = resource_manager.ResourceManager(tmp_path / ".ssm")
        manager.cleanup_old_files(commits_days=1)

        assert not commit_file.exists(), "日本語コミットがクリーンアップされなかった"
