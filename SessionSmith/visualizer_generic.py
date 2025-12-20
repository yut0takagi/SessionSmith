"""
一般的な変数の可視化機能
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import warnings

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    warnings.warn("matplotlib is not installed. Visualization features will be limited.")


def visualize_generic(
    trace_data: List[Dict[str, Any]],
    target_variables: List[str],
    output_file: Optional[Union[str, Path]],
    show: bool
) -> None:
    """一般的な変数の可視化"""
    if not MATPLOTLIB_AVAILABLE:
        raise ImportError(
            "matplotlib is required for visualization. "
            "Install it with: pip install matplotlib"
        )
    
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

