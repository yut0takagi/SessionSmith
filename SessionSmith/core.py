"""
基本的なセッション保存・復元機能
"""

import inspect
import logging
import os
import pickle
import types
import warnings
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Union

from .formats import (
    detect_format,
    load_hdf5,
    load_json,
    load_msgpack,
    load_pickle,
    save_hdf5,
    save_json,
    save_msgpack,
    save_pickle,
)
from .jupyter_utils import get_jupyter_exclude_list, is_jupyter_environment, is_jupyter_internal_var

# ロガー設定
logger = logging.getLogger("SessionSmith.core")
logger.addHandler(logging.NullHandler())


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


def _get_globals_dict(globals_dict: Optional[dict[str, Any]], depth: int = 2, copy: bool = True) -> dict[str, Any]:
    """
    グローバル変数辞書を取得します

    Args:
        globals_dict: グローバル変数辞書（Noneの場合は自動取得）
        depth: 呼び出し元からのフレーム深度（デフォルトは2：_get_globals_dict -> save/load_session -> ユーザーコード）
        copy: Trueの場合はコピーを返す（save_session用）、Falseの場合は参照を返す（load_session用）

    Returns:
        dict: グローバル変数辞書
    """
    if globals_dict is not None:
        if not isinstance(globals_dict, dict):
            raise TypeError(f"globals_dict must be a dict, got {type(globals_dict).__name__}")
        return globals_dict

    try:
        frame = inspect.currentframe()
        if frame is None:
            raise RuntimeError("Cannot access calling frame")

        # 指定された深度までフレームを遡る
        caller_frame = frame
        for _ in range(depth):
            if caller_frame.f_back is None:
                raise RuntimeError("Cannot access calling frame at specified depth")
            caller_frame = caller_frame.f_back

        # save_sessionはコピー（安全な読み取り）、load_sessionは参照（変更を反映）
        result = caller_frame.f_globals.copy() if copy else caller_frame.f_globals
        del frame
        return result
    except Exception as e:
        raise RuntimeError(f"Failed to get globals dict: {e}")


def save_session(
    file_path: Union[str, Path],
    globals_dict: Optional[dict[str, Any]] = None,
    exclude: Optional[list[str]] = None,
    compress: Union[bool, str] = False,
    protocol: Optional[int] = None,
    metadata: bool = False,
    verbose: bool = False,
    on_error: str = "skip",
    serializer: Optional[Callable[[Any], Any]] = None,
    exclude_jupyter: bool = True,
    format: Optional[Literal["pickle", "json", "msgpack", "hdf5"]] = None,
    use_ssm: bool = True,
) -> None:
    """
    現在のセッションの変数を保存します

    この関数は、デフォルトでSSM（`.ssm/`ディレクトリ）に統合されています。
    全てのセッションは`.ssm/`ディレクトリ内に保存され、バージョン管理されます。

    .. note::
        デフォルトでは、`save_session()` は自動的にSSMを初期化し、
        コミットとして`.ssm/`ディレクトリに保存します。
        必要に応じて、指定されたファイルパスにもエクスポートします。

        新規開発では `ssm` モジュールの直接使用を推奨します::

            from SessionSmith import ssm
            ssm.init()
            ssm.commit("message")  # バージョン管理付き

    Args:
        file_path: 保存するファイルパス（SSMに統合後は主にエクスポート用）
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
        use_ssm: SSMに統合して保存するか（デフォルト: True）。Falseの場合は従来通りファイルに直接保存

    Raises:
        TypeError: 引数の型が不正な場合
        ValueError: 引数の値が不正な場合
        IOError: ファイルの保存に失敗した場合
        ImportError: 必要なライブラリがインストールされていない場合
    """
    logger.debug("save_session called")

    # SSMに統合する場合
    if use_ssm:
        try:
            from . import ssm as ssm_module

            # SSMを初期化（既に初期化されている場合はスキップ）
            try:
                ssm_module.init()
            except Exception:
                pass  # 既に初期化されている可能性がある

            # 除外リストをSSMに設定
            if exclude:
                for name in exclude:
                    ssm_module.exclude(name)

            # コミットメッセージを生成
            file_path_obj = Path(file_path)
            commit_message = f"Save session: {file_path_obj.name}"
            if metadata:
                from datetime import datetime
                commit_message += f" ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"

            # SSMにコミット（.ssm/ディレクトリに保存）
            commit_hash = ssm_module.commit(commit_message)

            if verbose:
                print(f"✓ Session saved to SSM (commit: {commit_hash[:7]})")

            # 必要に応じて、指定されたファイルパスにもエクスポート
            if file_path:
                try:
                    ssm_module.export(file_path, commit_hash=commit_hash, format=format, compress=compress)
                    if verbose:
                        file_size = os.path.getsize(str(file_path))
                        print(f"✓ Also exported to {file_path} ({file_size:,} bytes)")
                except Exception as e:
                    if verbose:
                        logger.warning(f"Failed to export to {file_path}: {e}")

            return

        except Exception as e:
            # SSMの初期化に失敗した場合は従来の方法にフォールバック
            if verbose:
                logger.warning(f"Failed to use SSM, falling back to direct file save: {e}")
            use_ssm = False

    # 従来の方法（直接ファイルに保存）
    if not use_ssm:
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
        get_jupyter_exclude_list()
        # セル番号付きの変数も除外リストに追加
        for var_name in list(globals_dict.keys()):
            if is_jupyter_internal_var(var_name):
                if var_name not in exclude:
                    exclude.append(var_name)

    # Pythonの特別な変数やモジュール、関数などは保存しない
    skip_types = (types.ModuleType, types.FunctionType, type)
    session: dict[str, Any] = {}
    errors: list[str] = []

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
                        warnings.warn(error_msg, UserWarning, stacklevel=2)
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
                        warnings.warn(error_msg, UserWarning, stacklevel=2)
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
                warnings.warn(error_msg, UserWarning, stacklevel=2)
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

    except OSError as e:
        raise OSError(f"Failed to save session to {file_path}: {str(e)}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error saving session: {str(e)}") from e

    if verbose and errors:
        print(f"Warnings: {len(errors)} variables could not be saved")


def load_session(
    file_path: Optional[Union[str, Path]] = None,
    globals_dict: Optional[dict[str, Any]] = None,
    include: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
    verbose: bool = False,
    format: Optional[Literal["pickle", "json", "msgpack", "hdf5"]] = None,
    use_ssm: bool = True,
) -> dict[str, Any]:
    """
    セッション変数を現在の名前空間に復元します

    この関数は、デフォルトでSSM（`.ssm/`ディレクトリ）から読み込みます。
    `file_path`が指定されていない場合は、最新のコミットから復元します。

    .. note::
        デフォルトでは、`load_session()` はSSMの最新コミットから読み込みます。
        指定されたファイルパスが存在する場合は、そのファイルから読み込んで
        SSMにインポートします。

        新規開発では `ssm` モジュールの直接使用を推奨します::

            from SessionSmith import ssm
            ssm.init()
            ssm.checkout("abc123")      # バージョン管理付き
            ssm.import_session("file.pkl") # .pkl からインポート

    Args:
        file_path: セッションファイルパス（Noneの場合はSSMの最新コミットから読み込み）
        globals_dict: 復元するグローバル変数辞書（通常はglobals()を渡す）
        include: ロードする変数名のリスト（指定した変数のみロード）
        exclude: ロードから除外する変数名のリスト
        verbose: 詳細なログを出力するか
        format: 読み込み形式（'pickle', 'json', 'msgpack', 'hdf5'）。Noneの場合はファイル拡張子から自動検出
        use_ssm: SSMから読み込むか（デフォルト: True）。Falseの場合は従来通りファイルから直接読み込み

    Returns:
        dict: ロードされた変数の辞書

    Raises:
        FileNotFoundError: ファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
        TypeError: 引数の型が不正な場合
        ImportError: 必要なライブラリがインストールされていない場合
    """
    logger.debug("load_session called")

    # SSMから読み込む場合
    if use_ssm:
        try:
            from . import ssm as ssm_module

            # ファイルパスが指定されている場合
            if file_path:
                file_path_obj = Path(file_path)

                # ファイルが存在する場合はインポートしてから読み込み
                if file_path_obj.exists():
                    if verbose:
                        print(f"Importing {file_path} to SSM...")

                    commit_hash = ssm_module.import_session(
                        str(file_path),
                        message=f"Import from {file_path_obj.name}",
                        format=format
                    )

                    if verbose:
                        print(f"✓ Imported to SSM (commit: {commit_hash[:7]})")

                    # インポートしたコミットから復元
                    ssm_module.checkout(commit_hash)
                else:
                    # ファイルが存在しない場合はSSMの最新コミットから読み込み
                    if verbose:
                        print("File not found, loading from SSM latest commit...")
                    ssm_module.checkout()
            else:
                # ファイルパスが指定されていない場合は最新コミットから読み込み
                if verbose:
                    print("Loading from SSM latest commit...")
                ssm_module.checkout()

            # グローバル変数辞書を取得
            globals_dict = _get_globals_dict(globals_dict, copy=False)

            # SSMから読み込まれた変数を返す
            loaded_vars = {}
            for name, value in globals_dict.items():
                # 除外リストをチェック
                if exclude and name in exclude:
                    continue
                if include and name not in include:
                    continue
                # 特殊変数をスキップ
                if name.startswith("__") and name.endswith("__"):
                    continue
                if name.startswith("_"):
                    continue
                loaded_vars[name] = value

            if verbose:
                print(f"✓ Loaded {len(loaded_vars)} variables from SSM")

            return loaded_vars

        except Exception as e:
            # SSMからの読み込みに失敗した場合は従来の方法にフォールバック
            if verbose:
                logger.warning(f"Failed to load from SSM, falling back to direct file load: {e}")
            if file_path is None:
                raise FileNotFoundError("No file path specified and SSM is not available")
            use_ssm = False

    # 従来の方法（直接ファイルから読み込み）
    if not use_ssm:
        # バリデーション
        if file_path is None:
            raise ValueError("file_path is required when use_ssm=False")

        file_path = _validate_file_path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Session file '{file_path}' not found.")

        if not file_path.is_file():
            raise ValueError(f"'{file_path}' is not a file.")

        # load_sessionでは元のグローバル変数を変更する必要があるため、copy=False
        globals_dict = _get_globals_dict(globals_dict, copy=False)

    if include is not None and not isinstance(include, list):
        raise TypeError(f"include must be a list, got {type(include).__name__}")

        if exclude is not None and not isinstance(exclude, list):
            raise TypeError(f"exclude must be a list, got {type(exclude).__name__}")

        # 形式の検出
        detected_format = detect_format(file_path, format)

        # ファイルを読み込む（形式に応じて）
        session: dict[str, Any] = {}

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
            raise OSError(f"Failed to load session from {file_path}: {str(e)}") from e

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
        loaded_vars: list[str] = []
        for k, v in session.items():
            try:
                globals_dict[k] = v
                loaded_vars.append(k)
                if verbose:
                    print(f"Loaded variable: {k} ({type(v).__name__})")
            except Exception as e:
                if verbose:
                    warnings.warn(f"Failed to load variable '{k}': {str(e)}", UserWarning, stacklevel=2)

        if verbose:
            print(f"Loaded {len(loaded_vars)} variables")

        return session
