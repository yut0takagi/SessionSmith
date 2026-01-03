"""
cli.py のテスト
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from SessionSmith.cli import main, cmd_init, cmd_status


class TestCLIInit:
    """CLI init コマンドのテスト"""
    
    def test_init_command(self, tmp_path, monkeypatch):
        """init コマンドのテスト"""
        monkeypatch.chdir(tmp_path)
        
        # 引数をモック
        with patch.object(sys, 'argv', ['ssm', 'init']):
            try:
                main()
            except SystemExit:
                pass
        
        assert (tmp_path / ".ssm").exists()


class TestCLIStatus:
    """CLI status コマンドのテスト"""
    
    def test_status_not_initialized(self, tmp_path, monkeypatch, capsys):
        """初期化前の status テスト"""
        monkeypatch.chdir(tmp_path)
        
        with patch.object(sys, 'argv', ['ssm', 'status']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 1
        
        captured = capsys.readouterr()
        assert "not initialized" in captured.err.lower()


class TestCLIHelp:
    """CLI ヘルプのテスト"""
    
    def test_help_shows_commands(self, capsys):
        """ヘルプでコマンド一覧が表示されることを確認"""
        with patch.object(sys, 'argv', ['ssm', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 0
        
        captured = capsys.readouterr()
        assert "init" in captured.out
        assert "commit" in captured.out
        assert "log" in captured.out


class TestCLIWatch:
    """CLI watch コマンドのテスト"""
    
    def test_watch_not_initialized(self, tmp_path, monkeypatch, capsys):
        """初期化前の watch テスト"""
        monkeypatch.chdir(tmp_path)
        
        with patch.object(sys, 'argv', ['ssm', 'watch']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 1


class TestCLIStats:
    """CLI stats コマンドのテスト"""
    
    def test_stats_no_data(self, tmp_path, monkeypatch, capsys):
        """データがない場合の stats テスト"""
        monkeypatch.chdir(tmp_path)
        
        # まず初期化
        with patch.object(sys, 'argv', ['ssm', 'init']):
            try:
                main()
            except SystemExit:
                pass
        
        # stats を実行
        with patch.object(sys, 'argv', ['ssm', 'stats']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 1

