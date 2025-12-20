"""
Jupyter Notebook関連のユーティリティ関数
"""

import re
from typing import List


def is_jupyter_environment() -> bool:
    """
    Jupyter Notebook/IPython環境で実行されているかどうかを判定します
    
    Returns:
        bool: Jupyter環境の場合はTrue
    """
    try:
        get_ipython()  # type: ignore
        return True
    except NameError:
        return False


def get_jupyter_exclude_list() -> List[str]:
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


def is_jupyter_internal_var(var_name: str) -> bool:
    """
    変数名がJupyter Notebookの内部変数かどうかを判定します
    
    Args:
        var_name: 変数名
        
    Returns:
        bool: 内部変数の場合はTrue
    """
    if not isinstance(var_name, str):
        return False
    
    # 基本的な内部変数
    jupyter_vars = get_jupyter_exclude_list()
    if var_name in jupyter_vars:
        return True
    
    # セル番号付きの入力履歴（_i1, _i2, _i3, ...）
    if re.match(r'^_i\d+$', var_name):
        return True
    
    return False

