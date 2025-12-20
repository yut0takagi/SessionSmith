"""
セッション比較機能
"""

from typing import Dict, List, Set, Any
from .core import load_session
from .info import list_session_variables


def compare_sessions(
    file_path1: str,
    file_path2: str,
    detailed: bool = False
) -> Dict[str, Any]:
    """
    2つのセッションファイルを比較します

    Args:
        file_path1 (str): 最初のセッションファイルのパス
        file_path2 (str): 2番目のセッションファイルのパス
        detailed (bool): 詳細な比較情報を含めるか

    Returns:
        dict: 比較結果（追加、削除、変更された変数のリスト）
    """
    # 変数名のリストを取得
    vars1 = set(list_session_variables(file_path1))
    vars2 = set(list_session_variables(file_path2))

    # 共通変数、追加、削除を計算
    common = vars1 & vars2
    added = vars2 - vars1
    removed = vars1 - vars2

    result = {
        "file1": file_path1,
        "file2": file_path2,
        "common_variables": sorted(list(common)),
        "added_variables": sorted(list(added)),
        "removed_variables": sorted(list(removed)),
    }

    # 詳細な比較（値の変更を検出）
    if detailed:
        changed = []
        # 一時的な名前空間でロードして比較
        temp_globals1 = {}
        temp_globals2 = {}

        load_session(file_path1, globals_dict=temp_globals1)
        load_session(file_path2, globals_dict=temp_globals2)

        for var_name in common:
            val1 = temp_globals1.get(var_name)
            val2 = temp_globals2.get(var_name)

            # 値が異なるかチェック（簡易的な比較）
            try:
                import pickle
                if pickle.dumps(val1) != pickle.dumps(val2):
                    changed.append(var_name)
            except Exception:
                # 比較できない場合は変更されたとみなす
                changed.append(var_name)

        result["changed_variables"] = changed

    return result


def print_comparison(file_path1: str, file_path2: str, detailed: bool = False) -> None:
    """
    セッション比較結果を整形して表示します

    Args:
        file_path1 (str): 最初のセッションファイルのパス
        file_path2 (str): 2番目のセッションファイルのパス
        detailed (bool): 詳細な比較情報を含めるか
    """
    result = compare_sessions(file_path1, file_path2, detailed=detailed)

    print(f"Comparison: {result['file1']} vs {result['file2']}\n")

    print(f"Common variables ({len(result['common_variables'])}):")
    for var in result['common_variables']:
        print(f"  {var}")

    if result['added_variables']:
        print(f"\nAdded variables ({len(result['added_variables'])}):")
        for var in result['added_variables']:
            print(f"  + {var}")

    if result['removed_variables']:
        print(f"\nRemoved variables ({len(result['removed_variables'])}):")
        for var in result['removed_variables']:
            print(f"  - {var}")

    if detailed and result.get('changed_variables'):
        print(f"\nChanged variables ({len(result['changed_variables'])}):")
        for var in result['changed_variables']:
            print(f"  ~ {var}")

