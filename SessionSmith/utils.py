"""
ユーティリティ関数（検証、圧縮など）
"""

import pickle
import gzip
import bz2
import os
from typing import Optional, Tuple


def verify_session(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    セッションファイルの整合性を検証します

    Args:
        file_path (str): セッションファイルのパス

    Returns:
        tuple: (is_valid, error_message)
    """
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    try:
        # 圧縮形式を自動検出して読み込む
        try:
            with gzip.open(file_path, 'rb') as f:
                session = pickle.load(f)
        except (OSError, gzip.BadGzipFile):
            try:
                with bz2.open(file_path, 'rb') as f:
                    session = pickle.load(f)
            except OSError:
                with open(file_path, 'rb') as f:
                    session = pickle.load(f)

        # 基本的な構造チェック
        if not isinstance(session, dict):
            return False, "Session is not a dictionary"

        return True, None

    except pickle.UnpicklingError as e:
        return False, f"Pickle error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def get_file_size(file_path: str) -> int:
    """
    ファイルサイズを取得します

    Args:
        file_path (str): ファイルパス

    Returns:
        int: ファイルサイズ（バイト）
    """
    return os.path.getsize(file_path)


def detect_compression(file_path: str) -> Optional[str]:
    """
    ファイルの圧縮形式を検出します

    Args:
        file_path (str): ファイルパス

    Returns:
        str or None: 'gzip', 'bz2', または None
    """
    with open(file_path, 'rb') as f:
        header = f.read(3)

    if header[:2] == b'\x1f\x8b':
        return 'gzip'
    elif header[:3] == b'BZh':
        return 'bz2'
    else:
        return None

