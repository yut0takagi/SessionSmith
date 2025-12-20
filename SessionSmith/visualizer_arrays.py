"""
配列変数の可視化機能（バブルソート、ヒープソートなど）
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import warnings

try:
    import matplotlib.pyplot as plt
    import matplotlib.animation as anim_module
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    warnings.warn("matplotlib is not installed. Visualization features will be limited.")


def visualize_arrays(
    trace_data: List[Dict[str, Any]],
    array_vars: List[str],
    output_file: Optional[Union[str, Path]],
    animation: bool,
    interval: int,
    show: bool,
    debug: bool = False,
) -> None:
    """配列変数の可視化（バブルソート、ヒープソートなど）"""
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for visualization. "
            "Install it with: pip install matplotlib"
        )
    
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

