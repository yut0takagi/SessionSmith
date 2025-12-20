"""
SessionSmith - セッション保存・復元ライブラリ

堅牢で寛容なセッション管理ライブラリです。
Jupyter Notebook環境での使用に最適化されています。
"""

from .core import save_session, load_session
from .manager import SessionManager
from .info import get_session_info, list_session_variables, print_session_info
from .compare import compare_sessions, print_comparison
from .utils import verify_session
from .serializers import CustomSerializer
from .tracer import AlgorithmTracer
from .visualizer import visualize_algorithm_trace, print_trace_summary

__version__ = "0.1.3"

__all__ = [
    "save_session",
    "load_session",
    "SessionManager",
    "get_session_info",
    "list_session_variables",
    "print_session_info",
    "compare_sessions",
    "print_comparison",
    "verify_session",
    "CustomSerializer",
    "AlgorithmTracer",
    "visualize_algorithm_trace",
    "print_trace_summary",
]
