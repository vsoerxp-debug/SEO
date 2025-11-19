"""
このファイルは、SEO特化版の画面表示関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import streamlit as st
import utils
import constants as ct
import re


############################################################
# 関数定義
############################################################

def normalize_headings(html_content):
    """
    HTMLの見出しサイズを正規化（大きすぎるH1-H3をH6に変換）
    """
    # H1-H3をH6に変換
    html_content = re.sub(r'<h[1-3](\s[^>]*)?>', r'<h6\1>', html_content)
    html_content = re.sub(r'</h[1-3]>', '</h6>', html_content)
    return html_content

def display_app_title():
    """
    タイトル表示（SEO特化版・改良済み）
    """
    # タイトルとステータスを同じ行に配置して左寄せにする
    enhanced = getattr(st.session_state, 'enhanced_mode', False)
    status_label = "🚀 高精度" if enhanced else "⚙️ 標準"

    # タイトルを「通常文字より少し大きめ」に調整し、ステータスはタイトル直後に小さなバッジとして表示
    title_html = (
        f"<div style='display:flex; align-items:center; gap:12px;'>"
        f"<span style='font-size:18px; font-weight:600;'>{ct.APP_NAME}</span>"
        f"<span style='background:#f1f5f9; color:#0f172a; padding:4px 8px; border-radius:6px; font-size:13px;'>{status_label}</span>"
        f"</div>"
    )

    st.markdown(title_html, unsafe_allow_html=True)
    st.markdown("*SEO関連の資料から最適な情報を検索・回答します*")


def display_simple_seo_interface():
    """
    シンプルなSEO検索インターフェース（④⑤対応：不要要素削除）
    """
    st.markdown("---")
    st.markdown("SEOに関する疑問や質問を入力してください。関連する資料から最適な回答を提供します。")


def display_initial_seo_message():
    """
    SEO特化版の初期AIメッセージ（⑤対応：利用可能な情報削除）
    """
    with st.chat_message("assistant"):
        st.markdown("こんにちは！私は**SEO専門のアシスタント**です。")
        st.markdown("社内のSEO関連資料をもとに、あなたのSEOに関する質問にお答えします。")
        
        # 入力例の表示
        st.code("【入力例】\n・モバイルSEOの最適化方法を教えて\n・ローカルSEOで重要なポイントは？\n・Googleアップデートの対策方法", wrap_lines=True, language=None)


def display_unified_seo_content(content_text, sources=None, latest_info=None):
    """
    統一フォーマットでのSEO応答表示（インライン出典付き・フォント・改行完全統一）
    
    Args:
        content_text: 表示するテキスト内容
        sources: 参考資料リスト（インライン出典用）
        latest_info: 最新情報リスト（インライン出典用）
    
    Returns:
        None
    """
    import re
    
    # インライン出典を追加する関数
    def add_inline_citations(text, sources_list, info_list):
        """各段落末尾にインライン出典を追加"""
        paragraphs = text.split('\n\n')
        cited_paragraphs = []
        
        for i, paragraph in enumerate(paragraphs):
            if paragraph.strip():
                # 段落末尾に出典情報を追加
                citation = ""
                if info_list and i < len(info_list):
                    info = info_list[i] if i < len(info_list) else info_list[0]
                    site_name = info.get('site_name', 'Unknown Site')
                    url = info.get('url', '#')
                    citation = f' <a href="{url}" target="_blank" style="font-size: 14px; color: #0066cc;">({site_name})</a>'
                elif sources_list and i < len(sources_list):
                    source = sources_list[i] if i < len(sources_list) else sources_list[0]
                    title = source.get('title', 'Internal Document')
                    citation = f' <span style="font-size: 14px; color: #666;">({title})</span>'
                
                cited_paragraphs.append(paragraph + citation)
            else:
                cited_paragraphs.append(paragraph)
        
        return '\n\n'.join(cited_paragraphs)
    
    # インライン出典を追加
    if sources or latest_info:
        content_text = add_inline_citations(content_text, sources or [], latest_info or [])
    
    # マークダウン記号を完全除去し、太字のみ保持
    def clean_unified_display(text: str) -> str:
        # 見出し記号（#）を完全除去
        text = re.sub(r'(?m)^\s*#+\s*', '', text)
        # 太字記法は保持（**text** → <strong>text</strong>）
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        # その他のマークダウン記号を除去
        text = re.sub(r'^\s*[*\-+]\s+', '• ', text, flags=re.MULTILINE)  # リスト記号を統一
        # 改行を<br>に変換（重要：改行の統一）
        text = text.replace('\n', '<br>')
        return text

    processed_content = clean_unified_display(content_text)
    
    # 最強CSS優先度による完全統一（Streamlitデフォルト上書き）
    unified_content = f'''
    <div class="seo-ultimate-unified" translate="no" lang="ja" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important; font-size: 16px !important; line-height: 1.6 !important; color: #333333 !important;">
        {processed_content}
    </div>
    <style>
        /* 最強優先度：複数セレクタ + インラインスタイル + !important */
        .seo-ultimate-unified,
        .seo-ultimate-unified *,
        [data-testid="stChatMessage"] .seo-ultimate-unified,
        [data-testid="stChatMessage"] .seo-ultimate-unified *,
        div.stChatMessage .seo-ultimate-unified,
        div.stChatMessage .seo-ultimate-unified * {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
            color: #333333 !important;
            margin: 0.5em 0 !important;
        }}
        
        /* 段落の完全統一 */
        .seo-ultimate-unified p,
        [data-testid="stChatMessage"] .seo-ultimate-unified p,
        div.stChatMessage .seo-ultimate-unified p {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
            margin: 0.5em 0 !important;
        }}
        
        /* 強調要素の完全統一 */
        .seo-ultimate-unified strong,
        [data-testid="stChatMessage"] .seo-ultimate-unified strong,
        div.stChatMessage .seo-ultimate-unified strong {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #1f2937 !important;
        }}
        
        /* 見出しの完全統一 */
        .seo-ultimate-unified h1, .seo-ultimate-unified h2, .seo-ultimate-unified h3,
        .seo-ultimate-unified h4, .seo-ultimate-unified h5, .seo-ultimate-unified h6,
        [data-testid="stChatMessage"] .seo-ultimate-unified h1,
        [data-testid="stChatMessage"] .seo-ultimate-unified h2,
        [data-testid="stChatMessage"] .seo-ultimate-unified h3,
        [data-testid="stChatMessage"] .seo-ultimate-unified h4,
        [data-testid="stChatMessage"] .seo-ultimate-unified h5,
        [data-testid="stChatMessage"] .seo-ultimate-unified h6 {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
            font-size: 16px !important;
            font-weight: 600 !important;
            margin: 1em 0 0.5em 0 !important;
            color: #1f2937 !important;
        }}
    </style>
    '''
    st.markdown(unified_content, unsafe_allow_html=True)


def display_seo_response(llm_response):
    """
    SEO特化版のレスポンス表示（ハイブリッドRAG対応版・統一フォーマット使用）
    
    Args:
        llm_response: LLMからの回答
    
    Returns:
        str: 表示したコンテンツ
    """
    try:
        # 回答が見つからない場合の処理
        if llm_response.get("answer") == ct.INQUIRY_NO_MATCH_ANSWER:
            st.warning("該当するSEO情報が見つかりませんでした")
            st.info("以下をお試しください：\n- より具体的なSEOキーワードを使用\n- 異なる表現で質問を言い換え\n- 基本的なSEO用語で検索")
            return "SEO情報が見つかりませんでした"
        
        # ハイブリッドモードの場合は情報源の内訳を表示
        if llm_response.get("hybrid_mode", False):
            source_breakdown = llm_response.get("source_breakdown", {})
            if source_breakdown:
                internal_count = source_breakdown.get("internal", 0)
                realtime_count = source_breakdown.get("realtime", 0)
                
                if internal_count > 0 and realtime_count > 0:
                    st.info(f"📊 **統合情報**: 社内資料 {internal_count}件 + 最新情報 {realtime_count}件を統合して回答")
                elif realtime_count > 0:
                    st.info(f"🔄 **最新情報**: {realtime_count}件の最新SEO情報を含む回答")
        
        # 通常の回答表示
        answer = llm_response.get("answer", "回答を生成できませんでした。")

        # 統一表示関数を使用（インライン出典付き・フォント・改行完全統一）
        sources = llm_response.get("sources", [])
        latest_info = llm_response.get("latest_info", [])
        display_unified_seo_content(answer, sources, latest_info)
        
        # 追加の強制フォント統一CSS（Streamlit上書き対策）
        st.markdown("""
        <style>
        /* 超強力統一CSS：全てのチャットメッセージ要素を強制統一 */
        [data-testid="stChatMessage"] * {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # 最新情報が含まれる場合は注意事項を表示
        if llm_response.get("hybrid_mode", False) and llm_response.get("source_breakdown", {}).get("realtime", 0) > 0:
            st.caption("⚠️ 最新情報は外部サイトから取得したものです。詳細は元サイトでご確認ください。")
        
        # ソース情報の表示（最新情報は常に表示、社内資料は重複防止チェック）
        sources = llm_response.get("sources", [])
        latest_info = llm_response.get("latest_info", [])
        
        # 最新情報の出典は常に表示
        if latest_info:
            display_answer_with_sources(answer, [], latest_info)  # 最新情報のみ表示
        
        # 社内資料は重複防止チェック
        if not llm_response.get("unified_display", False) and sources:
            display_answer_with_sources(answer, sources, [])
        
        return answer
        
    except Exception as e:
        st.error(f"回答の表示中にエラーが発生しました: {str(e)}")
        return "回答表示エラー"


def display_answer_with_sources(answer, sources, latest_info=None):
    """
    回答とソースを表示（統一フォーマット使用）
    """
    st.markdown('<div style="font-size: 16px; font-weight: 600; margin: 16px 0 8px 0;">🎯 回答</div>', unsafe_allow_html=True)
    
    # 統一表示関数を使用（フォント・改行完全統一）
    display_unified_seo_content(answer)
    
    # 最強ソース表示CSS + Streamlit全体上書き
    st.markdown("""
    <style>
    /* Streamlit全体のフォント統一（最強優先度） */
    [data-testid="stChatMessage"] *,
    [data-testid="stChatMessage"],
    div.stChatMessage *,
    div.stChatMessage,
    .stMarkdown *,
    .stMarkdown {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
        font-size: 16px !important;
        line-height: 1.6 !important;
    }
    
    /* ソース表示の統一スタイル（16px統一） */
    .source-attribution {
        background-color: #f0f2f6;
        padding: 12px;
        border-radius: 6px;
        margin: 8px 0;
        border-left: 4px solid #0066cc;
        font-size: 16px !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
    }
    .source-title {
        color: #0066cc;
        text-decoration: none;
        font-weight: bold;
        font-size: 16px !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
    }
    .source-title:hover {
        text-decoration: underline;
    }
    .source-meta {
        font-size: 16px !important;
        color: #666;
        margin-top: 4px;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
    }
    .source-attribution strong {
        font-weight: 600 !important;
        font-size: 16px !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Yu Gothic UI', 'Meiryo', sans-serif !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 最新情報を表示（16px統一・サイト名とURL明記）
    if latest_info:
        st.markdown('<div style="font-size: 16px; font-weight: 600; margin: 16px 0 8px 0;">📰 最新情報の出典</div>', unsafe_allow_html=True)
        for idx, info in enumerate(latest_info, 1):
            site_name = info.get('site_name', 'Unknown Site')
            url = info.get('url', '#')
            display_url = info.get('display_url', url)
            title = info.get('title', 'No title')
            date = info.get('date', 'No date')
            summary = info.get('summary', '')
            
            # より詳細な出典情報の表示
            source_html = f"""
            <div class="source-attribution" style="background: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 12px;">
                <div style="margin: 0 0 8px 0; color: #333; font-size: 16px; font-weight: 600;">
                    📄 {title}
                </div>
                <div class="source-meta" style="margin-bottom: 8px;">
                    🌐 <strong>サイト名:</strong> {site_name}<br>
                    🔗 <strong>URL:</strong> <a href="{url}" target="_blank" style="color: #0066cc; text-decoration: none;">{display_url}</a><br>
                    � <strong>公開日:</strong> {date}
                </div>
                {f'<p style="margin: 8px 0; font-size: 16px; color: #555;">{summary[:300]}...</p>' if summary else ''}
                <a href="{url}" target="_blank" class="source-title" style="display: inline-block; margin-top: 8px; padding: 6px 12px; background: #0066cc; color: white; text-decoration: none; border-radius: 4px; font-size: 14px;">� 記事の詳細を見る</a>
            </div>
            """
            st.markdown(source_html, unsafe_allow_html=True)
    
    # 参考資料を表示（空でない場合のみ・動的表示）
    valid_sources = [s for s in sources if s.get('title') or s.get('content') or s.get('page_content')]
    if valid_sources:
        # 参考資料の数に応じて表示件数を調整（最大5件）
        display_count = min(len(valid_sources), 5)
        st.markdown(f'<div style="font-size: 16px; font-weight: 600; margin: 16px 0 8px 0;">📚 参考資料 ({display_count}件)</div>', unsafe_allow_html=True)
        
        for idx, source in enumerate(valid_sources[:display_count], 1):
            title = source.get('title', f'文書 {idx}')
            url = source.get('url', '')
            site_name = source.get('site_name', '')
            
            # ソース情報の表示（16px統一）
            source_html = f"""
            <div class="source-attribution">
                <div style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600;">
                    {idx}. <a href="{url}" target="_blank" class="source-title">{title}</a>
                </div>
            """
            
            if site_name:
                source_html += f'<div class="source-meta">📰 <strong>{site_name}</strong></div>'
            
            content = source.get('content', source.get('page_content', ''))
            if content:
                truncated = content[:200] + "..." if len(content) > 200 else content
                source_html += f'<p style="margin: 8px 0 0 0; font-size: 16px;">{truncated}</p>'
            
            source_html += "</div>"
            st.markdown(source_html, unsafe_allow_html=True)


def display_conversation_log():
    """
    会話ログの一覧表示（SEO特化版・簡素化）
    """
    # 会話ログのループ処理
    for message in st.session_state.messages:
        # 「message」辞書の中の「role」キーには「user」か「assistant」が入っている
        with st.chat_message(message["role"]):

            # ユーザー入力値の場合、翻訳防止対策を適用してテキストを表示
            if message["role"] == "user":
                protected_user_content = f'<div class="notranslate" translate="no" lang="ja">{message["content"]}</div>'
                st.markdown(protected_user_content, unsafe_allow_html=True)
            
            # AIからの回答の場合（SEO特化版）
            else:
                # 文字列の場合は翻訳防止対策を適用して表示
                if isinstance(message["content"], str):
                    protected_ai_content = f'<div class="notranslate" translate="no" lang="ja">{message["content"]}</div>'
                    st.markdown(protected_ai_content, unsafe_allow_html=True)
                # 辞書形式の場合（下位互換性のため）
                elif isinstance(message["content"], dict):
                    # SEO回答として処理（翻訳防止対策適用）
                    if "answer" in message["content"]:
                        protected_answer = f'<div class="notranslate" translate="no" lang="ja">{message["content"]["answer"]}</div>'
                        st.markdown(protected_answer, unsafe_allow_html=True)
                    else:
                        st.markdown(str(message["content"]))


def display_domain_analysis_interface():
    """
    ドメインSEO解析モードのインターフェース表示（実機能版）
    """
    st.markdown("### 🌐 ドメインSEO解析モード")
    st.markdown("---")
    
    st.info("""
    **このモードについて**
            
    特定の1ページを詳細に解析します。  
    
    **注意事項**
    - 解析するページとトップページは同一ドメインにしてください
    - 社内環境での利用を前提としています
    """, icon="ℹ️")
    
    st.markdown("---")
    
    # 入力フィールド（2URL方式・シンプル版）
    top_url = st.text_input(
        "トップページのURLを入力してください",
        placeholder="例: https://example.com",
        help="サイト全体の構造を把握するため、トップページのURLを入力してください"
    )
    
    target_url = st.text_input(
        "解析するページのURLを入力してください",
        placeholder="例: https://example.com/blog/seo-guide",
        help="詳細に分析したい特定ページのURLを入力してください"
    )
    
    # 解析ボタン
    if st.button("🔍 解析開始", type="primary"):
        if not top_url or not top_url.strip():
            st.error("トップページのURLを入力してください", icon="⚠️")
            return
        if not target_url or not target_url.strip():
            st.error("解析するページのURLを入力してください", icon="⚠️")
            return
        
        # 解析実行（デフォルト: 30ページクロール）
        with st.spinner("解析中... サイト構造を把握中 → 対象ページを詳細分析中..."):
            try:
                from domain_analyzer import analyze_single_page_with_context
                
                # 1ページ詳細解析関数を呼び出し（RAG連携版）
                result = analyze_single_page_with_context(
                    top_url.strip(),
                    target_url.strip(),
                    max_pages=30,  # デフォルト値
                    rag_function=utils.get_llm_response  # RAG経路を注入
                )
                
                if not result:
                    st.error("解析に失敗しました。URLを確認してください。", icon="❌")
                    return
                
                # 成功メッセージ（シンプル版）
                rag_mode = result.get("hybrid_mode", False)
                st.success("✅ 解析が完了しました！")

                
                # 結果表示（統一フォーマット使用）
                st.markdown("---")
                st.markdown("### 📊 解析レポート")
                
                # 統一表示関数を使用
                if result.get("unified_display", False):
                    # sourcesをlatest_info形式に変換
                    latest_info = [
                        {
                            "site_name": s.get("title", "ページ"),
                            "url": s.get("url", "#"),
                            "title": s.get("title", ""),
                            "summary": s.get("content", "")[:200]
                        }
                        for s in result.get("sources", [])
                    ]
                    display_unified_seo_content(
                        result.get("answer", ""),
                        sources=None,
                        latest_info=latest_info
                    )
                else:
                    st.markdown(result.get("answer", ""))
                
            except Exception as e:
                import logging
                logger = logging.getLogger(ct.LOGGER_NAME)
                logger.error(f"[1ページ解析UI] エラー: {e}")
                st.error(f"解析中にエラーが発生しました: {str(e)}", icon="❌")
                st.info("URLの形式を確認するか、別のドメインでお試しください。")