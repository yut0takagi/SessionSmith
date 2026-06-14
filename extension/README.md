# SessionSmith Extension for Cursor/VSCode

SessionSmithのCursor/VSCode拡張機能です。Jupyter NotebookやPythonファイルで、
変数を簡単に保存・復元できます。**v0.2.0 から gitgraph 風のセッショングラフ GUI** を搭載しました。

## 機能

- **🌳 Session Graph（NEW in v0.2.0）**: `.ssm/` のコミット履歴を gitgraph 風に可視化
  - ブランチをレーン色分け表示、マージコミットの分岐・合流を描画
  - ブランチ / タグ / HEAD のバッジ表示
  - コミットをクリックで詳細（変数一覧・型・サイズ・署名状態・親）を表示
  - GUI から **Checkout / Branch here / Tag here / Commit** を実行（Notebook/ターミナルに送信）
  - `.ssm/` の変更を監視して自動更新
- **🗂 Sessions ビュー（NEW in v0.2.0）**: アクティビティバーにブランチ・タグ・コミットのツリーを表示
- **Save Session**: 現在のPythonセッション（変数）を保存
- **Load Session**: セッションファイルを選択して変数を復元
- **Show Session Info**: セッションファイルの情報を表示
- **Notebook対応**: Jupyter Notebookでセルを追加せずに実行
- **自動検出**: Pythonインタープリターを自動検出（仮想環境対応）

## セッショングラフの使い方

1. Python 側で SSM を初期化・コミットしておく:
   ```python
   from SessionSmith import ssm
   ssm.init()
   ssm.commit("first snapshot")
   ```
2. アクティビティバーの **SessionSmith** アイコンを開く（または
   コマンドパレットで `SessionSmith: Open Session Graph`）
3. グラフ上のコミットをクリックすると右側に詳細が表示されます
4. 詳細パネルのボタンで Checkout / Branch / Tag、ツールバーの **＋ Commit** で
   現在のセッションをコミットできます

> グラフ表示は `.ssm/` を直接読むため、SessionSmith が未インストールでも閲覧できます。
> Checkout などの「実行」操作のみ Python（アクティブな Notebook かターミナル）に送信されます。

## 使い方

### Notebookでの使用

1. Jupyter Notebookを開く
2. 変数を定義:
   ```python
   x = 42
   y = "Hello"
   z = [1, 2, 3]
   ```
3. コマンドパレット（Cmd+Shift+P / Ctrl+Shift+P）を開く
4. `SessionSmith: Save Session` を選択
5. ファイル名を入力して保存

### Pythonファイルでの使用

1. Pythonファイルを開く
2. コマンドパレットから `SessionSmith: Save Session` を選択
3. ファイル名を入力して保存

### セッションの読み込み

1. コマンドパレットから `SessionSmith: Load Session` を選択
2. セッションファイル（.pkl, .json, .msgpack, .h5）を選択
3. 変数が復元されます

## 要件

- SessionSmithがインストールされている必要があります
  ```bash
  pip install SessionSmith
  ```

## サポート形式

- **Pickle** (.pkl) - デフォルト、すべてのPythonオブジェクトに対応
- **JSON** (.json) - 可読性が高く、他の言語でも利用可能
- **MessagePack** (.msgpack) - 高速でコンパクト
- **HDF5** (.h5) - 大規模データに適している

## 開発

```bash
cd extension
npm install
npm run compile
```

F5キーで拡張機能をデバッグ実行できます。

## ライセンス

MIT License

## リポジトリ

https://github.com/yut0takagi/SessionSmith

