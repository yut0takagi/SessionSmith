"""
ユーティリティ関数（検証、圧縮など）
"""

import pickle
import gzip
import bz2
import os
from typing import Optional, Tuple, Union, Dict, Any
from pathlib import Path


def verify_session(file_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    セッションファイルの整合性を検証します

    Args:
        file_path: セッションファイルのパス

    Returns:
        tuple: (is_valid, error_message)
        is_validがTrueの場合、error_messageはNone
        is_validがFalseの場合、error_messageにエラーの説明が含まれる
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        return False, f"File not found: {file_path}"
    
    if not file_path.is_file():
        return False, f"'{file_path}' is not a file."

    try:
        # 圧縮形式を自動検出して読み込む
        session: Dict[str, Any] = {}
        
        try:
            with gzip.open(str(file_path), 'rb') as f:
                session = pickle.load(f)
        except (OSError, gzip.BadGzipFile, EOFError):
            try:
                with bz2.open(str(file_path), 'rb') as f:
                    session = pickle.load(f)
            except (OSError, EOFError):
                try:
                    with open(str(file_path), 'rb') as f:
                        session = pickle.load(f)
                except EOFError:
                    return False, "File appears to be corrupted or empty"

        # 基本的な構造チェック
        if not isinstance(session, dict):
            return False, "Session is not a dictionary"

        # メタデータのチェック（存在する場合）
        if "__metadata__" in session:
            metadata = session["__metadata__"]
            if not isinstance(metadata, dict):
                return False, "Metadata is not a dictionary"

        return True, None

    except pickle.UnpicklingError as e:
        return False, f"Pickle error: {str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def get_file_size(file_path: Union[str, Path]) -> int:
    """
    ファイルサイズを取得します

    Args:
        file_path: ファイルパス

    Returns:
        int: ファイルサイズ（バイト）
        
    Raises:
        FileNotFoundError: ファイルが存在しない場合
        OSError: ファイル情報の取得に失敗した場合
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        return os.path.getsize(str(file_path))
    except OSError as e:
        raise OSError(f"Failed to get file size: {str(e)}") from e


def detect_compression(file_path: Union[str, Path]) -> Optional[str]:
    """
    ファイルの圧縮形式を検出します

    Args:
        file_path: ファイルパス

    Returns:
        str or None: 'gzip', 'bz2', または None
        
    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        with open(str(file_path), 'rb') as f:
            header = f.read(3)
    except IOError as e:
        raise IOError(f"Failed to read file: {str(e)}") from e

    if len(header) < 2:
        return None
    
    if header[:2] == b'\x1f\x8b':
        return 'gzip'
    elif len(header) >= 3 and header[:3] == b'BZh':
        return 'bz2'
    else:
        return None
