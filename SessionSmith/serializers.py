"""
カスタムシリアライザー機能
"""

from typing import Any, Callable, Optional, Dict, Type, Union
import warnings


class CustomSerializer:
    """
    カスタムシリアライザーを管理するクラス
    特定の型に対してカスタムシリアライゼーションを定義できます。
    """

    def __init__(self):
        """カスタムシリアライザーを初期化します"""
        self.serializers: Dict[Type[Any], Callable[[Any], Any]] = {}

    def register(
        self, 
        obj_type: Type[Any], 
        serializer: Callable[[Any], Any]
    ) -> None:
        """
        特定の型に対するシリアライザーを登録します

        Args:
            obj_type: シリアライズする型
            serializer: シリアライザー関数（obj -> serializable）
            
        Raises:
            TypeError: obj_typeが型でない、またはserializerが呼び出し可能でない場合
        """
        if not isinstance(obj_type, type):
            raise TypeError(f"obj_type must be a type, got {type(obj_type).__name__}")
        
        if not callable(serializer):
            raise TypeError("serializer must be callable")
        
        self.serializers[obj_type] = serializer

    def serialize(self, obj: Any) -> Any:
        """
        オブジェクトをシリアライズします
        登録されたシリアライザーを使用して変換を試みます。

        Args:
            obj: シリアライズするオブジェクト

        Returns:
            シリアライズ可能なオブジェクト（変換できない場合は元のオブジェクト）
        """
        if obj is None:
            return None
        
        obj_type = type(obj)

        # 登録されたシリアライザーをチェック（完全一致）
        if obj_type in self.serializers:
            try:
                return self.serializers[obj_type](obj)
            except Exception as e:
                warnings.warn(
                    f"Serializer for {obj_type.__name__} failed: {e}",
                    UserWarning
                )
                return obj

        # 型の階層をチェック（基底クラス用）
        for registered_type, serializer in self.serializers.items():
            try:
                if isinstance(obj, registered_type):
                    try:
                        return serializer(obj)
                    except Exception as e:
                        warnings.warn(
                            f"Serializer for {registered_type.__name__} failed: {e}",
                            UserWarning
                        )
                        return obj
            except Exception:
                # isinstanceチェックが失敗した場合（例：抽象基底クラス）
                continue

        return obj

    def __call__(self, obj: Any) -> Any:
        """
        関数として呼び出せるようにする
        
        Args:
            obj: シリアライズするオブジェクト
            
        Returns:
            シリアライズされたオブジェクト
        """
        return self.serialize(obj)

    def unregister(self, obj_type: Type[Any]) -> None:
        """
        登録されたシリアライザーを削除します
        
        Args:
            obj_type: 削除する型
            
        Raises:
            KeyError: 指定された型が登録されていない場合
        """
        if obj_type not in self.serializers:
            raise KeyError(f"No serializer registered for {obj_type.__name__}")
        del self.serializers[obj_type]

    def list_registered(self) -> list[Type[Any]]:
        """
        登録されている型のリストを取得します
        
        Returns:
            list: 登録されている型のリスト
        """
        return list(self.serializers.keys())


def create_serializer() -> CustomSerializer:
    """
    カスタムシリアライザーを作成します
    
    Returns:
        CustomSerializer: 新しいカスタムシリアライザーインスタンス
        
    Example:
        >>> serializer = create_serializer()
        >>> serializer.register(MyClass, lambda x: x.to_dict())
    """
    return CustomSerializer()
