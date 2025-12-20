"""
複数形式のサポート（pickle、JSON、MessagePack、HDF5）
"""

import json
from typing import Optional, Dict, Any, Union, Literal
from pathlib import Path
import warnings

# オプショナル依存のインポート
try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False

try:
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    HDF5_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

# サポートされている形式
SUPPORTED_FORMATS = ["pickle", "json", "msgpack", "hdf5"]

# 形式と拡張子のマッピング
FORMAT_EXTENSIONS = {
    "pickle": [".pkl", ".pickle"],
    "json": [".json"],
    "msgpack": [".msgpack", ".mp"],
    "hdf5": [".h5", ".hdf5"],
}


def detect_format(file_path: Union[str, Path], format: Optional[str] = None) -> str:
    """
    ファイルパスから形式を自動検出
    
    Args:
        file_path: ファイルパス
        format: 明示的に指定された形式（優先）
        
    Returns:
        str: 検出された形式
        
    Raises:
        ValueError: 形式が不明な場合
    """
    if format:
        if format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format: {format}. "
                f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )
        return format
    
    file_path = Path(file_path)
    suffix = file_path.suffix.lower()
    
    for fmt, extensions in FORMAT_EXTENSIONS.items():
        if suffix in extensions:
            return fmt
    
    # デフォルトはpickle
    return "pickle"


def convert_to_serializable(obj: Any) -> Any:
    """
    NumPy/PandasオブジェクトをJSON/MessagePackでシリアライズ可能な形式に変換
    
    Args:
        obj: 変換するオブジェクト
        
    Returns:
        シリアライズ可能なオブジェクト
    """
    if NUMPY_AVAILABLE and isinstance(obj, np.ndarray):
        return {
            "__type__": "ndarray",
            "data": obj.tolist(),
            "dtype": str(obj.dtype),
            "shape": obj.shape,
        }
    
    if NUMPY_AVAILABLE and isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    
    if NUMPY_AVAILABLE and isinstance(obj, np.bool_):
        return bool(obj)
    
    if PANDAS_AVAILABLE and isinstance(obj, pd.DataFrame):
        return {
            "__type__": "DataFrame",
            "data": obj.to_dict(orient="records"),
            "index": obj.index.tolist(),
            "columns": obj.columns.tolist(),
        }
    
    if PANDAS_AVAILABLE and isinstance(obj, pd.Series):
        return {
            "__type__": "Series",
            "data": obj.to_dict(),
            "index": obj.index.tolist(),
            "name": obj.name,
        }
    
    if isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    
    if isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    
    if isinstance(obj, set):
        return {"__type__": "set", "data": [convert_to_serializable(item) for item in obj]}
    
    # その他の型はそのまま返す（JSONでシリアライズ可能な型のみ）
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
    # シリアライズできない型は警告を出してスキップ
    warnings.warn(
        f"Object of type {type(obj).__name__} cannot be serialized to JSON/MessagePack. "
        f"Use pickle format or register a custom serializer.",
        UserWarning
    )
    return None


def convert_from_serializable(obj: Any) -> Any:
    """
    シリアライズされた形式からNumPy/Pandasオブジェクトに復元
    
    Args:
        obj: 復元するオブジェクト
        
    Returns:
        復元されたオブジェクト
    """
    if isinstance(obj, dict):
        if "__type__" in obj:
            obj_type = obj["__type__"]
            
            if obj_type == "ndarray" and NUMPY_AVAILABLE:
                return np.array(obj["data"], dtype=obj.get("dtype", None))
            
            if obj_type == "DataFrame" and PANDAS_AVAILABLE:
                df = pd.DataFrame(obj["data"], columns=obj.get("columns"))
                if "index" in obj:
                    df.index = obj["index"]
                return df
            
            if obj_type == "Series" and PANDAS_AVAILABLE:
                series = pd.Series(obj["data"], name=obj.get("name"))
                if "index" in obj:
                    series.index = obj["index"]
                return series
            
            if obj_type == "set":
                return set(obj["data"])
        
        # 再帰的に処理
        return {k: convert_from_serializable(v) for k, v in obj.items()}
    
    if isinstance(obj, list):
        return [convert_from_serializable(item) for item in obj]
    
    return obj


def save_pickle(session: Dict[str, Any], file_path: Path, compress: Optional[str] = None, protocol: Optional[int] = None) -> None:
    """pickle形式で保存"""
    import pickle
    import gzip
    import bz2
    
    data = pickle.dumps(session, protocol=protocol)
    
    if compress == "gzip":
        with gzip.open(str(file_path), 'wb') as f:
            f.write(data)
    elif compress == "bz2":
        with bz2.open(str(file_path), 'wb') as f:
            f.write(data)
    else:
        with open(str(file_path), 'wb') as f:
            f.write(data)


def load_pickle(file_path: Path) -> Dict[str, Any]:
    """pickle形式で読み込み"""
    import pickle
    import gzip
    import bz2
    
    # 圧縮形式を自動検出
    try:
        with gzip.open(str(file_path), 'rb') as f:
            return pickle.load(f)
    except (OSError, gzip.BadGzipFile, EOFError):
        try:
            with bz2.open(str(file_path), 'rb') as f:
                return pickle.load(f)
        except (OSError, EOFError):
            with open(str(file_path), 'rb') as f:
                return pickle.load(f)


def save_json(session: Dict[str, Any], file_path: Path, compress: Optional[str] = None) -> None:
    """JSON形式で保存"""
    import gzip
    import bz2
    
    # NumPy/Pandasオブジェクトを変換
    serializable_session = convert_to_serializable(session)
    
    json_str = json.dumps(serializable_session, indent=2, ensure_ascii=False)
    data = json_str.encode('utf-8')
    
    if compress == "gzip":
        with gzip.open(str(file_path), 'wb') as f:
            f.write(data)
    elif compress == "bz2":
        with bz2.open(str(file_path), 'wb') as f:
            f.write(data)
    else:
        with open(str(file_path), 'w', encoding='utf-8') as f:
            f.write(json_str)


def load_json(file_path: Path) -> Dict[str, Any]:
    """JSON形式で読み込み"""
    import gzip
    import bz2
    
    # 圧縮形式を自動検出
    try:
        with gzip.open(str(file_path), 'rb') as f:
            data = json.loads(f.read().decode('utf-8'))
    except (OSError, gzip.BadGzipFile, EOFError):
        try:
            with bz2.open(str(file_path), 'rb') as f:
                data = json.loads(f.read().decode('utf-8'))
        except (OSError, EOFError):
            with open(str(file_path), 'r', encoding='utf-8') as f:
                data = json.load(f)
    
    # NumPy/Pandasオブジェクトに復元
    return convert_from_serializable(data)


def save_msgpack(session: Dict[str, Any], file_path: Path, compress: Optional[str] = None) -> None:
    """MessagePack形式で保存"""
    if not MSGPACK_AVAILABLE:
        raise ImportError(
            "msgpack is required for MessagePack format. "
            "Install it with: pip install msgpack"
        )
    
    import gzip
    import bz2
    
    # NumPy/Pandasオブジェクトを変換
    serializable_session = convert_to_serializable(session)
    
    data = msgpack.packb(serializable_session, use_bin_type=True)
    
    if compress == "gzip":
        with gzip.open(str(file_path), 'wb') as f:
            f.write(data)
    elif compress == "bz2":
        with bz2.open(str(file_path), 'wb') as f:
            f.write(data)
    else:
        with open(str(file_path), 'wb') as f:
            f.write(data)


def load_msgpack(file_path: Path) -> Dict[str, Any]:
    """MessagePack形式で読み込み"""
    if not MSGPACK_AVAILABLE:
        raise ImportError(
            "msgpack is required for MessagePack format. "
            "Install it with: pip install msgpack"
        )
    
    import gzip
    import bz2
    
    # 圧縮形式を自動検出
    try:
        with gzip.open(str(file_path), 'rb') as f:
            data = msgpack.unpackb(f.read(), raw=False)
    except (OSError, gzip.BadGzipFile, EOFError):
        try:
            with bz2.open(str(file_path), 'rb') as f:
                data = msgpack.unpackb(f.read(), raw=False)
        except (OSError, EOFError):
            with open(str(file_path), 'rb') as f:
                data = msgpack.unpackb(f.read(), raw=False)
    
    # NumPy/Pandasオブジェクトに復元
    return convert_from_serializable(data)


def save_hdf5(session: Dict[str, Any], file_path: Path, compress: Optional[str] = None) -> None:
    """HDF5形式で保存"""
    if not HDF5_AVAILABLE:
        raise ImportError(
            "h5py is required for HDF5 format. "
            "Install it with: pip install h5py"
        )
    
    import h5py
    import pickle
    
    compression = compress if compress in ["gzip", "lzf", "szip"] else None
    
    with h5py.File(str(file_path), 'w') as f:
        for key, value in session.items():
            # キー名をクリーンアップ（HDF5の制約）
            clean_key = key.replace('/', '_')
            
            if NUMPY_AVAILABLE and isinstance(value, np.ndarray):
                f.create_dataset(clean_key, data=value, compression=compression)
            elif PANDAS_AVAILABLE and isinstance(value, pd.DataFrame):
                # DataFrameをndarrayとして保存（メタデータも保存）
                f.create_dataset(clean_key, data=value.values, compression=compression)
                f[clean_key].attrs['columns'] = [str(c) for c in value.columns]
                f[clean_key].attrs['index'] = value.index.tolist()
                f[clean_key].attrs['__type__'] = 'DataFrame'
            elif PANDAS_AVAILABLE and isinstance(value, pd.Series):
                # Seriesをndarrayとして保存
                f.create_dataset(clean_key, data=value.values, compression=compression)
                f[clean_key].attrs['index'] = value.index.tolist()
                f[clean_key].attrs['name'] = str(value.name) if value.name else ''
                f[clean_key].attrs['__type__'] = 'Series'
            elif isinstance(value, (int, float)):
                f.attrs[clean_key] = value
            elif isinstance(value, str):
                f.attrs[clean_key] = value.encode('utf-8')
            else:
                # その他の型はpickleでシリアライズして保存
                try:
                    pickled = pickle.dumps(value)
                    f.create_dataset(clean_key, data=np.frombuffer(pickled, dtype=np.uint8), compression=compression)
                    f[clean_key].attrs['__type__'] = 'pickle'
                except Exception:
                    # pickleできない場合はスキップ
                    warnings.warn(f"Cannot save {key} to HDF5 format", UserWarning)


def load_hdf5(file_path: Path) -> Dict[str, Any]:
    """HDF5形式で読み込み"""
    if not HDF5_AVAILABLE:
        raise ImportError(
            "h5py is required for HDF5 format. "
            "Install it with: pip install h5py"
        )
    
    import h5py
    import pickle
    
    session = {}
    
    with h5py.File(str(file_path), 'r') as f:
        # データセットを読み込み
        for key in f.keys():
            dataset = f[key]
            obj_type = dataset.attrs.get('__type__', None)
            
            if obj_type == 'DataFrame' and PANDAS_AVAILABLE:
                # DataFrameとして復元
                data = np.array(dataset)
                columns = [str(c) for c in dataset.attrs.get('columns', [])]
                index = dataset.attrs.get('index', list(range(len(data))))
                session[key] = pd.DataFrame(data, columns=columns, index=index)
            elif obj_type == 'Series' and PANDAS_AVAILABLE:
                # Seriesとして復元
                data = np.array(dataset)
                index = dataset.attrs.get('index', list(range(len(data))))
                name = dataset.attrs.get('name', None)
                session[key] = pd.Series(data, index=index, name=name if name else None)
            elif obj_type == 'pickle':
                # pickleでシリアライズされたオブジェクトを復元
                pickled = dataset[:].tobytes()
                session[key] = pickle.loads(pickled)
            else:
                # 通常のndarrayとして読み込み
                if NUMPY_AVAILABLE:
                    session[key] = np.array(dataset)
                else:
                    session[key] = dataset[:]
        
        # 属性を読み込み
        for key in f.attrs.keys():
            value = f.attrs[key]
            if isinstance(value, bytes):
                session[key] = value.decode('utf-8')
            else:
                session[key] = value
    
    return session

