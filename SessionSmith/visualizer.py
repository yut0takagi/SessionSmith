"""
アルゴリズムトレースの可視化機能
"""

import json
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import warnings

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


def _visualize_arrays(
    trace_data: List[Dict[str, Any]],
    array_vars: List[str],
    output_file: Optional[Union[str, Path]],
    animation: bool,
    interval: int,
    show: bool,
    debug: bool = False,
) -> None:
    """配列変数の可視化（バブルソート、ヒープソートなど）"""
    try:
        fig, axes = plt.subplots(len(array_vars), 1, figsize=(12, 4 * len(array_vars)))
        if len(array_vars) == 1:
            axes = [axes]
    except Exception as e:
        raise RuntimeError(f"Failed to create figure: {str(e)}") from e
    
    def get_array_value(step: Dict[str, Any], var_name: str) -> Optional[List[Union[int, float]]]:
        """ステップから配列の値を取得"""
        if not isinstance(step, dict):
            return None
        
        var_data = step.get("variables", {}).get(var_name)
        if var_data is None:
            return None
        
        # 直接リストの場合（tracer.pyでmax_array_size以下のリストは直接返される）
        if isinstance(var_data, list):
            # 空でないリストを返す（要素が数値かどうかは問わない）
            if len(var_data) > 0:
                # リストの要素が数値の場合
                if all(isinstance(x, (int, float)) for x in var_data):
                    return var_data
                # ネストされたリストや混合型の場合も、数値のみを抽出して返す
                try:
                    # 数値に変換可能な要素のみを抽出
                    numeric_data: List[Union[int, float]] = []
                    for x in var_data:
                        if isinstance(x, (int, float)):
                            numeric_data.append(x)
                        elif isinstance(x, list) and len(x) > 0:
                            # ネストされたリストの場合、最初の要素を使用
                            if isinstance(x[0], (int, float)):
                                numeric_data.append(x[0])
                    if len(numeric_data) > 0:
                        return numeric_data
                    # 数値が見つからない場合でも、リストとして返す（可視化を試みる）
                    return var_data
                except Exception:
                    # エラーが発生した場合でも、リストとして返す
                    return var_data
            return None
        
        # 辞書形式の場合（シリアライズされたデータ）
        if isinstance(var_data, dict):
            # ndarray型
            if var_data.get("type") == "ndarray":
                data = var_data.get("data")
                if data is not None and isinstance(data, list) and len(data) > 0:
                    return data
                sample = var_data.get("sample")
                if sample is not None and isinstance(sample, list) and len(sample) > 0:
                    return sample
            # list/tuple型（max_array_sizeを超えた場合）
            elif var_data.get("type") in ["list", "tuple"]:
                data = var_data.get("data")
                if data is not None and isinstance(data, list) and len(data) > 0:
                    return data
                sample = var_data.get("sample")
                if sample is not None and isinstance(sample, list) and len(sample) > 0:
                    return sample
        
        return None
    
    def animate(frame: int) -> None:
        """アニメーションフレーム"""
        if frame >= len(trace_data):
            return
        
        step = trace_data[frame]
        if not isinstance(step, dict):
            return
        
        line_num = step.get("line_number", 0)
        
        for idx, var_name in enumerate(array_vars):
            ax = axes[idx]
            ax.clear()
            
            # 現在のステップから配列を取得
            arr = get_array_value(step, var_name)
            
            # 現在のステップにデータがない場合、前のステップから取得を試みる
            if arr is None and frame > 0:
                for prev_frame in range(frame - 1, -1, -1):
                    prev_arr = get_array_value(trace_data[prev_frame], var_name)
                    if prev_arr is not None and len(prev_arr) > 0:
                        arr = prev_arr
                        break
            
            if arr is not None and len(arr) > 0:
                # バーグラフで表示
                try:
                    bars = ax.bar(range(len(arr)), arr, color='skyblue', edgecolor='black')
                    ax.set_title(f"{var_name} (Line {line_num})", fontsize=12)
                    ax.set_xlabel("Index", fontsize=10)
                    ax.set_ylabel("Value", fontsize=10)
                    max_val = max(arr) if arr else 1
                    ax.set_ylim(0, max_val * 1.1)
                    ax.grid(True, alpha=0.3)
                except Exception as e:
                    # エラーが発生した場合
                    error_msg = f"{var_name}: Error\n{str(e)}"
                    if debug:
                        error_msg += f"\nArray length: {len(arr) if arr else 0}"
                    ax.text(0.5, 0.5, error_msg, 
                           ha='center', va='center', transform=ax.transAxes,
                           fontsize=10)
                    ax.set_title(f"{var_name} (Line {line_num})", fontsize=12)
            else:
                # デバッグ情報を表示
                var_data = step.get("variables", {}).get(var_name)
                debug_msg = f"{var_name}: No data"
                if debug and var_data is not None:
                    debug_msg += f"\nType: {type(var_data).__name__}"
                    if isinstance(var_data, list):
                        debug_msg += f"\nLength: {len(var_data)}"
                        debug_msg += f"\nFirst 5: {var_data[:5] if len(var_data) > 0 else 'empty'}"
                    elif isinstance(var_data, dict):
                        debug_msg += f"\nKeys: {list(var_data.keys())}"
                        if 'data' in var_data:
                            debug_msg += f"\nData type: {type(var_data['data']).__name__}"
                        if 'sample' in var_data:
                            debug_msg += f"\nSample type: {type(var_data['sample']).__name__}"
                elif debug:
                    debug_msg += f"\nVariable not found in step"
                
                ax.text(0.5, 0.5, debug_msg, 
                       ha='center', va='center', transform=ax.transAxes,
                       fontsize=9)
                ax.set_title(f"{var_name} (Line {line_num})", fontsize=12)
        
        plt.tight_layout()
    
    if animation:
        try:
            anim = anim_module.FuncAnimation(
                fig, animate, frames=len(trace_data), 
                interval=interval, repeat=True, blit=False
            )
            if output_file:
                output_file = Path(output_file)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                
                if output_file.suffix == '.gif':
                    try:
                        anim.save(str(output_file), writer='pillow', fps=1000/interval)
                        print(f"Animation saved to {output_file}")
                    except Exception as e:
                        print(f"Failed to save GIF: {e}")
                        print("Trying to save as HTML instead...")
                        try:
                            html = anim.to_jshtml()
                            html_file = output_file.with_suffix('.html')
                            with open(str(html_file), 'w') as f:
                                f.write(html)
                            print(f"Animation saved to {html_file}")
                        except Exception as e2:
                            raise IOError(f"Failed to save animation: {str(e2)}") from e2
                elif output_file.suffix == '.html':
                    try:
                        html = anim.to_jshtml()
                        with open(str(output_file), 'w') as f:
                            f.write(html)
                        print(f"Animation saved to {output_file}")
                    except Exception as e:
                        raise IOError(f"Failed to save HTML: {str(e)}") from e
                else:
                    warnings.warn(f"Unknown file extension: {output_file.suffix}. Saving as HTML.")
                    html_file = output_file.with_suffix('.html')
                    html = anim.to_jshtml()
                    with open(str(html_file), 'w') as f:
                        f.write(html)
                    print(f"Animation saved to {html_file}")
            if show:
                plt.show()
        except Exception as e:
            plt.close(fig)
            raise RuntimeError(f"Failed to create animation: {str(e)}") from e
    else:
        # 最後のステップのみ表示
        try:
            animate(len(trace_data) - 1)
            if output_file:
                output_file = Path(output_file)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                plt.savefig(str(output_file), dpi=150, bbox_inches='tight')
                print(f"Plot saved to {output_file}")
            if show:
                plt.show()
        except Exception as e:
            plt.close(fig)
            raise RuntimeError(f"Failed to create plot: {str(e)}") from e


def _visualize_generic(
    trace_data: List[Dict[str, Any]],
    target_variables: List[str],
    output_file: Optional[Union[str, Path]],
    show: bool
) -> None:
    """一般的な変数の可視化"""
    try:
        fig, axes = plt.subplots(len(target_variables), 1, figsize=(12, 4 * len(target_variables)))
        if len(target_variables) == 1:
            axes = [axes]
    except Exception as e:
        raise RuntimeError(f"Failed to create figure: {str(e)}") from e
    
    for idx, var_name in enumerate(target_variables):
        ax = axes[idx]
        values: List[Union[int, float]] = []
        line_numbers: List[int] = []
        
        for step in trace_data:
            if not isinstance(step, dict):
                continue
            if var_name in step.get("variables", {}):
                value = step["variables"][var_name]
                # 数値の場合のみプロット
                if isinstance(value, (int, float)):
                    values.append(value)
                    line_numbers.append(step.get("line_number", 0))
        
        if values:
            ax.plot(line_numbers, values, marker='o', linewidth=2, markersize=4)
            ax.set_title(f"{var_name} over time", fontsize=12)
            ax.set_xlabel("Line Number", fontsize=10)
            ax.set_ylabel("Value", fontsize=10)
            ax.grid(True, alpha=0.3)
        else:
            ax.text(0.5, 0.5, f"{var_name}: No numeric data", 
                   ha='center', va='center', transform=ax.transAxes,
                   fontsize=12)
            ax.set_title(f"{var_name}", fontsize=12)
    
    plt.tight_layout()
    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            plt.savefig(str(output_file), dpi=150, bbox_inches='tight')
            print(f"Plot saved to {output_file}")
        except Exception as e:
            plt.close(fig)
            raise IOError(f"Failed to save plot: {str(e)}") from e
    if show:
        plt.show()
    else:
        plt.close(fig)


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
