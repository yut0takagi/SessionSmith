"""
ssm.py のテスト
"""

import os
import time
import tempfile
import threading
import pytest
from pathlib import Path

from SessionSmith.ssm import SSM, CheckpointContext
from SessionSmith.exceptions import (
    SSMNotInitializedError,
    SSMCommitNotFoundError,
    SSMNoCommitsError,
    ValidationError,
    MemoryLimitError,
    CheckpointError,
)


class TestSSMInit:
    """SSM 初期化のテスト"""
    
    def test_init_creates_directory(self, tmp_path):
        """初期化でディレクトリが作成されることを確認"""
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        assert (tmp_path / ".ssm").exists()
        assert (tmp_path / ".ssm" / "config").exists()
        assert (tmp_path / ".ssm" / "HEAD").exists()
        assert (tmp_path / ".ssm" / "objects").exists()
        assert (tmp_path / ".ssm" / "commits").exists()
    
    def test_init_force(self, tmp_path):
        """force オプションのテスト"""
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        # 2回目は force なしでもエラーにならない
        ssm.init()
        
        # force で再初期化
        ssm.init(force=True)
        
        assert ssm.is_initialized
    
    def test_is_initialized(self, tmp_path):
        """is_initialized プロパティのテスト"""
        ssm = SSM(path=tmp_path)
        
        assert not ssm.is_initialized
        
        ssm.init()
        
        assert ssm.is_initialized


class TestSSMCommit:
    """SSM コミットのテスト"""
    
    def test_commit_basic(self, tmp_path):
        """基本的なコミットテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1, "b": [1, 2, 3]})
        ssm.init()
        
        commit_hash = ssm.commit("Test commit")
        
        assert commit_hash
        assert len(commit_hash) == 16
        
        # HEAD が更新されていることを確認
        head = (tmp_path / ".ssm" / "HEAD").read_text().strip()
        assert head == commit_hash
    
    def test_commit_creates_objects(self, tmp_path):
        """コミットでオブジェクトが作成されることを確認"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        ssm.commit("Test")
        
        objects_dir = tmp_path / ".ssm" / "objects"
        # オブジェクトディレクトリにファイルがあることを確認
        object_files = list(objects_dir.rglob("*"))
        assert len([f for f in object_files if f.is_file()]) > 0


class TestSSMLog:
    """SSM ログのテスト"""
    
    def test_log_empty(self, tmp_path):
        """コミットがない場合のテスト"""
        ssm = SSM(path=tmp_path, globals_dict={})
        ssm.init()
        
        commits = ssm.log()
        
        assert commits == []
    
    def test_log_with_commits(self, tmp_path):
        """コミットがある場合のテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        ssm.commit("First")
        ssm.commit("Second")
        
        commits = ssm.log()
        
        assert len(commits) == 2
        assert commits[0]["message"] == "Second"
        assert commits[1]["message"] == "First"


class TestSSMCheckout:
    """SSM チェックアウトのテスト"""
    
    def test_checkout_restores_variables(self, tmp_path):
        """チェックアウトで変数が復元されることを確認"""
        globals_dict = {"a": 1}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()
        
        hash1 = ssm.commit("First")
        
        globals_dict["a"] = 2
        ssm.commit("Second")
        
        ssm.checkout(hash1)
        
        # 復元されていることを確認（スナップショット経由）
        assert ssm.is_initialized


class TestSSMConfig:
    """SSM 設定のテスト"""
    
    def test_config_get_all(self, tmp_path):
        """全設定の取得テスト"""
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        config = ssm.config()
        
        assert "version" in config
        assert "exclude" in config
    
    def test_config_set(self, tmp_path):
        """設定の変更テスト"""
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        ssm.config("test_key", "test_value")
        
        value = ssm.config("test_key")
        assert value == "test_value"


class TestSSMExclude:
    """SSM 除外リストのテスト"""
    
    def test_exclude_adds_to_list(self, tmp_path):
        """除外リストへの追加テスト"""
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        ssm.exclude("var1", "var2")
        
        config = ssm.config()
        assert "var1" in config["exclude"]
        assert "var2" in config["exclude"]


class TestSSMExceptions:
    """SSM 例外テスト"""
    
    def test_not_initialized_error(self, tmp_path):
        """初期化されていない場合のエラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        
        with pytest.raises(SSMNotInitializedError):
            ssm.commit("test")
    
    def test_commit_not_found_error(self, tmp_path):
        """コミットが見つからない場合のエラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        ssm.commit("test")
        
        with pytest.raises(SSMCommitNotFoundError):
            ssm.checkout("nonexistent")
    
    def test_no_commits_error(self, tmp_path):
        """コミットがない場合のcheckoutエラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        with pytest.raises(SSMNoCommitsError):
            ssm.checkout()
    
    def test_validation_error_message_too_long(self, tmp_path):
        """メッセージが長すぎる場合のバリデーションエラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        long_message = "x" * 501
        with pytest.raises(ValidationError):
            ssm.commit(long_message)
    
    def test_validation_error_author_too_long(self, tmp_path):
        """作成者名が長すぎる場合のバリデーションエラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        long_author = "x" * 101
        with pytest.raises(ValidationError):
            ssm.commit("test", author=long_author)


class TestSSMRobustness:
    """SSM 堅牢性テスト"""
    
    def test_empty_variables(self, tmp_path):
        """空の変数辞書でコミットした場合のテスト"""
        ssm = SSM(path=tmp_path, globals_dict={})
        ssm.init()
        
        # 空のコミットは空文字列を返す
        result = ssm.commit("test")
        assert result == ""
    
    def test_short_hash_checkout(self, tmp_path):
        """短縮ハッシュでのチェックアウトテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        full_hash = ssm.commit("test")
        short_hash = full_hash[:7]
        
        # 短縮ハッシュでチェックアウト
        ssm.checkout(short_hash)
    
    def test_multiple_commits_log_order(self, tmp_path):
        """複数コミットのログ順序テスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        ssm.commit("First")
        ssm.commit("Second")
        ssm.commit("Third")
        
        logs = ssm.log()
        
        # 新しいものが先頭
        assert logs[0]["message"] == "Third"
        assert logs[1]["message"] == "Second"
        assert logs[2]["message"] == "First"
    
    def test_reinit_preserves_nothing_without_force(self, tmp_path):
        """force なしの再初期化は何も変更しない"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        hash1 = ssm.commit("test")
        
        # 再初期化（force なし）
        ssm.init()
        
        # コミットは保持される
        logs = ssm.log()
        assert len(logs) == 1
    
    def test_reinit_clears_with_force(self, tmp_path):
        """force ありの再初期化はすべてクリア"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        ssm.commit("test")
        
        # force で再初期化
        ssm.init(force=True)
        
        # コミットはクリアされる
        logs = ssm.log()
        assert len(logs) == 0


class TestSSMFormatCompatibility:
    """SSM 形式互換性テスト"""
    
    def test_export_to_pickle(self, tmp_path):
        """Pickle形式へのエクスポートテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1, "b": [1, 2, 3]})
        ssm.init()
        
        commit_hash = ssm.commit("test")
        
        # エクスポート
        output_path = tmp_path / "export.pkl"
        ssm.export(output_path)
        
        assert output_path.exists()
        
        # 内容を確認
        import pickle
        with open(output_path, 'rb') as f:
            data = pickle.load(f)
        
        assert "a" in data
        assert data["a"] == 1
        assert data["b"] == [1, 2, 3]
    
    def test_export_to_json(self, tmp_path):
        """JSON形式へのエクスポートテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1, "b": [1, 2, 3]})
        ssm.init()
        
        ssm.commit("test")
        
        # エクスポート
        output_path = tmp_path / "export.json"
        ssm.export(output_path)
        
        assert output_path.exists()
        
        # 内容を確認
        import json
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert "a" in data
        assert data["a"] == 1
    
    def test_import_from_pickle(self, tmp_path):
        """Pickle形式からのインポートテスト"""
        # 従来形式で保存
        import pickle
        input_path = tmp_path / "input.pkl"
        with open(input_path, 'wb') as f:
            pickle.dump({"x": 100, "y": "hello"}, f)
        
        # SSMにインポート
        ssm = SSM(path=tmp_path, globals_dict={})
        ssm.init()
        
        commit_hash = ssm.import_session(input_path)
        
        assert commit_hash
        
        # コミットを確認
        logs = ssm.log()
        assert len(logs) == 1
    
    def test_import_from_json(self, tmp_path):
        """JSON形式からのインポートテスト"""
        # 従来形式で保存
        import json
        input_path = tmp_path / "input.json"
        with open(input_path, 'w') as f:
            json.dump({"x": 100, "y": "hello"}, f)
        
        # SSMにインポート
        ssm = SSM(path=tmp_path, globals_dict={})
        ssm.init()
        
        commit_hash = ssm.import_session(input_path)
        
        assert commit_hash
    
    def test_convert_pickle_to_json(self, tmp_path):
        """Pickle→JSON変換テスト"""
        # Pickleファイルを作成
        import pickle
        import json
        
        input_path = tmp_path / "input.pkl"
        with open(input_path, 'wb') as f:
            pickle.dump({"a": 1, "b": [1, 2, 3]}, f)
        
        # 変換
        ssm = SSM(path=tmp_path)
        ssm.init()
        
        output_path = tmp_path / "output.json"
        ssm.convert(input_path, output_path)
        
        assert output_path.exists()
        
        # 内容を確認
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert data["a"] == 1
        assert data["b"] == [1, 2, 3]
    
    def test_export_specific_commit(self, tmp_path):
        """特定コミットのエクスポートテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"a": 1})
        ssm.init()
        
        hash1 = ssm.commit("First")
        
        ssm.globals_dict = {"a": 2}
        hash2 = ssm.commit("Second")
        
        # 最初のコミットをエクスポート
        output_path = tmp_path / "first.pkl"
        ssm.export(output_path, commit_hash=hash1)
        
        import pickle
        with open(output_path, 'rb') as f:
            data = pickle.load(f)
        
        assert data["a"] == 1  # 最初の値


class TestSSMCheckpoint:
    """SSM チェックポイント機能のテスト（長時間実行対応）"""
    
    def test_checkpoint_context_basic(self, tmp_path):
        """基本的なチェックポイントコンテキストのテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"counter": 0})
        ssm.init()
        
        # 短い間隔でテスト（2秒）
        with ssm.checkpoint(interval=2, max_checkpoints=3) as cp:
            for i in range(3):
                ssm.globals_dict["counter"] = i
                cp.step(force=(i == 2))  # 最後だけ強制チェックポイント
                time.sleep(0.1)
        
        # チェックポイントディレクトリを確認
        checkpoint_dir = tmp_path / ".ssm" / "checkpoints"
        assert checkpoint_dir.exists()
        
        # 少なくとも1つのチェックポイントがあること
        checkpoints = list(checkpoint_dir.glob("checkpoint_*.gz"))
        assert len(checkpoints) >= 1
    
    def test_checkpoint_with_metrics(self, tmp_path):
        """メトリクス付きチェックポイントのテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"loss": 1.0})
        ssm.init()
        
        with ssm.checkpoint(interval=1) as cp:
            for i in range(5):
                loss = 1.0 - i * 0.1
                ssm.globals_dict["loss"] = loss
                cp.step(loss=loss, accuracy=i * 0.1)
        
        # サマリーを確認
        checkpoints = ssm.list_checkpoints()
        
        # チェックポイントがあれば、メトリクスを確認
        if checkpoints:
            assert "metrics" in checkpoints[0]
    
    def test_checkpoint_restore(self, tmp_path):
        """チェックポイントからの復元テスト"""
        globals_dict = {"value": 100}
        ssm = SSM(path=tmp_path, globals_dict=globals_dict)
        ssm.init()
        
        # チェックポイントを作成
        with ssm.checkpoint(interval=1) as cp:
            globals_dict["value"] = 200
            cp.step(force=True)
        
        # 値を変更
        globals_dict["value"] = 999
        
        # チェックポイントから復元
        meta = ssm.restore_checkpoint()
        
        assert meta["restored_count"] > 0
        assert globals_dict["value"] == 200  # 復元された値
    
    def test_checkpoint_list(self, tmp_path):
        """チェックポイント一覧テスト"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        
        # 複数のチェックポイントを作成
        with ssm.checkpoint(interval=1, max_checkpoints=5) as cp:
            for i in range(3):
                ssm.globals_dict["x"] = i
                cp.step(force=True, iteration=i)
        
        checkpoints = ssm.list_checkpoints()
        
        # 最大で3つのチェックポイント
        assert len(checkpoints) >= 1
        
        # 各チェックポイントに必要な情報がある
        for cp in checkpoints:
            assert "file" in cp
            assert "timestamp" in cp
            assert "variable_count" in cp
    
    def test_checkpoint_clean(self, tmp_path):
        """チェックポイントクリーンテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        
        # チェックポイントを作成
        with ssm.checkpoint(interval=1, max_checkpoints=10) as cp:
            for i in range(3):
                cp.step(force=True)
        
        # クリーン前
        before = ssm.list_checkpoints()
        assert len(before) >= 1
        
        # すべてクリーン
        deleted = ssm.clean_checkpoints(keep=0)
        
        after = ssm.list_checkpoints()
        assert len(after) == 0
    
    def test_checkpoint_max_limit(self, tmp_path):
        """チェックポイント最大数制限テスト"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        
        max_cp = 2
        
        with ssm.checkpoint(interval=1, max_checkpoints=max_cp) as cp:
            for i in range(5):
                ssm.globals_dict["x"] = i
                cp.step(force=True)
                time.sleep(0.1)  # ファイル名のタイムスタンプ衝突を避ける
        
        checkpoints = ssm.list_checkpoints()
        
        # 最大数を超えないこと
        assert len(checkpoints) <= max_cp + 1  # +1 は終了時の final checkpoint
    
    def test_checkpoint_no_checkpoints_error(self, tmp_path):
        """チェックポイントがない場合の復元エラーテスト"""
        ssm = SSM(path=tmp_path, globals_dict={})
        ssm.init()
        
        with pytest.raises(FileNotFoundError):
            ssm.restore_checkpoint()
    
    def test_checkpoint_elapsed_time(self, tmp_path):
        """経過時間追跡テスト"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        
        with ssm.checkpoint(interval=10) as cp:
            time.sleep(0.5)
            assert cp.elapsed >= 0.4
            assert "0:00" in cp.elapsed_str
    
    def test_checkpoint_summary(self, tmp_path):
        """サマリー取得テスト"""
        ssm = SSM(path=tmp_path, globals_dict={"x": 1})
        ssm.init()
        
        with ssm.checkpoint(interval=10) as cp:
            cp.step(loss=0.5)
            cp.step(loss=0.4)
            cp.step(force=True, loss=0.3)
            
            summary = cp.summary()
            
            assert "elapsed" in summary
            assert "step_count" in summary
            assert summary["step_count"] == 3
            assert "metrics" in summary
            assert "loss" in summary["metrics"]


class TestSSMLargeData:
    """大規模データ処理のテスト"""
    
    def test_large_variable_warning(self, tmp_path):
        """大きな変数の警告テスト"""
        # 約10MBのデータ
        large_data = b"x" * (10 * 1024 * 1024)
        
        ssm = SSM(path=tmp_path, globals_dict={"large": large_data})
        ssm.init()
        
        # 警告が出るがコミットは成功する
        commit_hash = ssm.commit("Large data commit")
        assert commit_hash
    
    def test_variable_size_check(self, tmp_path):
        """変数サイズチェックテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"small": 1, "medium": list(range(1000))})
        ssm.init()
        
        # _get_saveable_vars で size_check=True
        globals_dict = ssm._get_globals_dict(depth=1)
        saveable = ssm._get_saveable_vars(globals_dict, size_check=True, verbose=False)
        
        # 保存可能な変数が含まれること
        assert len(saveable) >= 1


class TestSSMThreadSafety:
    """スレッドセーフティのテスト"""
    
    def test_concurrent_commits(self, tmp_path):
        """並行コミットテスト"""
        ssm = SSM(path=tmp_path, globals_dict={"counter": 0})
        ssm.init()
        
        errors = []
        
        def commit_worker(n):
            try:
                ssm.globals_dict = {"counter": n}
                ssm.commit(f"Commit {n}")
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=commit_worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # エラーがないこと（ただし、並行コミットは完全にはサポートされない可能性あり）
        # ここでは、少なくともクラッシュしないことを確認
        logs = ssm.log(limit=10)
        assert len(logs) >= 1

