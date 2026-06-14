# SessionSmith

**SessionSmith** は、Jupyter Notebook や Python 実行時のセッション（変数・オブジェクト）を Git 風に管理できる堅牢なライブラリです。機械学習の長時間学習にも対応したチェックポイント機能を備えています。

## ⚠️ セキュリティ警告

**重要**: このライブラリは`pickle`を使用しています。信頼できないソースからのセッションファイルをロードしないでください。悪意のあるpickleファイルは任意のコードを実行する可能性があります。

- ✅ 信頼できるソースからのファイルのみをロードしてください
- ✅ 不審なファイルをロードする前に、`verify_session()`で検証してください
- ✅ 本番環境では、セッションファイルの保存場所へのアクセスを制限してください

## 特徴

- 🚀 **簡単**: たった2行で保存＆復元
- 🔧 **SSM**: Git風のセッション管理（`.ssm/` ディレクトリベース）
- 🔄 **常時記録**: クラッシュ対策の自動保存
- ⏱️ **チェックポイント**: 機械学習の長時間学習に対応（定期自動保存、中断時復元）
- 📦 **複数形式対応**: pickle（デフォルト）、JSON、MessagePack、HDF5
- 🔍 **自動検出**: ファイル拡張子から形式を自動検出
- 🗜️ **圧縮対応**: gzip/bz2圧縮でディスク容量を節約
- 📊 **情報表示**: セッションの詳細情報を確認
- 🔄 **比較機能**: 2つのセッションを比較
- 💾 **自動バックアップ**: 定期的な自動保存
- 🏷️ **バージョン管理**: Git風のコミット・チェックアウト機能
- 📈 **アルゴリズムトレーサー**: 1行ごとの変数状態記録・可視化
- 🎨 **可視化**: アルゴリズムの実行をアニメーションで表示
- 🚀 **拡張機能対応**: Cursor/VSCode拡張機能でコードを書かずに実行可能
- 🌐 **多言語対応**: 日本語・英語のエラーメッセージに対応
- 🛡️ **堅牢なエラーハンドリング**: リトライ、詳細なエラー情報、コンテキスト管理

## インストール

### pip でインストール（推奨）

```bash
pip install SessionSmith
```

### Homebrew でインストール

```bash
# 現在のリポジトリから直接インストール
brew install yut0takagi/SessionSmith/sessionsmith

# または、ローカルファイルからインストール
brew install --build-from-source ./Formula/sessionsmith.rb
```

可視化機能を使う場合:

```bash
pip install SessionSmith[visualization]
# または
pip install matplotlib
```

## クイックスタート

### SSM - Git風セッション管理（推奨）

```python
from SessionSmith import ssm

# 初期化（.ssm/ ディレクトリを作成）
ssm.init()

# 変数を作成
a = 1
b = [1, 2, 3]
model = train_model()

# コミット
ssm.commit("Initial state")

# 履歴を見る
ssm.log()

# ブランチ機能
ssm.branch('feature', create=True)  # ブランチ作成
ssm.checkout_branch('feature')      # ブランチ切り替え

# マージ機能
ssm.merge('feature')                # ブランチをマージ

# タグ機能
ssm.tag('v1.0.0')                   # タグ作成
ssm.checkout_tag('v1.0.0')         # タグからチェックアウト

# リモート機能
ssm.remote_add('origin', '/path/to/remote')  # リモート追加
ssm.push('origin', 'main')          # プッシュ
ssm.pull('origin', 'main')          # プル

# 常時記録を有効化（クラッシュ対策）
ssm.continuous()

# 以前の状態に復元
ssm.checkout("abc123")

# クラッシュ後の復元
ssm.recover()
```

### チェックポイント（長時間学習対応）

機械学習の学習ループなど、長時間実行されるタスクに最適です。

```python
from SessionSmith import ssm

ssm.init()

# 5分ごとに自動チェックポイント
with ssm.checkpoint(interval=300) as cp:
    for epoch in range(1000):
        loss = train()
        acc = validate()
        
        # 手動チェックポイント + メトリクス記録
        cp.step(loss=loss, accuracy=acc)
        
        # 学習が長くなっても自動保存される
        # Ctrl+C で中断しても自動保存される

# 中断後に復元
ssm.restore_checkpoint()

# チェックポイント一覧
ssm.list_checkpoints()
```

**チェックポイントの特徴:**
- ⏱️ 定期的な自動保存（バックグラウンド）
- 🛑 シグナル（Ctrl+C）での中断時に自動保存
- 💥 例外発生時に緊急保存
- 📊 メトリクスの追跡（loss, accuracy など）
- 🧹 古いチェックポイントの自動削除

### 形式変換（.pkl/.json との互換性）

```python
from SessionSmith import ssm

ssm.init()
ssm.commit("checkpoint")

# SSM → 従来形式へエクスポート
ssm.export("backup.pkl")
ssm.export("data.json")

# 従来形式 → SSMへインポート
ssm.import_session("old_session.pkl")

# 形式変換
ssm.convert("data.pkl", "data.json")
```

### 多言語対応（日本語・英語）

```python
from SessionSmith import set_language, get_language

# 日本語に設定
set_language('ja')
# または環境変数で設定: export SESSIONSMITH_LANG=ja

# 英語に設定
set_language('en')

# 自動検出（システムのロケールから判定）
set_language('auto')

# 現在の言語を確認
lang = get_language()  # 'ja' または 'en'
```

エラーメッセージや情報メッセージが設定した言語で表示されます。
SSMが初期化されている場合、言語設定は自動的に `.ssm/config` に保存されます。

### レガシーAPI（後方互換性）

> ⚠️ 以下のAPIは後方互換性のために残されています。新規開発では `ssm` の使用を推奨します。
> 
> **注意**: `save_session()` と `load_session()` は、デフォルトでSSM（`.ssm/`ディレクトリ）に統合されています。
> 全てのセッションは`.ssm/`ディレクトリ内に保存され、バージョン管理されます。

```python
from SessionSmith import save_session, load_session

# セッション保存（.ssm/ディレクトリに自動保存、バージョン管理付き）
save_session("my_session.pkl")  # SSMにコミット + オプションで.pklにもエクスポート

# セッション復元（SSMの最新コミットから読み込み）
load_session()  # ファイルパスなしで最新コミットから読み込み
load_session("my_session.pkl")  # ファイルが存在する場合はインポートしてから読み込み

# JSON形式で保存（安全、可読性）
save_session("my_session.json")  # SSMにコミット + オプションで.jsonにもエクスポート

# 従来通りファイルに直接保存する場合（use_ssm=False）
save_session("my_session.pkl", use_ssm=False)
load_session("my_session.pkl", use_ssm=False)
```

### CLI ツール

```bash
# 初期化
ssm init

# 状態確認
ssm status

# コミット
ssm commit -m "Add training data"

# 履歴
ssm log --oneline

# 監視モード（定期スナップショット）
ssm watch --interval 10

# ダッシュボード（Webブラウザ）
ssm dashboard

# 統計
ssm stats --graph
```

## 主な機能

### 1. SSM（Git風セッション管理）
- `.ssm/` ディレクトリベースのセッション管理
- コミット、履歴、チェックアウト
- ブランチ機能（分岐・切り替え）
- マージ機能（複数ブランチの統合）
- タグ機能（コミットへの名前付け）
- リモートリポジトリとの同期（push/pull）
- 常時記録（クラッシュ対策）
- CLIツール `ssm` コマンド

### 2. チェックポイント（長時間学習対応）
- 定期的な自動保存
- 中断・例外時の緊急保存
- メトリクス追跡
- 復元機能

### 3. 基本的な保存・復元
- 変数の選択的保存・復元
- 圧縮サポート（gzip/bz2）
- Jupyter Notebook内部変数の自動除外

### 4. SessionManagerクラス
- セッション管理の簡素化
- 自動バックアップ機能
- 常時記録機能

### 5. CLI ツール
- `ssm watch` - 監視モード
- `ssm stats` - 統計分析
- `ssm dashboard` - Webダッシュボード

### 6. セッション情報・比較
- セッション情報の表示
- 2つのセッションの比較
- セッションファイルの検証

### 7. アルゴリズム実行トレーサー
- 1行ごとの変数状態記録
- 可視化（アニメーション）
- トレースデータの保存・読み込み

## ⚠️ 複数ファイル使用時の注意事項

Python notebookで複数のファイルからインポートしたり、複数のファイルで同一変数名を使用する場合、変数名の衝突に注意してください。

- **変数名の衝突**: 複数のnotebookファイルから同じ`.ssm/`ディレクトリを使用する場合、同じ変数名が使われると衝突が発生する可能性があります
- **自動検出**: SSMは異なるファイルからのコミットを自動的に検出し、変数名の衝突を警告します
- **推奨**: ファイルごとに異なる変数名を使用するか、ファイル名をプレフィックスとして使用してください

詳細は [基本的な使い方](docs/getting-started.md#複数ファイル使用時の注意事項) を参照してください。

## 詳細なドキュメント

詳細な使い方は以下のドキュメントを参照してください：

- 🚀 [SSM - Git風セッション管理](docs/ssm-guide.md) - `.ssm/` ディレクトリベースの管理
- 💻 [CLI リファレンス](docs/cli-reference.md) - コマンドラインツールの使い方
- 📖 [基本的な使い方](docs/getting-started.md) - 保存・復元の詳細
- 📈 [アルゴリズムトレーサー](docs/algorithm-tracer.md) - トレース・可視化機能
- 🌐 [国際化（i18n）ガイド](docs/i18n-guide.md) - 多言語対応（日本語・英語）
- 📚 [APIリファレンス](docs/api-reference.md) - 全APIの詳細

## 使用例

### 機械学習ワークフロー

```python
from SessionSmith import ssm

# 初期化
ssm.init()

# データ準備
X_train, y_train = load_data()
model = create_model()

ssm.commit("Data loaded")

# モデル学習（長時間）
with ssm.checkpoint(interval=600) as cp:  # 10分ごと
    for epoch in range(100):
        for batch in dataloader:
            loss = model.train_step(batch)
        
        val_loss = validate(model)
        cp.step(epoch=epoch, loss=loss, val_loss=val_loss)
        
        print(f"Epoch {epoch}: loss={loss:.4f}")

# 学習完了時にコミット
ssm.commit("Training complete")

# バックアップをエクスポート
ssm.export("trained_model.pkl")
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

## Cursor/VSCode拡張機能

SessionSmithには、Cursor/VSCode用の拡張機能が用意されています。コードを書かずに、GUIからセッションの保存・復元が可能です。

### インストール

**Open VSX Registryから:**
1. Cursor/VSCodeでコマンドパレット（Cmd+Shift+P / Ctrl+Shift+P）を開く
2. `Extensions: Install Extension` を選択
3. `SessionSmith` を検索してインストール

または、以下のURLから直接インストール:
- https://open-vsx.org/extension/yut0takagi/sessionsmith

### 機能

- 🌳 **Session Graph（v0.2.0〜）**: `.ssm/` のコミット履歴を gitgraph 風に可視化。
  ブランチのレーン色分け、マージの分岐・合流、ブランチ/タグ/HEADバッジ、コミット詳細
  （変数一覧・署名状態）、GUI からの Checkout / Branch / Tag / Commit に対応
- 🗂 **Sessions ビュー（v0.2.0〜）**: アクティビティバーにブランチ・タグ・コミットのツリー表示
- ✅ **Save Session**: 現在のPythonセッション（変数）を保存
- ✅ **Load Session**: セッションファイルを選択して変数を復元
- ✅ **Show Session Info**: セッションファイルの情報を表示
- ✅ **Notebook対応**: Jupyter Notebookでセルを追加せずに実行
- ✅ **自動検出**: Pythonインタープリターを自動検出（仮想環境対応）

詳細は [extension/README.md](extension/README.md) を参照してください。

## ライセンス

MIT
