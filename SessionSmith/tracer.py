"""
アルゴリズム実行トレーサー
各行の実行時に変数の状態を記録し、可視化用データを生成
"""

import sys
import types
import inspect
import json
import pickle
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime
from pathlib import Path
import warnings


class AlgorithmTracer:
    """
    アルゴリズムの実行を1行ずつトレースし、変数の状態を記録するクラス
    
    使用例:
        tracer = AlgorithmTracer(target_variables=["arr", "i", "j"])
        tracer.start()
        # アルゴリズムを実行
        heap_sort(arr)
        tracer.stop()
        tracer.save("trace.json")
        
    または、コンテキストマネージャーとして:
        with AlgorithmTracer(target_variables=["arr"]) as tracer:
            bubble_sort(arr)
        tracer.save("trace.json")
    """
    
    def __init__(
        self,
        target_variables: Optional[List[str]] = None,
        track_all: bool = True,
        max_depth: int = 10,
        exclude_types: Optional[List[type]] = None,
        max_array_size: int = 1000,
        max_string_length: int = 200,
    ):
        """
        Args:
            target_variables: 追跡する変数名のリスト（Noneの場合は全て）
            track_all: 全ての変数を追跡するか
            max_depth: 再帰的なデータ構造の最大深度
            exclude_types: 追跡から除外する型のリスト
            max_array_size: 配列の最大要素数（超える場合はサンプルを取得）
            max_string_length: 文字列の最大長
            
        Raises:
            ValueError: パラメータが無効な場合
        """
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        if max_array_size < 0:
            raise ValueError("max_array_size must be non-negative")
        if max_string_length < 0:
            raise ValueError("max_string_length must be non-negative")
        
        self.target_variables = target_variables
        self.track_all = track_all
        self.max_depth = max_depth
        self.exclude_types = exclude_types or [type, types.ModuleType, types.FunctionType]
        self.max_array_size = max_array_size
        self.max_string_length = max_string_length
        
        self.trace_data: List[Dict[str, Any]] = []
        self.current_frame: Optional[Any] = None
        self.line_number = 0
        self.original_trace: Optional[Callable] = None
        self._is_tracing = False
        
    def _serialize_value(self, value: Any, depth: int = 0) -> Any:
        """
        値をシリアライズ可能な形式に変換
        
        Args:
            value: シリアライズする値
            depth: 現在の深度
            
        Returns:
            シリアライズ可能な形式の値
        """
        if depth > self.max_depth:
            return "<max depth reached>"
        
        # 除外する型をチェック
        if isinstance(value, tuple(self.exclude_types)):
            return f"<{type(value).__name__}>"
        
        # 基本的な型はそのまま
        if isinstance(value, (int, float, str, bool, type(None))):
            if isinstance(value, str) and len(value) > self.max_string_length:
                return value[:self.max_string_length] + "..."
            return value
        
        # リスト・タプル
        if isinstance(value, (list, tuple)):
            if len(value) > self.max_array_size:
                return {
                    "type": type(value).__name__,
                    "length": len(value),
                    "sample": [self._serialize_value(item, depth + 1) 
                              for item in value[:100]]
                }
            try:
                return [self._serialize_value(item, depth + 1) for item in value]
            except RecursionError:
                return f"<{type(value).__name__}: recursion error>"
        
        # 辞書
        if isinstance(value, dict):
            if len(value) > self.max_array_size:
                items = list(value.items())[:100]
                return {
                    "type": "dict",
                    "length": len(value),
                    "sample": {str(k): self._serialize_value(v, depth + 1) 
                              for k, v in items}
                }
            try:
                return {str(k): self._serialize_value(v, depth + 1) 
                       for k, v in value.items()}
            except RecursionError:
                return f"<dict: recursion error>"
        
        # NumPy配列
        try:
            import numpy as np
            if isinstance(value, np.ndarray):
                if value.size > self.max_array_size:
                    return {
                        "type": "ndarray",
                        "shape": list(value.shape),
                        "dtype": str(value.dtype),
                        "size": int(value.size),
                        "sample": value.flatten()[:100].tolist()
                    }
                try:
                    return {
                        "type": "ndarray",
                        "shape": list(value.shape),
                        "dtype": str(value.dtype),
                        "data": value.tolist()
                    }
                except Exception as e:
                    return f"<ndarray: conversion error: {str(e)}>"
        except ImportError:
            pass
        
        # その他のオブジェクトは文字列表現
        try:
            str_repr = str(value)
            if len(str_repr) > self.max_string_length:
                return f"{type(value).__name__}: {str_repr[:self.max_string_length]}..."
            return f"{type(value).__name__}: {str_repr}"
        except Exception:
            return f"<{type(value).__name__}>"
    
    def _capture_state(self, frame: Any) -> Dict[str, Any]:
        """
        現在のフレームの変数状態をキャプチャ
        
        Args:
            frame: 現在のフレームオブジェクト
            
        Returns:
            変数状態の辞書
        """
        try:
            state: Dict[str, Any] = {
                "line_number": frame.f_lineno,
                "filename": frame.f_code.co_filename,
                "function_name": frame.f_code.co_name,
                "variables": {}
            }
        except AttributeError:
            # フレームが無効な場合
            return {
                "line_number": 0,
                "filename": "<unknown>",
                "function_name": "<unknown>",
                "variables": {}
            }
        
        # ローカル変数とグローバル変数を取得
        try:
            local_vars = frame.f_locals.copy()
            global_vars = frame.f_globals.copy()
        except Exception:
            return state
        
        # 追跡対象の変数を決定
        vars_to_track: Dict[str, Any] = {}
        if self.track_all:
            vars_to_track.update(local_vars)
            # グローバル変数から内部変数を除外
            for k, v in global_vars.items():
                if not k.startswith("__"):
                    vars_to_track[k] = v
        else:
            for var_name in (self.target_variables or []):
                if var_name in local_vars:
                    vars_to_track[var_name] = local_vars[var_name]
                elif var_name in global_vars:
                    vars_to_track[var_name] = global_vars[var_name]
        
        # 変数をシリアライズ
        for var_name, var_value in vars_to_track.items():
            try:
                state["variables"][var_name] = self._serialize_value(var_value)
            except Exception as e:
                state["variables"][var_name] = f"<error: {str(e)}>"
        
        return state
    
    def _trace_callback(self, frame: Any, event: str, arg: Any) -> Optional[Callable]:
        """
        sys.settraceのコールバック関数
        
        Args:
            frame: 現在のフレーム
            event: イベントタイプ（'line', 'call', 'return'など）
            arg: イベント引数
            
        Returns:
            次のトレース関数（自分自身を返す）またはNone
        """
        if not self._is_tracing:
            return None
            
        if event == 'line':
            # 各行の実行時に状態を記録
            try:
                state = self._capture_state(frame)
                state["timestamp"] = datetime.now().isoformat()
                self.trace_data.append(state)
                self.line_number = frame.f_lineno
            except Exception:
                # エラーが発生してもトレーシングを継続
                pass
        
        return self._trace_callback
    
    def start(self) -> None:
        """トレーシングを開始"""
        if self._is_tracing:
            warnings.warn("Tracing is already running", UserWarning)
            return
        
        self.trace_data = []
        self.original_trace = sys.gettrace()
        self._is_tracing = True
        sys.settrace(self._trace_callback)
    
    def stop(self) -> None:
        """トレーシングを停止"""
        if not self._is_tracing:
            return
        
        self._is_tracing = False
        try:
            sys.settrace(self.original_trace)
        except Exception:
            pass
        finally:
            self.original_trace = None
    
    def __enter__(self) -> 'AlgorithmTracer':
        """コンテキストマネージャーとして使用"""
        self.start()
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[Exception], exc_tb: Optional[Any]) -> bool:
        """コンテキストマネージャーとして使用"""
        self.stop()
        return False  # 例外を伝播
    
    def save(self, file_path: Union[str, Path], format: str = "json") -> None:
        """
        トレースデータを保存
        
        Args:
            file_path: 保存先ファイルパス
            format: 保存形式（'json' または 'pickle'）
            
        Raises:
            ValueError: 無効な形式が指定された場合
            IOError: ファイルの保存に失敗した場合
        """
        file_path = Path(file_path)
        
        if format == "json":
            try:
                with open(str(file_path), 'w', encoding='utf-8') as f:
                    json.dump(self.trace_data, f, indent=2, ensure_ascii=False)
            except IOError as e:
                raise IOError(f"Failed to save trace data to {file_path}: {str(e)}") from e
        elif format == "pickle":
            try:
                with open(str(file_path), 'wb') as f:
                    pickle.dump(self.trace_data, f)
            except IOError as e:
                raise IOError(f"Failed to save trace data to {file_path}: {str(e)}") from e
        else:
            raise ValueError(f"Unknown format: {format}. Use 'json' or 'pickle'")
    
    def load(self, file_path: Union[str, Path], format: str = "json") -> None:
        """
        トレースデータを読み込み
        
        Args:
            file_path: ファイルパス
            format: ファイル形式（'json' または 'pickle'）
            
        Raises:
            FileNotFoundError: ファイルが存在しない場合
            ValueError: 無効な形式が指定された場合
            IOError: ファイルの読み込みに失敗した場合
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Trace file '{file_path}' not found.")
        
        if format == "json":
            try:
                with open(str(file_path), 'r', encoding='utf-8') as f:
                    self.trace_data = json.load(f)
            except IOError as e:
                raise IOError(f"Failed to load trace data from {file_path}: {str(e)}") from e
        elif format == "pickle":
            try:
                with open(str(file_path), 'rb') as f:
                    self.trace_data = pickle.load(f)
            except IOError as e:
                raise IOError(f"Failed to load trace data from {file_path}: {str(e)}") from e
        else:
            raise ValueError(f"Unknown format: {format}. Use 'json' or 'pickle'")
    
    def get_trace_data(self) -> List[Dict[str, Any]]:
        """
        トレースデータを取得
        
        Returns:
            トレースデータのリスト（コピーを返す）
        """
        return self.trace_data.copy()
    
    def clear(self) -> None:
        """トレースデータをクリア"""
        self.trace_data = []
    
    def get_summary(self) -> Dict[str, Any]:
        """
        トレースデータのサマリーを取得
        
        Returns:
            サマリー情報の辞書
        """
        if not self.trace_data:
            return {
                "total_steps": 0,
                "variables_tracked": [],
                "line_range": None,
                "functions_called": []
            }
        
        # 追跡された変数を取得
        all_vars: set[str] = set()
        line_numbers: List[int] = []
        functions: set[str] = set()
        
        for step in self.trace_data:
            all_vars.update(step.get("variables", {}).keys())
            line_numbers.append(step.get("line_number", 0))
            func_name = step.get("function_name", "")
            if func_name:
                functions.add(func_name)
        
        return {
            "total_steps": len(self.trace_data),
            "variables_tracked": sorted(list(all_vars)),
            "line_range": (min(line_numbers), max(line_numbers)) if line_numbers else None,
            "functions_called": sorted(list(functions))
        }
