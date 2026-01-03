# 国際化（i18n）ガイド

SessionSmithは多言語対応（日本語・英語）をサポートしています。

## 言語設定

### 環境変数で設定

```bash
export SESSIONSMITH_LANG=ja  # 日本語
export SESSIONSMITH_LANG=en  # 英語
export SESSIONSMITH_LANG=auto  # 自動検出
```

### Python APIで設定

```python
from SessionSmith import set_language, Language

set_language('ja')  # 日本語
set_language('en')  # 英語
set_language('auto')  # 自動検出
```

SSMが初期化されている場合、設定は自動的に `.ssm/config` に保存されます。

## 現在の言語を確認

```python
from SessionSmith import get_language

lang = get_language()  # 'ja' または 'en'
```

## 使用例

```python
from SessionSmith import ssm, set_language, SSMNotInitializedError

set_language('ja')

try:
    ssm.commit("test")
except SSMNotInitializedError as e:
    print(e)
    # SSMが初期化されていません: '.'. 'ssm.init()' または 'ssm init' を先に実行してください。
```

## 翻訳関数の使用

独自のメッセージを翻訳する場合：

```python
from SessionSmith import translate

message = translate("info.session_saved", file_path="data.pkl", size=1024, format="pickle")
print(message)
```

## 自動検出

言語を `auto` に設定すると、システムのロケールから自動的に言語を検出します。

## 関連ドキュメント

- [API リファレンス](api-reference.md) - 詳細なAPI
