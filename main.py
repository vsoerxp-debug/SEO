"""
このファイルは、Webアプリのメイン処理が記述されたファイルです。
"""

############################################################
# 1. ライブラリの読み込み
############################################################
# 環境変数を扱うためのモジュール
import os
# 「.env」ファイルから環境変数を読み込むための関数
from dotenv import load_dotenv
# ログ出力を行うためのモジュール
import logging
# streamlitアプリの表示を担当するモジュール
import streamlit as st
# 時刻関連のモジュール
import time
# （自作）画面表示以外の様々な関数が定義されているモジュール
import utils
# （自作）アプリ起動時に実行される初期化処理が記述された関数
from initialize import initialize
# （自作）画面表示系の関数が定義されているモジュール
import components as cp
# （自作）変数（定数）がまとめて定義・管理されているモジュール
import constants as ct
# （自作）サジェストキーワード取得モジュール
import suggest_keywords as sk
# （自作）練習問題モジュール
import practice_questions as pq


############################################################
# 2. 設定関連
############################################################
# ブラウザタブの表示文言を設定
st.set_page_config(
    page_title=ct.APP_NAME
)

# Chrome翻訳対策: HTMLメタタグで翻訳を無効化
st.markdown(
    """
    <meta name="google" content="notranslate">
    <meta http-equiv="Content-Language" content="ja">
    """,
    unsafe_allow_html=True
)

# ログ出力を行うためのロガーの設定
logger = logging.getLogger(ct.LOGGER_NAME)


############################################################
# 3. 初期化処理
############################################################
try:
    # 初期化処理（「initialize.py」の「initialize」関数を実行）
    initialize()
except Exception as e:
    # エラーログの出力
    logger.error(f"{ct.INITIALIZE_ERROR_MESSAGE}\n{e}")
    # エラーメッセージの画面表示
    st.error(utils.build_error_message(ct.INITIALIZE_ERROR_MESSAGE), icon=ct.ERROR_ICON)
    # 後続の処理を中断
    st.stop()

# アプリ起動時のログファイルへの出力
if not "initialized" in st.session_state:
    st.session_state.initialized = True
    logger.info(ct.APP_BOOT_MESSAGE)


############################################################
# 3-1. モード切り替え時のセッション状態リセット
############################################################
# モード切り替え検出用の前回モード記録
if "previous_mode" not in st.session_state:
    st.session_state.previous_mode = None


############################################################
# 4. Basic認証チェック
############################################################
def check_authentication():
    """
    Basic認証のチェックを行う関数
    認証情報は.envファイルから取得
    """
    # 認証状態の初期化
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # 未認証の場合はログイン画面を表示
    if not st.session_state.authenticated:
        # 環境変数から認証情報を取得（デフォルト値あり）
        correct_username = os.getenv("AUTH_USERNAME", "seo_team")
        correct_password = os.getenv("AUTH_PASSWORD", "seo2025pass")
        
        # ログイン画面の表示
        st.markdown(ct.AUTH_LOGIN_TITLE)
        st.markdown("社内SEO検索アプリへのアクセスには認証が必要です。")
        
        # 入力フォーム
        username = st.text_input(ct.AUTH_USERNAME_LABEL, key="auth_username")
        password = st.text_input(ct.AUTH_PASSWORD_LABEL, type="password", key="auth_password")
        
        # ログインボタン
        if st.button(ct.AUTH_LOGIN_BUTTON):
            # 認証チェック
            if username == correct_username and password == correct_password:
                st.session_state.authenticated = True
                logger.info(f"認証成功: ユーザー名={username}")
                st.success(ct.AUTH_SUCCESS_MESSAGE)
                st.rerun()
            else:
                logger.warning(f"認証失敗: ユーザー名={username}")
                st.error(ct.AUTH_ERROR_MESSAGE, icon=ct.ERROR_ICON)
        
        # 未認証の場合は以降の処理を中断
        st.stop()

# 認証チェックの実行
try:
    check_authentication()
except Exception as e:
    # 認証処理でエラーが発生した場合
    logger.error(f"認証処理エラー: {e}")
    st.error("認証処理でエラーが発生しました。システム管理者にお問い合わせください。", icon=ct.ERROR_ICON)
    st.stop()


############################################################
# 5. Chrome自動翻訳対策・フォント設定（日本語表示改善）
############################################################
try:
    # Chrome自動翻訳対策とフォント設定（日本語表示改善）
    st.markdown(
        """
        <script>
        // HTML言語属性の設定
        document.documentElement.setAttribute('lang', 'ja');
        document.documentElement.setAttribute('xml:lang', 'ja');
        
        // Chrome自動翻訳無効化の追加対策
        document.head.insertAdjacentHTML('beforeend', '<meta name="google" content="notranslate">');
        document.head.insertAdjacentHTML('beforeend', '<meta name="robots" content="notranslate">');
        
        // body要素にも日本語属性を設定
        document.addEventListener('DOMContentLoaded', function() {
            document.body.setAttribute('lang', 'ja');
            document.body.classList.add('notranslate');
            
            // Streamlitの主要コンテンツ要素にも適用
            const mainElements = document.querySelectorAll('[data-testid="stApp"], .main, .stApp');
            mainElements.forEach(function(element) {
                element.setAttribute('lang', 'ja');
                element.classList.add('notranslate');
            });
            
            // チャットメッセージ要素にも適用（動的に追加される要素対応）
            const observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'childList') {
                        const chatElements = document.querySelectorAll('[data-testid="chatAvatarIcon-assistant"], [data-testid="chatAvatarIcon-user"], .stChatMessage');
                        chatElements.forEach(function(element) {
                            element.setAttribute('lang', 'ja');
                            element.classList.add('notranslate');
                        });
                    }
                });
            });
            observer.observe(document.body, { childList: true, subtree: true });
        });
        </script>
        <style>
        html, body, [class*="css"] {
            font-family: "Yu Gothic UI", "Meiryo", "Noto Sans JP", sans-serif !important;
        }
        
        /* Chrome自動翻訳対策CSS */
        .notranslate {
            -webkit-transform: none;
            transform: none;
        }
        
        /* 特定の要素に翻訳無効化を強制適用 */
        [data-testid="stChatMessage"], 
        [data-testid="stMarkdown"], 
        .stChatMessage,
        .element-container {
            translate: no !important;
        }
        </style>
        <meta name="google" content="notranslate">
        <meta name="robots" content="notranslate">
        """,
        unsafe_allow_html=True
    )
except Exception as e:
    # Chrome自動翻訳対策・フォント設定エラーはアプリ動作に影響しないため、ログ出力のみ
    logger.warning(f"Chrome自動翻訳対策・フォント設定でエラーが発生しましたが、アプリは継続します: {e}")


############################################################
# 6. モード選択（サイドバー）
############################################################
with st.sidebar:
    # ============================================
    # 【情報範囲の明示】RSS無効化対応
    # ============================================
    st.markdown("### 📘 本システムの情報範囲")
    st.info("""
**このチャットボットは以下の情報を基礎として回答を生成しています:**

**SEO検定公式テキスト（2025・2026年版）**  
  ※収録内容は **2024年8月時点** のSEO情報に基づいています。

最新情報が必要な場合は [Google Search Central Blog](https://developers.google.com/search/blog)などをご確認ください。
""")
    st.markdown("---")
    
    st.markdown("### 🔧 モード選択")
    mode = st.radio(
        "操作モードを選択してください",
        (ct.MODE_SEO_QUESTION, ct.MODE_DOMAIN_ANALYSIS, ct.MODE_SUGGEST_KEYWORDS, ct.MODE_PRACTICE_QUESTIONS),
        index=0,
        help="SEO質問モード：社内資料を活用したSEO相談(2024年8月時点)\n\nドメインSEO解析モード：指定ドメインの自動SEO解析\n\nサジェストキーワード調査モード：2つのキーワードからサジェスト取得\n\nSEO検定練習問題モード：AI生成の練習問題で学習"
    )
    
    # モード切り替え検出とセッション状態リセット
    if st.session_state.previous_mode is not None and st.session_state.previous_mode != mode:
        # 練習問題モード専用の状態をリセット
        keys_to_delete = [key for key in st.session_state.keys() if key.startswith("practice_")]
        for key in keys_to_delete:
            del st.session_state[key]
        logger.info(f"[モード切替] {st.session_state.previous_mode} → {mode}: 練習問題状態をリセット")
    
    st.session_state.previous_mode = mode
    
    st.markdown("---")
    st.markdown("### 🔧 システム管理")
    if st.button("🗑️ キャッシュクリア", help="入力文字の誤変換や表示不具合を解決"):
        # セッション状態をクリア
        for key in list(st.session_state.keys()):
            if key not in ['retriever', 'initialized', 'authenticated']:  # 認証状態も保持
                del st.session_state[key]
        st.success("✅ キャッシュをクリアしました")
        st.rerun()


############################################################
# 7. SEO質問モードの表示
############################################################
if mode == ct.MODE_SEO_QUESTION:
    # タイトル表示
    cp.display_app_title()

    # 簡潔なSEO検索説明
    cp.display_simple_seo_interface()

    # AIメッセージの初期表示（SEO版）
    cp.display_initial_seo_message()


    ############################################################
    # 7-1. 会話ログの表示（SEO質問モード）
    ############################################################
    try:
        # 会話ログの表示
        cp.display_conversation_log()
    except Exception as e:
        # エラーログの出力
        logger.error(f"{ct.CONVERSATION_LOG_ERROR_MESSAGE}\n{e}")
        # エラーメッセージの画面表示
        st.error(utils.build_error_message(ct.CONVERSATION_LOG_ERROR_MESSAGE), icon=ct.ERROR_ICON)
        # 後続の処理を中断
        st.stop()


    ############################################################
    # 7-2. チャット入力の受け付け（SEO質問モード）
    ############################################################
    chat_message = st.chat_input(ct.CHAT_INPUT_HELPER_TEXT)


    ############################################################
    # 7-3. チャット送信時の処理（SEO質問モード）
    ############################################################
    if chat_message:
        # ==========================================
        # 7-3-1. ユーザーメッセージの表示
        # ==========================================
        # ユーザーメッセージのログ出力（SEO特化版）
        logger.info({"message": chat_message, "application_mode": "SEO_SEARCH"})

        # ユーザーメッセージを表示
        with st.chat_message("user"):
            st.markdown(chat_message)

        # ==========================================
        # 7-3-2. LLMからの回答取得
        # ==========================================
        # 「st.spinner」でグルグル回っている間、表示の不具合が発生しないよう空のエリアを表示
        res_box = st.empty()
        # LLMによる回答生成（回答生成が完了するまでグルグル回す）
        with st.spinner(ct.SPINNER_TEXT):
            try:
                # 画面読み込み時に作成したRetrieverを使い、Chainを実行
                llm_response = utils.get_llm_response(chat_message)
            except Exception as e:
                # エラーログの出力
                logger.error(f"{ct.GET_LLM_RESPONSE_ERROR_MESSAGE}\n{e}")
                # エラーメッセージの画面表示
                st.error(utils.build_error_message(ct.GET_LLM_RESPONSE_ERROR_MESSAGE), icon=ct.ERROR_ICON)
                # 後続の処理を中断
                st.stop()
        
        # ==========================================
        # 7-3-3. LLMからのSEO回答表示（簡素化版）
        # ==========================================
        with st.chat_message("assistant"):
            try:
                # 統一フォーマットでの表示判定
                if llm_response.get("unified_display", False):
                    # 非SEO応答の統一表示
                    cp.display_unified_seo_content(llm_response["answer"])
                    content = llm_response["answer"]
                else:
                    # SEO特化の回答表示(統一フォーマット使用)
                    content = cp.display_seo_response(llm_response)
                    
                    # 情報源注釈の追加(SEO質問モードのみ)
                    info_notice = "\n\n---\n\n📌 **情報源について**  \n※本回答は **SEO検定公式テキスト(2025・2026年版：2024年8月時点の情報)** に基づいています。"
                    st.markdown(info_notice)
                
                # AIメッセージのログ出力
                logger.info({"message": content, "seo_query": chat_message})
            except Exception as e:
                # エラーログの出力
                logger.error(f"{ct.DISP_ANSWER_ERROR_MESSAGE}\n{e}")
                # エラーメッセージの画面表示
                st.error(utils.build_error_message(ct.DISP_ANSWER_ERROR_MESSAGE), icon=ct.ERROR_ICON)
                # 後続の処理を中断
                st.stop()

        # ==========================================
        # 7-3-4. 会話ログへの追加
        # ==========================================
        # 表示用の会話ログにユーザーメッセージを追加
        st.session_state.messages.append({"role": "user", "content": chat_message})
        # 表示用の会話ログにAIメッセージを追加
        st.session_state.messages.append({"role": "assistant", "content": content})


############################################################
# 8. ドメインSEO解析モードの表示
############################################################
elif mode == ct.MODE_DOMAIN_ANALYSIS:
    # ドメイン解析インターフェースの表示（準備中画面）
    cp.display_domain_analysis_interface()


############################################################
# 9. サジェストキーワード調査モードの表示
############################################################
elif mode == ct.MODE_SUGGEST_KEYWORDS:
    # タイトル表示
    st.markdown(f"## {ct.SUGGEST_MODE_TITLE}")
    st.markdown(ct.SUGGEST_MODE_DESCRIPTION)
    st.markdown("---")
    
    # キーワード入力フォーム（2カラムレイアウト）
    col1, col2 = st.columns(2)
    
    with col1:
        keyword1 = st.text_input(
            ct.SUGGEST_KEYWORD1_LABEL,
            placeholder=ct.SUGGEST_KEYWORD1_PLACEHOLDER,
            key="suggest_keyword1",
            help="1つ目のメインキーワードを入力してください"
        )
    
    with col2:
        keyword2 = st.text_input(
            ct.SUGGEST_KEYWORD2_LABEL,
            placeholder=ct.SUGGEST_KEYWORD2_PLACEHOLDER,
            key="suggest_keyword2",
            help="2つ目のメインキーワードを入力してください"
        )
    
    # 検索ボタン
    if st.button(ct.SUGGEST_SEARCH_BUTTON, type="primary", use_container_width=True):
        # バリデーション
        is_valid, error_message = sk.validate_keywords(keyword1, keyword2)
        
        if not is_valid:
            st.error(error_message, icon=ct.ERROR_ICON)
            st.stop()
        
        # サジェスト取得
        try:
            with st.spinner(ct.SUGGEST_SEARCHING_MESSAGE):
                # サジェスト取得実行（Google → Bingフォールバック付き）
                results = sk.fetch_combined_suggests(keyword1, keyword2)
                
                # 結果のフォーマット（画面表示用：Markdown）
                formatted_output = sk.format_suggest_results(results, keyword1, keyword2)
                
                # 結果のフォーマット（ダウンロード用：CSV）
                csv_output = sk.format_suggest_results_to_csv(results, keyword1, keyword2)
                
                # ログ出力
                logger.info(f"サジェスト取得成功: keyword1='{keyword1}', keyword2='{keyword2}'")
            
            # 成功メッセージ
            st.success(ct.SUGGEST_SUCCESS_MESSAGE)
            
            # 結果表示
            st.markdown(formatted_output)
            
            # ダウンロードボタン（CSV形式）
            st.markdown("---")
            st.download_button(
                label="📥 結果をダウンロード (CSV形式)",
                data=csv_output,
                file_name=f"suggest_keywords_{keyword1}_{keyword2}_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                help="調査結果をCSV形式でダウンロードできます（Excel対応）"
            )
            
        except Exception as e:
            # エラーログの出力
            logger.error(f"サジェスト取得エラー: {e}")
            import traceback
            logger.error(f"トレースバック: {traceback.format_exc()}")
            # エラーメッセージの画面表示
            st.error(f"{ct.SUGGEST_ERROR_MESSAGE}\n\n詳細: {str(e)}", icon=ct.ERROR_ICON)


############################################################
# 10. SEO検定練習問題モードの表示
############################################################
elif mode == ct.MODE_PRACTICE_QUESTIONS:
    logger.info(f"[練習問題モード] モード開始: {mode}")
    
    # セッション状態初期化
    pq.initialize_session_state()
    logger.info("[練習問題モード] セッション状態初期化完了")
    
    # タイトル表示
    st.markdown(f"## {ct.PRACTICE_MODE_TITLE}")
    st.markdown(ct.PRACTICE_MODE_DESCRIPTION)
    st.markdown("---")
    
    # 級選択
    grade = st.radio(
        "受験級を選択してください",
        ["1級", "2級", "3級"],
        horizontal=True,
        key="practice_grade_selector",
        help="1級: 1-4級範囲、2級: 2-4級範囲、3級: 3-4級範囲"
    )
    logger.info(f"[練習問題モード] 選択された級: {grade}")
    
    # 問題生成上限チェック
    question_count = st.session_state.practice_question_count
    logger.info(f"[練習問題モード] 現在の問題数: {question_count}")
    
    if question_count >= ct.PRACTICE_QUESTIONS_CONFIG["MAX_QUESTIONS_PER_SESSION"]:
        logger.warning(f"[練習問題モード] 問題生成上限到達: {question_count}")
        st.warning(ct.PRACTICE_MAX_QUESTIONS_WARNING, icon="⚠️")
        st.stop()
    
    # 問題生成ボタン
    logger.info(f"[練習問題モード] 問題生成ボタン描画: ラベル={ct.PRACTICE_GENERATE_BUTTON}")
    button_clicked = st.button(ct.PRACTICE_GENERATE_BUTTON, type="primary", use_container_width=True)
    logger.info(f"[練習問題モード] ボタン状態: clicked={button_clicked}")
    
    if button_clicked:
        with st.spinner(ct.PRACTICE_GENERATING_MESSAGE):
            try:
                # 新しい問題を生成
                logger.info(f"[練習問題] ボタンクリック検知: {grade}の問題生成開始")
                pq.reset_current_question()
                question = pq.generate_question(grade)
                
                if question:
                    st.session_state.practice_current_question = question
                    st.session_state.practice_question_count += 1
                    logger.info(f"[練習問題] {grade}問題生成成功（通算{st.session_state.practice_question_count}問目）")
                    st.rerun()
                else:
                    logger.error("[練習問題] generate_question()がNoneを返しました")
                    st.error("問題の生成に失敗しました。もう一度お試しください。", icon=ct.ERROR_ICON)
            except Exception as e:
                logger.error(f"[練習問題] 問題生成中に例外発生: {type(e).__name__}: {e}", exc_info=True)
                st.error(f"エラーが発生しました: {e}", icon=ct.ERROR_ICON)
    
    # 問題表示
    if st.session_state.practice_current_question:
        question = st.session_state.practice_current_question
        pq.display_question(question)
        
        # 解答ボタン
        if not st.session_state.practice_show_explanation:
            if st.button(ct.PRACTICE_ANSWER_BUTTON, use_container_width=True):
                st.session_state.practice_show_explanation = True
                st.rerun()
        
        # 解説表示
        if st.session_state.practice_show_explanation and st.session_state.practice_user_answer is not None:
            pq.display_explanation(question, st.session_state.practice_user_answer)
            
            # 次の問題ボタン
            if st.button(ct.PRACTICE_NEXT_BUTTON, use_container_width=True):
                pq.reset_current_question()
                st.rerun()