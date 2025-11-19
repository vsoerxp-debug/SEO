# 🚀 Streamlit Community Cloud デプロイ手順書

## ⚠️ **重要: デプロイ時の必須対応事項**

Streamlit Community CloudにデプロイするSEOチャットボットは、以下の**重大な構造的問題**があります：

### 🔴 **問題: VectorDBが正しく機能しない**

#### 原因
1. **`vector_db/seo_knowledge/`はローカルで作成されたDB** → クラウドにそのままアップロードしても機能しない
2. **`data/`フォルダのPDF/DOCXファイルを読み込んでDBを再構築する必要がある**
3. **zipファイルは自動展開されない**

---

## ✅ **正しいデプロイ手順**

### Step 1: 必要なファイルをアップロード

以下のファイル・フォルダをStreamlit Community Cloudにアップロード：

```
SEO_Chatbot/
├── main.py
├── initialize.py
├── utils.py
├── components.py
├── constants.py
├── domain_analyzer.py
├── requirements.txt
├── .gitignore
├── .streamlit/
│   └── config.toml
├── data/                    ← ⚠️ 展開済みフォルダ（zipではない）
│   ├── SEO1-1 モバイルSEO.pdf
│   ├── SEO1-11 生成AIを使ったSEO.pdf
│   ├── ... (全21ファイル)
│   └── feeds/
│       └── rss_sources.csv
├── vector_db/               ← ⚠️ 空フォルダでOK（自動生成される）
│   └── db_version.txt
└── logs/                    ← ⚠️ 空フォルダでOK
```

### Step 2: 環境変数を設定

Streamlit Community Cloudの「Settings」→「Secrets」で以下を設定：

```toml
OPENAI_API_KEY = "sk-proj-xxxxx..."
LANGSMITH_TRACING = "true"
LANGSMITH_API_KEY = "lsv2_pt_xxxxx..."
USER_AGENT = "Enhanced-RAG-System/1.0.0"
```

### Step 3: **初回起動時にDBを強制再構築**

デプロイ後、初回起動時に以下のいずれかの方法でDBを再構築：

#### 方法A: `vector_db/db_version.txt`を削除してデプロイ

- `vector_db/db_version.txt`を削除またはリネーム
- これにより`check_persistent_db_exists()`が`False`を返し、新規DB作成される

#### 方法B: 強制再構築フラグを追加（推奨）

`initialize.py`の`initialize_retriever()`関数を修正：

```python
# Step 1: 永続化DBの存在確認
db_exists, db_status_reason = check_persistent_db_exists()
logger.info(f"永続化DB確認結果: {db_status_reason}")

# ⚠️ Streamlit Cloudデプロイ時は強制的に再構築
FORCE_REBUILD = os.getenv("FORCE_REBUILD_DB", "false").lower() == "true"
if FORCE_REBUILD:
    logger.warning("環境変数FORCE_REBUILD_DB=trueのため、DBを強制再構築します")
    db_exists = False
```

Streamlit Community Cloudの「Secrets」に追加：
```toml
FORCE_REBUILD_DB = "true"
```

初回起動後、この設定を削除すれば次回から既存DBを使用します。

---

## 🔍 **デプロイ後の確認方法**

### 1. ログの確認

Streamlit Community Cloudの「Manage app」→「Logs」で以下を確認：

```
永続化DB確認結果: ...
新規永続化DBを作成します
処理対象文書: 21件, 合計文字数: ...
```

### 2. SEO質問モードのテスト

アプリ起動後、以下の質問を試す：

- 「サイテーションとは？」
- 「メインページの推奨文字数は？」
- 「内部リンクの重要性は？」

✅ 正常に回答が返ってくれば成功

---

## ❌ **よくあるエラーと対処法**

### エラー1: 「SEO関連資料からの情報取得に失敗しました」

**原因**: VectorDBが空または存在しない

**対処法**:
1. `logs/application.log`で「処理対象文書: 0件」になっていないか確認
2. `data/`フォルダが正しくアップロードされているか確認
3. `FORCE_REBUILD_DB=true`を設定して再デプロイ

### エラー2: 「OpenAI API Keyが設定されていません」

**原因**: 環境変数が設定されていない

**対処法**:
Streamlit Community CloudのSecretsに`OPENAI_API_KEY`を設定

### エラー3: 「ModuleNotFoundError」

**原因**: `requirements.txt`の依存パッケージがインストールされていない

**対処法**:
`requirements.txt`がアップロードされているか確認

---

## 📊 **デプロイ前チェックリスト**

- [ ] `data/`フォルダが展開済み（zipではない）
- [ ] 全21個のPDF/DOCXファイルが`data/`に存在
- [ ] `requirements.txt`がアップロード済み
- [ ] `.streamlit/config.toml`がアップロード済み
- [ ] Streamlit SecretsにAPIキーを設定
- [ ] `FORCE_REBUILD_DB=true`を設定（初回のみ）
- [ ] `vector_db/db_version.txt`を削除（方法Aの場合）

---

## 🛠 **デプロイ後の初回セットアップ時間**

- **通常**: 3～5分（21個のPDF/DOCX読み込み + Embedding生成）
- **大量データ**: 10～15分

初回起動後、2回目以降は既存DBを使用するため数秒で起動します。
