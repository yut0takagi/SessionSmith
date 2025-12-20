"""
カスタムシリアライザー機能
"""

from typing import Any, Callable, Optional, Dict
import pickle


class CustomSerializer:
    """
    カスタムシリアライザーを管理するクラス
    """

    def __init__(self):
        self.serializers: Dict[type, Callable] = {}

    def register(self, obj_type: type, serializer: Callable) -> None:
        """
        特定の型に対するシリアライザーを登録します

        Args:
            obj_type (type): シリアライズする型
            serializer (callable): シリアライザー関数（obj -> serializable）
        """
        self.serializers[obj_type] = serializer

    def serialize(self, obj: Any) -> Any:
        """
        オブジェクトをシリアライズします

        Args:
            obj: シリアライズするオブジェクト

        Returns:
            シリアライズ可能なオブジェクト
        """
        obj_type = type(obj)

        # 登録されたシリアライザーをチェック
        if obj_type in self.serializers:
            return self.serializers[obj_type](obj)

        # 型の階層をチェック（基底クラス用）
        for registered_type, serializer in self.serializers.items():
            if isinstance(obj, registered_type):
                return serializer(obj)

        return obj

    def __call__(self, obj: Any) -> Any:
        """
        関数として呼び出せるようにする
        """
        return self.serialize(obj)


def create_serializer(*args, **kwargs) -> CustomSerializer:
    """
    カスタムシリアライザーを作成します

    Usage:
        serializer = create_serializer()
        serializer.register(MyClass, lambda x: x.to_dict())
    """
    return CustomSerializer()

