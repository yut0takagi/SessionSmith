"""コンソール出力のフォールバック（`SessionSmith._console`）のテスト

Windows の既定コンソール（cp1252 / cp932 など）では `✓` や日本語を
そのまま出力すると UnicodeEncodeError になるため、置換して出力を継続する。
"""

import io
import sys

import pytest

from SessionSmith._console import safe_print


def _cp1252_stream() -> io.TextIOWrapper:
    """Windows のレガシーコンソールを模した、cp1252 の厳密なストリーム

    `newline=""` で改行変換を無効にしている。既定のままだと Windows 上では
    `\n` が `\r\n` に変換され、アサーションがプラットフォーム依存になるため。
    """
    return io.TextIOWrapper(
        io.BytesIO(), encoding="cp1252", errors="strict", newline=""
    )


class TestSafePrint:
    def test_ascii_is_written_as_is(self):
        stream = _cp1252_stream()
        safe_print("hello", file=stream)
        stream.flush()
        assert stream.buffer.getvalue() == b"hello\n"

    def test_unencodable_chars_are_replaced_instead_of_raising(self):
        """cp1252 で表現できない文字があっても例外にならない"""
        stream = _cp1252_stream()
        safe_print("✓ コミットしました", file=stream)
        stream.flush()
        written = stream.buffer.getvalue()
        assert written.endswith(b"\n")
        assert b"?" in written

    def test_plain_print_would_raise_on_the_same_stream(self):
        """前提の確認: 素の print() は同じストリームで失敗する"""
        stream = _cp1252_stream()
        with pytest.raises(UnicodeEncodeError):
            print("✓", file=stream)

    def test_no_duplicated_output_on_fallback(self):
        """フォールバック時に本文が二重に出力されない"""
        stream = _cp1252_stream()
        safe_print("A✓B", file=stream)
        stream.flush()
        text = stream.buffer.getvalue().decode("cp1252")
        assert text == "A?B\n"

    def test_sep_and_end_are_honored(self):
        stream = _cp1252_stream()
        safe_print("a", "b", sep="-", end="!", file=stream)
        stream.flush()
        assert stream.buffer.getvalue() == b"a-b!"

    def test_defaults_to_current_stdout(self, capsys):
        """file 未指定時は呼び出し時点の sys.stdout に出力する"""
        safe_print("captured")
        assert capsys.readouterr().out == "captured\n"

    def test_flush_is_forwarded(self):
        flushed = []

        class _Stream(io.StringIO):
            def flush(self):
                flushed.append(True)
                super().flush()

        stream = _Stream()
        safe_print("x", file=stream, flush=True)
        assert flushed


class TestSSMOutputOnLegacyConsole:
    """実際の SSM 操作がレガシーコンソールでも落ちないこと（回帰テスト）"""

    def test_commit_does_not_raise_on_cp1252_stdout(self, tmp_path, monkeypatch):
        """`✓ コミットしました` の出力で UnicodeEncodeError にならないこと"""
        from SessionSmith.ssm import SSM

        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()

        stream = _cp1252_stream()
        monkeypatch.setattr(sys, "stdout", stream)

        commit_hash = ssm.commit("first")

        assert commit_hash
        stream.flush()
        # 出力自体は（置換されつつ）行われている
        assert stream.buffer.getvalue()
