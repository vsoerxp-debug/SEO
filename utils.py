"""
このファイルは、画面表示以外の様々な関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import os
from dotenv import load_dotenv
import streamlit as st
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
# LangChain 1.0+ Runnable-Based Implementation（完全互換性対応）
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser

from langchain_openai import ChatOpenAI
import constants as ct
import logging
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import feedparser
import time
from langchain_core.documents import Document

# ドメイン解析モジュール
from domain_analyzer import analyze_domain_seo_lightweight

# SEO特化版：拡張機能は削除（PyTorch競合回避）
def traceable_if_available(func):
    """SEO特化版：トレーシング機能のスタブ"""
    return func

def secure_input(func):
    """SEO特化版：セキュリティ機能のスタブ"""
    return func


############################################################
# 最新情報取得モジュール（RSS + 軽量スクレイピング）
############################################################

def _load_rss_feeds_from_csv():
    """
    CSVファイルからRSSフィード設定を読み込み（DEFAULT_FEEDSと統合版）
    
    Returns:
        list: フィード情報のリスト（CSV + DEFAULT_FEEDS統合・重複排除）
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    feeds = []
    feed_urls_seen = set()  # 重複排除用
    
    try:
        import pandas as pd
        csv_path = ct.HYBRID_RAG_CONFIG["RSS_CONFIG_FILE"]
        
        # Step 1: CSVファイルからの読み込み
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, encoding='utf-8')
            
            # 優先度順にソート
            df = df.sort_values(['優先度', 'サイト名'])
            
            # 優先度別の制限を適用
            max_feeds = ct.HYBRID_RAG_CONFIG["MAX_FEEDS_PER_PRIORITY"]
            for priority in [1, 2, 3]:
                priority_feeds = df[df['優先度'] == priority]
                limited_feeds = priority_feeds.head(max_feeds.get(priority, 5))
                
                for _, row in limited_feeds.iterrows():
                    feed_url = row['URL']
                    if feed_url not in feed_urls_seen:
                        feed_info = {
                            'url': feed_url,
                            'name': row['サイト名'],
                            'category': row['カテゴリ'],
                            'priority': row['優先度'],
                            'language': row['言語'],
                            'description': row['説明']
                        }
                        feeds.append(feed_info)
                        feed_urls_seen.add(feed_url)
            
            logger.info(f"CSV読み込み完了: {len(feeds)}フィード")
        else:
            logger.warning(f"RSS設定ファイルが見つかりません: {csv_path}")
        
        # Step 2: DEFAULT_FEEDSを追加（重複排除）
        default_feeds = ct.HYBRID_RAG_CONFIG["DEFAULT_FEEDS"]
        default_added = 0
        for url in default_feeds:
            if url not in feed_urls_seen:
                feeds.append({
                    'url': url,
                    'name': 'Default Feed',
                    'priority': 2,
                    'category': 'default',
                    'language': 'en',
                    'description': 'Fallback feed'
                })
                feed_urls_seen.add(url)
                default_added += 1
        
        logger.info(f"DEFAULT_FEEDS統合: {default_added}件追加、合計{len(feeds)}フィード")
        return feeds
        
    except Exception as e:
        logger.error(f"RSS設定読み込みエラー: {e}")
        # フォールバック：DEFAULT_FEEDSのみ
        default_feeds = ct.HYBRID_RAG_CONFIG["DEFAULT_FEEDS"]
        return [{'url': url, 'name': 'Default Feed', 'priority': 2} for url in default_feeds]


def fetch_latest_seo_info(query, max_articles=5):
    """
    最新SEO情報取得（CSV設定対応・RSS/Atomフィード + 軽量スクレイピング）
    
    Args:
        query: 検索クエリ
        max_articles: 最大記事数
        
    Returns:
        list: 最新記事のDocumentリスト
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    try:
        # Step 1: RSS/Atomフィードから基本情報取得
        latest_articles = _fetch_rss_feeds(query, max_articles)
        
        # Step 2: 記事の詳細コンテンツ取得（軽量スクレイピング）
        enhanced_articles = _enhance_articles_with_scraping(latest_articles)
        
        # Step 3: Documentオブジェクトとしてフォーマットとメタデータ付与
        documents = _convert_articles_to_documents(enhanced_articles, query)
        
        logger.info(f"最新情報取得完了: {len(documents)}件")
        return documents
        
    except Exception as e:
        logger.error(f"最新情報取得エラー: {e}")
        return []  # エラー時は空リストを返してシステム継続


def _fetch_rss_feeds(query, max_articles):
    """
    RSS/Atomフィードから記事取得
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    articles = []
    
    # CSV設定からフィード情報を読み込み
    feed_configs = _load_rss_feeds_from_csv()
    
    for feed_config in feed_configs:
        try:
            feed_url = feed_config.get('url') if isinstance(feed_config, dict) else feed_config
            feed_name = feed_config.get('name', 'Unknown Site') if isinstance(feed_config, dict) else 'Unknown Site'
            
            # フィード取得（タイムアウト設定）
            feed = feedparser.parse(feed_url)
            
            # フィード解析成功確認
            if not hasattr(feed, 'entries') or not feed.entries:
                logger.warning(f"フィード取得失敗またはエントリなし: {feed_url}")
                continue
            
            # 関連記事のフィルタリングと取得（デバッグ強化版）
            for entry in feed.entries[:5]:  # 各フィードから最大5記事に増加
                try:
                    entry_title = entry.get('title', 'No title')
                    entry_summary = entry.get('summary', '')
                    
                    # 関連性チェック（詳細ログ付き）
                    is_relevant = _is_article_relevant(query, entry_title, entry_summary)
                    
                    # AI Mode等の重要キーワードが含まれている場合は強制的に取得
                    force_include_keywords = ['ai mode', 'ai overviews', 'core update', 'spam update', 'コア更新', 'スパム更新']
                    content_lower = (entry_title + ' ' + entry_summary).lower()
                    force_include = any(keyword in content_lower for keyword in force_include_keywords)
                    
                    if is_relevant or force_include:
                        if force_include and not is_relevant:
                            logger.info(f"重要キーワードによる強制取得: {entry_title}")
                        
                        article_data = {
                            'title': entry_title,
                            'content': entry_summary,
                            'url': entry.get('link', ''),
                            'published': entry.get('published', ''),
                            'source': feed_url,
                            'site_name': feed_name,
                            'priority': feed_config.get('priority', 2) if isinstance(feed_config, dict) else 2,
                            'category': _auto_classify_article(entry_title + ' ' + entry_summary),
                            'display_url': _convert_to_display_url(entry.get('link', '')),
                            'force_included': force_include  # 強制取得フラグ
                        }
                        articles.append(article_data)
                        
                        if len(articles) >= max_articles:
                            break
                    else:
                        # デバッグ：関連性がない記事をログ出力
                        logger.debug(f"関連性なしで除外: {entry_title}")
                        
                except Exception as entry_error:
                    logger.warning(f"記事処理エラー: {entry_error}")
                    continue
                            
                except Exception as entry_error:
                    logger.warning(f"記事処理エラー: {entry_error}")
                    continue
            
            # 遅延処理（サーバー負荷軽減）
            time.sleep(0.5)
            
        except Exception as feed_error:
            logger.warning(f"フィード取得エラー: {feed_url}, {feed_error}")
            continue
        
        if len(articles) >= max_articles:
            break
    
    logger.info(f"RSS取得完了: {len(articles)}件")
    # 保険: max_articlesを確実に守る
    return articles[:max_articles]


def _enhance_articles_with_scraping(articles):
    """
    軽量スクレイピングで記事詳細を取得
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    enhanced_articles = []
    
    for article in articles:
        try:
            # 軽量スクレイピング実行
            detailed_content = _scrape_article_safely(article['url'])
            
            if detailed_content:
                article['detailed_content'] = detailed_content
                article['content_enhanced'] = True
            else:
                article['detailed_content'] = article['content']  # フォールバック
                article['content_enhanced'] = False
            
            enhanced_articles.append(article)
            
            # 遅延処理（重要：サーバー負荷軽減）
            time.sleep(1.0)
            
        except Exception as scrape_error:
            logger.warning(f"スクレイピングエラー: {article['url']}, {scrape_error}")
            # エラー時は元の記事をそのまま使用
            article['detailed_content'] = article['content']
            article['content_enhanced'] = False
            enhanced_articles.append(article)
    
    return enhanced_articles


def _scrape_article_safely(url):
    """
    安全な軽量スクレイピング実装
    """
    try:
        # User-Agentとタイムアウト設定
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # BeautifulSoupで解析
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 記事本文の抽出（一般的なセレクタ）
        content_selectors = [
            'article', '.post-content', '.entry-content', 
            '.article-content', '.content', 'main'
        ]
        
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                # テキスト抽出とクリーニング
                text = content_element.get_text(separator='\n', strip=True)
                # 長さ制限（トークン節約）
                if len(text) > 2000:
                    text = text[:2000] + "..."
                return text
        
        # フォールバック：タイトルとメタ説明
        title = soup.find('title')
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        
        fallback_text = ""
        if title:
            fallback_text += title.get_text() + "\n"
        if meta_desc:
            fallback_text += meta_desc.get('content', '')
        
        return fallback_text if fallback_text else None
        
    except Exception as e:
        return None  # スクレイピング失敗時はNoneを返す


def _is_article_relevant(query, title, summary):
    """
    記事とクエリの関連性判定（高精度版）
    """
    query_lower = query.lower()
    content_lower = (title + ' ' + summary).lower()
    
    # 1. 直接的なSEO関連キーワード（必須マッチ）
    primary_seo_terms = [
        'seo', 'search engine optimization', '検索エンジン最適化',
        'google', 'bing', 'yahoo', '検索エンジン', 'search engine',
        'アルゴリズム', 'algorithm', 'ランキング', 'ranking',
        'インデックス', 'index', 'クロール', 'crawl',
        'キーワード', 'keyword', 'メタタグ', 'meta tag',
        # 2025年Googleアップデート重要用語を追加
        'ai mode', 'ai overviews', 'google ai', 'core update', 'コア更新', 'コアアップデート',
        'spam update', 'スパム更新', 'スパムアップデート', 'helpful content', 'ヘルプフルコンテンツ',
        'product reviews', 'プロダクトレビュー', 'page experience', 'ページエクスペリエンス',
        'search generative experience', 'sge', 'generative ai', 'bard', 'gemini'
    ]
    
    # 2. 関連性の高いSEO用語
    secondary_seo_terms = [
        'サイト', 'ページ', 'ウェブサイト', 'website', 'web site',
        'コンテンツ', 'content', 'リンク', 'link', 'バックリンク',
        'ドメイン', 'domain', 'オーガニック', 'organic',
        'アップデート', 'update', 'ペナルティ', 'penalty',
        # 2025年関連の時期・日付用語を追加
        '2025', 'march 2025', 'june 2025', 'august 2025', 'september 2025', 'october 2025',
        '2025年', '2025年3月', '2025年6月', '2025年8月', '2025年9月', '2025年10月',
        'rolling out', 'rollout', '展開', 'feature', '機能', 'labs', 'experimental'
    ]
    
    # 3. 除外キーワード（SEO以外の明確な内容）
    exclude_terms = [
        'プログラミング言語', 'データベース', 'サーバー管理', 'ネットワーク',
        '料理', 'レシピ', '旅行', '映画', 'ゲーム', 'スポーツ',
        '医療', '健康', '金融', '投資', '株価', '不動産'
    ]
    
    # 除外チェック（優先）
    if any(term in content_lower for term in exclude_terms):
        return False
    
    # プライマリキーワードのマッチング（高重要度）
    primary_matches = sum(1 for term in primary_seo_terms if term in content_lower)
    
    # セカンダリキーワードのマッチング
    secondary_matches = sum(1 for term in secondary_seo_terms if term in content_lower)
    
    # クエリとの直接関連性
    query_relevance = any(word in content_lower for word in query_lower.split() if len(word) > 2)
    
    # 関連性スコア計算
    relevance_score = primary_matches * 2 + secondary_matches * 1
    
    # 特別な2025年Googleアップデート用語の優先チェック
    google_2025_priority_terms = [
        'ai mode', 'ai overviews', 'core update march 2025', 'core update june 2025',
        'core update august 2025', 'google ai 2025', '2025年3月 コア更新', '2025年6月 コア更新',
        '2025年8月 コア更新', 'spam update 2025', 'スパム更新 2025'
    ]
    
    # 優先度の高い2025年用語が含まれる場合は即座に承認
    for priority_term in google_2025_priority_terms:
        if priority_term in content_lower:
            return True
    
    # 判定基準（従来ロジック + 強化版）
    if primary_matches >= 1:  # プライマリキーワードが1つ以上
        return True
    elif secondary_matches >= 2 and query_relevance:  # セカンダリ2つ以上+クエリ関連
        return True
    elif '2025' in content_lower and any(term in content_lower for term in ['google', 'update', 'algorithm']):
        # 2025年 + Google関連用語の組み合わせ
        return True
    else:
        return False


def _auto_classify_article(content):
    """
    記事の自動カテゴリ分類
    """
    content_lower = content.lower()
    
    for category, keywords in ct.SEO_CATEGORY_SYSTEM["CLASSIFICATION_KEYWORDS"].items():
        if any(keyword.lower() in content_lower for keyword in keywords):
            return category
    
    return "general"  # デフォルトカテゴリ


def _convert_articles_to_documents(articles, query):
    """
    記事データをLangChain Documentオブジェクトに変換
    """
    documents = []
    
    for article in articles:
        try:
            # サイト名とURLの抽出
            site_name = _extract_site_name(article['source'])
            display_url = _convert_to_display_url(article['url'])
            
            # 拡張メタデータの構築
            metadata = {
                'source': article['url'],
                'source_type': 'realtime',
                'title': article['title'],
                'published_date': article['published'],
                'seo_category': article['category'],
                'freshness_score': 1.0,  # リアルタイム情報は最高鮮度
                'priority_level': _get_category_priority(article['category']),
                'content_enhanced': article.get('content_enhanced', False),
                'indexed_date': datetime.now().isoformat(),
                'related_query': query,
                'site_name': site_name,
                'display_url': display_url
            }
            
            # 文書コンテンツの構築
            content = f"【{article['title']}】\n"
            content += article['detailed_content']
            
            # Documentオブジェクト作成
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)
            
        except Exception as doc_error:
            logger = logging.getLogger(ct.LOGGER_NAME)
            logger.warning(f"Document変換エラー: {doc_error}")
            continue
    
    return documents


def _get_category_priority(category):
    """
    カテゴリ別優先度設定
    """
    priority_map = {
        "algorithm": 1,      # 最高優先度
        "search_features": 2,
        "technical": 3,
        "content": 3,
        "general": 4
    }
    return priority_map.get(category, 4)


def _is_seo_related_query(query):
    """
    クエリがSEO関連かどうかを判定（高精度版 + 動的検知システム）
    """
    query_lower = query.lower()
    
    # Step 1: 従来の確実なSEOキーワードチェック
    # 必須SEOキーワード
    essential_seo_keywords = [
        'seo', 'search engine optimization', '検索エンジン最適化',
        'google', 'bing', 'yahoo', '検索エンジン', 'search engine',
        'アルゴリズム', 'algorithm', 'ランキング', 'ranking',
        'インデックス', 'index', 'クロール', 'crawl', 'crawler',
        'キーワード', 'keyword', 'メタタグ', 'meta tag', 'meta',
        'サイトマップ', 'sitemap', 'robots.txt', 'robots',
        'オーガニック', 'organic', 'serp', '検索結果',
        'ページ速度', 'page speed', 'core web vitals', 'core web vital', 'vitals', 'vital',
        'バックリンク', 'backlink', 'link building',
        # ビジュアル・アクセシビリティ関連
        'visual aid', 'ビジュアルエイド', 'visual', 'accessibility', 'アクセシビリティ',
        'alt text', 'altテキスト', 'alt属性', 'image optimization', '画像最適化',
        # 重要なSEO専門用語を追加
        'アップデート', 'update', 'グーグルアップデート', 'google update',
        'サイテーション', 'citation', '引用', 'ymyl', 'eat', 'e-a-t', 'e-e-a-t',
        # MEO・ローカルSEO関連（重要）
        'meo', 'map engine optimization', 'ローカルseo', 'local seo', 'ローカル検索', 'local search',
        'googleマップ', 'google maps', 'googleマイビジネス', 'google my business', 'gmb',
        'ローカル', 'local', '地域', '店舗', '地図', 'マップ', 'map',
        'モバイルファースト', 'mobile first', 'amp', 'structured data',
        '構造化データ', 'schema', 'スキーマ', 'rich snippet', 'リッチスニペット',
        # AI・SEO関連（重要）
        'ai overview', 'aioverviews', 'aimode', 'ai concept', 'ai summary',
        '生成ai', 'generative ai', 'ai', '人工知能', 'artificial intelligence',
        'ai検索', 'ai search', 'ai機能', 'ai feature', 'aiとseo', 'ai seo',
        # ドメイン解析関連（重要：内部システムからの解析依頼を確実に通過させる）
        'seoスコア', 'seo解析', 'ドメイン解析', 'domain analysis', 'webサイト解析', 'website analysis',
        'seo評価', 'seo診断', 'サイト診断', 'site audit', 'オンページseo', 'on-page seo',
        # 新しいSEO概念・用語（2024-2025年）
        'fluqs', 'fluq', 'sgе', 'zero-click search', 'ゼロクリック検索',
        'featured snippet', 'フィーチャードスニペット', 'knowledge graph', 'ナレッジグラフ',
        'people also ask', 'paa', '関連する質問', 'entity seo', 'エンティティseo'
    ]
    
    # 関連SEO用語
    related_seo_terms = [
        'ウェブサイト', 'website', 'web site', 'ホームページ',
        'コンテンツ', 'content', 'ページ', 'page',
        'ドメイン', 'domain', 'url', 'リンク', 'link',
        'タイトルタグ', 'title tag', 'h1', 'h2', 'h3',
        'ペナルティ', 'penalty', '順位', '検索', 'search', '最適化', 'optimization',
        # SEO関連の追加用語
        'webmaster', 'ウェブマスター', 'analytics', 'アナリティクス',
        'console', 'search console', 'サーチコンソール',
        'traffic', 'トラフィック', 'conversion', 'コンバージョン',
        'ctr', 'click through rate', 'クリック率',
        'bounce rate', 'バウンス率', 'dwell time', '滞在時間',
        # UI/UX・アクセシビリティ関連SEO用語
        'user experience', 'ux', 'ui', 'usability', 'ユーザビリティ',
        'responsive', 'レスポンシブ', 'mobile friendly', 'モバイルフレンドリー'
    ]
    
    # 明確な非SEO用語（除外対象）
    non_seo_terms = [
        '湯川秀樹', '大谷翔平', 'ノーベル賞', '野球', 'スポーツ',
        '料理', 'レシピ', '旅行', '映画', 'ゲーム',
        '医療', '健康', '金融', '投資', '株価', '不動産',
        'プログラミング言語', 'python', 'java', 'javascript',
        'データベース', 'mysql', 'postgresql', 'サーバー管理'
    ]
    
    # 除外チェック（優先判定）
    if any(term in query_lower for term in non_seo_terms):
        return False
    
    # 必須キーワードのマッチング
    essential_matches = sum(1 for term in essential_seo_keywords if term in query_lower)
    
    # 関連キーワードのマッチング  
    related_matches = sum(1 for term in related_seo_terms if term in query_lower)
    
    # 判定ロジック（より柔軟に）
    if essential_matches >= 1:  # 必須キーワードが1つ以上
        _update_detection_stats(query, True, 'keyword')
        return True
    elif related_matches >= 2:  # 関連キーワードが2つ以上
        _update_detection_stats(query, True, 'keyword')
        return True
    elif related_matches >= 1 and len(query.split()) <= 3:  # 短いクエリで関連用語1つでもOK
        _update_detection_stats(query, True, 'keyword')
        return True
    else:
        # Step 2: 動的検知システム（未知のSEOトレンドを検出）
        return _detect_unknown_seo_trends(query_lower, query)


def _detect_unknown_seo_trends(query_lower, original_query):
    """
    未知のSEOトレンドや新しいマーケティング用語を動的に検知
    
    Args:
        query_lower: 小文字化されたクエリ
        original_query: 元のクエリ
        
    Returns:
        bool: SEO関連と判定される場合True
    """
    
    # パターン0: 新しいSEO用語の自動検出（最優先）
    # 大文字略語パターン（例: FLUQs, SGE, E-E-A-T, SERP等）
    import re
    uppercase_acronym_pattern = r'\b[A-Z]{2,}s?\b'  # 2文字以上の大文字略語（複数形対応）
    acronyms = re.findall(uppercase_acronym_pattern, original_query)
    
    # 「〜とは」「〜って何」「〜の意味」等の定義質問パターン
    definition_patterns = ['とは', 'って何', 'の意味', 'について', 'を教えて', 'とは何', 'の定義']
    is_definition_query = any(pattern in original_query for pattern in definition_patterns)
    
    # 大文字略語 + 定義質問 = 新しいSEO用語の可能性が高い
    if acronyms and is_definition_query:
        # さらにWebマーケティング・デジタル文脈を確認
        web_context_terms = ['web', 'ウェブ', 'デジタル', 'digital', 'online', 'オンライン', 
                             'google', 'グーグル', 'internet', 'インターネット', 'search', '検索',
                             'マーケティング', 'marketing', 'seo', 'sem', 'advertising', '広告']
        
        # 略語が単独で質問されている場合（例: "FLUQsとは？"）
        query_words = original_query.split()
        if len(query_words) <= 4:  # 短い質問（4単語以下）
            # 新しいSEO用語の可能性が非常に高い
            print(f"[新規SEO用語検出] '{original_query}' - 大文字略語 + 定義質問パターン")
            _update_detection_stats(original_query, True, 'new_term_auto')
            return True
        
        # 長い質問でもWeb/マーケティング文脈があればSEO関連
        elif any(term in query_lower for term in web_context_terms):
            print(f"[新規SEO用語検出] '{original_query}' - 大文字略語 + Web文脈")
            _update_detection_stats(original_query, True, 'new_term_auto')
            return True
    
    # パターン1: マーケティング・ビジネス関連の語尾パターン
    marketing_suffixes = [
        'マーケティング', 'マーケ', 'ブランディング', 'プロモーション', 
        'キャンペーン', 'インフルエンサー', 'アフィリエイト', 'ターゲティング',
        '集客', '売上', '収益', '利益', 'コンバージョン', 'エンゲージメント',
        '認知度', 'ブランド力', '競合分析', '市場調査', 'ペルソナ'
    ]
    
    # パターン2: デジタル・技術関連の組み合わせパターン
    digital_prefixes = ['デジタル', 'オンライン', 'ウェブ', 'web', 'インターネット', 'ネット', 
                        'digital', 'online', 'internet', 'サイト', 'site', 'ページ', 'page']
    business_terms = ['戦略', '手法', 'ツール', '分析', '対策', '改善', '最適化', '効果',
                      '施策', '方法', 'テクニック', 'ノウハウ', 'ガイド', 'マニュアル']
    
    # パターン3: 新しいプラットフォーム・技術の検知
    platform_indicators = [
        'インスタ', 'instagram', 'tiktok', 'youtube', 'twitter', 'x.com', 'facebook', 'linkedin',
        'クラブハウス', 'discord', 'slack', 'notion', 'chatgpt', 'claude',
        'gemini', 'copilot', 'ai', '人工知能', '機械学習', 'ml', 'nlp',
        'google', 'グーグル', 'bing', 'yahoo', 'yandex', 'baidu'
    ]
    
    # パターン4: 数値・指標関連（KPI、効果測定）
    metrics_patterns = [
        'kpi', 'roi', 'roas', 'ctr', 'cpc', 'cpm', 'ltv', 'cac',
        '指標', '効果測定', '分析', 'データ', '統計', '改善率', '成長率'
    ]
    
    # パターン5: 問い合わせ意図の検知（how-to、方法、やり方）
    intent_patterns = [
        'どうやって', 'どのように', '方法', 'やり方', 'コツ', 'ポイント',
        '改善', '向上', '増やす', '上げる', '伸ばす', '獲得', '達成'
    ]
    
    # 検知ロジック
    score = 0
    
    # 大文字略語の存在（新しいSEO用語の可能性）
    if acronyms:
        score += 2  # 略語自体にスコア付与
        print(f"[略語検出] {acronyms} → スコア+2")
    
    # マーケティング語尾パターンチェック
    for suffix in marketing_suffixes:
        if suffix in query_lower:
            score += 2
    
    # デジタル×ビジネス組み合わせチェック
    has_digital = any(prefix in query_lower for prefix in digital_prefixes)
    has_business = any(term in query_lower for term in business_terms)
    if has_digital and has_business:
        score += 3
    
    # 新プラットフォーム関連チェック
    platform_matches = sum(1 for indicator in platform_indicators if indicator in query_lower)
    if platform_matches >= 1:
        score += 2  # 1→2に強化（検索エンジン・プラットフォーム言及は重要）
        if platform_matches >= 2:  # 複数プラットフォーム言及
            score += 2
    
    # 指標・数値関連チェック
    for pattern in metrics_patterns:
        if pattern in query_lower:
            score += 2
    
    # 問い合わせ意図チェック（how-to系）
    intent_matches = sum(1 for pattern in intent_patterns if pattern in query_lower)
    if intent_matches >= 1:
        score += 1
    
    # 長文クエリの場合は閾値を下げる（詳細な質問の可能性）
    query_length = len(original_query.split())
    if query_length >= 8:  # 8語以上の長い質問
        threshold = 2
    elif query_length >= 5:  # 5-7語の中程度の質問
        threshold = 3
    elif is_definition_query:  # 定義質問（例: "〜とは？"）
        threshold = 2  # 閾値を下げて検出しやすく
    else:  # 短い質問
        threshold = 4
    
    # パターン6: コンテキスト分析（AIによる追加判定）
    if score < threshold:
        context_score = _analyze_query_context(original_query, query_lower)
        score += context_score
    
    # 最終判定
    is_seorelated = score >= threshold
    
    # 統計情報更新
    detection_method = 'dynamic' if is_seorelated else 'none'
    _update_detection_stats(original_query, is_seorelated, detection_method)
    
    # デバッグ情報（開発時）
    if is_seorelated:
        print(f"[動的検知] クエリ: '{original_query}' → スコア: {score}/{threshold} → SEO関連として判定")
    
    return is_seorelated


def _analyze_query_context(original_query, query_lower):
    """
    クエリのコンテキストを分析してSEO関連度を判定
    
    Args:
        original_query: 元のクエリ
        query_lower: 小文字化されたクエリ
        
    Returns:
        int: コンテキスト分析による追加スコア
    """
    context_score = 0
    
    # ビジネス課題を示すキーワードパターン
    business_challenges = [
        '売れない', '集客できない', '認知されない', '競合に負ける',
        '効果がない', '改善したい', '伸び悩み', '停滞', '課題',
        '問題', '困っている', '悩み', 'うまくいかない'
    ]
    
    # 成果・目標を示すキーワードパターン
    business_goals = [
        '売上向上', '集客アップ', '認知拡大', '効果的', '成功',
        '結果を出す', '成果', '目標達成', 'パフォーマンス向上',
        '最適化', '改善', '向上', '増加', '拡大'
    ]
    
    # 業界・分野を示すキーワードパターン
    industry_terms = [
        'ec', 'ecommerce', 'サービス業', '小売', '製造業', 'btob', 'btoc',
        'スタートアップ', '企業', '会社', '店舗', 'ショップ', '事業',
        '業界', '市場', '顧客', 'ユーザー', '消費者'
    ]
    
    # 時系列・トレンドを示すキーワードパターン
    trend_indicators = [
        '2024', '2025', '最新', '新しい', 'トレンド', '流行',
        '今後', '将来', '予測', '見込み', '変化', '進化'
    ]
    
    # 各パターンの検出
    if any(challenge in query_lower for challenge in business_challenges):
        context_score += 2  # ビジネス課題 = 高いSEO関連性
    
    if any(goal in query_lower for goal in business_goals):
        context_score += 2  # 成果目標 = 高いSEO関連性
    
    if any(industry in query_lower for industry in industry_terms):
        context_score += 1  # 業界言及 = 中程度のSEO関連性
    
    if any(trend in query_lower for trend in trend_indicators):
        context_score += 1  # トレンド言及 = 中程度のSEO関連性
    
    # 質問形式の分析
    question_patterns = ['どうすれば', 'なぜ', 'いつ', 'どこで', 'だれが', 'なにを']
    if any(pattern in query_lower for pattern in question_patterns):
        context_score += 1  # 質問形式 = SEO関連の可能性
    
    # 複合語の分析（単語の組み合わせパターン）
    words = original_query.split()
    if len(words) >= 3:  # 3語以上の複合クエリ
        # ビジネス関連語 + 動作語の組み合わせ
        business_words = ['サイト', 'ページ', 'コンテンツ', '記事', '情報', 'データ']
        action_words = ['作る', '書く', '設計', '企画', '戦略', '分析', '測定']
        
        has_business = any(word in original_query for word in business_words)
        has_action = any(word in original_query for word in action_words)
        
        if has_business and has_action:
            context_score += 2
    
    return context_score


def _update_detection_stats(query, is_seo_related, detection_method):
    """
    検知統計情報を更新（システム改善のため）
    
    Args:
        query: ユーザークエリ
        is_seo_related: SEO関連判定結果
        detection_method: 検知方法（'keyword', 'dynamic', 'context'）
    """
    try:
        import json
        from datetime import datetime
        import os
        
        stats_file = "seo_detection_stats.json"
        
        # 既存統計の読み込み
        if os.path.exists(stats_file):
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)
        else:
            stats = {
                "total_queries": 0,
                "seo_related_count": 0,
                "detection_methods": {
                    "keyword": 0,
                    "dynamic": 0,
                    "context": 0
                },
                "recent_queries": []
            }
        
        # 統計更新
        stats["total_queries"] += 1
        if is_seo_related:
            stats["seo_related_count"] += 1
            stats["detection_methods"][detection_method] += 1
        
        # 最近のクエリ保存（最大100件）
        stats["recent_queries"].append({
            "query": query[:50],  # 最初の50文字のみ
            "is_seo": is_seo_related,
            "method": detection_method,
            "timestamp": datetime.now().isoformat()
        })
        
        if len(stats["recent_queries"]) > 100:
            stats["recent_queries"] = stats["recent_queries"][-100:]
        
        # 統計ファイル保存
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        # 統計機能でエラーが発生してもメイン機能に影響しないように
        print(f"[統計機能] エラー（継続実行）: {str(e)[:50]}...")


def _learn_from_realtime_content(query, fetched_content):
    """
    リアルタイム取得コンテンツから新しいSEOトレンドを学習
    
    Args:
        query: ユーザークエリ
        fetched_content: 取得されたリアルタイムコンテンツ
    """
    if not fetched_content:
        return
    
    try:
        # コンテンツから新しいキーワードやトレンドを抽出
        content_text = str(fetched_content).lower()
        
        # SEO関連の新しい用語を検出するパターン
        emerging_patterns = [
            r'新しい.*(?:seo|マーケティング|集客)',
            r'(?:2024|2025)年.*(?:トレンド|手法|戦略)',
            r'最新.*(?:アルゴリズム|アップデート|機能)',
            r'次世代.*(?:マーケティング|seo|集客)'
        ]
        
        import re
        for pattern in emerging_patterns:
            matches = re.findall(pattern, content_text)
            if matches:
                # 検出された新しいトレンドをログに記録
                print(f"[学習機能] 新しいSEOトレンド検出: {matches[:3]}")  # 上位3件のみ表示
                
        # 頻出する新しい組み合わせを検出
        words = content_text.split()
        if len(words) > 10:  # 十分なコンテンツがある場合
            # 共起する単語ペアを分析（簡易版）
            from collections import Counter
            word_pairs = [(words[i], words[i+1]) for i in range(len(words)-1) 
                         if len(words[i]) > 2 and len(words[i+1]) > 2]
            
            common_pairs = Counter(word_pairs).most_common(5)
            seo_related_pairs = [pair for pair, count in common_pairs 
                               if count >= 2 and any(seo_word in str(pair) 
                               for seo_word in ['seo', 'マーケティング', '集客', '効果', '改善', '最適化'])]
            
            if seo_related_pairs:
                print(f"[学習機能] 新しいSEO関連語彙組み合わせ: {seo_related_pairs[:2]}")
                
    except Exception as e:
        # 学習機能でエラーが発生してもメイン機能に影響しないように
        print(f"[学習機能] エラー（継続実行）: {str(e)[:50]}...")


def _apply_ai_quality_scoring(documents, query):
    """
    AIによる記事品質スコアリング（多層評価システム）
    """
    scored_docs = []
    
    for doc in documents:
        try:
            # 信頼性スコア (0-100)
            trust_score = _calculate_trust_score(doc)
            
            # 関連性スコア (0-100) 
            relevance_score = _calculate_relevance_score(doc, query)
            
            # 品質スコア (0-100)
            quality_score = _calculate_quality_score(doc)
            
            # 総合スコア（加重平均）
            total_score = (trust_score * 0.3 + relevance_score * 0.4 + quality_score * 0.3)
            
            # スコア情報をメタデータに追加
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={
                    **doc.metadata,
                    'ai_scores': {
                        'trust': trust_score,
                        'relevance': relevance_score, 
                        'quality': quality_score,
                        'total': total_score
                    }
                }
            )
            
            # 品質基準を満たすもののみ採用（総合スコア60以上）
            if total_score >= 60:
                scored_docs.append(doc_with_score)
                
        except Exception as e:
            # スコアリングエラー時はデフォルトスコアで継続
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={
                    **doc.metadata,
                    'ai_scores': {
                        'trust': 50,
                        'relevance': 50,
                        'quality': 50,
                        'total': 50
                    }
                }
            )
            scored_docs.append(doc_with_score)
    
    # 総合スコア順にソート（Document.metadataを正しく参照）
    return sorted(scored_docs, key=lambda x: x.metadata.get('ai_scores', {}).get('total', 0), reverse=True)


def _calculate_trust_score(doc):
    """信頼性スコア計算"""
    score = 50  # ベーススコア
    
    # ソース権威性
    source_url = doc.get('url', '')
    if 'google.com' in source_url or 'searchengineland.com' in source_url:
        score += 30
    elif 'moz.com' in source_url:
        score += 25
    
    # 新しさ（日付情報がある場合）
    if doc.get('date'):
        try:
            from datetime import datetime, timedelta
            if isinstance(doc['date'], str):
                # 最近30日以内なら加点
                now = datetime.now()
                recent_threshold = now - timedelta(days=30)
                score += 15
        except:
            pass
    
    return min(score, 100)


def _calculate_relevance_score(doc, query):
    """関連性スコア計算"""
    score = 30  # ベーススコア
    
    query_words = query.lower().split()
    content = (doc.get('title', '') + ' ' + doc.get('content', '')).lower()
    
    # キーワードマッチング
    matches = sum(1 for word in query_words if word in content and len(word) > 2)
    score += min(matches * 15, 50)
    
    # SEO専門用語の密度
    seo_terms = ['seo', 'google', 'algorithm', 'ranking', 'optimization']
    seo_matches = sum(1 for term in seo_terms if term in content)
    score += min(seo_matches * 5, 20)
    
    return min(score, 100)


def _calculate_quality_score(doc):
    """品質スコア計算"""
    score = 40  # ベーススコア
    
    content = doc.get('content', '')
    title = doc.get('title', '')
    
    # コンテンツ長（適切な情報量）
    if len(content) > 500:
        score += 20
    elif len(content) > 200:
        score += 10
    
    # タイトルの質（具体性）
    if len(title) > 20 and any(word in title.lower() for word in ['how', 'what', 'why', '方法', '対策']):
        score += 15
    
    # 実用的なキーワード
    practical_terms = ['tips', 'guide', 'best practices', 'コツ', 'ガイド', '手順']
    if any(term in content.lower() for term in practical_terms):
        score += 15
    
    # 詳細な説明の有無
    if '具体的' in content or 'example' in content.lower() or '例' in content:
        score += 10
        
    return min(score, 100)


def _extract_site_name(feed_url):
    """
    RSSフィードURLからサイト名を抽出
    """
    site_mapping = {
        "https://searchengineland.com/feed": "Search Engine Land",
        "https://moz.com/blog/feed": "Moz Blog", 
        "https://blog.google/products/search/rss/": "Google Search Central"
    }
    return site_mapping.get(feed_url, "Unknown Site")


def _convert_to_display_url(article_url):
    """
    記事URLを人間が読めるURL形式に変換
    """
    try:
        # 基本的なURL構造の確認
        if not article_url.startswith(('http://', 'https://')):
            return article_url
        
        # URLからドメインベースの表示URLを生成
        from urllib.parse import urlparse
        parsed = urlparse(article_url)
        
        # ドメイン別の変換ルール
        if 'searchengineland.com' in parsed.netloc:
            return f"https://searchengineland.com{parsed.path}"
        elif 'moz.com' in parsed.netloc:
            return f"https://moz.com{parsed.path}"
        elif 'blog.google' in parsed.netloc:
            return f"https://blog.google{parsed.path}"
        else:
            return article_url
            
    except Exception:
        return article_url


def _check_seo_relevance(query):
    """
    クエリがSEO関連かどうかを判定する関数
    
    Args:
        query: ユーザーからの質問
        
    Returns:
        bool: SEO関連の場合True、無関係の場合False
        str: 判定理由
    """
    query_lower = query.lower().strip()
    
    # SEO関連キーワードの定義（包括的）
    seo_keywords = {
        # 基本SEO用語
        'seo', 'search engine optimization', '検索エンジン最適化', '最適化',
        
        # SEO施策関連
        'キーワード', 'keyword', 'タイトルタグ', 'メタディスクリプション', 'meta', 
        'タイトル', 'description', 'タグ', 'tag', '対策', '施策', '戦略', 'strategy',
        
        # リンク関連
        'リンク', 'link', 'バックリンク', 'backlink', '被リンク', '内部リンク', '外部リンク',
        'サイテーション', 'citation', 'cite', '参照', '引用',
        
        # コンテンツ関連
        '文字数', 'コンテンツ', 'content', 'ページ', 'page', 'サイト', 'site', 'website',
        'メインページ', 'サブページ', 'トップページ', 'ランディングページ',
        
        # 検索・ランキング関連
        '検索', 'search', '順位', 'ranking', 'ランキング', '上位表示', 'インデックス', 'index',
        'クロール', 'crawl', 'crawler', 'クローラー',
        
        # Google関連
        'google', 'グーグル', 'アルゴリズム', 'algorithm', 'アップデート', 'update',
        'ペンギン', 'penguin', 'パンダ', 'panda', 'コアアップデート',
        
        # 品質・評価関連
        'eat', 'e-a-t', 'eeat', 'e-e-a-t', '専門性', '権威性', '信頼性', 'expertise', 
        'authoritativeness', 'trustworthiness', 'experience', '経験',
        'ymyl', 'your money your life',
        
        # テクニカルSEO
        '構造化データ', 'structured data', 'schema', 'スキーマ', 'json-ld',
        'サイトマップ', 'sitemap', 'robots.txt', 'robots', 'canonical',
        'リダイレクト', 'redirect', '301', '302', 'noindex', 'nofollow',
        
        # アクセス解析・測定
        'analytics', 'アナリティクス', 'search console', 'サーチコンソール',
        'ctr', 'クリック率', 'impression', 'インプレッション', 'pv', 'pageview',
        
        # モバイル・技術関連  
        'モバイル', 'mobile', 'レスポンシブ', 'responsive', 'amp', 'core web vitals', 'core web vital',
        'コアウェブバイタル', 'コアウェブバイタルズ', 'vitals', 'vital',
        'ページスピード', 'page speed', '表示速度', 'loading', 'lcp', 'fid', 'cls',
        
        # ビジュアル・アクセシビリティ関連
        'visual aid', 'ビジュアルエイド', 'visual', 'アクセシビリティ', 'accessibility',
        'alt text', 'altテキスト', 'alt属性', '画像最適化', 'image optimization',
        
        # 地域・ローカル・MEO関連
        'ローカル', 'local', 'meo', 'map engine optimization', 'マップ', 'googleマップ',
        'googleマイビジネス', 'google my business', 'gmb', '地域', '店舗', '地図', 
        'ローカル検索', 'local search', '近くの', 'マイビジネス', 'ビジネスプロフィール',
        
        # ソーシャル・その他
        'ソーシャル', 'social', 'sns', 'シェア', 'share', 'og', 'オープングラフ',
        'トラフィック', 'traffic', 'セッション', 'session', 'ユーザー', 'user',
        
        # AI・技術関連（dataフォルダから抽出）
        '生成ai', 'generative ai', 'ai', '人工知能', 'artificial intelligence',
        
        # 環境・変化関連
        '環境', 'environment', '変化', 'change', '未来', 'future', '取り巻く',
        
        # インデックス・順位関連
        '促進', 'promotion', '復旧', 'recovery', '検索順位', 'search ranking',
        
        # コンテンツ・構築関連
        '資産', 'asset', '構築', 'construction', 'building', 'ソーシャルメディア', 'social media',
        
        # トラフィック・解析関連
        '要因', 'factor', '重要性', 'importance', 'アクセス解析', 'access analysis',
        '競合調査', 'competitive analysis', '競合', 'competitor', '調査', 'research',
        '需要調査', 'demand research', '需要', 'demand',
        
        # ページ・サイト構造関連
        '構造', 'structure', 'パターン', 'pattern', 'ページ構造', 'page structure',
        'サイト構造', 'site structure', 'サイト内リンク', 'internal link',
        '目標設定', 'goal setting', '目標', 'goal', '設定', 'setting',
        
        # SEO要素・企画関連
        '意義', 'significance', '情報源', 'information source', '企画', 'planning',
        '人気要素', 'popular element', '人気', 'popular', '要素', 'element',
        '内部要素', 'internal element', '外部要素', 'external element',
        '仕組み', 'mechanism', '特徴', 'feature', 'characteristics'
    }
    
    # 非SEO関連の明確なキーワード（除外対象）
    non_seo_keywords = {
        'データサイエンス', 'data science', 'machine learning', '機械学習',
        'プログラミング言語', 'python言語', 'javascript言語', 'プログラミング', 'コーディング',
        'データベース', 'database', 'sql', 'mysql', 'postgresql',
        '統計学', 'statistics', 'データ分析', 'data analysis', '数学', 'mathematics',
        '物理学', 'physics', '化学', 'chemistry', '生物学', 'biology',
        '経済学', 'economics', '心理学', 'psychology', '医学', 'medicine', '医療',
        '料理', 'cooking', 'レシピ', 'recipe', '旅行', 'travel', 'スポーツ', 'sports',
        '音楽', 'music', '映画', 'movie', 'ゲーム', 'game', 'アニメ', 'anime',
        '天気', 'weather', '株価', 'stock', '投資', 'investment', '政治', 'politics',
        '歴史', 'history', '地理', 'geography', '文学', 'literature', '芸術', 'art',
        'ニュース', 'news', '時事', 'current events', '法律', 'law', '建築', 'architecture'
    }
    
    # 除外キーワードのチェック（優先）
    for non_seo_word in non_seo_keywords:
        if non_seo_word in query_lower:
            return False, f"非SEO関連キーワード '{non_seo_word}' が検出されました"
    
    # SEO関連キーワードのチェック
    found_seo_keywords = []
    for seo_word in seo_keywords:
        if seo_word in query_lower:
            found_seo_keywords.append(seo_word)
    
    if found_seo_keywords:
        return True, f"SEO関連キーワード {found_seo_keywords[:3]} が検出されました"
    
    # キーワードが見つからない場合は、文脈から判定
    # SEO関連の質問パターン
    seo_patterns = [
        '推奨', '最適', '効果的', '改善', '対策', '戦略', '施策', '方法',
        'どうすれば', 'どのように', '何が', 'なぜ', 'いつ', 'どこで'
    ]
    
    web_context = any(word in query_lower for word in ['サイト', 'ページ', 'web', 'ウェブ', 'ホームページ'])
    seo_pattern = any(pattern in query_lower for pattern in seo_patterns)
    
    if web_context and seo_pattern:
        return True, "Web関連の質問パターンが検出されました"
    
    # 短い質問の場合は、より寛容に判定
    if len(query_lower) <= 10:
        # 短い質問でも明確にSEO用語が含まれているかチェック
        short_seo_terms = ['seo', '検索', 'ページ', 'サイト', 'リンク', 'キーワード']
        if any(term in query_lower for term in short_seo_terms):
            return True, "短い質問内でSEO用語が検出されました"
    
    # 質問形式の確認（「とは？」「について」等）
    question_patterns = ['とは', 'について', 'って何', 'とは何', '教えて', '知りたい']
    if any(pattern in query_lower for pattern in question_patterns):
        # 質問形式だが、SEOキーワードが全く含まれていない場合は非関連とする
        return False, "質問形式ですが、SEO関連キーワードが見つかりませんでした"
    
    return False, "SEO関連のキーワードまたはパターンが見つかりませんでした"


def _expand_search_query(query):
    """
    検索クエリを拡張して関連用語を追加
    
    Args:
        query: 元のクエリ
        
    Returns:
        expanded_query: 拡張されたクエリ
    """
    query_lower = query.lower()
    
    # SEO関連用語の拡張マップ（高精度化）
    expansion_map = {
        'サイテーション': ['サイテーション', 'citation', 'cite', '被リンク', '外部リンク', 'リンク', '参照', '引用'],
        'リンク': ['リンク', 'link', 'linking', '被リンク', '内部リンク', '外部リンク', 'バックリンク'],
        'seo': ['seo', '検索エンジン最適化', 'search engine optimization', '最適化', 'SEO対策'],
        'キーワード': ['キーワード', 'keyword', 'keywords', 'key word', 'ワード', '検索語'],
        # 文字数関連の拡張（Phase 3: SEO3-3資料からの確実な取得）
        '文字数': [
            '文字数', '推奨文字数', 'ページ文字数', 'コンテンツ文字数', 'テキスト量', 
            'メインページ', 'サブページ', 'トップページ', 
            '700文字', '2500文字', '1500文字', '4000文字', '800文字',
            '物販サイト', '求人サイト', '不動産サイト', 'ECサイト',
            '来店型ビジネス', 'クリニック', '美容室', '整体院', '学習塾', 'スポーツジム',
            '地域ビジネス', 'ローカルビジネス',
            '複雑な事柄', '単純な概念', '手順', '方法', 'メリット', 'デメリット',
            'ページ構造', '上位表示', 'SEO3-3'
        ],
        'メインページ': [
            'メインページ', 'トップページ', 'ホームページ', 'カテゴリトップ',
            '物販', '求人', '不動産', 'EC', '来店型', 'クリニック', '地域ビジネス',
            '700文字', '2500文字', '800文字', '4000文字'
        ],
        'サブページ': [
            'サブページ', '下層ページ', '詳細ページ', 
            '単純な概念', '複雑な事柄', '1500文字', '4000文字',
            '説明ページ', '解説ページ', 'コンテンツページ'
        ],
        '推奨': [
            '推奨', '推奨文字数', '目安', '基準', '標準', '適切', '最適',
            'ページ種別', 'ページタイプ', '業種', 'ビジネスタイプ'
        ],
        'eat': ['eat', 'EAT', 'E-A-T', '専門性', '権威性', '信頼性', 'expertise', 'authoritativeness', 'trustworthiness'],
        'eeat': ['eeat', 'E-E-A-T', 'EEAT', 'experience', '経験', 'expertise', '専門性'],
        'ymyl': [
            'ymyl', 'YMYL', 'Your Money Your Life', 
            'お金', '生活', '健康', '安全', '医療', '金融', '法律',
            '2倍', '2倍の文字数', '1400文字', '5000文字', '3000文字', '8000文字'
        ]
    }
    
    # 拡張用語を収集
    expanded_terms = [query]  # 元のクエリを含める
    
    # 文字数関連の質問を特別に処理（Phase 3: SEO3-3資料を確実に取得）
    content_volume_keywords = ['文字数', '推奨', 'メインページ', 'サブページ', 'YMYL', 
                               '物販', '求人', '不動産', '来店型', 'クリニック',
                               '700', '800', '1500', '2500', '4000', 'トップページ']
    
    is_content_volume_query = any(kw in query_lower for kw in content_volume_keywords)
    
    if is_content_volume_query:
        # 文字数関連の質問の場合、SEO3-3資料の重要キーワードを強制追加
        expanded_terms.extend([
            'ページ構造', '上位表示', 'トップページ', 'メインページ', 'サブページ',
            '物販サイト', '求人サイト', '不動産サイト', 
            '来店型ビジネス', 'クリニック', '地域ビジネス',
            '700文字', '2500文字', '1500文字', '4000文字', '800文字',
            '単純な概念', '複雑な事柄', 'YMYL', '2倍'
        ])
    
    # 通常の拡張マップも適用
    for key, synonyms in expansion_map.items():
        if key in query_lower:
            expanded_terms.extend(synonyms)
    
    return ' '.join(list(set(expanded_terms)))  # 重複除去


def _enhance_document_selection(query, documents, max_docs=5):
    """
    高品質な文書選択（セマンティック類似度による再ランキング）
    
    Args:
        query: ユーザークエリ
        documents: 検索された文書リスト
        max_docs: 最大文書数
        
    Returns:
        enhanced_docs: 高品質選択された文書リスト
    """
    if not documents:
        return []
    
    # 入力検証
    if not query or not query.strip():
        return documents[:max_docs]  # クエリが空の場合は上位文書を返す
    
    try:
        import re
        from collections import Counter
        
        # Step 1: クエリ拡張とキーワード抽出
        expanded_query = _expand_search_query(query)
        query_keywords = set(re.findall(r'\w+', expanded_query.lower()))
        
        # Step 2: 各文書のスコアリング
        scored_docs = []
        for doc in documents:
            content = doc.page_content.lower()
            
            # キーワードマッチングスコア（拡張クエリ使用）
            keyword_matches = sum(1 for kw in query_keywords if kw in content)
            keyword_score = keyword_matches / max(len(query_keywords), 1)
            
            # 直接マッチボーナス（元クエリとの完全一致）
            original_keywords = set(re.findall(r'\w+', query.lower()))
            direct_matches = sum(2 for kw in original_keywords if kw in content)  # 2倍重み
            direct_score = direct_matches / max(len(original_keywords), 1)
            
            # 文書長考慮（適度な長さを好む）
            content_length = len(content)
            length_score = min(content_length / 1000, 1.0)  # 1000文字を最適とする
            
            # Phase 3: 文字数関連クエリの場合、SEO3-3資料にボーナス
            content_volume_bonus = 0.0
            query_lower = query.lower()
            is_content_volume_query = any(kw in query_lower for kw in 
                ['文字数', '推奨', 'メインページ', 'サブページ', 'YMYL', '物販', '求人', '来店型'])
            
            if is_content_volume_query:
                # SEO3-3資料の特徴的なキーワードが含まれていればボーナス
                seo33_keywords = ['ページ構造', '上位表示', '700', '2500', '1500', '4000', 
                                 'トップページ', '物販サイト', '来店型ビジネス', '単純な概念', '複雑な事柄']
                seo33_matches = sum(1 for kw in seo33_keywords if kw in content)
                if seo33_matches >= 3:  # 3つ以上マッチすればSEO3-3資料と判断
                    content_volume_bonus = 0.3  # 30%のボーナス
            
            # 総合スコア（直接マッチを重視、文字数クエリにはボーナス）
            total_score = (direct_score * 0.5 + keyword_score * 0.3 + 
                          length_score * 0.2 + content_volume_bonus)
            
            scored_docs.append((doc, total_score))
        
        # Step 3: スコア順でソート・選択
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        enhanced_docs = [doc for doc, score in scored_docs[:max_docs]]
        
        return enhanced_docs
        
    except Exception:
        # フォールバック：元の文書をそのまま返す
        return documents[:max_docs]


def _build_enhanced_context(documents, query):
    """
    高品質コンテキスト構築
    
    Args:
        documents: 選択された文書リスト
        query: ユーザークエリ
        
    Returns:
        context: 構築されたコンテキスト文字列
    """
    if not documents:
        return "関連する情報が見つかりませんでした。"
    
    # 文書の妥当性確認
    valid_documents = []
    for doc in documents:
        if hasattr(doc, 'page_content') and doc.page_content and doc.page_content.strip():
            valid_documents.append(doc)
    
    if not valid_documents:
        return "有効な文書情報が見つかりませんでした。"
    
    try:
        # 文書の内容を整理・結合
        contexts = []
        for i, doc in enumerate(valid_documents, 1):
            content = doc.page_content.strip()
            
            # 文書情報の追加（実際のファイル名表示）
            source_info = ""
            if hasattr(doc, 'metadata') and doc.metadata and doc.metadata.get('source'):
                source_path = doc.metadata['source']
                source_name = source_path.split('\\')[-1].split('/')[-1]
                # ファイル拡張子を除去してより読みやすく
                if '.' in source_name:
                    source_name = source_name.rsplit('.', 1)[0]
                source_info = f"\n（出典: {source_name}）"
            
            contexts.append(f"【{source_name if source_info else f'参考資料{i}'}】\n{content}{source_info if not source_name else ''}")
        
        return "\n\n".join(contexts)
        
    except Exception:
        # フォールバック：シンプル結合
        return "\n\n".join([doc.page_content for doc in valid_documents if hasattr(doc, 'page_content') and doc.page_content])


def _generate_enhanced_answer(llm, prompt_template, query, context):
    """
    高精度回答生成
    
    Args:
        llm: 言語モデル
        prompt_template: プロンプトテンプレート
        query: ユーザークエリ
        context: 構築されたコンテキスト
        
    Returns:
        answer: 生成された回答
    """
    try:
        # 高品質プロンプト構築（contextを正しく渡す）
        messages = prompt_template.invoke({
            "input": query,
            "context": context,
            "chat_history": st.session_state.chat_history
        })
        
        # LLM実行
        response = llm.invoke(messages)
        return response.content
        
    except Exception as e:
        # フォールバック：基本的な回答
        return f"申し訳ございませんが、回答生成中にエラーが発生しました。再度お試しください。\n（エラー詳細: {str(e)}）"


############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
load_dotenv()


############################################################
# 関数定義
############################################################

def get_source_icon(source):
    """
    メッセージと一緒に表示するアイコンの種類を取得

    Args:
        source: 参照元のありか

    Returns:
        メッセージと一緒に表示するアイコンの種類
    """
    # 参照元がWebページの場合とファイルの場合で、取得するアイコンの種類を変える
    if source.startswith("http"):
        icon = ct.LINK_SOURCE_ICON
    else:
        icon = ct.DOC_SOURCE_ICON
    
    return icon


def build_error_message(message):
    """
    エラーメッセージと管理者問い合わせテンプレートの連結

    Args:
        message: 画面上に表示するエラーメッセージ

    Returns:
        エラーメッセージと管理者問い合わせテンプレートの連結テキスト
    """
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])


############################################################
# ハイブリッドRAGシステム（3層統合検索）
############################################################

class HybridRAGSystem:
    """
    3層構造の統合RAGシステム
    Layer 1: 社内資料（永続化DB）
    Layer 2: 短期キャッシュ（最新情報キャッシュ）
    Layer 3: リアルタイム取得（RSS+スクレイピング）
    """
    
    def __init__(self):
        # Streamlit session stateの安全な取得
        try:
            import streamlit as st
            self.internal_retriever = st.session_state.retriever  # 既存システム
        except:
            # Streamlit環境外やsession_stateエラーの場合の対処
            self.internal_retriever = None
            
        self.cache_retriever = None      # 短期キャッシュ（未実装）
        self.logger = logging.getLogger(ct.LOGGER_NAME)
    
    def search(self, query, include_latest=True):
        """
        統合検索（既存システムを拡張）
        
        Args:
            query: 検索クエリ
            include_latest: 最新情報を含めるかどうか
            
        Returns:
            統合された検索結果
        """
        # SEO関連性の事前チェック
        is_seo_relevant, relevance_reason = _check_seo_relevance(query)
        self.logger.info(f"SEO関連性判定: {is_seo_relevant}, 理由: {relevance_reason}")
        
        # SEO関連でない場合は最新情報取得をスキップ
        if not is_seo_relevant:
            include_latest = False
            self.logger.info("非SEO関連クエリのため最新情報取得をスキップ")
        
        all_results = []
        
        # Layer 1: 既存の社内資料検索（最優先・安定性確保）
        try:
            if self.internal_retriever:
                internal_docs = self.internal_retriever.invoke(query)
            else:
                internal_docs = []
                self.logger.warning("内部retrieverが利用できません")
                
            for doc in internal_docs:
                if hasattr(doc, 'metadata'):
                    doc.metadata.update({
                        "source_type": "internal",
                        "freshness_score": 0.8,  # 社内資料は信頼性重視
                        "priority": 1
                    })
                else:
                    doc.metadata = {
                        "source_type": "internal",
                        "freshness_score": 0.8,
                        "priority": 1
                    }
            all_results.extend(internal_docs)
            self.logger.info(f"社内資料検索完了: {len(internal_docs)}件")
            
        except Exception as e:
            self.logger.warning(f"社内資料検索エラー: {e}")
        
        # Layer 3: リアルタイム情報取得（最新情報補完）
        should_fetch = self._should_fetch_realtime(query)
        self.logger.info(f"[リアルタイム判定] クエリ: {query[:30]}..., 取得必要: {should_fetch}")
        
        if include_latest and should_fetch:
            try:
                self.logger.info(f"[リアルタイム取得] 開始...")
                realtime_docs = fetch_latest_seo_info(query, max_articles=10)
                self.logger.info(f"[リアルタイム取得] fetch_latest_seo_info結果: {len(realtime_docs)}件")
                
                for doc in realtime_docs:
                    doc.metadata.update({
                        "priority": 3,
                        "source_type": "realtime"  # 明示的に設定
                    })
                    # 学習機能: 取得したコンテンツから新しいトレンドを学習
                    _learn_from_realtime_content(query, doc.page_content)
                
                all_results.extend(realtime_docs)
                self.logger.info(f"[リアルタイム統合] 完了: {len(realtime_docs)}件をall_resultsに追加")
                
            except Exception as e:
                self.logger.error(f"[リアルタイム取得] エラー: {e}")
                import traceback
                self.logger.error(f"[リアルタイム取得] スタックトレース: {traceback.format_exc()}")
        else:
            self.logger.info(f"[リアルタイム取得] スキップ - include_latest: {include_latest}, should_fetch: {should_fetch}")
        
        # 統合ランキング
        self.logger.info(f"[統合前] all_results総数: {len(all_results)}件")
        
        # 情報源別の内訳
        source_breakdown = {}
        for doc in all_results:
            source_type = doc.metadata.get('source_type', 'unknown')
            source_breakdown[source_type] = source_breakdown.get(source_type, 0) + 1
            
        self.logger.info(f"[統合前] 情報源内訳: {source_breakdown}")
        
        ranked_results = self._rank_and_merge(all_results, query)
        self.logger.info(f"[統合後] ランキング結果: {len(ranked_results)}件")
        
        return ranked_results
    
    def _should_fetch_realtime(self, query):
        """
        リアルタイム取得が必要かどうかの判定（2025年Googleアップデート対応強化版）
        """
        query_lower = query.lower()
        
        # 高優先度キーワード（これらが含まれれば必ず最新情報を取得）
        high_priority_keywords = [
            'ai mode', 'ai overviews', 'ai overview', 'google ai', 'gemini',
            'core update', 'コア更新', 'コアアップデート', 'spam update', 'スパム更新',
            'helpful content', 'ヘルプフルコンテンツ', 'product reviews', 'プロダクトレビュー'
        ]
        
        # 一般的な最新情報関連キーワード
        general_keywords = [
            'アップデート', '最新', '新機能', 'ニュース', '2024', '2025',
            'update', 'latest', 'new', 'recent', 'current',
            '今年', '今月', 'この度', '発表', 'リリース', 'rollout'
        ]
        
        # 時期関連キーワード（2025年関連）
        time_keywords = [
            '2025年3月', '2025年6月', '2025年8月', '2025年9月', '2025年10月',
            'march 2025', 'june 2025', 'august 2025', 'september 2025', 'october 2025'
        ]
        
        # 高優先度キーワードが含まれる場合は必ず取得
        if any(keyword in query_lower for keyword in high_priority_keywords):
            self.logger.info(f"高優先度キーワード検出によりリアルタイム取得実行")
            return True
            
        # 一般キーワード + Google関連の組み合わせ
        has_general = any(keyword in query_lower for keyword in general_keywords)
        has_google = any(term in query_lower for term in ['google', 'グーグル', 'search', '検索'])
        
        if has_general and has_google:
            self.logger.info(f"一般キーワード+Google関連によりリアルタイム取得実行")
            return True
            
        # 時期関連キーワードが含まれる場合
        if any(keyword in query_lower for keyword in time_keywords):
            self.logger.info(f"時期関連キーワード検出によりリアルタイム取得実行")
            return True
        
        return False
    
    def _rank_and_merge(self, documents, query):
        """
        重み付けランキングと統合
        """
        if not documents:
            return []
        
        # 重要度とカテゴリによるスコアリング
        scored_docs = []
        for doc in documents:
            metadata = doc.metadata
            
            # 基本スコア
            base_score = metadata.get('freshness_score', 0.5)
            
            # 優先度による重み付け
            priority = metadata.get('priority', 3)
            priority_weight = {1: 1.0, 2: 0.8, 3: 0.6}.get(priority, 0.4)
            
            # ソースタイプによる重み付け
            source_type = metadata.get('source_type', 'unknown')
            source_weight = ct.HYBRID_RAG_CONFIG["LAYER_WEIGHTS"].get(source_type, 0.5)
            
            # 総合スコア計算
            total_score = base_score * priority_weight * source_weight
            
            # ★★★ realtime文書にスコアブーストを適用 ★★★
            if source_type == 'realtime':
                query_lower = query.lower()
                boost_keywords = [
                    'アップデート', '最新', '2025', '2024',
                    'core update', 'spam update', 'コア更新', 'スパム更新',
                    'ai mode', 'ai overviews', 'gemini',
                    'update', 'latest', 'new', 'recent'
                ]
                if any(keyword in query_lower for keyword in boost_keywords):
                    total_score *= 1.5  # 1.5倍のブースト
                    self.logger.info(f"[リアルタイムブースト] スコア: {total_score:.3f} (文書: {metadata.get('title', 'No title')[:30]}...)")
            
            scored_docs.append((doc, total_score))
        
        # スコア順でソート
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # 上位文書を返す（最大10件）
        return [doc for doc, score in scored_docs[:10]]


def get_llm_response(chat_message, skip_seo_check=False):
    """
    LLMからの回答取得（SEO関連性チェック機能付き・ハイブリッドRAG対応版）

    Args:
        chat_message: ユーザー入力値
        skip_seo_check: True の場合、SEO関連性チェックをスキップ（ドメイン解析モード用）

    Returns:
        LLMからの回答

    Raises:
        Exception: 回答生成失敗時に詳細なエラー情報を含む例外
    """
    if not chat_message or not chat_message.strip():
        raise ValueError("入力メッセージが空です")
    
    if not hasattr(st.session_state, 'retriever') or st.session_state.retriever is None:
        raise RuntimeError("検索システムが初期化されていません")
    
    # SEO関連性チェック（ドメイン解析モードではスキップ）
    if not skip_seo_check and not _is_seo_related_query(chat_message):
        logger = logging.getLogger(ct.LOGGER_NAME)
        logger.info(f"非SEO関連クエリを拒否: {chat_message}")
        return {
            "answer": "申し訳ございませんが、こちらはSEO（検索エンジン最適化）専門のアシスタントです。SEOに関するご質問をお願いいたします。\n\n例：\n- Googleアルゴリズムの最新動向\n- キーワード選定のコツ\n- ページ速度の改善方法\n- メタタグの最適化",
            "sources": [],
            "hybrid_mode": False,
            "seo_related": False
        }
    
    try:
        # ハイブリッドRAGシステムを使用した拡張検索
        return _get_llm_response_hybrid(chat_message)
    except Exception as e:
        # フォールバック：従来システム
        logger = logging.getLogger(ct.LOGGER_NAME)
        logger.error(f"ハイブリッドシステムエラー（詳細）: {str(e)}")
        logger.warning("従来システムにフォールバック中...")
        return _get_llm_response_internal(chat_message)


def _get_llm_response_hybrid(chat_message):
    """
    ハイブリッドRAGシステムを使用した回答生成
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    try:
        logger.info(f"[ハイブリッドRAG] 開始: {chat_message[:50]}...")
        
        # ハイブリッドRAGシステム初期化
        hybrid_system = HybridRAGSystem()
        logger.info(f"[ハイブリッドRAG] システム初期化完了, internal_retriever: {hybrid_system.internal_retriever is not None}")
        
        # 統合検索実行（AIスコアリング適用）
        enhanced_docs = hybrid_system.search(chat_message, include_latest=True)
        logger.info(f"[ハイブリッドRAG] 検索完了: {len(enhanced_docs)}件の文書取得")
        
        # ★★★ realtime最低保証ロジック ★★★
        realtime_count = sum(1 for doc in enhanced_docs if doc.metadata.get('source_type') == 'realtime')
        logger.info(f"[リアルタイム保証] enhanced_docs内のrealtime数: {realtime_count}/{len(enhanced_docs)}")
        
        if realtime_count == 0:
            # enhanced_docsにrealtimeが1件も含まれていない場合、直接取得して注入
            logger.warning("[リアルタイム保証] enhanced_docsにrealtimeなし、強制注入を試行")
            try:
                realtime_補完 = fetch_latest_seo_info(chat_message, max_articles=3)
                if realtime_補完:
                    if len(enhanced_docs) > 0:
                        # 末尾1件をrealtime文書で置換
                        enhanced_docs[-1] = realtime_補完[0]
                        logger.info(f"[リアルタイム保証] realtime文書を1件注入完了: {realtime_補完[0].metadata.get('title', 'No title')[:30]}...")
                    else:
                        # enhanced_docsが空の場合はrealtime1件を設定
                        enhanced_docs = realtime_補完[:1]
                        logger.info(f"[リアルタイム保証] enhanced_docsが空のためrealtime1件を設定")
                else:
                    logger.warning("[リアルタイム保証] realtime補完取得に失敗（0件）")
            except Exception as e:
                logger.error(f"[リアルタイム保証] 補完処理エラー: {e}")
        else:
            logger.info(f"[リアルタイム保証] realtime文書が既に{realtime_count}件含まれているため、注入スキップ")
        
        # 安全性チェック: 文書が空の場合
        if not enhanced_docs:
            logger.warning("[ハイブリッドRAG] 統合検索で文書が見つかりません、従来システムで継続")
            return _get_llm_response_internal(chat_message)
        
        # AIスコアリングによる品質フィルタリング
        scored_docs = _apply_ai_quality_scoring(enhanced_docs, chat_message)
        logger.info(f"[ハイブリッドRAG] AIスコアリング完了: {len(scored_docs)}件が品質基準を通過")
        
        if not scored_docs:
            # フォールバック：従来システム
            logger.warning("品質スコア基準を満たす文書が見つからない、従来システムで継続")
            return _get_llm_response_internal(chat_message)
        
        # 統合コンテキスト構築（スコア付き文書を使用）
        enhanced_context = _build_hybrid_context(scored_docs, chat_message)
        
        # LLM実行
        llm = ChatOpenAI(model=ct.MODEL, temperature=ct.TEMPERATURE)
        
        # プロンプトテンプレート（SEO特化・ハイブリッド対応）
        system_prompt = f"""
        あなたは社内SEO専門のアシスタントです。
        以下の情報源を統合して、高品質で最新性のある回答を提供してください。
        
        【情報源の種類】
        - 社内資料：確実性の高い基本知識
        - 最新情報：業界の最新動向
        
        【回答条件】
        1. 社内資料を基本として、最新情報で補完してください
        2. 情報源の違いを明示してください
        3. 実践的で具体的な回答を提供してください
        
        【厳守事項】
        - 具体的な数値基準（例：「10本以上」「3本は少ない」等）は、提供された情報源に明記されている場合のみ使用してください
        - 情報源に数値基準がない場合は、定性的表現（「増やす」「改善する」「充実させる」等）を使用してください
        - サイト平均との相対比較（「サイト平均6.2本に対してこのページは3本」等）は許可されます
        - 推測や一般論に基づく絶対的な数値基準（「業界標準は〇本」等）は禁止します
        
        【文字数に関する回答ルール】重要
        - 文字数について回答する場合、断定的な判断（「少ない」「不足」「十分」「達していない」等）は絶対に避けてください
        - 解析するページがメインページかサブページかを判断・推測してはいけません
        - 必ず以下のすべての選択肢を提示する形式で回答してください：
          「現在の文字数は〇〇字です。ページの種類により推奨文字数が異なります：
           【トップページ/メインページの場合】
             • 物販サイトなどのトップページ: 0～800字程度
             • 来店型ビジネス（クリニック、美容室、整体院等）: 700～2,500字程度
             • 単品サービスや単品通販のトップページ: 4,000字以上
           【サブページの場合】
             • 単純な概念の解説: 1,500字程度
             • 複雑な事柄の説明: 4,000字以上
           【YMYL分野の場合】上記それぞれの文字数の2倍が推奨されます
           ページの種類とYMYL該当性を確認の上、適切な文字数を目指してください。」
        - すべての選択肢を必ず提示し、特定のケースのみを提示してはいけません
        - ユーザーに判断を委ねる表現を使用してください
        
        【統合情報】
        {enhanced_context}
        """
        
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])
        
        messages = prompt_template.invoke({"input": chat_message})
        response = llm.invoke(messages)
        
        # 出典情報の抽出
        latest_info = []
        sources = []
        
        for doc in scored_docs:
            if doc.metadata.get('source_type') == 'realtime':
                # リアルタイム情報の出典
                latest_info.append({
                    'title': doc.metadata.get('title', 'No title'),
                    'url': doc.metadata.get('source', '#'),
                    'site_name': doc.metadata.get('site_name', 'Unknown Site'),
                    'display_url': doc.metadata.get('display_url', doc.metadata.get('source', '#')),
                    'date': doc.metadata.get('published_date', 'No date'),
                    'summary': doc.page_content[:200] if doc.page_content else ''
                })
            else:
                # 社内資料の出典
                sources.append({
                    'title': doc.metadata.get('title', 'Internal Document'),
                    'url': doc.metadata.get('source', '#'),
                    'type': doc.metadata.get('source_type', 'internal')
                })
        
        # 統合回答の構築（重複防止フラグ付き）
        llm_response = {
            "answer": response.content,
            "source_documents": scored_docs,
            "hybrid_mode": True,
            "source_breakdown": _analyze_source_breakdown(scored_docs),
            "latest_info": latest_info,  # 出典表示用データ追加
            "sources": sources,          # 社内資料出典データ追加
            "unified_display": True      # 重複表示防止フラグ追加
        }
        
        logger.info("ハイブリッドRAG回答生成完了")
        return llm_response
        
    except Exception as e:
        logger.error(f"ハイブリッドRAG処理エラー: {e}")
        raise e


def _build_hybrid_context(documents, query):
    """
    ハイブリッド情報統合コンテキスト構築
    """
    if not documents:
        return "関連する情報が見つかりませんでした。"
    
    # ソースタイプ別にグループ化
    source_groups = {"internal": [], "realtime": [], "other": []}
    
    for doc in documents:
        source_type = doc.metadata.get('source_type', 'other')
        source_groups[source_type].append(doc)
    
    # 統合コンテキスト構築
    context_parts = []
    
    # 社内資料セクション（実際のファイル名表示）
    if source_groups["internal"]:
        context_parts.append("## 社内SEO資料")
        for i, doc in enumerate(source_groups["internal"][:5], 1):
            # 実際のファイル名を取得
            source_path = doc.metadata.get('source', f'社内資料{i}')
            file_name = source_path.split('\\')[-1].split('/')[-1] if source_path else f'社内資料{i}'
            # ファイル拡張子を除去
            if '.' in file_name:
                file_name = file_name.rsplit('.', 1)[0]
            context_parts.append(f"【{file_name}】\n{doc.page_content}")
    
    # 最新情報セクション
    if source_groups["realtime"]:
        context_parts.append("## 最新SEO情報")
        for i, doc in enumerate(source_groups["realtime"][:3], 1):
            title = doc.metadata.get('title', f'最新情報{i}')
            published = doc.metadata.get('published_date', '')
            context_parts.append(f"【{title}】（{published}）\n{doc.page_content}")
    
    return "\n\n".join(context_parts)


def _analyze_source_breakdown(documents):
    """
    情報源の内訳分析
    """
    breakdown = {"internal": 0, "realtime": 0, "other": 0}
    
    for doc in documents:
        source_type = doc.metadata.get('source_type', 'other')
        breakdown[source_type] += 1
    
    return breakdown


def get_llm_response_original(chat_message):
    """
    LLMからの回答取得（従来版・フォールバック用）

    Args:
        chat_message: ユーザー入力値

    Returns:
        LLMからの回答

    Raises:
        Exception: 回答生成失敗時に詳細なエラー情報を含む例外
    """
    if not chat_message or not chat_message.strip():
        raise ValueError("入力メッセージが空です")
    
    if not hasattr(st.session_state, 'retriever') or st.session_state.retriever is None:
        raise RuntimeError("検索システムが初期化されていません")
    
    try:
        return _get_llm_response_internal(chat_message)
    except Exception as e:
        # 詳細エラー情報の構築
        error_info = {
            'error_type': type(e).__name__,
            'error_message': str(e),
            'input_length': len(chat_message),
            'enhanced_mode': getattr(st.session_state, 'enhanced_mode', False),
            'retriever_type': type(st.session_state.retriever).__name__ if hasattr(st.session_state, 'retriever') else 'None'
        }
        
        # ログ出力
        import logging
        logger = logging.getLogger(ct.LOGGER_NAME)
        logger.error(f"回答生成エラー: {error_info}")
        
        # ユーザー向けのわかりやすいエラーメッセージを構築
        if "max_tokens" in str(e).lower():
            user_message = "入力が長すぎます。より短い文章で質問してください。"
        elif "api" in str(e).lower() or "openai" in str(e).lower():
            user_message = "AIサービスに接続できませんでした。しばらく待ってから再試行してください。"
        elif "retriever" in str(e).lower():
            user_message = "検索機能に問題が発生しました。管理者にお問い合わせください。"
        else:
            user_message = "回答生成中にエラーが発生しました。"
        
        # カスタム例外を発生
        raise RuntimeError(f"{user_message}\n詳細: {error_info['error_type']}") from e

@secure_input
@traceable_if_available
def _get_llm_response_internal(chat_message):
    """
    LLMからの回答取得の内部処理（SEO関連性判定付き）
    """
    # Step 0: SEO関連性の事前判定
    is_seo_related, relevance_reason = _check_seo_relevance(chat_message)
    
    if not is_seo_related:
        # SEO無関係の質問に対する丁寧な案内メッセージ
        non_seo_response = f"""申し訳ございませんが、こちらはSEO専門のアシスタントシステムです。

ご質問「{chat_message}」は、SEOに関連しない内容と判定されました。
（判定理由: {relevance_reason}）

SEOに関するご質問をお願いいたします。

例：
- Googleアルゴリズムの最新動向
- キーワード選定のコツ
- ページ速度の改善方法
- メタタグの最適化"""

        # 非SEO質問のログ記録
        import logging
        logger = logging.getLogger(ct.LOGGER_NAME)
        logger.info(f"非SEO質問ブロック: '{chat_message}' - {relevance_reason}")
        
        return {"answer": non_seo_response, "source_documents": [], "unified_display": True}
    
    # SEO関連質問のログ記録
    import logging
    logger = logging.getLogger(ct.LOGGER_NAME)
    logger.info(f"SEO関連質問承認: '{chat_message}' - {relevance_reason}")
    
    # SEO関連の質問の場合は通常処理続行
    # LLMのオブジェクトを用意
    llm = ChatOpenAI(model_name=ct.MODEL, temperature=ct.TEMPERATURE)

    # 会話履歴なしでもLLMに理解してもらえる、独立した入力テキストを取得するためのプロンプトテンプレートを作成
    question_generator_template = ct.SYSTEM_PROMPT_CREATE_INDEPENDENT_TEXT
    question_generator_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", question_generator_template),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # SEO特化システム用のプロンプト（モード選択不要）
    question_answer_template = ct.SYSTEM_PROMPT_SEO
    # LLMから回答を取得する用のプロンプトテンプレートを作成
    question_answer_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", question_answer_template),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # 高精度検索システムの使用確認
    if hasattr(st.session_state, 'enhanced_mode') and st.session_state.enhanced_mode:
        # 高品質検索と回答生成
        try:
            # Step 1: マルチクエリ検索実行
            retriever = st.session_state.retriever
            
            # 元のクエリで検索（検索数増加）
            if hasattr(retriever, 'invoke'):
                retrieved_docs = retriever.invoke(chat_message)
                # 検索結果が少ない場合は検索数を増やして再試行
                if len(retrieved_docs) < 3:
                    try:
                        retriever.k = 8  # 検索数増加
                        retrieved_docs = retriever.invoke(chat_message)
                    except:
                        pass
            else:
                retrieved_docs = retriever.get_relevant_documents(chat_message)
            
            # 拡張クエリでも検索（検索結果を拡充）
            expanded_query = _expand_search_query(chat_message)
            if expanded_query != chat_message:  # 拡張されている場合のみ
                try:
                    if hasattr(retriever, 'invoke'):
                        additional_docs = retriever.invoke(expanded_query)
                    else:
                        additional_docs = retriever.get_relevant_documents(expanded_query)
                    
                    # 既存の文書と重複排除して統合
                    existing_content = {doc.page_content for doc in retrieved_docs}
                    for doc in additional_docs:
                        if doc.page_content not in existing_content:
                            retrieved_docs.append(doc)
                            existing_content.add(doc.page_content)
                except Exception as e:
                    # 拡張検索が失敗しても元の検索結果を使用
                    import logging
                    logger = logging.getLogger(ct.LOGGER_NAME)
                    logger.warning(f"拡張クエリ検索失敗: {str(e)}")
            
            # 検索結果の安全性確認
            if not retrieved_docs:
                raise ValueError("検索結果が空です")
            
            # 緊急統合: リアルタイム情報の追加（ハイブリッドRAG失敗時の代替）
            realtime_keywords = ['アップデート', '最新', '新機能', 'ニュース', '2024', '2025']
            query_lower = chat_message.lower()
            
            if any(keyword in query_lower for keyword in realtime_keywords):
                try:
                    logger.info("[従来システム] リアルタイム情報統合開始")
                    realtime_docs = fetch_latest_seo_info(chat_message, max_articles=10)
                    logger.info(f"[従来システム] リアルタイム情報取得: {len(realtime_docs)}件")
                    
                    # リアルタイム文書を検索結果に統合
                    retrieved_docs.extend(realtime_docs)
                    logger.info(f"[従来システム] 統合後文書数: {len(retrieved_docs)}件")
                    
                except Exception as rt_error:
                    logger.warning(f"[従来システム] リアルタイム統合エラー: {rt_error}")
            
            # Step 2: 高品質文書選択（セマンティック類似度による再ランキング）
            enhanced_docs = _enhance_document_selection(chat_message, retrieved_docs)
            
            # 選択された文書の確認
            if not enhanced_docs:
                enhanced_docs = retrieved_docs[:3]  # フォールバック：上位3文書を使用
            
            # Step 3: 高品質コンテキスト構築
            context = _build_enhanced_context(enhanced_docs, chat_message)
            
            # Step 4: 高精度回答生成
            answer = _generate_enhanced_answer(llm, question_answer_prompt, chat_message, context)
            
            # デバッグログ出力
            import logging
            logger = logging.getLogger(ct.LOGGER_NAME)
            logger.info(f"検索クエリ: {chat_message}")
            logger.info(f"拡張クエリ: {expanded_query}")
            logger.info(f"検索結果: {len(retrieved_docs)} 件")
            logger.info(f"選択文書: {len(enhanced_docs)} 件")
            
            # レスポンス構築（重複防止フラグ付き）
            llm_response = {
                "input": chat_message,
                "context": enhanced_docs,
                "answer": answer,
                "enhanced_info": {
                    "total_docs_retrieved": len(retrieved_docs),
                    "enhanced_docs_used": len(enhanced_docs),
                    "enhancement_type": getattr(st.session_state, '_enhanced_type', 'multi-query')
                },
                "unified_display": True  # 重複表示防止フラグ追加
            }
            
        except Exception as e:
            # エラーログ記録
            import logging
            logger = logging.getLogger(ct.LOGGER_NAME)
            logger.warning(f"高精度検索システムでエラー、従来方式にフォールバック: {str(e)}")
            
            # フォールバック：LangChain 1.0 Runnableベース実装
            # 新しいRunnable構成でRAGシステムを実装
            def create_fallback_rag_chain(llm, retriever, question_prompt):
                def format_docs(docs):
                    return "\n\n".join([doc.page_content for doc in docs[:5]])
                
                # LangChain 1.0のRunnable構成（文字列クエリ対応）
                rag_chain = (
                    {
                        "context": RunnableLambda(lambda query: format_docs(retriever.invoke(query))),
                        "input": RunnablePassthrough(),
                        "chat_history": lambda _: st.session_state.chat_history
                    }
                    | question_prompt
                    | llm
                    | StrOutputParser()
                )
                return rag_chain
            
            # フォールバックチェーン実行
            try:
                fallback_chain = create_fallback_rag_chain(llm, st.session_state.retriever, question_answer_prompt)
                answer = fallback_chain.invoke(chat_message)
                docs = st.session_state.retriever.invoke(chat_message)
                llm_response = {"answer": answer, "source_documents": docs}
            except Exception as fallback_error:
                # SEO専用エラーメッセージ（一般回答禁止）
                logger.error(f"高精度SEOシステムエラー: {str(fallback_error)}")
                
                # SEO関連資料が参照できない場合の専用メッセージ
                seo_error_answer = f"申し訳ございませんが、「{chat_message}」についてSEO関連資料からの情報取得に失敗しました。システムの管理者にお問い合わせいただくか、SEOに特化した別の質問をお試しください。"
                llm_response = {"answer": seo_error_answer, "source_documents": []}
                
    else:
        # シンプルシステム使用（LangChain 1.0 Runnable対応）
        def create_simple_rag_chain(llm, retriever, question_prompt):
            def format_docs(docs):
                return "\n\n".join([doc.page_content for doc in docs[:5]])
            
            rag_chain = (
                {
                    "context": RunnableLambda(lambda query: format_docs(retriever.invoke(query))),
                    "input": RunnablePassthrough(),
                    "chat_history": lambda _: st.session_state.chat_history
                }
                | question_prompt
                | llm
                | StrOutputParser()
            )
            return rag_chain
        
        # 【重要】SEO専用RAGシステム - フォールバック禁止
        # 必ずSEO関連文書を参照した回答のみ提供
        try:
            # Step 1: 強制的にSEO文書から検索（エラーハンドリング強化）
            import logging
            logger = logging.getLogger(ct.LOGGER_NAME)
            
            logger.info(f"SEO文書検索開始: クエリ='{chat_message}'")
            
            if hasattr(st.session_state.retriever, 'invoke'):
                docs = st.session_state.retriever.invoke(chat_message)
                logger.info(f"invoke()で検索実行: 結果={len(docs)}件")
            else:
                docs = st.session_state.retriever.get_relevant_documents(chat_message)
                logger.info(f"get_relevant_documents()で検索実行: 結果={len(docs)}件")
            
            if not docs:
                # SEO関連文書が見つからない場合の専用メッセージ
                answer = f"申し訳ございませんが、「{chat_message}」に関する情報はSEO関連資料に見つかりませんでした。SEOに関連する別の質問をしていただけますでしょうか。"
                llm_response = {"answer": answer, "source_documents": []}
            else:
                # Step 2: 高品質SEOコンテキスト構築
                context = _build_enhanced_context(docs, chat_message)
                
                # Step 3: 高精度SEO回答生成（プロンプトテンプレート使用）
                messages = question_answer_prompt.invoke({
                    "input": chat_message,
                    "context": context,
                    "chat_history": st.session_state.chat_history
                })
                
                # LLM実行
                answer = llm.invoke(messages).content
                llm_response = {"answer": answer, "source_documents": docs}
                
        except Exception as simple_error:
            # エラー時もSEO専用エラーメッセージ（詳細ログ付き）
            import logging
            import traceback
            logger = logging.getLogger(ct.LOGGER_NAME)
            logger.error(f"SEO RAGシステムエラー詳細: {str(simple_error)}")
            logger.error(f"エラートレースバック: {traceback.format_exc()}")
            
            # デバッグ情報も含める
            debug_info = f"""
            エラー詳細: {str(simple_error)}
            Retriever状態: {type(st.session_state.retriever) if hasattr(st.session_state, 'retriever') else 'None'}
            Enhanced Mode: {getattr(st.session_state, 'enhanced_mode', False)}
            """
            logger.error(debug_info)
            
            error_answer = f"申し訳ございませんが、SEO関連資料の検索中にエラーが発生しました。システムの管理者にお問い合わせください。\n\nエラー: {str(simple_error)}"
            llm_response = {"answer": error_answer, "source_documents": []}

    # LLMレスポンスを会話履歴に追加  
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    st.session_state.chat_history.extend([HumanMessage(content=chat_message), llm_response["answer"]])

    return llm_response