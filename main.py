"""
このファイルは、Webアプリのメイン処理が記述されたファイルです。
"""

############################################################
# 1. ライブラリの読み込み
############################################################
# 「.env」ファイルから環境変数を読み込むための関数
from dotenv import load_dotenv
# ログ出力を行うためのモジュール
import logging
# streamlitアプリの表示を担当するモジュール
import streamlit as st
# （自作）画面表示以外の様々な関数が定義されているモジュール
import utils
# （自作）アプリ起動時に実行される初期化処理が記述された関数
from initialize import initialize
# （自作）画面表示系の関数が定義されているモジュール
import components as cp
# （自作）変数（定数）がまとめて定義・管理されているモジュール
import constants as ct


############################################################
# 2. 設定関連
############################################################
# ブラウザタブの表示文言を設定
st.set_page_config(
    page_title=ct.APP_NAME
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
# 4. Chrome自動翻訳対策・フォント設定（日本語表示改善）
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
# 5. モード選択（サイドバー）
############################################################
with st.sidebar:
    st.markdown("### 🔧 モード選択")
    mode = st.radio(
        "操作モードを選択してください",
        (ct.MODE_SEO_QUESTION, ct.MODE_DOMAIN_ANALYSIS),
        index=0,
        help="SEO質問モード：社内資料とWeb最新情報を活用したSEO相談\nドメインSEO解析モード：指定ドメインの自動SEO解析（準備中）"
    )
    
    st.markdown("---")
    st.markdown("### 🔧 システム管理")
    if st.button("🗑️ キャッシュクリア", help="入力文字の誤変換や表示不具合を解決"):
        # セッション状態をクリア
        for key in list(st.session_state.keys()):
            if key not in ['retriever', 'initialized']:  # 重要な設定は保持
                del st.session_state[key]
        st.success("✅ キャッシュをクリアしました")
        st.rerun()


############################################################
# 6. SEO質問モードの表示
############################################################
if mode == ct.MODE_SEO_QUESTION:
    # タイトル表示
    cp.display_app_title()

    # 簡潔なSEO検索説明
    cp.display_simple_seo_interface()

    # AIメッセージの初期表示（SEO版）
    cp.display_initial_seo_message()


    ############################################################
    # 6-1. 会話ログの表示（SEO質問モード）
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
    # 6-2. チャット入力の受け付け（SEO質問モード）
    ############################################################
    chat_message = st.chat_input(ct.CHAT_INPUT_HELPER_TEXT)


    ############################################################
    # 6-3. チャット送信時の処理（SEO質問モード）
    ############################################################
    if chat_message:
        # ==========================================
        # 6-3-1. ユーザーメッセージの表示
        # ==========================================
        # ユーザーメッセージのログ出力（SEO特化版）
        logger.info({"message": chat_message, "application_mode": "SEO_SEARCH"})

        # ユーザーメッセージを表示
        with st.chat_message("user"):
            st.markdown(chat_message)

        # ==========================================
        # 6-3-2. LLMからの回答取得
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
        # 6-3-3. LLMからのSEO回答表示（簡素化版）
        # ==========================================
        with st.chat_message("assistant"):
            try:
                # 統一フォーマットでの表示判定
                if llm_response.get("unified_display", False):
                    # 非SEO応答の統一表示
                    cp.display_unified_seo_content(llm_response["answer"])
                    content = llm_response["answer"]
                else:
                    # SEO特化の回答表示（統一フォーマット使用）
                    content = cp.display_seo_response(llm_response)
                
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
        # 6-3-4. 会話ログへの追加
        # ==========================================
        # 表示用の会話ログにユーザーメッセージを追加
        st.session_state.messages.append({"role": "user", "content": chat_message})
        # 表示用の会話ログにAIメッセージを追加
        st.session_state.messages.append({"role": "assistant", "content": content})


############################################################
# 7. ドメインSEO解析モードの表示
############################################################
elif mode == ct.MODE_DOMAIN_ANALYSIS:
    # ドメイン解析インターフェースの表示（準備中画面）
    cp.display_domain_analysis_interface()