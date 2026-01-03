# Homebrew Formula for SessionSmith

このディレクトリには、HomebrewでSessionSmithをインストールするためのFormulaが含まれています。

## インストール方法

### 方法1: GitHubリポジトリから直接インストール

```bash
brew install yut0takagi/SessionSmith/sessionsmith
```

### 方法2: ローカルファイルからインストール

```bash
# リポジトリをクローンした後
cd SessionSmith
brew install --build-from-source ./Formula/sessionsmith.rb
```

## 更新方法

新しいバージョンをリリースする際は、タグを作成してプッシュするだけです：

```bash
git tag v0.1.9
git push origin v0.1.9
```

GitHub Actionsが自動的に以下を実行します：
1. リリースアーカイブのSHA256を計算
2. `Formula/sessionsmith.rb` の `url` と `sha256` を自動更新
3. 変更をコミットしてプッシュ

### 手動で更新する場合

GitHub Actionsが動作しない場合や、手動で更新したい場合：

1. SHA256を計算：
   ```bash
   shasum -a 256 <(curl -L https://github.com/yut0takagi/SessionSmith/archive/refs/tags/v0.1.9.tar.gz)
   ```

2. `Formula/sessionsmith.rb` の `url` と `sha256` を更新

3. 変更をコミットしてプッシュ

## テスト

```bash
# Formulaの構文チェック
brew audit --strict ./Formula/sessionsmith.rb

# インストールテスト
brew install --build-from-source ./Formula/sessionsmith.rb
brew test sessionsmith
```

