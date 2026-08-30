"""
コンソール出力のヘルパー

Windows の既定コンソールはレガシーなコードページ（`cp1252` / `cp932` など）を使うため、
`✓` や `⚠`、日本語メッセージのような文字をそのまま `print()` すると
`UnicodeEncodeError` で処理全体が落ちてしまう。

出力は本質的な処理ではないので、端末が表現できない文字は `?` に置き換えてでも
処理を継続させる。パッケージ内の `print()` はすべて `safe_print()` に置き換えている。
"""

import sys
from typing import Any, Optional, TextIO


def _to_encodable(text: str, stream: TextIO) -> str:
    """`stream` のエンコーディングで表現できない文字を置換した文字列を返す"""
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        # エンコーディング名が不正な場合などの最終手段
        return text.encode("ascii", errors="replace").decode("ascii")


def safe_print(
    *args: Any,
    sep: str = " ",
    end: str = "\n",
    file: Optional[TextIO] = None,
    flush: bool = False,
) -> None:
    """
    `print()` の代替。端末が表現できない文字があっても例外を送出しない。

    `print()` は引数ごとに `write()` を呼ぶため、途中で `UnicodeEncodeError` が
    発生すると出力が中途半端に残る。ここでは文字列を組み立ててから1回だけ
    `write()` することで、失敗時の二重出力を避けている。
    """
    stream = file if file is not None else sys.stdout
    text = sep.join(str(a) for a in args) + end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        stream.write(_to_encodable(text, stream))
    if flush:
        stream.flush()
