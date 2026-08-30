# Change Log

## [0.3.1] - 2026-08-30

### Fixed

- **大文字小文字違いの参照名で安全ガードを迂回し、現在のブランチを削除できてしまう問題を修正 (#62)**
  - ブランチ/タグの存在確認に `fs.existsSync()` を使っていたため、macOS（APFS の既定）と
    Windows では `branches/feature` しか無いのに `FEATURE` が「存在する」と判定されていた
  - `deleteRef` の「現在のブランチは削除できません」ガードは `cfg.current_branch === name` の
    文字列比較なので `'feature' !== 'FEATURE'` で素通りし、**実体の `feature` が
    `FEATURE.bak` に退避されてブランチが消えていた**
  - `renameRef` も同様で、リネームしても `current_branch` が更新されず、存在しないブランチを
    指した壊れた状態になっていた
  - 存在確認をディレクトリ列挙 + 厳密比較に変更（`refExists()`）。
    リネーム先が既存参照と大文字小文字だけ異なる場合も明示的に拒否する
- **`isValidRefName()` を Python 側の `validate_ref_name()` と再同期**
  - SessionSmith 本体 v2.3.0 で追加された規則が拡張側に反映されていなかった
  - Windows の予約デバイス名（`CON` / `PRN` / `AUX` / `NUL` / `COM1`〜`COM9` /
    `LPT1`〜`LPT9`。拡張子付きも同様）と、末尾が `.` の名前を拒否するようにした

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
- サイドバー表示: アクティビティバーの SessionSmith パネルに Session Graph（webview ビュー）を追加。幅に応じて詳細ペインを縦積み。Sessions ツリーと併存。

### Changed
- webview を TypeScript 化し esbuild でバンドル、レンダラをモジュール分割
- 純ロジック（layout / search / ssmReader / ssmRefs）に `node:test` のユニットテストを追加

## [0.2.0]

### Added
- gitgraph 風の Session Graph GUI、アクティビティバーの Sessions ツリー
