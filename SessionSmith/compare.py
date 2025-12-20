"""
セッション比較機能
"""

from typing import Dict, List, Set, Any, Union
from pathlib import Path
import warnings
from .core import load_session
from .info import list_session_variables


def compare_sessions(
    file_path1: Union[str, Path],
    file_path2: Union[str, Path],
    detailed: bool = False
) -> Dict[str, Any]:
    """
    2つのセッションファイルを比較します

    Args:
        file_path1: 最初のセッションファイルのパス
        file_path2: 2番目のセッションファイルのパス
        detailed: 詳細な比較情報を含めるか（値の変更を検出）

    Returns:
        dict: 比較結果（追加、削除、変更された変数のリスト）
        
    Raises:
        FileNotFoundError: いずれかのファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    def _resolve_and_check(path: Union[str, Path]) -> Path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Session file '{p}' not found.")
        return p

    file_path1 = _resolve_and_check(file_path1)
    file_path2 = _resolve_and_check(file_path2)

    def _get_variable_set(path: Path) -> Set[str]:
        try:
            return set(list_session_variables(path))
        except Exception as e:
            raise IOError(f"Failed to read session variables: {str(e)}") from e

    vars1 = _get_variable_set(file_path1)
    vars2 = _get_variable_set(file_path2)

    # 共通変数、追加、削除を計算
    common = vars1 & vars2
    added = vars2 - vars1
    removed = vars1 - vars2

    result: Dict[str, Any] = {
        "file1": str(file_path1),
        "file2": str(file_path2),
        "common_variables": sorted(list(common)),
        "added_variables": sorted(list(added)),
        "removed_variables": sorted(list(removed)),
    }

    # 詳細な比較（値の変更を検出）
    if detailed:
        changed: List[str] = []
        # 一時的な名前空間でロードして比較
        temp_globals1: Dict[str, Any] = {}
        temp_globals2: Dict[str, Any] = {}

        try:
            load_session(file_path1, globals_dict=temp_globals1)
            load_session(file_path2, globals_dict=temp_globals2)
        except Exception as e:
            raise IOError(f"Failed to load sessions for comparison: {str(e)}") from e

        for var_name in common:
            val1 = temp_globals1.get(var_name)
            val2 = temp_globals2.get(var_name)

            # 値が異なるかチェック（簡易的な比較）
            try:
                import pickle
                # 両方の値がNoneの場合は同じとみなす
                if val1 is None and val2 is None:
                    continue
                # 一方がNoneの場合は変更されたとみなす
                if val1 is None or val2 is None:
                    changed.append(var_name)
                    continue
                # pickleで比較
                if pickle.dumps(val1) != pickle.dumps(val2):
                    changed.append(var_name)
            except Exception as e:
                # 比較できない場合は変更されたとみなす
                warnings.warn(
                    f"Could not compare variable '{var_name}': {str(e)}",
                    UserWarning
                )
                changed.append(var_name)

        result["changed_variables"] = changed

    return result


def print_comparison(
    file_path1: Union[str, Path], 
    file_path2: Union[str, Path], 
    detailed: bool = False
) -> None:
    """
    セッション比較結果を整形して表示します

    Args:
        file_path1: 最初のセッションファイルのパス
        file_path2: 2番目のセッションファイルのパス
        detailed: 詳細な比較情報を含めるか
        
    Raises:
        FileNotFoundError: いずれかのファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    try:
        result = compare_sessions(file_path1, file_path2, detailed=detailed)
    except Exception as e:
        print(f"Error comparing sessions: {e}")
        raise

    print(f"Comparison: {result['file1']} vs {result['file2']}\n")

    if result['common_variables']:
        print(f"Common variables ({len(result['common_variables'])}):")
        for var in result['common_variables']:
            print(f"  {var}")
    else:
        print("Common variables: None")

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
