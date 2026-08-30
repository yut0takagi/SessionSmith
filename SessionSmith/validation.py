"""
入力バリデーション（参照名ルール・パストラバーサル対策）

ブランチ名・タグ名・リモート名など、ユーザー指定の文字列がそのまま
`.ssm/` 配下のファイルパス構築に使われる箇所で共通して使用する検証ヘルパー。

ここで定義する参照名ルールは VS Code 拡張側 (extension/src/ssmRefs.ts の
``isValidRefName`` / ``NAME_RE``) と一致させています。どちらか一方だけを
変更すると Python 側と拡張側でブランチ/タグ名の受理・拒否が食い違うため、
ルールを変更する場合は両方を同時に更新してください。
"""

import os
import re
from pathlib import Path
from typing import Union

from .exceptions import ValidationError

# 許可する文字: ASCII の英数字・アンダースコア・ハイフン・ドットのみ。
# 拡張側の NAME_RE = /^[A-Za-z0-9_.-]+$/ と同一。
_REF_NAME_CHARS_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

#: 参照名（ブランチ/タグ/リモート名）の最大長
MAX_REF_NAME_LENGTH = 255

# Windows の予約デバイス名。ディレクトリ配下でもデバイスとして解決されるため、
# `branches/NUL` のようなパスへの書き込みはヌルデバイスに吸われてしまう。
# 参照は1名前1ファイルで保持しているので、名前として使わせない。
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _has_control_chars(text: str) -> bool:
    """C0 制御文字（NUL含む）または DEL を含むか"""
    return any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text)


def validate_ref_name(name: str, kind: str = "name") -> str:
    """
    ブランチ名・タグ名・リモート名を検証します。

    許可: ASCII の英数字・``_``・``-``・``.`` のみで構成された、
    1〜255文字の名前（例: ``main``, ``v1.0.0``, ``feature-1``, ``exp_2``）。

    拒否:
        - 空文字列 / 文字列以外
        - 255文字を超える名前
        - NUL を含む制御文字
        - パスセパレータ（``/`` または ``\\``）
        - ``.`` や ``..``、またはドットのみで構成される名前
        - 上記の許可文字セット以外を含む名前
        - ``-`` から始まる名前（CLI オプションと誤認されるのを防ぐ）
        - ``.`` で終わる名前（Windows が末尾のドットを削除して衝突するため）
        - Windows の予約デバイス名（``CON``, ``PRN``, ``AUX``, ``NUL``,
          ``COM1``〜``COM9``, ``LPT1``〜``LPT9``。拡張子付きも同様）

    Args:
        name: 検証する名前
        kind: エラーメッセージ・``ValidationError.field`` に使う種別
              （例: "branch_name", "tag_name", "remote_name"）

    Returns:
        str: 検証済みの名前（そのまま返す）

    Raises:
        ValidationError: 名前が無効な場合
    """
    if not isinstance(name, str) or not name:
        raise ValidationError(kind, "Name must be a non-empty string", name)

    if len(name) > MAX_REF_NAME_LENGTH:
        raise ValidationError(
            kind, f"Name must be {MAX_REF_NAME_LENGTH} characters or less", name
        )

    if _has_control_chars(name):
        raise ValidationError(kind, "Name must not contain control characters", name)

    if "/" in name or "\\" in name:
        raise ValidationError(kind, "Name must not contain path separators", name)

    if set(name) == {"."}:
        raise ValidationError(kind, "Name must not be '.' or '..'", name)

    if not _REF_NAME_CHARS_RE.match(name):
        raise ValidationError(
            kind,
            "Name may only contain ASCII letters, digits, '_', '-', and '.'",
            name,
        )

    if name.startswith("-"):
        raise ValidationError(kind, "Name must not start with '-'", name)

    # Windows はファイル名末尾のドットを削除するため、'v2.' と 'v2' が衝突する
    if name.endswith("."):
        raise ValidationError(kind, "Name must not end with '.'", name)

    # 予約デバイス名は拡張子付き（NUL.txt など）でも予約扱いになる
    if name.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        raise ValidationError(
            kind,
            f"Name must not be a Windows reserved device name: {name.split('.')[0]}",
            name,
        )

    return name


def ensure_within(base_dir: Union[str, Path], target_path: Union[str, Path]) -> Path:
    """
    ``target_path`` が ``base_dir`` の配下に収まっていることを確認します（多層防御）。

    ``validate_ref_name()`` を通過した名前から組み立てたパスであっても、
    シンボリックリンクや将来のコード変更で見落とされたケースにより意図した
    ディレクトリの外を読み書きしてしまうことを防ぐための最終防衛ラインです。

    Args:
        base_dir: 許可される親ディレクトリ（例: ``.ssm/branches``）
        target_path: 検証対象のパス

    Returns:
        Path: 検証済みの ``target_path``

    Raises:
        ValidationError: ``target_path`` が ``base_dir`` の配下でない場合
    """
    base_real = os.path.realpath(os.fspath(base_dir))
    target_real = os.path.realpath(os.fspath(target_path))

    if target_real != base_real and not target_real.startswith(base_real + os.sep):
        raise ValidationError(
            "path",
            f"Path escapes the allowed directory: {target_path}",
            str(target_path),
        )

    return Path(target_path)


def validate_path_arg(path: Union[str, "os.PathLike[str]"], field: str = "path") -> Path:
    """
    エクスポート/インポート先などユーザーが選ぶ任意の保存先パスを検証します。

    保存先自体はユーザーが自由に選べるため、パストラバーサル（``..`` の使用など）
    は許可しますが、明らかに不正な入力は拒否します。

    拒否:
        - 空文字列 / None
        - NUL を含む制御文字

    Args:
        path: 検証するパス
        field: エラーメッセージ・``ValidationError.field`` に使うフィールド名

    Returns:
        Path: 検証済みのパス

    Raises:
        ValidationError: パスが空、または制御文字を含む場合
    """
    if path is None:
        raise ValidationError(field, "Path must not be empty", path)

    try:
        path_str = os.fspath(path)
    except TypeError:
        raise ValidationError(
            field, f"Path must be str or PathLike, got {type(path).__name__}", path
        ) from None

    if not path_str or not path_str.strip():
        raise ValidationError(field, "Path must not be empty", path)

    if _has_control_chars(path_str):
        raise ValidationError(field, "Path must not contain control characters", path)

    return Path(path_str)
