"""
アルゴリズムトレースの可視化機能
"""

import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import warnings
from .visualizer_arrays import visualize_arrays as _visualize_arrays
from .visualizer_generic import visualize_generic as _visualize_generic

# matplotlibはオプショナル依存として扱う
try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as anim_module
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    warnings.warn("matplotlib is not installed. Visualization features will be limited.")


def visualize_algorithm_trace(
    trace_file: Optional[Union[str, Path]] = None,
    trace_data: Optional[List[Dict[str, Any]]] = None,
    output_file: Optional[Union[str, Path]] = None,
    target_variables: Optional[List[str]] = None,
    animation: bool = True,
    interval: int = 500,
    show: bool = True,
    debug: bool = False,
) -> None:
    """
    アルゴリズムトレースを可視化
    
    Args:
        trace_file: トレースデータファイル（JSON形式）
        trace_data: トレースデータ（直接渡す場合）
        output_file: 出力ファイル（GIFまたはHTML）
        target_variables: 可視化する変数名のリスト
        animation: アニメーションを作成するか
        interval: アニメーションの間隔（ミリ秒、最小値は100）
        show: プロットを表示するか
        debug: デバッグ情報を出力するか
        
    Raises:
        ImportError: matplotlibがインストールされていない場合
        ValueError: 引数が無効な場合
        FileNotFoundError: トレースファイルが存在しない場合
        IOError: ファイルの読み込み/保存に失敗した場合
    """
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for visualization. "
            "Install it with: pip install matplotlib"
        )
    
    if interval < 100:
        raise ValueError("interval must be at least 100 milliseconds")
    
    # トレースデータを読み込み
    if trace_data is None:
        if trace_file is None:
            raise ValueError("Either trace_file or trace_data must be provided")
        
        trace_file = Path(trace_file)
        if not trace_file.exists():
            raise FileNotFoundError(f"Trace file '{trace_file}' not found.")
        
        try:
            with open(str(trace_file), 'r', encoding='utf-8') as f:
                trace_data = json.load(f)
        except IOError as e:
            raise IOError(f"Failed to read trace file '{trace_file}': {str(e)}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in trace file '{trace_file}': {str(e)}") from e
    
    if not trace_data:
        if debug:
            print("トレースデータが空です")
        return
    
    if not isinstance(trace_data, list):
        raise ValueError("trace_data must be a list of dictionaries")
    
    # デバッグ: 最初のステップのデータ構造を確認
    if debug and trace_data:
        first_step = trace_data[0]
        print(f"デバッグ: 最初のステップの変数: {list(first_step.get('variables', {}).keys())}")
        if target_variables:
            for var_name in target_variables:
                var_data = first_step.get("variables", {}).get(var_name)
                if var_data is not None:
                    print(f"デバッグ: 変数 '{var_name}' の型: {type(var_data).__name__}, 値: {str(var_data)[:100]}")
                else:
                    print(f"デバッグ: 変数 '{var_name}' が見つかりません")
    
    # 可視化する変数を決定
    if target_variables is None:
        # 最初のステップから全ての変数を取得
        all_vars: set[str] = set()
        for step in trace_data:
            if isinstance(step, dict):
                all_vars.update(step.get("variables", {}).keys())
        target_variables = sorted(list(all_vars))
        if debug:
            print(f"デバッグ: 自動検出された変数: {target_variables}")
    
    # 配列やリストの可視化
    array_vars: List[str] = []
    for var_name in target_variables:
        # 全てのステップで変数の型を確認
        found_array = False
        for step in trace_data:
            if not isinstance(step, dict):
                continue
            var_data = step.get("variables", {}).get(var_name)
            if var_data is not None:
                # 直接リストの場合
                if isinstance(var_data, list) and len(var_data) > 0:
                    array_vars.append(var_name)
                    found_array = True
                    if debug:
                        print(f"デバッグ: 変数 '{var_name}' をリストとして検出（長さ: {len(var_data)}）")
                    break
                # 辞書形式の場合（シリアライズされたデータ）
                elif isinstance(var_data, dict):
                    var_type = var_data.get("type")
                    if var_type == "ndarray":
                        # dataまたはsampleが存在するか確認
                        data = var_data.get("data")
                        sample = var_data.get("sample")
                        if data is not None or sample is not None:
                            array_vars.append(var_name)
                            found_array = True
                            if debug:
                                print(f"デバッグ: 変数 '{var_name}' をndarrayとして検出")
                            break
                    elif var_type in ["list", "tuple"]:
                        # dataまたはsampleが存在するか確認
                        data = var_data.get("data")
                        sample = var_data.get("sample")
                        if data is not None or sample is not None:
                            array_vars.append(var_name)
                            found_array = True
                            if debug:
                                print(f"デバッグ: 変数 '{var_name}' を{var_type}として検出")
                            break
        if not found_array and debug:
            # デバッグ: 変数が見つからない場合、詳細を表示
            for step in trace_data[:3]:  # 最初の3ステップを確認
                if not isinstance(step, dict):
                    continue
                var_data = step.get("variables", {}).get(var_name)
                if var_data is not None:
                    print(f"デバッグ: 変数 '{var_name}' のデータ: 型={type(var_data).__name__}, 値={str(var_data)[:200]}")
                    break
            else:
                print(f"警告: 変数 '{var_name}' はどのステップでも見つかりませんでした")
    
    if array_vars:
        _visualize_arrays(trace_data, array_vars, output_file, animation, interval, show, debug)
    else:
        _visualize_generic(trace_data, target_variables, output_file, show)


def print_trace_summary(
    trace_file: Optional[Union[str, Path]] = None, 
    trace_data: Optional[List[Dict[str, Any]]] = None
) -> None:
    """
    トレースデータのサマリーを表示
    
    Args:
        trace_file: トレースデータファイル（JSON形式）
        trace_data: トレースデータ（直接渡す場合）
        
    Raises:
        ValueError: 引数が無効な場合
        FileNotFoundError: トレースファイルが存在しない場合
        IOError: ファイルの読み込みに失敗した場合
    """
    if trace_data is None:
        if trace_file is None:
            raise ValueError("Either trace_file or trace_data must be provided")
        
        trace_file = Path(trace_file)
        if not trace_file.exists():
            raise FileNotFoundError(f"Trace file '{trace_file}' not found.")
        
        try:
            with open(str(trace_file), 'r', encoding='utf-8') as f:
                trace_data = json.load(f)
        except IOError as e:
            raise IOError(f"Failed to read trace file '{trace_file}': {str(e)}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in trace file '{trace_file}': {str(e)}") from e
    
    if not trace_data:
        print("トレースデータが空です")
        return
    
    if not isinstance(trace_data, list):
        raise ValueError("trace_data must be a list of dictionaries")
    
    # 変数を収集
    all_vars: set[str] = set()
    line_numbers: List[int] = []
    functions: set[str] = set()
    
    for step in trace_data:
        if not isinstance(step, dict):
            continue
        all_vars.update(step.get("variables", {}).keys())
        line_numbers.append(step.get("line_number", 0))
        func_name = step.get("function_name", "")
        if func_name:
            functions.add(func_name)
    
    print("=" * 60)
    print("トレースサマリー")
    print("=" * 60)
    print(f"総ステップ数: {len(trace_data)}")
    print(f"追跡された変数: {len(all_vars)}")
    print(f"  変数リスト: {', '.join(sorted(all_vars))}")
    if line_numbers:
        print(f"行番号範囲: {min(line_numbers)} - {max(line_numbers)}")
    if functions:
        print(f"実行された関数: {', '.join(sorted(functions))}")
    print("=" * 60)
