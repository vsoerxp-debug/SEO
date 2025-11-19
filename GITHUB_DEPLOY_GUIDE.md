# GitHub & Streamlit Cloud デプロイガイド

## 🔴 重要: ChromaDB (vector_db) をGitHubにアップロードしない理由

### 問題の原因

**❌ ローカルのvector_db/をGitHubにアップロードすると:**
1. ローカル環境で作成されたChromaDBファイルが含まれる
2. Streamlit Cloud上でこのファイルを読み込むと、環境の違いにより動作しない
3. 結果: 「SEO関連資料からの情報取得に失敗しました」エラー

**✅ vector_db/を除外すると:**
1. Streamlit Cloud上で初回起動時に新規作成される
2. クラウド環境に最適化されたDBが生成される
3. 正常に動作する

---

## 📦 GitHubにアップロードするファイル・フォルダ

### ✅ 必須ファイル（必ずアップロード）

#### Pythonコアファイル
```
main.py                  # メインアプリケーション
initialize.py            # RAGシステム初期化
utils.py                 # ユーティリティ関数
components.py            # UIコンポーネント
constants.py             # 定数定義
domain_analyzer.py       # ドメイン分析機能
```

#### 設定ファイル
```
requirements.txt         # Pythonパッケージ依存関係
.gitignore              # Git除外設定
.streamlit/
  └── config.toml       # Streamlit設定
```

#### データフォルダ（最重要）
```
data/                    # SEO資料フォルダ（全体）
  ├── SEO1-1 モバイルSEO.pdf
  ├── SEO1-2 コンテンツSEO.pdf
  ├── ... (全21ファイル)
  └── feeds/
      └── rss_sources.csv
```

#### ドキュメント
```
README.md                # プロジェクト説明
CHECKLIST.md            # チェックリスト
DEPLOY_INSTRUCTIONS.md  # デプロイ手順書
.env.example            # 環境変数のテンプレート
```

---

### ❌ アップロードしないファイル・フォルダ（.gitignoreで除外済み）

#### ChromaDB / Vector Database
```
vector_db/              # 🚨 絶対にアップロードしない
  ├── db_version.txt
  ├── seo_knowledge/
  │   ├── chroma.sqlite3
  │   └── ...
  └── ...
```

**理由:** Streamlit Cloud上で自動生成されるため、ローカルのDBは不要

#### ログファイル
```
logs/                   # ログファイル（クラウド上で自動生成）
  └── application.log.*
```

#### 環境変数
```
.env                    # 🚨 絶対にアップロードしない（API Keyが含まれる）
```

**理由:** Streamlit Cloud Secretsで設定するため

#### 仮想環境
```
env/                    # Python仮想環境
venv/
__pycache__/           # Pythonキャッシュ
*.pyc
```

#### テスト・デバッグファイル
```
test_*.py              # テストスクリプト
debug_*.py             # デバッグツール
inspect_*.py
investigate_*.py
check_*.py
backup_*.py
```

**理由:** 開発用ファイル、デプロイ不要

#### ドキュメント（開発用）
```
IMPLEMENTATION_REPORT*.md
PHASE*.md
improvements_*.md
高精度RAG導入ガイド.md
FIX_DEPLOYMENT_ISSUE.md
```

**理由:** 開発記録、デプロイ不要

#### その他
```
base/                   # 旧バージョン
SEO/                    # 別プロジェクト
.triton_cache/         # キャッシュ
#役割：*.txt            # メモファイル
```

---

## 🚀 GitHub → Streamlit Cloud デプロイ手順

### Step 1: .gitignoreの確認

現在の `.gitignore` ファイルには以下が追加されています：

```gitignore
# ChromaDB / Vector Database
# 🚨 重要: vector_db フォルダはGitにアップロードしない
vector_db/
*.db
*.sqlite3
*.sqlite3-journal
.chroma/

# ログファイル
logs/
*.log

# テスト用ファイル
test_*.py
check_*.py
debug_*.py
# ... など
```

✅ **この設定により、vector_db/ は自動的に除外されます**

---

### Step 2: GitHubリポジトリの準備

#### 2-1. 既存のvector_db/を削除（Git管理から）

既にGitにコミット済みの場合、以下のコマンドで削除：

```bash
# Git管理から削除（ローカルファイルは残す）
git rm -r --cached vector_db/
git rm -r --cached logs/
git rm --cached .env

# コミット
git add .gitignore
git commit -m "Remove vector_db and logs from Git tracking"
```

#### 2-2. 必要なファイルをコミット

```bash
# ステータス確認（vector_db/がUntracked filesに表示されればOK）
git status

# 必要なファイルをステージング
git add main.py initialize.py utils.py components.py constants.py domain_analyzer.py
git add requirements.txt .gitignore .streamlit/config.toml
git add data/
git add README.md CHECKLIST.md DEPLOY_INSTRUCTIONS.md .env.example

# コミット
git commit -m "Prepare for Streamlit Cloud deployment"

# GitHubにプッシュ
git push origin main
```

---

### Step 3: Streamlit Community Cloud デプロイ

#### 3-1. Streamlit Cloudで新規アプリ作成

1. https://share.streamlit.io/ にアクセス
2. **New app** をクリック
3. GitHubリポジトリを選択
4. メインファイル: `main.py`
5. **Deploy** をクリック

#### 3-2. Secrets設定（必須）

**Settings → Secrets** で以下を設定：

```toml
# OpenAI API Key（必須）
OPENAI_API_KEY = "sk-proj-xxxxxxxxxxxxxxxxxxxxx"

# 初回デプロイ時のみ（必須）
FORCE_REBUILD_DB = "true"

# LangSmith（オプション）
LANGSMITH_API_KEY = "your_langsmith_key"
LANGSMITH_PROJECT = "your_project_name"
LANGCHAIN_TRACING_V2 = "true"
LANGCHAIN_ENDPOINT = "https://api.smith.langchain.com"

# User Agent（オプション）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

⚠️ **重要:** `FORCE_REBUILD_DB = "true"` を設定することで、初回起動時に空のvector_db/に対してデータを自動投入します

---

### Step 4: 初回起動の確認

#### 4-1. ログの監視

**Settings → Logs** を開き、以下のメッセージを確認：

```
永続化DB確認結果: DBが存在しません
⚠️ 環境変数 FORCE_REBUILD_DB=true が設定されているため、VectorDBを強制再構築します
新規永続化DBを作成します
処理対象文書: 21件, 合計文字数: 500,000+, 推定トークン数: 125,000+
標準処理：チャンクサイズ500、バッチサイズ50
...
永続化DBロード成功: 1件のテスト検索結果
```

✅ **「処理対象文書: 21件」が表示されればOK**

⏱️ **初回起動は3～15分かかります** - タイムアウトしても正常です。再起動すると完成したDBを読み込みます。

#### 4-2. 動作テスト

アプリが起動したら、以下をテスト：

1. **SEO質問モード**を選択
2. 入力: `サイテーションとは？`
3. **期待される結果:** SEO資料からの詳細な回答

❌ **「SEO関連資料からの情報取得に失敗しました」が表示されなければ成功！**

---

### Step 5: 初回起動後の設定変更

✅ 動作確認が完了したら、**FORCE_REBUILD_DB を削除または false に変更**

**Settings → Secrets:**
```toml
OPENAI_API_KEY = "sk-proj-xxxxxxxxxxxxxxxxxxxxx"
# FORCE_REBUILD_DB = "false"  ← この行を削除 or false に変更
```

**理由:** 毎回DBを再構築すると起動が遅くなるため

---

## 🔧 トラブルシューティング

### エラー1: 「SEO関連資料からの情報取得に失敗しました」

**原因:**
- vector_db/がGitにコミットされている
- FORCE_REBUILD_DB が設定されていない
- data/ フォルダが空

**解決方法:**
```bash
# Step 1: vector_db/をGit管理から削除
git rm -r --cached vector_db/
git commit -m "Remove vector_db from Git"
git push

# Step 2: Streamlit Cloud Secretsで設定
FORCE_REBUILD_DB = "true"

# Step 3: アプリを再起動（Settings → Reboot app）
```

---

### エラー2: 「処理対象文書: 0件」と表示される

**原因:** data/ フォルダが空、またはファイルがアップロードされていない

**解決方法:**
```bash
# data/ フォルダの確認
ls data/

# 全21ファイルが存在することを確認
git add data/
git commit -m "Add SEO data files"
git push
```

---

### エラー3: タイムアウトエラー

**原因:** 初回起動時のDB構築に時間がかかる（正常な動作）

**解決方法:**
1. ログで「永続化DBロード成功」を確認
2. 数分待ってから **Settings → Reboot app** で再起動
3. 2回目以降は既存DBを読み込むため高速起動

---

### エラー4: ModuleNotFoundError

**原因:** requirements.txt が正しくアップロードされていない

**解決方法:**
```bash
# requirements.txt の確認
cat requirements.txt

# GitHubにプッシュ
git add requirements.txt
git commit -m "Update requirements.txt"
git push
```

---

## 📋 デプロイ前チェックリスト

### ローカル環境での確認

- [ ] `.gitignore` に `vector_db/` が含まれている
- [ ] `.gitignore` に `.env` が含まれている
- [ ] `data/` フォルダに21個のPDF/DOCXファイルが存在
- [ ] `requirements.txt` が最新
- [ ] `.env.example` が存在（参考用）

### Git管理の確認

```bash
# 確認コマンド
git status

# vector_db/ がUntracked filesに表示されればOK
# .env がUntracked filesに表示されればOK
```

- [ ] `vector_db/` がGit管理外（Untracked）
- [ ] `.env` がGit管理外（Untracked）
- [ ] `data/` フォルダがGit管理対象
- [ ] すべてのPythonファイルがコミット済み

### GitHubリポジトリの確認

- [ ] GitHubに `vector_db/` フォルダが存在しない
- [ ] GitHubに `.env` ファイルが存在しない
- [ ] GitHubに `data/` フォルダが存在する
- [ ] 全21個のSEOファイルがGitHub上で確認できる

### Streamlit Cloud設定の確認

- [ ] `OPENAI_API_KEY` が設定されている
- [ ] `FORCE_REBUILD_DB = "true"` が設定されている（初回のみ）
- [ ] メインファイルが `main.py` に設定されている

---

## 🎯 重要なポイントまとめ

### ✅ やるべきこと

1. **vector_db/ をGit管理から除外**
   ```bash
   git rm -r --cached vector_db/
   ```

2. **data/ フォルダは必ずアップロード**
   ```bash
   git add data/
   ```

3. **Streamlit Secrets で FORCE_REBUILD_DB=true を設定**
   - 初回起動時のみ
   - 動作確認後は false に変更

### ❌ やってはいけないこと

1. **vector_db/ をGitにコミットしない**
   - ローカルDBをアップロードすると動作不良
   
2. **.env をGitにコミットしない**
   - API Keyが漏洩する危険性
   
3. **初回起動時に FORCE_REBUILD_DB を設定しない**
   - 空のDBのまま起動してしまう

---

## 📚 参考資料

- [DEPLOY_INSTRUCTIONS.md](./DEPLOY_INSTRUCTIONS.md) - 詳細なデプロイ手順
- [.env.example](./.env.example) - 環境変数のテンプレート
- [README.md](./README.md) - プロジェクト概要

---

## 🆘 サポート

問題が解決しない場合は、以下を確認してください：

1. **Streamlit Cloud Logs** - エラーメッセージの詳細
2. **GitHub Repository** - vector_db/ が含まれていないか
3. **Secrets設定** - OPENAI_API_KEY と FORCE_REBUILD_DB の値

---

**最終更新: 2025年11月19日**
