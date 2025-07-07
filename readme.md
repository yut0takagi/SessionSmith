
# SessionSmith

**SessionSmith** は、Jupyter Notebook や Python 実行時のセッション（変数・オブジェクト）を簡単に保存・復元できる軽量ライブラリです。

## 特徴

- `dill` を使ってシームレスにセッション保存
- たった2行で保存＆復元
- 簡単＆高速

## インストール

```bash
pip install SessionSmith
```

## 使い方

```python
from session_smith import save_session, load_session

# セッション保存
save_session("my_session.dill")

# セッション復元
load_session("my_session.dill")
```

## ライセンス

MIT

