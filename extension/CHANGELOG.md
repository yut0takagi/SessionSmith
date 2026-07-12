# Change Log

## [0.3.0] - 2026-07-12

### Added
- Session Graph の全面刷新（洗練3ゾーンレイアウト）
- ズーム / パン（Ctrl/Cmd+ホイール・ドラッグ・Fit・1:1・キーボード）
- 横断検索（メッセージ / ハッシュ / author / 変数名）とハイライト・dim
- GUI からの **merge**（QuickPick でブランチ選択）
- ブランチ / タグの **削除・リネーム**（`.ssm` の参照ファイルを直接操作、Python 不要・`.bak` 退避）
- リサイズ可能な詳細ペイン（幅を永続化）
- 空状態オンボーディング（`ssm.init()` のコピー、コミット0件ガイド）、reduced-motion 対応
- 拡張アイコン（icon.png）

### Changed
- webview を TypeScript 化し esbuild でバンドル、レンダラをモジュール分割
- 純ロジック（layout / search / ssmReader / ssmRefs）に `node:test` のユニットテストを追加

## [0.2.0]

### Added
- gitgraph 風の Session Graph GUI、アクティビティバーの Sessions ツリー
