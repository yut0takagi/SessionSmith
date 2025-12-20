"""
バージョン管理機能（Git風）
"""

import json
import shutil
import hashlib
import getpass
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from datetime import datetime
from .compare import compare_sessions
from .info import get_session_info


class VersionControl:
    """
    セッションのバージョン管理クラス（内部使用）
    Git風のコミット、チェックアウト、ログ機能を提供
    """
    
    def __init__(self, base_path: Path):
        """
        Args:
            base_path: バージョン管理のベースパス
        """
        self.base_path = base_path
        self.vc_dir = base_path / ".sessionvc"
        self.commits_dir = self.vc_dir / "commits"
        self.metadata_file = self.vc_dir / "metadata.json"
        
        self._init_vc()
    
    def _init_vc(self) -> None:
        """バージョン管理ディレクトリを初期化"""
        self.vc_dir.mkdir(parents=True, exist_ok=True)
        self.commits_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.metadata_file.exists():
            self._save_metadata({
                "commits": [],
                "current_commit": None,
                "head": None
            })
    
    def _save_metadata(self, metadata: Dict[str, Any]) -> None:
        """メタデータを保存"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise IOError(f"Failed to save version control metadata: {str(e)}") from e
    
    def _load_metadata(self) -> Dict[str, Any]:
        """メタデータを読み込み"""
        if not self.metadata_file.exists():
            return {"commits": [], "current_commit": None, "head": None}
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise IOError(f"Failed to load version control metadata: {str(e)}") from e
    
    def _generate_commit_hash(self, message: str, timestamp: str) -> str:
        """コミットハッシュを生成"""
        content = f"{message}{timestamp}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()[:12]
    
    def _get_default_author(self) -> str:
        """デフォルトの作成者名を取得"""
        try:
            username = getpass.getuser()
            return f"{username} <{username}@localhost>"
        except Exception:
            return "Unknown <unknown@localhost>"
    
    def commit(
        self,
        message: str,
        file_path: Path,
        author: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        セッションをコミット
        
        Args:
            message: コミットメッセージ
            file_path: コミットするセッションファイル
            author: 作成者名
            tags: タグのリスト
            
        Returns:
            str: コミットハッシュ
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")
        
        metadata = self._load_metadata()
        timestamp = datetime.now().isoformat()
        commit_hash = self._generate_commit_hash(message, timestamp)
        
        # セッションファイルをコミットディレクトリにコピー
        commit_file = self.commits_dir / f"{commit_hash}.pkl"
        try:
            shutil.copy2(str(file_path), str(commit_file))
        except Exception as e:
            raise IOError(f"Failed to copy session file: {str(e)}") from e
        
        # セッション情報を取得
        try:
            session_info = get_session_info(str(file_path))
        except Exception:
            session_info = None
        
        commit_info: Dict[str, Any] = {
            "hash": commit_hash,
            "message": message,
            "timestamp": timestamp,
            "author": author or self._get_default_author(),
            "tags": tags or [],
            "session_file": str(file_path.relative_to(self.base_path)),
            "file_size": commit_file.stat().st_size,
            "variable_count": session_info.get("variable_count") if session_info else None,
        }
        
        if metadata["head"]:
            commit_info["parent"] = metadata["head"]
        else:
            commit_info["parent"] = None
        
        metadata["commits"].append(commit_info)
        metadata["head"] = commit_hash
        metadata["current_commit"] = commit_hash
        
        self._save_metadata(metadata)
        
        return commit_hash
    
    def log(
        self,
        limit: Optional[int] = None,
        oneline: bool = False
    ) -> List[Dict[str, Any]]:
        """
        コミット履歴を表示
        
        Args:
            limit: 表示するコミット数の上限
            oneline: 1行形式で表示するか
            
        Returns:
            list: コミット情報のリスト
        """
        metadata = self._load_metadata()
        commits = metadata["commits"]
        
        if limit:
            commits = commits[-limit:]
        
        commits = list(reversed(commits))  # 新しい順に
        
        if oneline:
            for commit in commits:
                print(f"{commit['hash']} {commit['message']}")
        else:
            for commit in commits:
                print(f"commit {commit['hash']}")
                print(f"Author: {commit['author']}")
                print(f"Date:   {commit['timestamp']}")
                if commit['tags']:
                    print(f"Tags:   {', '.join(commit['tags'])}")
                print(f"")
                print(f"    {commit['message']}")
                print(f"")
        
        return commits
    
    def checkout(
        self,
        commit_hash: Optional[str] = None,
        message: Optional[str] = None,
        target_file: Optional[Path] = None
    ) -> Path:
        """
        以前のコミット状態に戻す
        
        Args:
            commit_hash: コミットハッシュ
            message: コミットメッセージ（部分一致で検索）
            target_file: 復元先のファイルパス
            
        Returns:
            Path: 復元されたファイルのパス
        """
        metadata = self._load_metadata()
        
        # コミットを検索
        if commit_hash:
            commit = next(
                (c for c in metadata["commits"] if c["hash"] == commit_hash),
                None
            )
        elif message:
            commit = next(
                (c for c in metadata["commits"] if message.lower() in c["message"].lower()),
                None
            )
        else:
            raise ValueError("Either commit_hash or message must be provided")
        
        if not commit:
            raise ValueError(f"Commit not found: {commit_hash or message}")
        
        # コミットファイルのパス
        commit_file = self.commits_dir / f"{commit['hash']}.pkl"
        if not commit_file.exists():
            raise FileNotFoundError(f"Commit file not found: {commit_file}")
        
        # 復元先のファイルパス
        if target_file is None:
            target_file = self.base_path / commit["session_file"]
        else:
            target_file = Path(target_file)
            if not target_file.is_absolute():
                target_file = self.base_path / target_file
        
        # ファイルをコピー
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(commit_file), str(target_file))
        except Exception as e:
            raise IOError(f"Failed to restore session: {str(e)}") from e
        
        # 現在のコミットを更新
        metadata["current_commit"] = commit["hash"]
        self._save_metadata(metadata)
        
        return target_file
    
    def diff(
        self,
        commit1: Optional[str] = None,
        commit2: Optional[str] = None,
        detailed: bool = True
    ) -> Dict[str, Any]:
        """
        2つのコミット間の差分を表示
        
        Args:
            commit1: 最初のコミットハッシュ（Noneの場合はHEAD）
            commit2: 2番目のコミットハッシュ（Noneの場合はHEAD）
            detailed: 詳細な差分を含めるか
            
        Returns:
            dict: 差分情報
        """
        metadata = self._load_metadata()
        
        if commit1 is None:
            commit1 = metadata["head"]
        if commit2 is None:
            commit2 = metadata["head"]
        
        if not commit1 or not commit2:
            raise ValueError("No commits available")
        
        file1 = self.commits_dir / f"{commit1}.pkl"
        file2 = self.commits_dir / f"{commit2}.pkl"
        
        if not file1.exists() or not file2.exists():
            raise FileNotFoundError("Commit files not found")
        
        return compare_sessions(str(file1), str(file2), detailed=detailed)
    
    def status(self) -> Dict[str, Any]:
        """
        現在の状態を確認
        
        Returns:
            dict: 状態情報
        """
        metadata = self._load_metadata()
        return {
            "total_commits": len(metadata["commits"]),
            "current_commit": metadata["current_commit"],
            "head": metadata["head"],
            "latest_commit": metadata["commits"][-1] if metadata["commits"] else None
        }
    
    def tag(
        self,
        tag_name: str,
        commit_hash: Optional[str] = None
    ) -> None:
        """
        コミットにタグを追加
        
        Args:
            tag_name: タグ名
            commit_hash: コミットハッシュ（Noneの場合はHEAD）
        """
        metadata = self._load_metadata()
        
        if commit_hash is None:
            commit_hash = metadata["head"]
        
        commit = next(
            (c for c in metadata["commits"] if c["hash"] == commit_hash),
            None
        )
        
        if not commit:
            raise ValueError(f"Commit not found: {commit_hash}")
        
        if tag_name not in commit["tags"]:
            commit["tags"].append(tag_name)
            self._save_metadata(metadata)
    
    def show(
        self,
        commit_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        コミットの詳細情報を表示
        
        Args:
            commit_hash: コミットハッシュ（Noneの場合はHEAD）
            
        Returns:
            dict: コミット情報
        """
        metadata = self._load_metadata()
        
        if commit_hash is None:
            commit_hash = metadata["head"]
        
        commit = next(
            (c for c in metadata["commits"] if c["hash"] == commit_hash),
            None
        )
        
        if not commit:
            raise ValueError(f"Commit not found: {commit_hash}")
        
        # セッション情報も取得
        commit_file = self.commits_dir / f"{commit_hash}.pkl"
        if commit_file.exists():
            try:
                session_info = get_session_info(str(commit_file))
                commit["session_info"] = session_info
            except Exception:
                pass
        
        return commit

