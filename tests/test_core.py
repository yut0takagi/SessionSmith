"""
core.py のテスト
"""

import os
import tempfile
import pytest
from pathlib import Path

from SessionSmith.core import save_session, load_session
from SessionSmith.exceptions import ValidationError


class TestSaveSession:
    """save_session のテスト"""
    
    def test_save_basic(self, tmp_path):
        """基本的な保存テスト"""
        file_path = tmp_path / "test.pkl"
        
        # テスト用変数
        test_vars = {
            "a": 1,
            "b": [1, 2, 3],
            "c": {"key": "value"},
        }
        
        save_session(file_path, globals_dict=test_vars)
        
        assert file_path.exists()
        assert file_path.stat().st_size > 0
    
    def test_save_with_exclude(self, tmp_path):
        """除外リストのテスト"""
        file_path = tmp_path / "test.pkl"
        
        test_vars = {
            "keep": 1,
            "exclude_me": 2,
        }
        
        save_session(file_path, globals_dict=test_vars, exclude=["exclude_me"])
        
        loaded = load_session(file_path, globals_dict={})
        
        assert "keep" in loaded
        assert "exclude_me" not in loaded
    
    def test_save_with_compression(self, tmp_path):
        """圧縮テスト"""
        file_path = tmp_path / "test.pkl"
        
        test_vars = {"data": list(range(1000))}
        
        # 非圧縮
        save_session(file_path, globals_dict=test_vars, compress=False)
        uncompressed_size = file_path.stat().st_size
        
        # 圧縮
        save_session(file_path, globals_dict=test_vars, compress=True)
        compressed_size = file_path.stat().st_size
        
        assert compressed_size < uncompressed_size


class TestLoadSession:
    """load_session のテスト"""
    
    def test_load_basic(self, tmp_path):
        """基本的な復元テスト"""
        file_path = tmp_path / "test.pkl"
        
        original = {
            "a": 1,
            "b": [1, 2, 3],
            "c": {"key": "value"},
        }
        
        save_session(file_path, globals_dict=original)
        
        restored = {}
        load_session(file_path, globals_dict=restored)
        
        assert restored["a"] == 1
        assert restored["b"] == [1, 2, 3]
        assert restored["c"] == {"key": "value"}
    
    def test_load_with_include(self, tmp_path):
        """選択的ロードテスト"""
        file_path = tmp_path / "test.pkl"
        
        original = {"a": 1, "b": 2, "c": 3}
        save_session(file_path, globals_dict=original)
        
        restored = {}
        load_session(file_path, globals_dict=restored, include=["a", "b"])
        
        assert "a" in restored
        assert "b" in restored
        assert "c" not in restored
    
    def test_load_file_not_found(self, tmp_path):
        """存在しないファイルのテスト"""
        file_path = tmp_path / "nonexistent.pkl"
        
        with pytest.raises(FileNotFoundError):
            load_session(file_path, globals_dict={})


class TestFormats:
    """複数形式のテスト"""
    
    def test_json_format(self, tmp_path):
        """JSON形式のテスト"""
        file_path = tmp_path / "test.json"
        
        original = {"a": 1, "b": [1, 2, 3]}
        save_session(file_path, globals_dict=original, format="json")
        
        restored = {}
        load_session(file_path, globals_dict=restored, format="json")
        
        assert restored["a"] == 1
        assert restored["b"] == [1, 2, 3]


class TestValidation:
    """入力バリデーションのテスト"""
    
    def test_invalid_file_path_type(self, tmp_path):
        """無効なファイルパス型のテスト"""
        with pytest.raises(TypeError):
            save_session(123, globals_dict={"a": 1})
    
    def test_empty_file_path(self, tmp_path):
        """空のファイルパスのテスト"""
        with pytest.raises(ValueError):
            save_session("", globals_dict={"a": 1})
    
    def test_invalid_compress_option(self, tmp_path):
        """無効な圧縮オプションのテスト"""
        file_path = tmp_path / "test.pkl"
        
        with pytest.raises(ValueError):
            save_session(file_path, globals_dict={"a": 1}, compress="invalid")


class TestRobustness:
    """堅牢性テスト"""
    
    def test_save_large_data(self, tmp_path):
        """大きなデータの保存テスト"""
        file_path = tmp_path / "large.pkl"
        
        # 1MBのデータ
        large_data = {"data": list(range(100000))}
        save_session(file_path, globals_dict=large_data)
        
        restored = {}
        load_session(file_path, globals_dict=restored)
        
        assert len(restored["data"]) == 100000
    
    def test_save_special_characters_in_path(self, tmp_path):
        """特殊文字を含むパスのテスト"""
        special_dir = tmp_path / "test 日本語"
        special_dir.mkdir()
        file_path = special_dir / "test.pkl"
        
        save_session(file_path, globals_dict={"a": 1})
        
        restored = {}
        load_session(file_path, globals_dict=restored)
        
        assert restored["a"] == 1
    
    def test_save_nested_data(self, tmp_path):
        """ネストしたデータの保存テスト"""
        file_path = tmp_path / "nested.pkl"
        
        nested = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": 42
                    }
                }
            }
        }
        save_session(file_path, globals_dict=nested)
        
        restored = {}
        load_session(file_path, globals_dict=restored)
        
        assert restored["level1"]["level2"]["level3"]["value"] == 42

