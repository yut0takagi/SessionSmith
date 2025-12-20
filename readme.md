# SessionSmith

**SessionSmith** は、Jupyter Notebook や Python 実行時のセッション（変数・オブジェクト）を簡単に保存・復元できる軽量ライブラリです。

## ⚠️ セキュリティ警告

**重要**: このライブラリは`pickle`を使用しています。信頼できないソースからのセッションファイルをロードしないでください。悪意のあるpickleファイルは任意のコードを実行する可能性があります。

- ✅ 信頼できるソースからのファイルのみをロードしてください
- ✅ 不審なファイルをロードする前に、`verify_session()`で検証してください
- ✅ 本番環境では、セッションファイルの保存場所へのアクセスを制限してください

## 特徴

- 🚀 **簡単**: たった2行で保存＆復元
- 📦 **複数形式対応**: pickle（デフォルト）、JSON、MessagePack、HDF5
- 🔍 **自動検出**: ファイル拡張子から形式を自動検出
- 🗜️ **圧縮対応**: gzip/bz2圧縮でディスク容量を節約
- 📊 **情報表示**: セッションの詳細情報を確認
- 🔄 **比較機能**: 2つのセッションを比較
- 💾 **自動バックアップ**: 定期的な自動保存
- 🏷️ **バージョン管理**: Git風のコミット・チェックアウト機能
- 📈 **アルゴリズムトレーサー**: 1行ごとの変数状態記録・可視化
- 🎨 **可視化**: アルゴリズムの実行をアニメーションで表示
- 🚀 **拡張機能対応**: 拡張機能(SessionSmith)を利用することでコードを書かずに実行可能

## インストール

```bash
pip install SessionSmith
```

可視化機能を使う場合:

```bash
pip install SessionSmith[visualization]
# または
pip install matplotlib
```

## クイックスタート

### 基本的な使い方

```python
from SessionSmith import save_session, load_session

# セッション保存（pickle形式、デフォルト）
save_session("my_session.pkl")

# セッション復元
load_session("my_session.pkl")

# JSON形式で保存（安全、可読性）
save_session("my_session.json")

# MessagePack形式で保存（安全、高速）
save_session("my_session.msgpack", format="msgpack")

# HDF5形式で保存（科学計算データに最適）
save_session("my_session.h5", format="hdf5")
```

### SessionManagerを使う

```python
from SessionSmith import SessionManager

# マネージャーを作成
manager = SessionManager()

# 保存
manager.save("session.pkl")

# ロード
manager.load("session.pkl")
```

### バージョン管理（新機能）

```python
from SessionSmith import SessionManager

# バージョン管理を有効化
manager = SessionManager(enable_version_control=True)

# 保存（自動的にコミット）
manager.save("session.pkl", commit_message="Initial state")

# コミット履歴を確認
manager.log()

# 以前の状態に戻す
manager.checkout(message="Initial state")
```

## 主な機能

### 1. 基本的な保存・復元
- 変数の選択的保存・復元
- 圧縮サポート（gzip/bz2）
- Jupyter Notebook内部変数の自動除外

### 2. SessionManagerクラス
- セッション管理の簡素化
- 自動バックアップ機能
- バージョン管理機能（Git風）

### 3. セッション情報・比較
- セッション情報の表示
- 2つのセッションの比較
- セッションファイルの検証

### 4. アルゴリズム実行トレーサー
- 1行ごとの変数状態記録
- 可視化（アニメーション）
- トレースデータの保存・読み込み

### 5. カスタムシリアライザー
- 特定の型に対するカスタムシリアライゼーション
- 拡張可能な設計

## 詳細なドキュメント

詳細な使い方は以下のドキュメントを参照してください：

- 📖 [基本的な使い方](docs/getting-started.md) - 保存・復元の詳細
- 🔄 [バージョン管理](docs/version-control.md) - Git風のバージョン管理機能
- 📈 [アルゴリズムトレーサー](docs/algorithm-tracer.md) - トレース・可視化機能
- 📚 [APIリファレンス](docs/api-reference.md) - 全APIの詳細

## 使用例

### 複数形式のサポート

```python
# pickle形式（デフォルト、互換性重視）
save_session("session.pkl")

# JSON形式（安全、可読性）
save_session("session.json")

# MessagePack形式（安全、高速）
save_session("session.msgpack", format="msgpack")

# HDF5形式（科学計算データに最適）
save_session("session.h5", format="hdf5")
```

### 圧縮保存

```python
# gzip圧縮で保存
save_session("session.pkl", compress=True)
```

### セレクティブロード

```python
# 特定の変数のみ復元
load_session("session.pkl", include=["data", "model"])
```

### 自動バックアップ

```python
manager = SessionManager()
manager.auto_save(interval=300, file_path="autosave.pkl")
```

### アルゴリズム可視化

```python
from SessionSmith import AlgorithmTracer, visualize_algorithm_trace

with AlgorithmTracer(target_variables=["arr"]) as tracer:
    bubble_sort(arr)

visualize_algorithm_trace(
    trace_data=tracer.get_trace_data(),
    output_file="animation.gif",
    target_variables=["arr"]
)
```

## ライセンス

MIT
