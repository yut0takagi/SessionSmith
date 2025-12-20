"""
基本的なセッション保存・復元機能
"""

import pickle
import types
import inspect
import gzip
import bz2
from typing import Optional, List, Dict, Any, Union, Callable, Literal
import warnings
import os
from pathlib import Path
from .jupyter_utils import (
    is_jupyter_environment,
    get_jupyter_exclude_list,
    is_jupyter_internal_var
)
from .formats import (
    detect_format,
    save_pickle,
    load_pickle,
    save_json,
    load_json,
    save_msgpack,
    load_msgpack,
    save_hdf5,
    load_hdf5,
)


def _validate_file_path(file_path: Union[str, Path]) -> Path:
    """
    ファイルパスを検証し、Pathオブジェクトに変換します
    
    Args:
        file_path: ファイルパス
        
    Returns:
        Path: 検証済みのPathオブジェクト
        
    Raises:
        TypeError: ファイルパスが文字列またはPathオブジェクトでない場合
        ValueError: ファイルパスが空の場合
    """
    if not isinstance(file_path, (str, Path)):
        raise TypeError(f"file_path must be str or Path, got {type(file_path).__name__}")
    
    if not str(file_path).strip():
        raise ValueError("file_path cannot be empty")
    
    return Path(file_path)


def _validate_compress_option(compress: Union[bool, str]) -> Optional[str]:
    """
    圧縮オプションを検証します
    
    Args:
        compress: 圧縮形式
        
    Returns:
        str or None: 圧縮形式（'gzip', 'bz2', または None）
        
    Raises:
        ValueError: 無効な圧縮形式が指定された場合
    """
    if not compress:
        return None
    
    if compress is True or compress == "gzip":
        return "gzip"
    elif compress == "bz2":
        return "bz2"
    else:
        raise ValueError(
            f"Invalid compression type: {compress}. "
            f"Expected True, 'gzip', 'bz2', or False/None"
        )


def _validate_on_error_option(on_error: str) -> str:
    """
    エラー処理オプションを検証します
    
    Args:
        on_error: エラー処理オプション
        
    Returns:
        str: 検証済みのエラー処理オプション
        
    Raises:
        ValueError: 無効なオプションが指定された場合
    """
    valid_options = {"skip", "warn", "raise"}
    if on_error not in valid_options:
        raise ValueError(
            f"Invalid on_error option: {on_error}. "
            f"Expected one of {valid_options}"
        )
    return on_error


def _get_globals_dict(globals_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    グローバル変数辞書を取得します
    
    Args:
        globals_dict: グローバル変数辞書（Noneの場合は自動取得）
        
    Returns:
        dict: グローバル変数辞書
    """
    if globals_dict is not None:
        if not isinstance(globals_dict, dict):
            raise TypeError(f"globals_dict must be a dict, got {type(globals_dict).__name__}")
        return globals_dict
    
    try:
        frame = inspect.currentframe()
        if frame is None or frame.f_back is None:
            raise RuntimeError("Cannot access calling frame")
        caller_frame = frame.f_back
        result = caller_frame.f_globals.copy()
        del frame
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to get globals dict: {e}")


def save_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    exclude: Optional[List[str]] = None,
    compress: Union[bool, str] = False,
    protocol: Optional[int] = None,
    metadata: bool = False,
    verbose: bool = False,
    on_error: str = "skip",
    serializer: Optional[Callable[[Any], Any]] = None,
    exclude_jupyter: bool = True,
    format: Optional[Literal["pickle", "json", "msgpack", "hdf5"]] = None,
) -> None:
    """
    現在のセッションの変数を保存します

    Args:
        file_path: 保存するファイルパス
        globals_dict: 保存対象のグローバル変数辞書（通常はglobals()を渡す）
        exclude: 除外したい変数名のリスト
        compress: 圧縮形式。Trueの場合はgzip、'gzip'または'bz2'を指定可能
        protocol: pickleプロトコルバージョン（pickle形式のみ、デフォルトは最新）
        metadata: メタデータ（保存日時、バージョンなど）を保存するか
        verbose: 詳細なログを出力するか
        on_error: エラー時の動作。'skip'（スキップ）、'warn'（警告）、'raise'（例外）
        serializer: カスタムシリアライザー関数
        exclude_jupyter: Jupyter Notebookの内部変数を自動的に除外するか（デフォルト: True）
        format: 保存形式（'pickle', 'json', 'msgpack', 'hdf5'）。Noneの場合はファイル拡張子から自動検出

    Raises:
        TypeError: 引数の型が不正な場合
        ValueError: 引数の値が不正な場合
        IOError: ファイルの保存に失敗した場合
        ImportError: 必要なライブラリがインストールされていない場合
    """
    # バリデーション
    file_path = _validate_file_path(file_path)
    compress_type = _validate_compress_option(compress)
    on_error = _validate_on_error_option(on_error)
    globals_dict = _get_globals_dict(globals_dict)
    
    # 形式の検出
    detected_format = detect_format(file_path, format)
    
    if exclude is None:
        exclude = []
    elif not isinstance(exclude, list):
        raise TypeError(f"exclude must be a list, got {type(exclude).__name__}")
    
    if protocol is not None and not isinstance(protocol, int):
        raise TypeError(f"protocol must be an int, got {type(protocol).__name__}")
    
    if serializer is not None and not callable(serializer):
        raise TypeError("serializer must be callable")

    # Jupyter Notebookの内部変数を自動的に除外
    if exclude_jupyter and is_jupyter_environment():
        jupyter_exclude = get_jupyter_exclude_list()
        # セル番号付きの変数も除外リストに追加
        for var_name in list(globals_dict.keys()):
            if is_jupyter_internal_var(var_name):
                if var_name not in exclude:
                    exclude.append(var_name)

    # Pythonの特別な変数やモジュール、関数などは保存しない
    skip_types = (types.ModuleType, types.FunctionType, type)
    session: Dict[str, Any] = {}
    errors: List[str] = []

    for k, v in globals_dict.items():
        # 特別な変数をスキップ
        if k.startswith("__") and k.endswith("__"):
            continue
        if k in exclude:
            continue
        if isinstance(v, skip_types):
            continue

        try:
            # カスタムシリアライザーが指定されている場合は使用
            if serializer:
                try:
                    v = serializer(v)
                except Exception as e:
                    error_msg = f"Serializer failed for variable '{k}': {str(e)}"
                    errors.append(error_msg)
                    if on_error == "warn":
                        warnings.warn(error_msg, UserWarning)
                    elif on_error == "raise":
                        raise
                    continue

            # 形式に応じて検証
            if detected_format == "pickle":
                # Pickleで保存できるかどうか一度試す
                try:
                    pickle.dumps(v, protocol=protocol)
                    session[k] = v
                    if verbose:
                        print(f"Saved variable: {k} ({type(v).__name__})")
                except (pickle.PicklingError, TypeError) as e:
                    error_msg = f"Failed to pickle variable '{k}': {str(e)}"
                    errors.append(error_msg)
                    if on_error == "warn":
                        warnings.warn(error_msg, UserWarning)
                    elif on_error == "raise":
                        raise pickle.PicklingError(error_msg) from e
            else:
                # JSON/MessagePack/HDF5形式の場合はそのまま追加（変換は保存時に実行）
                session[k] = v
                if verbose:
                    print(f"Saved variable: {k} ({type(v).__name__})")

        except Exception as e:
            error_msg = f"Unexpected error saving variable '{k}': {str(e)}"
            errors.append(error_msg)
            if on_error == "warn":
                warnings.warn(error_msg, UserWarning)
            elif on_error == "raise":
                raise

    # メタデータの追加
    if metadata:
        from datetime import datetime
        from . import __version__
        session["__metadata__"] = {
            "version": __version__,
            "saved_at": datetime.now().isoformat(),
            "variable_count": len(session),
        }

    # ファイルに保存
    try:
        # ディレクトリが存在しない場合は作成
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 形式に応じて保存
        if detected_format == "pickle":
            save_pickle(session, file_path, compress_type, protocol)
        elif detected_format == "json":
            save_json(session, file_path, compress_type)
        elif detected_format == "msgpack":
            save_msgpack(session, file_path, compress_type)
        elif detected_format == "hdf5":
            save_hdf5(session, file_path, compress_type)
        else:
            raise ValueError(f"Unsupported format: {detected_format}")

        if verbose:
            file_size = os.path.getsize(str(file_path))
            print(f"Session saved to {file_path} ({file_size:,} bytes, format: {detected_format})")

    except (IOError, OSError) as e:
        raise IOError(f"Failed to save session to {file_path}: {str(e)}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error saving session: {str(e)}") from e

    if verbose and errors:
        print(f"Warnings: {len(errors)} variables could not be saved")


def load_session(
    file_path: Union[str, Path],
    globals_dict: Optional[Dict[str, Any]] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    verbose: bool = False,
    format: Optional[Literal["pickle", "json", "msgpack", "hdf5"]] = None,
) -> Dict[str, Any]:
    """
    セッション変数を現在の名前空間に復元します

    Args:
        file_path: セッションファイルパス
        globals_dict: 復元するグローバル変数辞書（通常はglobals()を渡す）
        include: ロードする変数名のリスト（指定した変数のみロード）
        exclude: ロードから除外する変数名のリスト
        verbose: 詳細なログを出力するか
        format: 読み込み形式（'pickle', 'json', 'msgpack', 'hdf5'）。Noneの場合はファイル拡張子から自動検出

    Returns:
        dict: ロードされた変数の辞書

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
        TypeError: 引数の型が不正な場合
        ImportError: 必要なライブラリがインストールされていない場合
    """
    # バリデーション
    file_path = _validate_file_path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Session file '{file_path}' not found.")
    
    if not file_path.is_file():
        raise ValueError(f"'{file_path}' is not a file.")
    
    globals_dict = _get_globals_dict(globals_dict)
    
    if include is not None and not isinstance(include, list):
        raise TypeError(f"include must be a list, got {type(include).__name__}")
    
    if exclude is not None and not isinstance(exclude, list):
        raise TypeError(f"exclude must be a list, got {type(exclude).__name__}")

    # 形式の検出
    detected_format = detect_format(file_path, format)
    
    # ファイルを読み込む（形式に応じて）
    session: Dict[str, Any] = {}
    compression_detected: Optional[str] = None
    
    try:
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
        raise IOError(f"Failed to load session from {file_path}: {str(e)}") from e

    # セッションが辞書でない場合
    if not isinstance(session, dict):
        raise ValueError(f"Session file '{file_path}' does not contain a dictionary")

    # メタデータを除外
    metadata = session.pop("__metadata__", None)
    if metadata and verbose:
        print(f"Session metadata: {metadata}")
        print(f"Format: {detected_format}")

    # フィルタリング
    if include:
        session = {k: v for k, v in session.items() if k in include}
    if exclude:
        session = {k: v for k, v in session.items() if k not in exclude}

    # グローバル変数に更新
    loaded_vars: List[str] = []
    for k, v in session.items():
        try:
            globals_dict[k] = v
            loaded_vars.append(k)
            if verbose:
                print(f"Loaded variable: {k} ({type(v).__name__})")
        except Exception as e:
            if verbose:
                warnings.warn(f"Failed to load variable '{k}': {str(e)}", UserWarning)

    if verbose:
        print(f"Loaded {len(loaded_vars)} variables")

    return session
