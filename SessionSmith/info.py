"""
セッション情報表示機能
"""

import pickle
import gzip
import bz2
import os
from typing import Dict, Any, List, Optional
from datetime import datetime


def get_session_info(file_path: str) -> Dict[str, Any]:
    """
    セッションファイルの詳細情報を取得します

    Args:
        file_path (str): セッションファイルのパス

    Returns:
        dict: セッション情報（変数名、型、サイズなど）
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Session file '{file_path}' not found.")

    # ファイルを読み込む
    try:
        try:
            with gzip.open(file_path, 'rb') as f:
                session = pickle.load(f)
            compression = "gzip"
        except (OSError, gzip.BadGzipFile):
            try:
                with bz2.open(file_path, 'rb') as f:
                    session = pickle.load(f)
                compression = "bz2"
            except OSError:
                with open(file_path, 'rb') as f:
                    session = pickle.load(f)
                compression = None
    except Exception as e:
        raise IOError(f"Failed to load session: {str(e)}")

    # メタデータを取得
    metadata = session.pop("__metadata__", None)

    # 変数情報を収集
    variables = []
    total_size = 0

    for var_name, var_value in session.items():
        var_type = type(var_value).__name__
        try:
            var_size = len(pickle.dumps(var_value))
            total_size += var_size
        except Exception:
            var_size = None

        variables.append({
            "name": var_name,
            "type": var_type,
            "size": var_size,
        })

    # ファイル情報
    file_size = os.path.getsize(file_path)
    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

    info = {
        "file_path": file_path,
        "file_size": file_size,
        "compression": compression,
        "modified_time": file_mtime.isoformat(),
        "variable_count": len(variables),
        "total_data_size": total_size,
        "metadata": metadata,
        "variables": sorted(variables, key=lambda x: x["name"]),
    }

    return info


def list_session_variables(file_path: str) -> List[str]:
    """
    セッションファイルに含まれる変数名のリストを取得します

    Args:
        file_path (str): セッションファイルのパス

    Returns:
        list: 変数名のリスト
    """
    info = get_session_info(file_path)
    return [v["name"] for v in info["variables"]]


def print_session_info(file_path: str) -> None:
    """
    セッション情報を整形して表示します

    Args:
        file_path (str): セッションファイルのパス
    """
    info = get_session_info(file_path)

    print(f"Session File: {info['file_path']}")
    print(f"File Size: {info['file_size']:,} bytes")
    if info['compression']:
        print(f"Compression: {info['compression']}")
    print(f"Modified: {info['modified_time']}")
    print(f"Variables: {info['variable_count']}")
    print(f"Total Data Size: {info['total_data_size']:,} bytes")

    if info['metadata']:
        print(f"\nMetadata:")
        for k, v in info['metadata'].items():
            print(f"  {k}: {v}")

    print(f"\nVariables:")
    for var in info['variables']:
        size_str = f"{var['size']:,} bytes" if var['size'] else "unknown size"
        print(f"  {var['name']:20s} ({var['type']:15s}) - {size_str}")

