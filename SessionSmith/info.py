"""
セッション情報表示機能
"""

import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from ._console import safe_print


def _load_session_file(file_path: Union[str, Path], format: Optional[str] = None) -> tuple[dict[str, Any], Optional[str]]:
    """
    セッションファイルを読み込みます（圧縮形式を自動検出）

    Args:
        file_path: セッションファイルのパス

    Returns:
        tuple: (セッションデータ, 圧縮形式)

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Session file '{file_path}' not found.")

    if not file_path.is_file():
        raise ValueError(f"'{file_path}' is not a file.")

    from .formats import detect_format, load_hdf5, load_json, load_msgpack, load_pickle
    from .utils import detect_compression

    session: dict[str, Any] = {}
    # マジックナンバーから圧縮形式を判定する（gzip / bz2 / 非圧縮）
    compression: Optional[str] = detect_compression(file_path)

    try:
        detected_format = detect_format(file_path, format)

        if detected_format == "pickle":
            session = load_pickle(file_path)
        elif detected_format == "json":
            session = load_json(file_path)
        elif detected_format == "msgpack":
            session = load_msgpack(file_path)
        elif detected_format == "hdf5":
            session = load_hdf5(file_path)
        else:
            raise ValueError(f"Unsupported format: {detected_format}")
    except Exception as e:
        raise OSError(f"Failed to load session from {file_path}: {str(e)}") from e

    if not isinstance(session, dict):
        raise ValueError(f"Session file '{file_path}' does not contain a dictionary")

    return session, compression


def get_session_info(file_path: Union[str, Path]) -> dict[str, Any]:
    """
    セッションファイルの詳細情報を取得します

    Args:
        file_path: セッションファイルのパス

    Returns:
        dict: セッション情報（変数名、型、サイズなど）

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    file_path = Path(file_path)
    session, compression = _load_session_file(file_path)

    # メタデータを取得
    metadata = session.pop("__metadata__", None)

    # 変数情報を収集
    variables: list[dict[str, Any]] = []
    total_size = 0

    for var_name, var_value in session.items():
        var_type = type(var_value).__name__
        var_size: Optional[int] = None

        try:
            var_size = len(pickle.dumps(var_value))
            total_size += var_size
        except Exception:
            # シリアライズできない場合はサイズを取得できない
            pass

        variables.append({
            "name": var_name,
            "type": var_type,
            "size": var_size,
        })

    # ファイル情報
    try:
        file_size = os.path.getsize(str(file_path))
        file_mtime = datetime.fromtimestamp(os.path.getmtime(str(file_path)))
    except OSError as e:
        raise OSError(f"Failed to get file information: {str(e)}") from e

    info: dict[str, Any] = {
        "file_path": str(file_path),
        "file_size": file_size,
        "compression": compression,
        "modified_time": file_mtime.isoformat(),
        "variable_count": len(variables),
        "total_data_size": total_size,
        "metadata": metadata,
        "variables": sorted(variables, key=lambda x: x["name"]),
    }

    return info


def list_session_variables(file_path: Union[str, Path]) -> list[str]:
    """
    セッションファイルに含まれる変数名のリストを取得します

    Args:
        file_path: セッションファイルのパス

    Returns:
        list: 変数名のリスト

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    info = get_session_info(file_path)
    return [v["name"] for v in info["variables"]]


def print_session_info(file_path: Union[str, Path]) -> None:
    """
    セッション情報を整形して表示します

    Args:
        file_path: セッションファイルのパス

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    try:
        info = get_session_info(file_path)
    except Exception as e:
        safe_print(f"Error loading session info: {e}")
        raise

    safe_print(f"Session File: {info['file_path']}")
    safe_print(f"File Size: {info['file_size']:,} bytes")
    if info['compression']:
        safe_print(f"Compression: {info['compression']}")
    safe_print(f"Modified: {info['modified_time']}")
    safe_print(f"Variables: {info['variable_count']}")
    safe_print(f"Total Data Size: {info['total_data_size']:,} bytes")

    if info['metadata']:
        safe_print("\nMetadata:")
        for k, v in info['metadata'].items():
            safe_print(f"  {k}: {v}")

    safe_print("\nVariables:")
    for var in info['variables']:
        size_str = f"{var['size']:,} bytes" if var['size'] is not None else "unknown size"
        safe_print(f"  {var['name']:20s} ({var['type']:15s}) - {size_str}")
