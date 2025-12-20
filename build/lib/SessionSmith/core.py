"""
基本的なセッション保存・復元機能
"""

import pickle
import types
import inspect
import gzip
import bz2
from typing import Optional, List, Dict, Any, Union
import warnings
import os
import re


def _is_jupyter_environment() -> bool:
    """
    Jupyter Notebook/IPython環境で実行されているかどうかを判定します
    
    Returns:
        bool: Jupyter環境の場合はTrue
    """
    try:
        get_ipython()
        return True
    except NameError:
        return False


def _get_jupyter_exclude_list() -> List[str]:
    """
    Jupyter Notebookの内部変数のリストを取得します
    
    Returns:
        list: 除外すべき変数名のリスト
    """
    return [
        # IPython/Jupyterの内部変数
        '_ih', '_oh', '_dh',  # 入力履歴、出力履歴、ディレクトリ履歴
        'In', 'Out',  # 入力と出力のリスト/辞書
        '_', '__', '___',  # 最後の3つの出力
        '_i', '_ii', '_iii',  # 現在、前、前々の入力
        # セル番号付きの入力履歴（_i1, _i2, ...）は正規表現で除外
    ]


def _is_jupyter_internal_var(var_name: str) -> bool:
    """
    変数名がJupyter Notebookの内部変数かどうかを判定します
    
    Args:
        var_name (str): 変数名
        
    Returns:
        bool: 内部変数の場合はTrue
    """
    # 基本的な内部変数
    jupyter_vars = _get_jupyter_exclude_list()
    if var_name in jupyter_vars:
        return True
    
    # セル番号付きの入力履歴（_i1, _i2, _i3, ...）
    if re.match(r'^_i\d+$', var_name):
        return True
    
    return False


def save_session(
    file_path: str,
    globals_dict: Optional[Dict[str, Any]] = None,
    exclude: Optional[List[str]] = None,
    compress: Union[bool, str] = False,
    protocol: Optional[int] = None,
    metadata: bool = False,
    verbose: bool = False,
    on_error: str = "skip",
    serializer: Optional[callable] = None,
    exclude_jupyter: bool = True,
) -> None:
    """
    現在のセッションの変数を全てpickleで保存します

    Args:
        file_path (str): 保存するファイルパス
        globals_dict (dict, optional): 保存対象のグローバル変数辞書（通常はglobals()を渡す）
        exclude (list, optional): 除外したい変数名のリスト
        compress (bool or str): 圧縮形式。Trueの場合はgzip、'gzip'または'bz2'を指定可能
        protocol (int, optional): pickleプロトコルバージョン（デフォルトは最新）
        metadata (bool): メタデータ（保存日時、バージョンなど）を保存するか
        verbose (bool): 詳細なログを出力するか
        on_error (str): エラー時の動作。'skip'（スキップ）、'warn'（警告）、'raise'（例外）
        serializer (callable, optional): カスタムシリアライザー関数
        exclude_jupyter (bool): Jupyter Notebookの内部変数を自動的に除外するか（デフォルト: True）
    """
    if globals_dict is None:
        frame = inspect.currentframe().f_back
        globals_dict = frame.f_globals
        del frame

    if exclude is None:
        exclude = []

    # Jupyter Notebookの内部変数を自動的に除外
    if exclude_jupyter and _is_jupyter_environment():
        jupyter_exclude = _get_jupyter_exclude_list()
        # セル番号付きの変数も除外リストに追加
        for var_name in globals_dict.keys():
            if _is_jupyter_internal_var(var_name):
                if var_name not in exclude:
                    exclude.append(var_name)

    # 圧縮形式の決定
    compress_type = None
    if compress:
        if compress is True or compress == "gzip":
            compress_type = "gzip"
        elif compress == "bz2":
            compress_type = "bz2"
        else:
            raise ValueError(f"Unknown compression type: {compress}")

    # Pythonの特別な変数やモジュール、関数などは保存しない
    skip_types = (types.ModuleType, types.FunctionType, type)
    session = {}
    errors = []

    for k, v in globals_dict.items():
        if k.startswith("__") and k.endswith("__"):
            continue
        if k in exclude:
            continue
        if isinstance(v, skip_types):
            continue

        try:
            # カスタムシリアライザーが指定されている場合は使用
            if serializer:
                v = serializer(v)

            # Pickleで保存できるかどうか一度試す
            pickle.dumps(v, protocol=protocol)
            session[k] = v

            if verbose:
                print(f"Saved variable: {k} ({type(v).__name__})")

        except Exception as e:
            error_msg = f"Failed to save variable '{k}': {str(e)}"
            errors.append(error_msg)

            if on_error == "warn":
                warnings.warn(error_msg)
            elif on_error == "raise":
                raise
            # on_error == "skip" の場合は何もしない

    # メタデータの追加
    if metadata:
        from datetime import datetime
        session["__metadata__"] = {
            "version": "0.1.1",
            "saved_at": datetime.now().isoformat(),
            "variable_count": len(session),
        }

    # ファイルに保存
    try:
        if compress_type == "gzip":
            with gzip.open(file_path, 'wb') as f:
                pickle.dump(session, f, protocol=protocol)
        elif compress_type == "bz2":
            with bz2.open(file_path, 'wb') as f:
                pickle.dump(session, f, protocol=protocol)
        else:
            with open(file_path, 'wb') as f:
                pickle.dump(session, f, protocol=protocol)

        if verbose:
            file_size = os.path.getsize(file_path)
            print(f"Session saved to {file_path} ({file_size} bytes)")

    except Exception as e:
        raise IOError(f"Failed to save session to {file_path}: {str(e)}")

    if verbose and errors:
        print(f"Warnings: {len(errors)} variables could not be saved")


def load_session(
    file_path: str,
    globals_dict: Optional[Dict[str, Any]] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    pickleで保存したセッション変数を現在の名前空間に復元します

    Args:
        file_path (str): pickleファイルパス
        globals_dict (dict, optional): 復元するグローバル変数辞書（通常はglobals()を渡す）
        include (list, optional): ロードする変数名のリスト（指定した変数のみロード）
        exclude (list, optional): ロードから除外する変数名のリスト
        verbose (bool): 詳細なログを出力するか

    Returns:
        dict: ロードされた変数の辞書
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Session file '{file_path}' not found.")

    if globals_dict is None:
        frame = inspect.currentframe().f_back
        globals_dict = frame.f_globals
        del frame

    # ファイルを読み込む（圧縮形式を自動検出）
    try:
        # gzipで試す
        try:
            with gzip.open(file_path, 'rb') as f:
                session = pickle.load(f)
        except (OSError, gzip.BadGzipFile):
            # bz2で試す
            try:
                with bz2.open(file_path, 'rb') as f:
                    session = pickle.load(f)
            except OSError:
                # 通常のpickleファイルとして読み込む
                with open(file_path, 'rb') as f:
                    session = pickle.load(f)
    except Exception as e:
        raise IOError(f"Failed to load session from {file_path}: {str(e)}")

    # メタデータを除外
    metadata = session.pop("__metadata__", None)
    if metadata and verbose:
        print(f"Session metadata: {metadata}")

    # フィルタリング
    if include:
        session = {k: v for k, v in session.items() if k in include}
    if exclude:
        session = {k: v for k, v in session.items() if k not in exclude}

    # グローバル変数に更新
    loaded_vars = []
    for k, v in session.items():
        globals_dict[k] = v
        loaded_vars.append(k)
        if verbose:
            print(f"Loaded variable: {k} ({type(v).__name__})")

    if verbose:
        print(f"Loaded {len(loaded_vars)} variables")

    return session

