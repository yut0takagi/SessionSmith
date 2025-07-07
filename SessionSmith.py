import dill
import os

__version__ = "0.1.0"


def save_session(filename: str = "session.dill") -> None:
    """
    現在のセッション（グローバル変数）を dill で保存します。

    Parameters:
        filename (str): 保存するファイル名（拡張子 .dill 推奨）

    Returns:
        None
    """
    with open(filename, 'wb') as f:
        dill.dump_session(f)


def load_session(filename: str = "session.dill") -> None:
    """
    保存されたセッション（グローバル変数）を復元します。

    Parameters:
        filename (str): 読み込むファイル名

    Returns:
        None
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Session file '{filename}' not found.")

    with open(filename, 'rb') as f:
        dill.load_session(f)


__all__ = ["save_session", "load_session"]