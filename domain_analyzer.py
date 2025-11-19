"""
ドメインSEO解析モジュール
指定ドメインを軽量クロールしてSEO要素を分析
"""

############################################################
# ライブラリの読み込み
############################################################
import logging
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from langchain_openai import ChatOpenAI
import constants as ct


############################################################
# ドメイン解析関数
############################################################

def analyze_domain_seo_lightweight(domain: str, max_pages: int = 10, rag_function=None):
    """
    指定ドメインを最大max_pagesまで軽量クロールし、SEO観点で分析する。
    
    Args:
        domain: 解析対象のドメインまたはURL
        max_pages: 最大クロールページ数（デフォルト10）
        rag_function: RAG経路の関数（utils.get_llm_responseを想定）
                     Noneの場合は従来の直接LLM呼び出し
        
    Returns:
        dict: 既存UIで使用可能な形式の解析結果
            {
                "answer": str,           # LLM生成の解析レポート
                "sources": list,         # クロールしたページ情報
                "hybrid_mode": bool,     # RAG使用時True
                "seo_related": bool,     # True
                "unified_display": bool  # True（統一表示使用）
            }
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    cfg = ct.DOMAIN_ANALYSIS_CONFIG
    
    try:
        # 1. URL正規化
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        
        parsed_url = urlparse(domain)
        base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        logger.info(f"[ドメイン解析] 開始: {domain} (最大{max_pages}ページ)")
        
        # 2. robots.txt確認
        robot_parser = None
        if cfg.get("RESPECT_ROBOTS_TXT", True):
            robot_parser = _setup_robots_parser(base_domain, cfg)
        
        # 3. ページクロール
        pages_data = _crawl_pages(
            domain, 
            base_domain, 
            max_pages, 
            robot_parser, 
            cfg
        )
        
        if not pages_data:
            return {
                "answer": "有効なページが見つかりませんでした。URLを確認してください。",
                "sources": [],
                "hybrid_mode": False,
                "seo_related": True,
                "unified_display": True
            }
        
        logger.info(f"[ドメイン解析] クロール完了: {len(pages_data)}ページ取得")
        
        # 4. ページ単位のSEOスコアリング（3カテゴリ評価）
        scored_pages = []
        for page in pages_data:
            # 新3カテゴリスコアリング（技術/コンテンツ/企画）
            scored_page = _apply_comprehensive_seo_scoring(page)
            scored_pages.append(scored_page)
        
        avg_score = sum(p.get('comprehensive_score', 0) for p in scored_pages) / len(scored_pages)
        logger.info(f"[ドメイン解析] スコアリング完了: 平均{avg_score:.1f}点（3軸12項目評価）")
        
        # 5. RAG連携またはLLMで解析レポート生成
        use_rag = rag_function is not None
        
        if use_rag:
            # RAG経路：社内SEO検定資料を活用した解析
            logger.info("[ドメイン解析] RAG経路で解析レポート生成開始")
            try:
                analysis_summary = _build_analysis_summary_for_rag(scored_pages, domain)
                logger.debug(f"[ドメイン解析] RAG送信テキスト（先頭200文字）: {analysis_summary[:200]}")
                
                # ドメイン解析モードではSEOチェックをスキップ
                rag_result = rag_function(analysis_summary, skip_seo_check=True)
                
                # RAG結果の形式チェック
                if isinstance(rag_result, dict) and "answer" in rag_result:
                    # SEO関連判定の結果を確認
                    if rag_result.get("seo_related") is False:
                        logger.error(f"[ドメイン解析] SEO関連判定失敗！ RAGがSEO質問として認識しませんでした")
                        logger.error(f"[ドメイン解析] 送信テキスト: {analysis_summary[:500]}")
                        logger.info("[ドメイン解析] 従来方式（直接LLM）へフォールバック")
                        analysis_report = _generate_seo_analysis_report(scored_pages, domain)
                        use_rag = False
                    else:
                        analysis_report = rag_result["answer"]
                        logger.info("[ドメイン解析] RAG経路でレポート生成成功")
                else:
                    # 想定外の形式の場合はフォールバック
                    logger.warning(f"[ドメイン解析] RAG結果が想定外の形式: {type(rag_result)}")
                    logger.warning(f"[ドメイン解析] RAG結果内容: {str(rag_result)[:300]}")
                    analysis_report = _generate_seo_analysis_report(scored_pages, domain)
                    use_rag = False
                    
            except Exception as rag_error:
                # RAGエラー時は従来方式へフォールバック
                logger.error(f"[ドメイン解析] RAG連携エラー: {rag_error}")
                logger.error(f"[ドメイン解析] エラー詳細: {type(rag_error).__name__}")
                logger.info("[ドメイン解析] 従来方式（直接LLM）へフォールバック")
                analysis_report = _generate_seo_analysis_report(scored_pages, domain)
                use_rag = False
        else:
            # 従来方式：直接LLM呼び出し
            logger.info("[ドメイン解析] 従来方式（直接LLM）で解析レポート生成")
            analysis_report = _generate_seo_analysis_report(scored_pages, domain)
        
        # 6. 結果を既存UIに合わせた形式で返却（スコア情報を含む）
        sources = [
            {
                "title": page["title"],
                "url": page["url"],
                "content": page["summary"],
                "score": page.get("score", None),
                "comprehensive_score": page.get("comprehensive_score", None),
                "category_scores": page.get("category_scores", None),
                "check_results": page.get("check_results", None)
            }
            for page in scored_pages
        ]
        
        # 平均スコアとページ別詳細を追加
        avg_score = sum(p.get("score", 0) for p in scored_pages) / len(scored_pages)
        
        return {
            "answer": analysis_report,
            "sources": sources,
            "hybrid_mode": use_rag,  # RAG使用時はTrue
            "seo_related": True,
            "unified_display": True,
            "domain_scores": {
                "avg_score": round(avg_score, 1),
                "max_score": max((p.get("score", 0) for p in scored_pages), default=0),
                "min_score": min((p.get("score", 0) for p in scored_pages), default=0),
                "pages": scored_pages
            }
        }
        
    except Exception as e:
        logger.error(f"[ドメイン解析] エラー: {e}")
        return {
            "answer": f"解析中にエラーが発生しました: {str(e)}",
            "sources": [],
            "hybrid_mode": False,
            "seo_related": True,
            "unified_display": True
        }


def _setup_robots_parser(base_domain: str, cfg: dict):
    """
    robots.txtの設定
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    try:
        rp = RobotFileParser()
        robots_url = urljoin(base_domain, "/robots.txt")
        rp.set_url(robots_url)
        rp.read()
        logger.info(f"[robots.txt] 読み込み完了: {robots_url}")
        return rp
    except Exception as e:
        logger.warning(f"[robots.txt] 読み込み失敗: {e}, クロールを継続")
        return None


def _crawl_pages(start_url: str, base_domain: str, max_pages: int, robot_parser, cfg: dict):
    """
    ページクロール処理
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    visited = set()
    to_visit = [start_url]
    pages_data = []
    
    headers = {"User-Agent": cfg.get("USER_AGENT", "SEO-Analysis-Bot/1.0")}
    timeout = cfg.get("REQUEST_TIMEOUT", 10)
    delay = float(cfg.get("CRAWL_DELAY", 1.0))
    
    while to_visit and len(pages_data) < max_pages:
        url = to_visit.pop(0)
        
        if url in visited:
            continue
        
        # robots.txt確認
        if robot_parser and not robot_parser.can_fetch(headers["User-Agent"], url):
            logger.info(f"[robots.txt] ブロック: {url}")
            visited.add(url)
            continue
        
        try:
            # ページ取得
            response = requests.get(url, headers=headers, timeout=timeout)
            
            if response.status_code != 200:
                logger.warning(f"[クロール] ステータス {response.status_code}: {url}")
                visited.add(url)
                continue
            
            if "text/html" not in response.headers.get("Content-Type", ""):
                visited.add(url)
                continue
            
            visited.add(url)
            
            # HTML解析
            soup = BeautifulSoup(response.text, "html.parser")
            
            # SEO要素抽出
            page_data = _extract_seo_elements(soup, url)
            pages_data.append(page_data)
            
            logger.info(f"[クロール] 成功 ({len(pages_data)}/{max_pages}): {url}")
            
            # 内部リンク収集
            if len(pages_data) < max_pages:
                internal_links = _extract_internal_links(soup, url, base_domain)
                for link in internal_links:
                    if link not in visited and link not in to_visit:
                        to_visit.append(link)
            
            # クロール間隔
            time.sleep(delay)
            
        except requests.Timeout:
            logger.warning(f"[クロール] タイムアウト: {url}")
            visited.add(url)
        except Exception as e:
            logger.warning(f"[クロール] エラー: {url}, {e}")
            visited.add(url)
    
    return pages_data


def _extract_seo_elements(soup: BeautifulSoup, url: str):
    """
    SEO要素の抽出（拡張版：技術・コンテンツ・企画人気要素に焦点）
    
    SEO検定資料の「自分でできる努力」に該当する指標を重点的に抽出。
    SNS/構造化データ/国際化/セキュリティも抽出するが、採点には使用しない。
    
    Args:
        soup: BeautifulSoupオブジェクト
        url: ページURL
        
    Returns:
        dict: SEO要素の辞書
    """
    import re
    
    # ==================== 基本要素 ====================
    # タイトル
    title = soup.title.string.strip() if soup.title and soup.title.string else "(タイトルなし)"
    
    # メタディスクリプション
    meta_desc = soup.find("meta", attrs={"name": "description"})
    description = meta_desc.get("content", "").strip() if meta_desc and meta_desc.get("content") else "(meta descriptionなし)"
    
    # メタキーワード（整合性チェック用）
    meta_keywords_tag = soup.find("meta", attrs={"name": "keywords"})
    meta_keywords = meta_keywords_tag.get("content", "").strip() if meta_keywords_tag and meta_keywords_tag.get("content") else ""
    meta_keywords_list = [k.strip() for k in meta_keywords.split(",")] if meta_keywords else []
    
    # 見出し（H1-H3）- 検出数を増やして構造分析精度向上
    headings = {
        "h1": [h.get_text(strip=True) for h in soup.find_all("h1")],
        "h2": [h.get_text(strip=True) for h in soup.find_all("h2")][:10],
        "h3": [h.get_text(strip=True) for h in soup.find_all("h3")][:10]
    }
    
    # 本文抽出（ノイズ除去）
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    
    # メインコンテンツのテキストを取得（ヘッダー/フッター/ナビ/サイドメニューを除外）
    # 【優先戦略】article、main、content系タグがあればそれを優先使用
    
    # 候補タグをすべて収集
    candidate_tags = []
    
    # 1. <article>タグ（ブログ記事など）
    article_tag = soup.find('article')
    if article_tag:
        candidate_tags.append(('article', article_tag))
    
    # 2. entry-content, post-content等のclass名
    content_classes = ['entry-content', 'post-content', 'article-content', 'blog-content', 'content-body', 'main-content']
    for cls in content_classes:
        elem = soup.find(class_=cls)
        if elem:
            candidate_tags.append((f'class:{cls}', elem))
            break
    
    # 3. <main>タグ
    main_tag = soup.find('main')
    if main_tag:
        candidate_tags.append(('main', main_tag))
    
    # 候補タグから最適なものを選択（文字数が100文字以上のもの優先）
    main_content_tag = None
    selected_source = None
    
    for source, tag in candidate_tags:
        # このタグからテキストを抽出して文字数を確認
        test_text = _extract_text_from_tag(tag, soup)
        test_text_clean = re.sub(r'[\s\u3000]+', '', test_text)
        char_count = len(test_text_clean)
        
        # 100文字以上のコンテンツを持つ最初のタグを使用
        if char_count >= 100:
            main_content_tag = tag
            selected_source = source
            break
    
    # どの候補も100文字未満の場合、最初の候補を使用（従来の動作）
    if not main_content_tag and candidate_tags:
        selected_source, main_content_tag = candidate_tags[0]
    
    # メインコンテンツタグからテキストを抽出
    if main_content_tag:
        text_content = _extract_text_from_tag(main_content_tag, soup)
    
    else:
        # フォールバック：メインコンテンツタグが見つからない場合は従来ロジック
        navigation_keywords = ['header', 'footer', 'nav', 'menu', 'navigation', 'sidebar', 'aside', 'side', 'breadcrumb']
        
        excluded_tags = set()
        
        # 1. header, footer, navタグを除外
        for tag in soup.find_all(['header', 'footer', 'nav']):
            if tag:
                excluded_tags.add(tag)
        
        # 2. class/idにナビゲーション関連キーワードを含む要素を除外
        for tag in soup.find_all(True):
            if not tag or tag in excluded_tags:
                continue
            
            try:
                classes = tag.get('class', [])
                if isinstance(classes, list):
                    class_str = ' '.join(classes).lower()
                    if any(keyword in class_str for keyword in navigation_keywords):
                        excluded_tags.add(tag)
                        continue
                
                tag_id = tag.get('id', '').lower()
                if any(keyword in tag_id for keyword in navigation_keywords):
                    excluded_tags.add(tag)
            except (AttributeError, TypeError):
                continue
        
        # 除外対象以外のテキストを取得
        text_parts = []
        for element in soup.descendants:
            if isinstance(element, str):
                try:
                    parent = element.parent
                    is_excluded = False
                    while parent:
                        if parent in excluded_tags:
                            is_excluded = True
                            break
                        parent = parent.parent
                    
                    if not is_excluded:
                        text = element.strip()
                        if text:
                            text_parts.append(text)
                except (AttributeError, TypeError):
                    continue
        
        text_content = "\n".join(text_parts)
    text_lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    text_summary = " ".join(text_lines)[:800]  # RAG精度向上のため800文字に延長
    
    # 画像のalt属性チェック（ヘッダー/フッター/メニュー/ロゴ/装飾画像を除外）
    images = soup.find_all("img")
    
    # コンテンツ内の説明画像のみを評価対象とする
    # 除外対象：
    # - リンク内の画像（ナビゲーション用）
    # - ヘッダー/フッター/メニュー内の画像
    # - ロゴ画像
    # - 装飾画像（アイコン、背景など）
    content_images = []
    for img in images:
        # 1. ナビゲーション要素内の画像を除外
        if _is_navigation_element(img):
            continue
        
        # 2. ロゴまたは装飾画像を除外
        if _is_logo_or_decorative_image(img):
            continue
        
        # 3. リンク内の画像を除外（ナビゲーション用画像リンク）
        parent = img.find_parent("a")
        if parent is None:
            # リンクで囲まれていない、かつナビゲーション/ロゴでない画像のみを評価対象
            content_images.append(img)
    
    images_without_alt = sum(1 for img in content_images if not img.get("alt"))
    images_total_for_alt = len(content_images)  # alt属性評価対象の画像数
    
    # 不適切なalt属性を検出（汎用的な表現、ファイル名、無意味な文字列）
    images_with_poor_alt = []
    for img in content_images:
        alt_text = img.get("alt", "").strip()
        if alt_text and _is_poor_quality_alt(alt_text):
            images_with_poor_alt.append({
                "src": img.get("src", "")[:100],
                "alt": alt_text
            })
    
    # ==================== 技術・コンテンツ・企画人気の内部指標 ====================
    # メインコンテンツの文字数（日本語対応：空白・改行を除く実際の文字数）
    # ヘッダー/フッター/ナビゲーション/サイドメニューを除外したtext_contentから
    # 空白・タブ・改行を除去して純粋な文字数をカウント
    text_content_clean = re.sub(r'[\s\u3000]+', '', text_content)  # 半角・全角スペース、改行等を除去
    body_char_count = len(text_content_clean)
    
    # 後方互換性のため、body_word_countも保持（単語数として近似）
    # 英語の場合は単語数、日本語の場合は文字数として機能
    words = re.findall(r'\w+', text_content, flags=re.UNICODE)
    body_word_count = len(words)
    
    # 番号リスト/箇条書き/表/コード断片の有無（実用コンテンツの兆候）
    has_ordered_list = bool(soup.find("ol"))
    has_unordered_list = bool(soup.find("ul"))
    has_table = bool(soup.find("table"))
    has_code = bool(soup.find("pre") or soup.find("code"))
    
    # FAQ/HowTo/目次の簡易検出（先頭200行から）
    flat_text = " ".join(text_lines[:200]).lower()
    faq_like = any(k in flat_text for k in ["faq", "よくある質問", "q&a", "質問", "回答"])
    howto_like = any(k in flat_text for k in ["手順", "方法", "やり方", "ステップ", "やること"])
    toc_like = any(k in flat_text for k in ["目次", "contents", "table of contents"])
    
    # 更新日の兆候（ページ内表記を簡易検出）
    updated_regex = r"(更新日|最終更新|last\s*updated|更新:?)\s*[：: ]?\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}"
    updated_mention = bool(re.search(updated_regex, text_content, flags=re.IGNORECASE))
    
    # メインコンテンツ内の内部リンク数とアンカーテキスト多様度
    # （ヘッダー/フッター/ナビゲーション/サイドメニューを除外）
    internal_links = []
    anchor_texts = []
    base_netloc = urlparse(url).netloc
    for a in soup.find_all("a", href=True):
        # ナビゲーション要素内のリンクをスキップ（メインコンテンツのみ対象）
        if _is_navigation_element(a):
            continue
        
        target = urljoin(url, a["href"])
        pr = urlparse(target)
        if pr.scheme in ("http", "https") and pr.netloc == base_netloc:
            internal_links.append(target.split("#")[0])
            txt = a.get_text(strip=True)
            if txt:
                anchor_texts.append(txt.lower())
    
    internal_links = list(set(internal_links))  # 重複除去
    anchor_diversity = len(set(anchor_texts)) / max(1, len(anchor_texts)) if anchor_texts else 0.0
    
    # 内部リンクの関連性評価（軽量実装：アンカーテキストとページtitle/H1との類似度）
    def _tokenize(s):
        return set(re.findall(r"\w+", s.lower()))
    
    page_keywords = _tokenize(title + " " + " ".join(headings.get("h1", [])))
    link_relevance_score = 0.0
    
    if anchor_texts and page_keywords:
        relevant_links = 0
        for anchor in anchor_texts:
            anchor_keywords = _tokenize(anchor)
            # Jaccard類似度で関連性を評価
            intersection = len(page_keywords & anchor_keywords)
            union = len(page_keywords | anchor_keywords)
            similarity = intersection / max(union, 1)
            
            # 20%以上の類似度で「関連性あり」と判定
            if similarity > 0.2:
                relevant_links += 1
        
        link_relevance_score = relevant_links / max(len(anchor_texts), 1)
    
    # タイトル↔H1の整合性（Jaccard類似度で近似）
    # 注：_tokenize関数は上記で定義済み
    
    title_h1_sim = 0.0
    if headings["h1"]:
        t_tokens = _tokenize(title)
        h_tokens = _tokenize(headings["h1"][0])
        inter = len(t_tokens & h_tokens)
        uni = len(t_tokens | h_tokens)
        title_h1_sim = inter / uni if uni else 0.0
    
    # ==================== 国際化SEO ====================
    # hreflang（多言語・多地域対応）
    hreflang_links = []
    for link in soup.find_all("link", attrs={"rel": "alternate", "hreflang": True}):
        href = link.get("href", "")
        hreflang = link.get("hreflang", "")
        if href and hreflang:
            hreflang_links.append({"href": href, "hreflang": hreflang})
    
    # html lang属性
    html_tag = soup.find("html")
    html_lang = html_tag.get("lang", "") if html_tag else ""
    
    # canonical（正規URL）
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical_tag.get("href", "") if canonical_tag else ""
    
    # ==================== SNS最適化（拡散性・クリック率改善） ====================
    # OGP（Open Graph Protocol）- Facebook等
    ogp_data = {}
    ogp_tags = soup.find_all("meta", attrs={"property": lambda x: x and x.startswith("og:")})
    for tag in ogp_tags:
        prop = tag.get("property", "")
        content = tag.get("content", "")
        if prop and content:
            ogp_data[prop] = content
    
    # Twitter Card
    twitter_data = {}
    twitter_tags = soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")})
    for tag in twitter_tags:
        name = tag.get("name", "")
        content = tag.get("content", "")
        if name and content:
            twitter_data[name] = content
    
    # ==================== 構造化データ（Schema.org） ====================
    # JSON-LD形式の構造化データ
    import json
    ld_json_data = []
    ld_json_types = []
    
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            json_content = json.loads(script.string)
            # @typeを抽出（複数階層対応）
            def extract_types(data):
                types = []
                if isinstance(data, dict):
                    if "@type" in data:
                        types.append(data["@type"])
                    for value in data.values():
                        types.extend(extract_types(value))
                elif isinstance(data, list):
                    for item in data:
                        types.extend(extract_types(item))
                return types
            
            types = extract_types(json_content)
            ld_json_types.extend(types)
            ld_json_data.append(json_content)
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass  # 不正な形式はスキップ
    
    # ==================== 技術的SEO ====================
    # robots meta
    robots_meta = soup.find("meta", attrs={"name": "robots"})
    robots_content = robots_meta.get("content", "").lower() if robots_meta else ""
    
    # viewport（モバイル対応）
    viewport_meta = soup.find("meta", attrs={"name": "viewport"})
    viewport_content = viewport_meta.get("content", "") if viewport_meta else ""
    
    return {
        # 基本要素
        "url": url,
        "title": title,
        "description": description,
        "meta_keywords": meta_keywords,
        "meta_keywords_list": meta_keywords_list,
        "headings": headings,
        "summary": text_summary,
        "images_total": len(images),
        "images_without_alt": images_without_alt,
        "images_total_for_alt": images_total_for_alt,  # alt属性評価対象の画像数（ヘッダー/フッター/メニュー/ロゴ/装飾/リンク画像を除外）
        "images_with_poor_alt": images_with_poor_alt,  # 不適切なalt属性を持つ画像リスト
        
        # ==================== 技術・コンテンツ・企画人気の内部指標（採点対象） ====================
        "body_char_count": body_char_count,  # 本文文字数（空白除外、日本語対応）
        "body_word_count": body_word_count,  # 後方互換性のため保持（単語数近似）
        "has_ordered_list": has_ordered_list,
        "has_unordered_list": has_unordered_list,
        "has_table": has_table,
        "has_code": has_code,
        "faq_like": faq_like,
        "howto_like": howto_like,
        "toc_like": toc_like,
        "updated_mention": updated_mention,
        "internal_links_count": len(internal_links),
        "anchor_diversity": round(anchor_diversity, 3),
        "link_relevance_score": round(link_relevance_score, 3),  # 内部リンク関連性スコア（0.0～1.0）
        "title_h1_similarity": round(title_h1_sim, 3),
        
        # ==================== 技術的SEO（採点に使用） ====================
        "robots_content": robots_content,
        "canonical_url": canonical_url,
        "viewport_content": viewport_content,
        
        # ==================== 以下は抽出のみ（採点には使用しない） ====================
        # 国際化SEO
        "hreflang_links": hreflang_links,
        "html_lang": html_lang,
        
        # SNS最適化
        "ogp_data": ogp_data,
        "twitter_data": twitter_data,
        
        # 構造化データ
        "ld_json_types": ld_json_types,  # ['Article', 'Organization', 'BreadcrumbList'] 等
        "ld_json_data": ld_json_data,    # 生データ（詳細分析用）
    }


def _extract_text_from_tag(main_content_tag, soup):
    """
    指定されたタグからテキストを抽出（ナビゲーション要素を除外）
    
    Args:
        main_content_tag: テキストを抽出するタグ
        soup: BeautifulSoupオブジェクト（未使用だが互換性のため保持）
    
    Returns:
        str: 抽出されたテキスト
    """
    navigation_keywords = ['header', 'footer', 'nav', 'menu', 'navigation', 'sidebar', 'aside', 'side', 'breadcrumb']
    
    excluded_tags = set()
    
    # メインコンテンツ内のheader, footer, navタグを除外
    for tag in main_content_tag.find_all(['header', 'footer', 'nav']):
        if tag:
            excluded_tags.add(tag)
    
    # メインコンテンツ内のclass/idにナビゲーションキーワードを含む要素を除外
    for tag in main_content_tag.find_all(True):
        if not tag or tag in excluded_tags:
            continue
        
        try:
            classes = tag.get('class', [])
            if isinstance(classes, list):
                class_str = ' '.join(classes).lower()
                if any(keyword in class_str for keyword in navigation_keywords):
                    excluded_tags.add(tag)
                    continue
            
            tag_id = tag.get('id', '').lower()
            if any(keyword in tag_id for keyword in navigation_keywords):
                excluded_tags.add(tag)
        except (AttributeError, TypeError):
            continue
    
    # メインコンテンツからテキスト抽出
    text_parts = []
    for element in main_content_tag.descendants:
        if isinstance(element, str):
            try:
                parent = element.parent
                is_excluded = False
                while parent and parent != main_content_tag:
                    if parent in excluded_tags:
                        is_excluded = True
                        break
                    parent = parent.parent
                
                if not is_excluded:
                    text = element.strip()
                    if text:
                        text_parts.append(text)
            except (AttributeError, TypeError):
                continue
    
    return "\n".join(text_parts)


def _is_navigation_element(tag):
    """
    ヘッダー、フッター、ナビゲーションメニュー要素かを判定
    
    Args:
        tag: BeautifulSoupのタグオブジェクト
    
    Returns:
        bool: ナビゲーション要素内にある場合True
    """
    # 除外対象のタグ名
    navigation_tags = {'header', 'footer', 'nav'}
    
    # 除外対象のrole属性
    navigation_roles = {'navigation', 'banner', 'contentinfo', 'complementary'}
    
    # 除外対象のclass/id キーワード（部分一致）
    navigation_keywords = {
        'header', 'footer', 'nav', 'menu', 'navigation', 
        'sidebar', 'aside', 'side', 'breadcrumb', 'gnav', 'global-nav',
        'hamburger', 'drawer', 'top-menu', 'bottom-menu'
    }
    
    # 親要素を遡ってチェック
    current = tag
    while current:
        # タグ名チェック
        if hasattr(current, 'name') and current.name in navigation_tags:
            return True
        
        # role属性チェック
        if hasattr(current, 'get') and current.get('role') in navigation_roles:
            return True
        
        # class属性チェック（部分一致）
        classes = current.get('class', [])
        if isinstance(classes, list):
            class_str = ' '.join(classes).lower()
            if any(keyword in class_str for keyword in navigation_keywords):
                return True
        
        # id属性チェック（部分一致）
        element_id = current.get('id', '').lower()
        if any(keyword in element_id for keyword in navigation_keywords):
            return True
        
        # 親要素に移動
        current = current.parent if hasattr(current, 'parent') else None
    
    return False


def _is_logo_or_decorative_image(img):
    """
    ロゴ画像または装飾画像かを判定（ALT属性評価から除外すべき画像）
    
    Args:
        img: BeautifulSoupの<img>タグオブジェクト
    
    Returns:
        bool: ロゴまたは装飾画像の場合True
    """
    # ロゴを示すキーワード
    logo_keywords = {
        'logo', 'brand', 'site-logo', 'site-brand', 'company-logo',
        'ロゴ', 'ブランド', 'サイトロゴ'
    }
    
    # 装飾画像を示すキーワード（背景、アイコンなど）
    decorative_keywords = {
        'icon', 'decoration', 'bg', 'background', 'banner', 'hero',
        'thumbnail', 'avatar', 'profile-pic', 'spacer', 'separator',
        'アイコン', '装飾', '背景', 'バナー'
    }
    
    # すべてのキーワードを統合
    all_keywords = logo_keywords | decorative_keywords
    
    # 1. class属性のチェック
    img_classes = img.get('class', [])
    if isinstance(img_classes, list):
        class_str = ' '.join(img_classes).lower()
        if any(keyword in class_str for keyword in all_keywords):
            return True
    
    # 2. id属性のチェック
    img_id = img.get('id', '').lower()
    if any(keyword in img_id for keyword in all_keywords):
        return True
    
    # 3. src属性のチェック（ファイル名にロゴ等が含まれる）
    img_src = img.get('src', '').lower()
    if any(keyword in img_src for keyword in all_keywords):
        return True
    
    # 4. alt属性のチェック（既にロゴと明記されている場合）
    img_alt = img.get('alt', '').lower()
    if any(keyword in img_alt for keyword in logo_keywords):
        return True
    
    # 5. 親要素のリンクをチェック（ロゴはトップページへのリンク内にあることが多い）
    parent_link = img.find_parent('a')
    if parent_link:
        href = parent_link.get('href', '')
        # トップページ（/, /index.html, /index.php等）へのリンク内の画像
        if href in ['/', '/index.html', '/index.php', '/home', '']:
            # さらに親要素がヘッダー内にある場合
            if _is_navigation_element(img):
                return True
    
    # 6. role属性チェック（装飾的な画像）
    img_role = img.get('role', '').lower()
    if img_role in ['presentation', 'none']:
        return True
    
    return False


def _is_poor_quality_alt(alt_text):
    """
    不適切なalt属性を検出（汎用的表現、ファイル名、無意味な文字列）
    
    Args:
        alt_text: alt属性の文字列
    
    Returns:
        bool: 不適切な場合True
    """
    if not alt_text or not alt_text.strip():
        return False  # 空の場合は別途カウント済み
    
    alt_lower = alt_text.lower().strip()
    
    # 汎用的すぎる表現
    poor_quality_patterns = [
        r'^(画像|image|img|photo|写真|ブログ画像|記事画像)$',
        r'^(画像|image|img|photo)\d+$',  # "画像1", "image01"等
        r'^(fig|figure|pic|picture)\d*$',
        
        # ファイル名そのまま
        r'^\w+\.(jpg|jpeg|png|gif|webp|svg)$',
        r'^(dsc|img|image)_?\d+$',  # "DSC_0001", "IMG001"等
        
        # 無意味な文字列
        r'^(untitled|名称未設定|noname|no_name|unnamed)$',
        
        # 空白やプレースホルダー
        r'^(\s*|xxx|aaa|test|sample|サンプル)$',
        
        # 単純すぎる表現（1～2文字）
        r'^.{1,2}$'
    ]
    
    for pattern in poor_quality_patterns:
        if re.match(pattern, alt_lower, re.IGNORECASE):
            return True
    
    # 長さチェック（短すぎる or 長すぎる）
    if len(alt_text) < 3 or len(alt_text) > 125:
        return True
    
    return False


def _extract_internal_links(soup: BeautifulSoup, current_url: str, base_domain: str):
    """
    メインコンテンツ内の内部リンクを抽出
    （ヘッダー/フッター/ナビゲーション/サイドメニューを除外）
    
    Args:
        soup: BeautifulSoupオブジェクト
        current_url: 現在のページURL
        base_domain: ベースドメイン
    
    Returns:
        list: メインコンテンツ内の内部リンクのリスト（最大20件）
    """
    internal_links = []
    
    for link in soup.find_all("a", href=True):
        # ナビゲーション要素内のリンクをスキップ（メインコンテンツのみ対象）
        if _is_navigation_element(link):
            continue
        
        href = link["href"]
        full_url = urljoin(current_url, href)
        parsed = urlparse(full_url)
        
        # 同一ドメインの内部リンクのみ
        if parsed.netloc == urlparse(base_domain).netloc:
            # フラグメント除去
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url += f"?{parsed.query}"
            
            internal_links.append(clean_url)
    
    return list(set(internal_links))[:20]  # 最大20件


def _build_analysis_summary_for_rag(scored_pages: list, domain: str) -> str:
    """
    RAG経路に渡すための解析サマリテキストを生成（拡張版）
    
    社内SEO検定資料を活用した改善提案を得るため、
    ページの観測データを構造化テキストにまとめる。
    
    新規評価項目（OGP、構造化データ、hreflang等）を含む包括的な情報を提供。
    
    Args:
        scored_pages: スコアリング済みページデータ
        domain: 解析対象ドメイン
        
    Returns:
        str: RAG用の解析サマリテキスト
    """
    # スコア統計（新基準：comprehensive_score優先）
    comprehensive_scores = [p.get("comprehensive_score") for p in scored_pages if p.get("comprehensive_score") is not None]
    
    if comprehensive_scores:
        # 新基準スコアが存在する場合
        avg_comp_score = sum(comprehensive_scores) / len(comprehensive_scores)
        low_score_pages = [p for p in scored_pages if p.get("comprehensive_score", 0) < 60]
        mid_score_pages = [p for p in scored_pages if 60 <= p.get("comprehensive_score", 0) < 80]
        high_score_pages = [p for p in scored_pages if p.get("comprehensive_score", 0) >= 80]
        sorted_pages = sorted(scored_pages, key=lambda p: p.get("comprehensive_score", 0))
        use_new_score = True
    else:
        # 新スコア使用（comprehensive_scoreベース）
        avg_comp_score = sum(p.get("comprehensive_score", 0) for p in scored_pages) / len(scored_pages)
        low_score_pages = [p for p in scored_pages if p.get("comprehensive_score", 0) < 60]
        mid_score_pages = [p for p in scored_pages if 60 <= p.get("comprehensive_score", 0) < 80]
        high_score_pages = [p for p in scored_pages if p.get("comprehensive_score", 0) >= 80]
        sorted_pages = sorted(scored_pages, key=lambda p: p.get("comprehensive_score", 0))
        use_new_score = True
    
    # カテゴリ別平均スコア集計（新3カテゴリ）
    category_averages = {}
    category_details = {}  # カテゴリ別の詳細情報
    
    if use_new_score:
        for page in scored_pages:
            cat_scores = page.get("category_scores", {})
            for cat_name, cat_data in cat_scores.items():
                if cat_name not in category_averages:
                    category_averages[cat_name] = []
                    category_details[cat_name] = {
                        "max": cat_data.get("max", 0),
                        "scores": []
                    }
                category_averages[cat_name].append(cat_data.get("percentage", 0))
                category_details[cat_name]["scores"].append(cat_data.get("score", 0))
        
        # 平均値計算
        for cat_name in category_averages:
            total_percentage = sum(category_averages[cat_name])
            count = len(category_averages[cat_name])
            category_averages[cat_name] = total_percentage / count if count > 0 else 0
            
            total_score = sum(category_details[cat_name]["scores"])
            category_details[cat_name]["avg_score"] = total_score / count if count > 0 else 0
    
    # サイト全体の問題点集計
    site_issues = {
        "ogp_missing": 0,
        "twitter_missing": 0,
        "structured_data_missing": 0,
        "canonical_missing": 0,
        "viewport_missing": 0,
        "hreflang_missing": 0,
        "robots_issue": 0,
        "https_issue": 0
    }
    
    for page in scored_pages:
        check_results = page.get("check_results", {})
        if check_results.get("ogp_exists") is False:
            site_issues["ogp_missing"] += 1
        if check_results.get("twitter_card_exists") is False:
            site_issues["twitter_missing"] += 1
        if check_results.get("structured_data_exists") is False:
            site_issues["structured_data_missing"] += 1
        if check_results.get("canonical_appropriate") is False:
            site_issues["canonical_missing"] += 1
        if check_results.get("mobile_responsive") is False:
            site_issues["viewport_missing"] += 1
        if page.get("hreflang_links") and len(page.get("hreflang_links", [])) == 0:
            site_issues["hreflang_missing"] += 1
        if check_results.get("robots_meta_appropriate") is False:
            site_issues["robots_issue"] += 1
        if check_results.get("https_enabled") is False:
            site_issues["https_issue"] += 1
    
    # ページ別詳細サマリ（スコア低い順＝改善優先順）
    page_summaries = []
    for i, page in enumerate(sorted_pages, 1):
        # 基本情報
        score_display = page.get("comprehensive_score", page.get("score", 0))
        h1_text = ", ".join(page.get("headings", {}).get("h1", [])[:3])
        if not h1_text:
            h1_text = "（H1なし）"
        
        h2_count = len(page.get("headings", {}).get("h2", []))
        h3_count = len(page.get("headings", {}).get("h3", []))
        
        img_total = page.get("images_total", 0)
        img_wo_alt = page.get("images_without_alt", 0)
        alt_ratio = 0 if img_total == 0 else ((img_total - img_wo_alt) / img_total * 100)
        
        # 新規項目情報
        ogp_status = "設定済み" if page.get("ogp_data") and len(page.get("ogp_data", {})) >= 3 else "未設定"
        twitter_status = "設定済み" if page.get("twitter_data") and len(page.get("twitter_data", {})) >= 1 else "未設定"
        
        ld_types = page.get("ld_json_types", [])
        structured_data_status = f"あり（{', '.join(ld_types[:3])}）" if ld_types else "なし"
        
        canonical_status = "あり" if page.get("canonical_url") else "なし"
        viewport_status = "適切" if page.get("viewport_content") and "width=device-width" in page.get("viewport_content", "") else "不適切または未設定"
        hreflang_status = f"あり（{len(page.get('hreflang_links', []))}言語）" if page.get("hreflang_links") else "なし"
        
        # カテゴリ別スコア（新3カテゴリ）
        cat_scores_text = ""
        cat_details_text = ""
        if page.get("category_scores"):
            cat_scores = page.get("category_scores", {})
            cat_names_jp = {
                "technical": "技術",
                "content": "コンテンツ",
                "planning": "企画"
            }
            
            # 3カテゴリのスコア表示
            cat_scores_list = []
            for cat_key in ["technical", "content", "planning"]:
                if cat_key in cat_scores:
                    cat_data = cat_scores[cat_key]
                    cat_pct = cat_data.get("percentage", 0)
                    cat_name_jp = cat_names_jp.get(cat_key, cat_key)
                    cat_scores_list.append(f"{cat_name_jp}:{cat_pct:.1f}%")
            
            if cat_scores_list:
                cat_scores_text = f"\n  【3軸評価】{', '.join(cat_scores_list)}"
            
            # 60%未満のカテゴリを警告
            low_categories = [(cat_names_jp.get(cat, cat), data.get("percentage", 100)) 
                            for cat, data in cat_scores.items() 
                            if data.get("percentage", 100) < 60]
            if low_categories:
                low_cat_names = [f"{name}({pct:.0f}%)" for name, pct in low_categories]
                cat_details_text = f"\n  ⚠️ 【要改善】{', '.join(low_cat_names)}"
        
        # 新規指標の追加
        body_chars = page.get("body_char_count", 0)  # 文字数
        body_words = page.get("body_word_count", 0)  # 単語数（後方互換）
        internal_links = page.get("internal_links_count", 0)
        anchor_div = page.get("anchor_diversity", 0.0)
        link_relevance = page.get("link_relevance_score", 0.0)  # 内部リンク関連性スコア
        title_h1_sim = page.get("title_h1_similarity", 0.0)
        
        readability_elements = []
        if page.get("has_ordered_list"):
            readability_elements.append("番号リスト")
        if page.get("has_unordered_list"):
            readability_elements.append("箇条書き")
        if page.get("has_table"):
            readability_elements.append("表")
        if page.get("has_code"):
            readability_elements.append("コード")
        readability_text = ", ".join(readability_elements) if readability_elements else "なし"
        
        planning_elements = []
        if page.get("howto_like"):
            planning_elements.append("HowTo")
        if page.get("faq_like"):
            planning_elements.append("FAQ")
        if page.get("toc_like"):
            planning_elements.append("目次")
        planning_text = ", ".join(planning_elements) if planning_elements else "なし"
        
        updated_text = "あり" if page.get("updated_mention") else "なし"
        
        # 画像alt属性の詳細情報
        poor_alt_images = page.get("images_with_poor_alt", [])
        img_alt_detail = ""
        if img_wo_alt > 0 or len(poor_alt_images) > 0:
            img_alt_detail = "\n  ⚠️【画像alt属性の問題】"
            if img_wo_alt > 0:
                img_alt_detail += f"\n    - alt属性未設定: {img_wo_alt}枚"
            if len(poor_alt_images) > 0:
                img_alt_detail += f"\n    - 不適切なalt属性（汎用的表現）: {len(poor_alt_images)}枚"
                # 最大3件まで例示
                for idx, img_info in enumerate(poor_alt_images[:3], 1):
                    img_alt_detail += f"\n      例{idx}: alt=\"{img_info['alt']}\" (src={img_info['src'][:60]}...)"
        
        page_summaries.append(
            f"【ページ{i}】{cat_scores_text}{cat_details_text}\n"
            f"  URL: {page['url']}\n"
            f"  タイトル: {page['title']} （{len(page['title'])}文字）\n"
            f"  メタディスクリプション: {page['description'][:80]}... （{len(page['description'])}文字）\n"
            f"  H1: {h1_text} （タイトル-H1類似度: {title_h1_sim:.1%}）\n"
            f"  見出し構造: H2={h2_count}個, H3={h3_count}個\n"
            f"  本文文字数: {body_chars}文字\n"
            f"    （推奨: メイン物販/求人/不動産0～800字、メイン来店型700～2,500字、メイン複雑4,000字以上、サブ単純1,500字以上、サブ複雑4,000字以上、YMYL分野は2倍）\n"
            f"  内部リンク: {internal_links}本（メインコンテンツ内）（アンカー多様性: {anchor_div:.1%}、関連性: {link_relevance:.1%}）\n"
            f"  　※関連性評価方法: アンカーテキストとページのtitle・H1との類似度で判定（Jaccard係数使用）\n"
            f"  画像: 評価対象{img_total}枚（ヘッダー/フッター/メニュー/ロゴ/装飾/リンク画像除外）, alt属性充足率={alt_ratio:.0f}%{img_alt_detail}\n"
            f"  可読性要素: {readability_text}\n"
            f"  企画要素: {planning_text} / 更新日表示: {updated_text}\n"
            f"  【参考】canonical: {canonical_status}, OGP: {ogp_status}, 構造化データ: {structured_data_status}"
        )
    
    # カテゴリ別評価の要約（新3カテゴリ）
    category_summary_text = ""
    if category_averages:
        # カテゴリ名の日本語化
        cat_names_jp = {
            "technical": "技術要因",
            "content": "コンテンツ要因",
            "planning": "企画人気要素"
        }
        
        category_summary_text = "\n【3軸評価の結果】\n"
        for cat_name in ["technical", "content", "planning"]:
            if cat_name in category_averages:
                avg_pct = category_averages[cat_name]
                status = "優秀" if avg_pct >= 80 else ("良好" if avg_pct >= 60 else "要改善")
                
                category_summary_text += f"  - {cat_names_jp[cat_name]}: {avg_pct:.1f}% [{status}]\n"
        
        # 弱点カテゴリの特定
        low_categories = [(cat, avg) for cat, avg in category_averages.items() if avg < 60]
        if low_categories:
            category_summary_text += "\n  【重点改善カテゴリ】\n"
            for cat, avg in sorted(low_categories, key=lambda x: x[1]):
                category_summary_text += f"    → {cat_names_jp.get(cat, cat)}: {avg:.1f}%\n"
    
    # サイト全体の参考情報（評価対象外の項目）
    site_issues_text = "\n【参考：評価対象外の項目】\n"
    site_issues_text += "以下は情報として取得済みです：\n"
    
    reference_items = []
    if site_issues["ogp_missing"] > 0:
        reference_items.append(f"  - OGP未設定: {site_issues['ogp_missing']}ページ（SNSシェア時のクリック率向上施策）")
    if site_issues["twitter_missing"] > 0:
        reference_items.append(f"  - Twitter Card未設定: {site_issues['twitter_missing']}ページ（Twitter拡散性向上施策）")
    if site_issues["structured_data_missing"] > 0:
        reference_items.append(f"  - 構造化データなし: {site_issues['structured_data_missing']}ページ（リッチリザルト表示施策）")
    if site_issues["https_issue"] > 0:
        reference_items.append(f"  - HTTPS未対応: {site_issues['https_issue']}ページ（セキュリティ向上施策）")
    
    if reference_items:
        site_issues_text += "\n".join(reference_items) + "\n"
    else:
        site_issues_text += "  - 参考項目（OGP/構造化データ/HTTPS等）は概ね設定済み\n"
    
    # RAG用クエリテキスト構築（3カテゴリ評価版）
    # 重要：「自分でできる努力」（技術/コンテンツ/企画）に焦点を当てる
    summary_text = f"""
【SEO解析依頼】Webサイトのsearch engine optimization（検索エンジン最適化）評価レポート作成

ドメイン「{domain}」のSEO最適化状況を、「自分でコントロール可能な要因」に絞って分析しました。
Google検索順位向上のため、社内SEO検定資料の基準に基づき優先順位付きで具体的な改善提案を作成してください。

【解析概要】
- 解析ページ数: {len(scored_pages)}ページ
{category_summary_text}

【各ページの詳細】（改善優先順）
{chr(10).join(page_summaries)}

{site_issues_text}

【依頼事項】
以下の3つの「自分でコントロール可能な要因」について、社内SEO検定資料の基準に基づいた具体的な改善提案を作成してください：

1. **技術要因** - クロール/インデックス制御とサイト構造
   - インデックス可能性（robots meta、noindex設定の適切性）
   - canonical URL（重複コンテンツ回避）
   - URL構造（階層の浅さ、わかりやすさ）
   - 見出し階層（H1→H2→H3の論理的な構造）
   - 内部リンク（本数、アンカーテキストの多様性）

2. **コンテンツ要因** - 情報の質と量
   - 本文語数（日本語で800語以上が目安）
   - タイトル-H1整合性（主題の一貫性）
   - 可読性向上要素（箇条書き・表・コードブロック等の情報設計）
   - 画像alt属性（アクセシビリティ＋画像検索対策）
     ※alt属性の改善提案時は以下を必ず含めてください：
     【重要】画像alt属性の適切な記述方法
     ■ 現状の問題：「ブログ画像」「画像1」のような汎用的表現は不適切
     ■ alt属性の目的：
       - 視覚障害者への情報提供（スクリーンリーダー対応）
       - 画像が表示されない場合の代替テキスト
       - 画像検索エンジン対策（Google画像検索でのランキング向上）
     ■ 適切な記述方法：
       ✅ 良い例: alt="SEOキーワード調査ツールの管理画面スクリーンショット"
       ✅ 良い例: alt="2025年Google検索アルゴリズム更新の影響を示すグラフ"
       ✅ 良い例: alt="東京都新宿区の当社オフィス外観"
       ❌ 悪い例: alt="ブログ画像"
       ❌ 悪い例: alt="画像1"
       ❌ 悪い例: alt="photo.jpg"
     ■ 記述時の質問：
       - この画像は何を示していますか？
       - 視覚障害者の方が画像を見られない場合、どう説明しますか？
       - この画像が表示されない場合、どんなテキストがあれば内容が理解できますか？
     ■ Googleガイドライン準拠：
       - 具体的で説明的なテキストを使用
       - キーワードの詰め込みは避ける
       - 文脈に合った自然な文章
       - 文字数目安: 3～125文字
   - H1タグの存在と適切性

3. **企画人気要素** - ユーザー体験とコンテンツ企画
   - HowTo/FAQ/目次の設置（ユーザビリティ向上）
   - 更新性の表示（最終更新日など、情報鮮度の明示）

【参考情報】（評価対象外）
以下の要素は情報として取得済みです。必要に応じて参考情報として改善提案に含めてください：
- SNS最適化：OGP（Open Graph Protocol）、Twitter Card（拡散性向上）
- 構造化データ：Schema.org JSON-LD（リッチリザルト表示）
- 国際化SEO：hreflangタグ（多言語サイト）
- セキュリティ：HTTPS化状況

【改善提案の要件】
- 改善が必要なページ・カテゴリを優先的に改善提案
- 優先順位別（高/中/低）にアクションリストを作成
- Google検索エンジンのランキング向上に直結する施策を優先
- 上記【3軸評価の結果】で問題があるカテゴリを重点的に改善提案に含める

【厳守事項】
- 具体的な数値基準（例：「10本以上」「3本は少ない」等）は、社内SEO検定資料に明記されている場合のみ使用してください
- 資料に数値基準がない場合は、定性的表現（「増やす」「改善する」「充実させる」等）を使用してください
- 推測や一般論に基づく絶対的な数値基準（「業界標準は〇本」等）は禁止します
- 内部リンクの評価では「関連性」を重視してください（SEO検定資料：アンカーテキストマッチの重要性）
"""
    
    return summary_text.strip()


def _generate_seo_analysis_report(pages_data: list, domain: str):
    """
    LLMを使用してSEO解析レポートを生成（スコア情報を活用）
    
    Args:
        pages_data: スコアリング済みページデータ（score情報を含む）
        domain: 解析対象ドメイン
        
    Returns:
        str: LLM生成の解析レポート
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    try:
        # スコア順にソート（低いページから改善提案）
        sorted_pages = sorted(pages_data, key=lambda p: p.get("score", 0))
        
        # プロンプト構築（スコア情報を含む）
        pages_summary = "\n\n".join([
            f"### ページ {i+1}: {page['title']} [SEOスコア: {page.get('score', 0)}/100点]\n"
            f"URL: {page['url']}\n"
            f"タイトル長: {len(page['title'])}文字\n"
            f"メタディスクリプション: {page['description']}\n"
            f"H1タグ: {len(page['headings']['h1'])}個 - {', '.join(page['headings']['h1'][:3]) if page['headings']['h1'] else '(なし)'}\n"
            f"H2タグ: {len(page['headings']['h2'])}個\n"
            f"画像: 合計{page['images_total']}枚, alt属性なし{page['images_without_alt']}枚\n"
            f"概要: {page['summary'][:200]}..."
            for i, page in enumerate(sorted_pages)
        ])
        
        # スコア統計
        avg_score = sum(p.get("score", 0) for p in pages_data) / len(pages_data)
        low_score_pages = [p for p in pages_data if p.get("score", 0) < 60]
        
        prompt = f"""
あなたはSEO検定1級レベルのSEO専門アシスタントです。
以下のドメインの解析結果を基に、**SEOスコアを考慮した**改善提案を行ってください。

【解析対象ドメイン】
{domain}

【解析ページ数】
{len(pages_data)}ページ

【SEOスコア統計】
- 平均スコア: {avg_score:.1f}/100点
- 60点未満のページ: {len(low_score_pages)}ページ（優先改善対象）

【各ページの詳細】（スコアの低い順）
{pages_summary}

【重要】
- スコアが低いページを優先的に改善提案してください
- 各改善提案には、期待されるスコア向上効果を記載してください
- 社内SEO検定資料の基準に基づいた推奨事項を含めてください

【出力形式】
以下の構成で、実践的な改善提案をしてください：

**総合評価**
- 平均SEOスコア: {avg_score:.1f}/100点
- サイト全体のSEO状況を3-5行で要約

**主な問題点（優先度順）**
- 問題点1（影響度：高/中/低）
- 問題点2（影響度：高/中/低）
- 問題点3（影響度：高/中/低）

**具体的な改善提案（スコア向上効果付き）**
1. タイトルタグの最適化 [期待スコア向上: +XX点]
   - 現状の問題点
   - 具体的な改善方法
   - 改善例

2. メタディスクリプションの改善 [期待スコア向上: +XX点]
   - 現状の問題点
   - 具体的な改善方法
   - 改善例

3. 見出し構造の最適化 [期待スコア向上: +XX点]
   - 現状の問題点
   - 具体的な改善方法
   - 改善例

4. 画像のalt属性設定 [期待スコア向上: +XX点]
   - 現状の問題点
   - 具体的な改善方法
   - 改善例

**優先順位別アクションリスト**
【高優先度】（スコア60点未満のページを優先）
- アクション1（対象ページ: URL）
- アクション2（対象ページ: URL）

【中優先度】（スコア60-80点のページ）
- アクション3（対象ページ: URL）
- アクション4（対象ページ: URL）

【低優先度】（スコア80点以上のページ）
- 現状維持または微調整

**期待される総合効果**
- 全ページ改善後の推定平均スコア: XX点 → XX点（+XX点向上）
"""
        
        # LLM実行
        llm = ChatOpenAI(model=ct.MODEL, temperature=0.3)
        response = llm.invoke(prompt)
        
        logger.info(f"[LLM解析] レポート生成完了（平均スコア: {avg_score:.1f}点）")
        return response.content
        
    except Exception as e:
        logger.error(f"[LLM解析] エラー: {e}")
        return f"解析は完了しましたが、レポート生成中にエラーが発生しました: {str(e)}"


############################################################
# SEO検定資料準拠の3カテゴリ評価
############################################################

def _apply_comprehensive_seo_scoring(page: dict) -> dict:
    """
    SEO検定資料の「自分でできる努力」に焦点を絞った評価
    
    評価対象：
    - 技術要因：クロール/インデックス制御、URL構造、見出し階層、内部リンク
    - コンテンツ要因：本文量、タイトル-H1整合、情報設計、画像alt、H1有無
    - 企画人気要素：HowTo/FAQ/目次、更新性
    
    評価対象外（抽出のみ）：
    - SNS最適化（OGP/Twitter Card）
    - 構造化データ（Schema.org）
    - 国際化SEO（hreflang）
    - セキュリティ（HTTPS）
    
    Args:
        page: ページデータ
        
    Returns:
        dict: 評価結果が追加されたページデータ
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    # 配点
    W = {
        # 技術要因
        "indexable": 10,           # robotsにnoindexが無い
        "canonical": 8,            # canonical設定（自己参照/適切）
        "url_depth": 6,            # URL深さ<=3
        "headings_hierarchy": 8,   # H1→H2→H3
        "internal_links": 8,       # 内部リンク本数・多様性
        
        # コンテンツ要因
        "body_words": 10,          # 本文語数の閾値（日本語: 800語目安）
        "title_h1_align": 8,       # タイトルとH1の主題整合
        "readability_blocks": 10,  # 箇条書き/表/コード等の情報設計
        "alt_ratio": 6,            # 画像altの充足
        "h1_present": 6,           # H1の存在
        
        # 企画人気要素
        "howto_faq_toc": 10,       # HowTo/FAQ/目次のいずれか
        "freshness": 10,           # 更新日の記述などの新しさ兆候
    }
    
    # スコアリング結果の保存用
    category_scores = {}
    check_results = {}
    
    # データ取得（基本要素）
    title = page.get("title", "") or ""
    desc = page.get("description", "") or ""
    heads = page.get("headings", {})
    h1s = heads.get("h1", [])
    h2s = heads.get("h2", [])
    h3s = heads.get("h3", [])
    img_total = page.get("images_total_for_alt", page.get("images_total", 0))  # alt評価対象画像数（ヘッダー/フッター/メニュー/ロゴ/装飾/リンク画像を除外）
    img_wo_alt = page.get("images_without_alt", 0)
    url = page.get("url", "")
    
    # データ取得（新規抽出要素）
    robots_content = page.get("robots_content", "")
    canonical_url = page.get("canonical_url", "")
    path_depth = len(urlparse(url).path.strip("/").split("/")) if url else 0
    internal_links_count = page.get("internal_links_count", 0)
    anchor_diversity = page.get("anchor_diversity", 0.0)
    body_char_count = page.get("body_char_count", 0)  # 文字数（優先）
    body_word_count = page.get("body_word_count", 0)  # 後方互換性のため保持
    title_h1_similarity = page.get("title_h1_similarity", 0.0)
    
    # スコアリング開始
    score = 0.0
    
    # ==================== 技術要因 ====================
    # 1. Indexable
    if "noindex" not in robots_content:
        score += W["indexable"]
        check_results["indexable"] = True
    else:
        check_results["indexable"] = False
    
    # 2. Canonical
    if canonical_url:
        score += W["canonical"]
        check_results["canonical"] = True
    else:
        check_results["canonical"] = False
    
    # 3. URL深さ
    if path_depth <= 3:
        score += W["url_depth"]
        check_results["url_shallow"] = True
    else:
        check_results["url_shallow"] = False
    
    # 4. 見出し階層
    if h1s and (h2s or h3s):
        score += W["headings_hierarchy"]
        check_results["headings_hierarchy"] = True
    else:
        check_results["headings_hierarchy"] = False
    
    # 5. 内部リンク
    if internal_links_count >= 5 and anchor_diversity >= 0.3:
        score += W["internal_links"]
        check_results["internal_links_min"] = True
        check_results["anchor_diversity_min"] = True
    else:
        check_results["internal_links_min"] = internal_links_count >= 5
        check_results["anchor_diversity_min"] = anchor_diversity >= 0.3
    
    # ==================== コンテンツ要因 ====================
    # 6. 本文文字数
    # 基準: 800文字以上
    # （参考: メインページ推奨700～2,500字、サブページ推奨1,000字以上）
    if body_char_count >= 800:
        score += W["body_words"]
        check_results["body_words_enough"] = True
    else:
        check_results["body_words_enough"] = False
    
    # 7. タイトル-H1整合
    if title_h1_similarity >= 0.5:
        score += W["title_h1_align"]
        check_results["title_h1_aligned"] = True
    else:
        check_results["title_h1_aligned"] = False
    
    # 8. 可読性ブロック
    has_readability_blocks = any([
        page.get("has_ordered_list"),
        page.get("has_unordered_list"),
        page.get("has_table"),
        page.get("has_code")
    ])
    if has_readability_blocks:
        score += W["readability_blocks"]
        check_results["readability_blocks"] = True
    else:
        check_results["readability_blocks"] = False
    
    # 9. 画像alt
    if img_total == 0:
        score += W["alt_ratio"]
        check_results["alt_ok"] = True
    else:
        alt_ratio = (img_total - img_wo_alt) / img_total
        if alt_ratio >= 0.6:
            score += W["alt_ratio"]
            check_results["alt_ok"] = True
        else:
            check_results["alt_ok"] = False
    
    # 10. H1存在
    if h1s:
        score += W["h1_present"]
        check_results["h1_exists"] = True
    else:
        check_results["h1_exists"] = False
    
    # ==================== 企画人気要素 ====================
    # 11. HowTo/FAQ/目次
    has_planning_elements = any([
        page.get("howto_like"),
        page.get("faq_like"),
        page.get("toc_like")
    ])
    if has_planning_elements:
        score += W["howto_faq_toc"]
        check_results["howto_faq_toc"] = True
    else:
        check_results["howto_faq_toc"] = False
    
    # 12. 更新性
    if page.get("updated_mention"):
        score += W["freshness"]
        check_results["freshness_sign"] = True
    else:
        check_results["freshness_sign"] = False
    
    # ==================== カテゴリスコアの計算 ====================
    category_scores = {
        "technical": {
            "score": sum([
                W["indexable"] if check_results.get("indexable") else 0,
                W["canonical"] if check_results.get("canonical") else 0,
                W["url_depth"] if check_results.get("url_shallow") else 0,
                W["headings_hierarchy"] if check_results.get("headings_hierarchy") else 0,
                W["internal_links"] if (check_results.get("internal_links_min") and check_results.get("anchor_diversity_min")) else 0
            ]),
            "max": 40,
            "percentage": 0.0
        },
        "content": {
            "score": sum([
                W["body_words"] if check_results.get("body_words_enough") else 0,
                W["title_h1_align"] if check_results.get("title_h1_aligned") else 0,
                W["readability_blocks"] if check_results.get("readability_blocks") else 0,
                W["alt_ratio"] if check_results.get("alt_ok") else 0,
                W["h1_present"] if check_results.get("h1_exists") else 0
            ]),
            "max": 40,
            "percentage": 0.0
        },
        "planning": {
            "score": sum([
                W["howto_faq_toc"] if check_results.get("howto_faq_toc") else 0,
                W["freshness"] if check_results.get("freshness_sign") else 0
            ]),
            "max": 20,
            "percentage": 0.0
        }
    }
    
    # パーセンテージ計算
    for cat_name, cat_data in category_scores.items():
        if cat_data["max"] > 0:
            cat_data["percentage"] = round(100 * cat_data["score"] / cat_data["max"], 1)
    
    # 総合スコア
    page["comprehensive_score"] = round(score, 1)
    page["category_scores"] = category_scores
    page["check_results"] = check_results
    
    logger.debug(f"[包括スコアリング] {url[:50]}: {score:.1f}点")
    
    return page


############################################################
# 1ページ詳細解析（サイト全体構造を活用）
############################################################

def analyze_single_page_with_context(top_url: str, target_url: str, max_pages: int = 30, rag_function=None):
    """
    トップページURLを起点にサイト全体構造を取得し、
    対象ページ（target_url）をSEO文脈付きで詳細解析する。
    
    Args:
        top_url: サイト全体構造を取得するトップページURL
        target_url: 詳細解析する対象ページURL
        max_pages: 構造把握のための最大クロールページ数（デフォルト30）
        rag_function: RAG経路の関数（utils.get_llm_responseを想定）
        
    Returns:
        dict: 解析結果
            {
                "answer": str,              # LLM生成の解析レポート
                "target_url": str,          # 解析対象URL
                "contextual_score": float,  # コンテキスト評価スコア
                "structure_summary": dict,  # サイト全体構造の要約
                "page_analysis": dict,      # 対象ページの詳細分析
                "sources": list,            # 参照ページ情報
                "hybrid_mode": bool,        # RAG使用時True
                "seo_related": bool,        # True
                "unified_display": bool     # True（統一表示使用）
            }
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    cfg = ct.DOMAIN_ANALYSIS_CONFIG
    
    try:
        # 1. URL正規化
        if not top_url.startswith(("http://", "https://")):
            top_url = "https://" + top_url
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url
        
        parsed_top = urlparse(top_url)
        parsed_target = urlparse(target_url)
        base_domain = f"{parsed_top.scheme}://{parsed_top.netloc}"
        
        logger.info(f"[1ページ解析] 開始: 構造={top_url}, 対象={target_url}")
        
        # 2. robots.txt確認
        robot_parser = None
        if cfg.get("RESPECT_ROBOTS_TXT", True):
            robot_parser = _setup_robots_parser(base_domain, cfg)
        
        # 3. サイト全体構造をクロール（軽量：内部リンク収集のみ）
        logger.info(f"[1ページ解析] サイト構造クロール開始（最大{max_pages}ページ）")
        structure_pages = _crawl_pages(
            top_url,
            base_domain,
            max_pages,
            robot_parser,
            cfg
        )
        
        if not structure_pages:
            return {
                "answer": "サイト構造の取得に失敗しました。URLを確認してください。",
                "target_url": target_url,
                "sources": [],
                "hybrid_mode": False,
                "seo_related": True,
                "unified_display": True
            }
        
        # 4. サイト全体構造の要約
        structure_summary = _summarize_site_structure(structure_pages)
        logger.info(f"[1ページ解析] 構造要約完了: {structure_summary['page_count']}ページ")
        
        # 5. 対象ページの詳細解析
        logger.info(f"[1ページ解析] 対象ページ解析開始: {target_url}")
        
        # 対象ページが構造クロール結果に含まれているか確認
        target_page_data = None
        for page in structure_pages:
            if page.get("url") == target_url:
                target_page_data = page
                break
        
        # 含まれていない場合は個別取得
        if not target_page_data:
            try:
                headers = {"User-Agent": cfg.get("USER_AGENT", "SEO-Analysis-Bot/1.0")}
                timeout = cfg.get("REQUEST_TIMEOUT", 10)
                
                if robot_parser and not robot_parser.can_fetch(headers["User-Agent"], target_url):
                    return {
                        "answer": "対象ページはrobots.txtでクロールがブロックされています。",
                        "target_url": target_url,
                        "sources": [],
                        "hybrid_mode": False,
                        "seo_related": True,
                        "unified_display": True
                    }
                
                response = requests.get(target_url, headers=headers, timeout=timeout)
                if response.status_code != 200:
                    return {
                        "answer": f"対象ページの取得に失敗しました（ステータス: {response.status_code}）",
                        "target_url": target_url,
                        "sources": [],
                        "hybrid_mode": False,
                        "seo_related": True,
                        "unified_display": True
                    }
                
                soup = BeautifulSoup(response.text, "html.parser")
                target_page_data = _extract_seo_elements(soup, target_url)
                
            except Exception as e:
                logger.error(f"[1ページ解析] 対象ページ取得エラー: {e}")
                return {
                    "answer": f"対象ページの解析中にエラーが発生しました: {str(e)}",
                    "target_url": target_url,
                    "sources": [],
                    "hybrid_mode": False,
                    "seo_related": True,
                    "unified_display": True
                }
        
        # 6. サイト構造コンテキストを加味した評価
        contextual_evaluation = _evaluate_page_with_site_context(
            target_page_data,
            structure_summary
        )
        
        logger.info(f"[1ページ解析] コンテキスト評価完了: {contextual_evaluation['contextual_score']:.1f}点")
        
        # 7. RAG連携またはLLMで改善提案生成
        use_rag = rag_function is not None
        
        if use_rag:
            # RAG経路：社内SEO検定資料を活用した改善提案
            logger.info("[1ページ解析] RAG経路で改善提案生成開始")
            try:
                analysis_summary = _build_single_page_context_summary(
                    target_page_data,
                    structure_summary,
                    contextual_evaluation
                )
                
                logger.debug(f"[1ページ解析] RAG送信テキスト（先頭200文字）: {analysis_summary[:200]}")
                
                # RAG経路で改善提案を取得
                query = f"""【1ページ詳細SEO解析】
以下のページについて、サイト全体構造を踏まえた具体的な改善提案をしてください。

{analysis_summary}

**重要**: 以下の要素に焦点を当てて提案してください：

## 改善提案項目

1. **タイトルタグ** - 推奨30文字以内（モバイル表示で見切れないように）。キーワード配置、サイト全体との整合性
2. **メタディスクリプションタグ** - 推奨80文字程度（モバイルでは約80文字まで表示）。魅力的な説明文、CTR向上
3. **H1タグ** - 推奨25～30文字以内（モバイルでの可読性を考慮）。タイトルとの整合性、キーワード使用、わかりやすさ
4. **内部リンク戦略** - リンク数、アンカーテキスト多様度、関連性（アンカーテキストとページtitle・H1との類似度で評価）
5. **画像alt属性** - 設定率、適切性、アクセシビリティ（※リンク画像は評価対象外。ページ内容の説明として使用されている画像のみを評価）
6. **コンテンツ量** - ページ種別により推奨文字数が異なります（SEO3-3より）。**重要: 断定的な判断（「少ない」「不足」「達していない」等）は避け、必ず以下のすべての選択肢を提示してください**：
   【トップページ/メインページの場合】物販サイトなど: 0～800字、来店型ビジネス: 700～2,500字、単品サービスや単品通販: 4,000字以上
   【サブページの場合】単純な概念: 1,500字程度、複雑な事柄: 4,000字以上
   【YMYL分野の場合】上記それぞれの文字数の2倍が推奨
   ※解析するページがメインページかサブページかは判断せず、すべての選択肢を提示してユーザーに判断を委ねてください
7. **メタキーワードの整合性** - サイト全体キーワードとの乖離度（SEO効果はないが内部品質管理として有用）
8. **E-E-A-T要素** - 専門性(Expertise)、経験(Experience)、権威性(Authoritativeness)、信頼性(Trustworthiness)の観点から評価
9. **コンテンツ品質** - 発見・学び・娯楽・感動の要素。ユーザー価値を満たすか

**除外事項**: H2-H6タグ、canonicalタグ、構造化データ、OGP設定、FAQ/How-to/目次、更新日時表記などは不要です。
上記項目について、すぐに実行できる具体的なアクションプランを提示してください。
"""
                
                # ドメイン解析モードではSEOチェックをスキップ
                rag_response = rag_function(query, skip_seo_check=True)
                analysis_report = rag_response.get("answer", "RAG応答の取得に失敗しました")
                
            except Exception as e:
                logger.error(f"[1ページ解析] RAG処理エラー: {e}")
                analysis_report = f"RAG処理中にエラーが発生しました: {str(e)}"
        else:
            # 直接LLM経路（フォールバック）
            logger.info("[1ページ解析] 直接LLM経路で改善提案生成")
            analysis_report = _generate_single_page_report_direct(
                target_page_data,
                structure_summary,
                contextual_evaluation
            )
        
        # 8. 結果の整形
        sources = [
            {
                "url": target_url,
                "title": target_page_data.get("title", ""),
                "content": target_page_data.get("summary", "")[:300]
            }
        ]
        
        logger.info(f"[1ページ解析] 完了: {target_url}")
        
        return {
            "answer": analysis_report,
            "target_url": target_url,
            "contextual_score": contextual_evaluation["contextual_score"],
            "structure_summary": structure_summary,
            "page_analysis": target_page_data,
            "sources": sources,
            "hybrid_mode": use_rag,
            "seo_related": True,
            "unified_display": True
        }
        
    except Exception as e:
        logger.error(f"[1ページ解析] エラー: {e}")
        return {
            "answer": f"解析中にエラーが発生しました: {str(e)}",
            "target_url": target_url if 'target_url' in locals() else "",
            "sources": [],
            "hybrid_mode": False,
            "seo_related": True,
            "unified_display": True
        }


def _summarize_site_structure(pages: list) -> dict:
    """
    サイト全体の階層・カテゴリ・頻出語を要約
    
    Args:
        pages: クロールしたページデータのリスト
        
    Returns:
        dict: サイト構造の要約
            {
                "page_count": int,
                "depth_distribution": dict,  # {深さ: ページ数}
                "top_keywords": list,        # [(キーワード, 出現回数), ...]
                "avg_internal_links": float, # 平均内部リンク数
                "avg_word_count": float      # 平均文字数
            }
    """
    from collections import Counter
    
    depth_map = {}
    all_path_keywords = []
    total_internal_links = 0
    total_word_count = 0
    
    for page in pages:
        url = page.get("url", "")
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        
        # URL深さの計算
        depth = len(path.split("/")) if path else 0
        depth_map[depth] = depth_map.get(depth, 0) + 1
        
        # パスからキーワード抽出
        path_parts = [p for p in path.split("/") if p and len(p) > 2]
        all_path_keywords.extend(path_parts)
        
        # 内部リンク数
        total_internal_links += page.get("internal_links_count", 0)
        
        # 文字数（body_char_countを優先、なければbody_word_count）
        total_word_count += page.get("body_char_count", page.get("body_word_count", 0))
    
    page_count = len(pages)
    keyword_counts = Counter(all_path_keywords)
    
    return {
        "page_count": page_count,
        "depth_distribution": depth_map,
        "top_keywords": keyword_counts.most_common(10),
        "avg_internal_links": round(total_internal_links / page_count, 1) if page_count > 0 else 0,
        "avg_word_count": round(total_word_count / page_count, 1) if page_count > 0 else 0
    }


def _evaluate_page_with_site_context(page_data: dict, structure_summary: dict) -> dict:
    """
    サイト全体構造のコンテキストを加味したページ評価
    
    既存の3カテゴリ評価システムを基礎とし、サイト全体との比較情報を追加する。
    
    Args:
        page_data: 対象ページのSEO要素
        structure_summary: サイト全体構造の要約
        
    Returns:
        dict: コンテキスト評価結果
            {
                "contextual_score": float,        # コンテキスト加味後の総合スコア
                "base_score": float,              # 基本スコア（3カテゴリ評価）
                "context_adjustments": dict,      # コンテキストによる調整
                "suggestions": list               # 改善提案
            }
    """
    # 基本スコア（既存の3カテゴリ評価）
    scored_page = _apply_comprehensive_seo_scoring(page_data.copy())
    base_score = scored_page.get("comprehensive_score", 0)
    
    # コンテキストによる調整
    context_bonus = 0
    context_adjustments = {}
    suggestions = []
    
    # 1. 内部リンクの量と質の評価（SEO検定資料準拠：関連性重視）
    page_links = page_data.get("internal_links_count", 0)
    link_relevance = page_data.get("link_relevance_score", 0.0)
    
    if page_links == 0:
        suggestions.append(
            "内部リンクが0本です。"
            "SEO検定資料では『関連性の高いページへのリンクを増やす』ことが推奨されています。"
        )
        context_adjustments["internal_links"] = -5
        context_bonus -= 5
        
    elif page_links <= 2:
        suggestions.append(
            f"内部リンクが{page_links}本と少ないです。"
            "このページのテーマに関連する記事やカテゴリページへのリンクを追加しましょう。"
        )
        context_adjustments["internal_links"] = -3
        context_bonus -= 3
        
    elif page_links >= 3 and link_relevance < 0.4:
        suggestions.append(
            f"内部リンクは{page_links}本ありますが、関連性が低いリンクが含まれている可能性があります（関連性スコア: {link_relevance:.0%}）。"
            "アンカーテキストにページのキーワードを含めるか、より関連性の高いページへのリンクに見直しましょう。"
            "（SEO検定資料：アンカーテキストマッチの重要性）"
        )
        context_adjustments["internal_links"] = -2
        context_bonus -= 2
        
    elif page_links >= 3 and link_relevance >= 0.6:
        # 良好なケース：ボーナス
        context_adjustments["internal_links"] = +2
        context_bonus += 2
    
    # 2. コンテンツ量の評価（SEO検定資料準拠：ページ種別ごとの推奨提示）
    page_chars = page_data.get("body_char_count", page_data.get("body_word_count", 0))
    
    # SEO検定資料（SEO3-3）に基づく推奨文字数を選択肢形式で提示
    # メインページかサブページかの判断はせず、すべての選択肢を提示
    suggestions.append(
        f"現在の文字数は{page_chars}字です。ページの種類により推奨文字数が異なります：\n"
        "【トップページ/メインページの場合】\n"
        "  ・物販サイトなどのトップページ: 0～800字程度\n"
        "  ・来店型ビジネス（クリニック、美容室、整体院等）: 700～2,500字程度\n"
        "  ・単品サービスや単品通販のトップページ: 4,000字以上\n"
        "【サブページの場合】\n"
        "  ・単純な概念の解説: 1,500字程度\n"
        "  ・複雑な事柄の説明: 4,000字以上\n"
        "【YMYL分野の場合】上記それぞれの文字数の2倍が推奨されます\n"
        "ページの種類とYMYL該当性を確認の上、適切な文字数を目指してください。"
    )
    
    # スコアリングは控えめに（極端に少ない/十分な場合のみ調整）
    if page_chars < 400:
        # どのページタイプでも400字未満は少なすぎる
        context_adjustments["content_volume"] = -2
        context_bonus -= 2
    elif page_chars >= 2000:
        # 2000字以上あれば大抵のページタイプで十分
        context_adjustments["content_volume"] = +2
        context_bonus += 2
    
    # 3. URL階層の妥当性
    url = page_data.get("url", "")
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    page_depth = len(path.split("/")) if path else 0
    
    depth_dist = structure_summary.get("depth_distribution", {})
    if page_depth > 4:
        suggestions.append(f"URL階層が深すぎます（{page_depth}階層）。サイト構造の見直しを検討しましょう。")
        context_adjustments["url_depth"] = -2
        context_bonus -= 2
    
    # 4. サイト全体のキーワードとの整合性
    top_keywords = [kw for kw, count in structure_summary.get("top_keywords", [])]
    page_title = page_data.get("title", "").lower()
    page_h1 = " ".join(page_data.get("headings", {}).get("h1", [])).lower()
    
    keyword_match = False
    for kw in top_keywords[:5]:  # 上位5キーワードをチェック
        if kw.lower() in page_title or kw.lower() in page_h1:
            keyword_match = True
            break
    
    if not keyword_match and top_keywords:
        suggestions.append(f"サイト全体の主要キーワード（{', '.join(top_keywords[:3])}）との整合性を確認しましょう。")
        context_adjustments["keyword_alignment"] = -2
        context_bonus -= 2
    elif keyword_match:
        context_adjustments["keyword_alignment"] = +3
        context_bonus += 3
    
    # 5. メタキーワードタグとサイト全体キーワードの整合性チェック
    meta_keywords_list = page_data.get("meta_keywords_list", [])
    if meta_keywords_list and top_keywords:
        # メタキーワードとサイト全体キーワードの共通部分を計算
        meta_kw_lower = [mk.lower() for mk in meta_keywords_list]
        site_kw_lower = [sk.lower() for sk in top_keywords[:10]]
        
        common_keywords = set(meta_kw_lower) & set(site_kw_lower)
        alignment_ratio = len(common_keywords) / len(meta_kw_lower) if meta_kw_lower else 0
        
        if alignment_ratio < 0.3:  # 30%未満が一致
            misaligned_keywords = [mk for mk in meta_keywords_list if mk.lower() not in site_kw_lower]
            suggestions.append(
                f"メタキーワード（{', '.join(meta_keywords_list[:3])}）がサイト全体の主要テーマと乖離しています。"
                f"特に『{', '.join(misaligned_keywords[:2])}』はサイト構造との整合性を確認してください。"
            )
            context_adjustments["meta_keywords_alignment"] = -2
            context_bonus -= 2
        elif alignment_ratio >= 0.7:  # 70%以上が一致
            context_adjustments["meta_keywords_alignment"] = +2
            context_bonus += 2
    
    # 最終スコア計算
    contextual_score = max(0, min(100, base_score + context_bonus))
    
    return {
        "contextual_score": round(contextual_score, 1),
        "base_score": round(base_score, 1),
        "context_adjustments": context_adjustments,
        "suggestions": suggestions
    }


def _build_single_page_context_summary(page_data: dict, structure_summary: dict, evaluation: dict) -> str:
    """
    RAG経路に渡すための1ページ解析サマリテキストを生成
    
    Args:
        page_data: 対象ページのSEO要素
        structure_summary: サイト全体構造の要約
        evaluation: コンテキスト評価結果
        
    Returns:
        str: RAG用サマリテキスト
    """
    url = page_data.get("url", "")
    title = page_data.get("title", "")
    description = page_data.get("description", "")
    meta_keywords = page_data.get("meta_keywords", "")
    h1_list = page_data.get("headings", {}).get("h1", [])
    h1_text = ", ".join(h1_list) if h1_list else "(なし)"
    
    char_count = page_data.get("body_char_count", 0)  # 文字数（優先）
    word_count = page_data.get("body_word_count", 0)  # 後方互換
    internal_links = page_data.get("internal_links_count", 0)
    anchor_diversity = page_data.get("anchor_diversity", 0)
    link_relevance = page_data.get("link_relevance_score", 0)  # 内部リンク関連性スコア
    images_total = page_data.get("images_total", 0)
    images_no_alt = page_data.get("images_without_alt", 0)
    images_for_alt = page_data.get("images_total_for_alt", images_total)  # alt評価対象画像数（ヘッダー/フッター/メニュー/ロゴ/装飾/リンク画像を除外）
    poor_alt_images = page_data.get("images_with_poor_alt", [])  # 不適切なalt属性を持つ画像
    
    # サイト全体構造情報
    site_pages = structure_summary.get("page_count", 0)
    site_avg_words = structure_summary.get("avg_word_count", 0)
    site_avg_links = structure_summary.get("avg_internal_links", 0)
    top_keywords = structure_summary.get("top_keywords", [])
    top_kw_str = ", ".join([f"{kw}({cnt})" for kw, cnt in top_keywords[:5]]) if top_keywords else "(なし)"
    
    # 評価情報
    base_score = evaluation.get("base_score", 0)
    contextual_score = evaluation.get("contextual_score", 0)
    adjustments = evaluation.get("context_adjustments", {})
    suggestions = evaluation.get("suggestions", [])
    
    summary = f"""
■ 解析対象ページ
URL: {url}
タイトル: {title}
メタディスクリプション: {description}
メタキーワード: {meta_keywords if meta_keywords else "(設定なし)"}
H1: {h1_text}

■ ページの基本指標
- 文字数: {char_count}字
  ※推奨文字数はページ種別により異なります：
    【トップページ/メインページ】物販サイトなど0～800字、来店型ビジネス700～2,500字、単品サービスや単品通販4,000字以上
    【サブページ】単純な概念1,500字程度、複雑な事柄4,000字以上
    【YMYL分野】上記それぞれの2倍
  ※このページがどのタイプに該当するかは判断せず、すべての選択肢をユーザーに提示してください
- 内部リンク数: {internal_links}本（メインコンテンツ内のみ、ヘッダー/フッター/ナビ/サイドメニュー除外）
- アンカーテキスト多様度: {anchor_diversity:.2f}（1.0に近いほど多様）
- 内部リンク関連性: {link_relevance:.1%}（アンカーテキストとページtitle・H1との類似度、Jaccard係数使用）
- 画像: 評価対象{images_for_alt}枚（ヘッダー/フッター/メニュー/ロゴ/装飾/リンク画像除外）
  - alt属性なし: {images_no_alt}枚
  - 不適切なalt属性（汎用的表現）: {len(poor_alt_images)}枚

■ サイト全体構造情報
- サイト全体: {site_pages}ページ
- サイト主要キーワード: {top_kw_str}
- メタキーワードとサイト全体の整合性: {adjustments.get("meta_keywords_alignment", "N/A")}

■ SEO評価
- 基本スコア（3カテゴリ評価）: {base_score}点
- コンテキスト評価（サイト全体を考慮）: {contextual_score}点
- コンテキスト調整: {adjustments}

■ 自動検出された改善提案
{chr(10).join([f"- {s}" for s in suggestions]) if suggestions else "- (特になし)"}

■ 依頼事項
上記の情報を踏まえ、SEO検定資料に基づいた具体的な改善提案を行ってください。
特に「自分で改善可能な範囲」を重視し、E-E-A-T（専門性・経験・権威性・信頼性）やコンテンツ品質（発見・学び・娯楽・感動の要素）の観点からも評価してください。
"""
    
    return summary.strip()


def _generate_single_page_report_direct(page_data: dict, structure_summary: dict, evaluation: dict) -> str:
    """
    直接LLM経路での改善提案生成（フォールバック）
    
    Args:
        page_data: 対象ページのSEO要素
        structure_summary: サイト全体構造の要約
        evaluation: コンテキスト評価結果
        
    Returns:
        str: 改善提案レポート
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    try:
        llm = ChatOpenAI(
            model=ct.CHATBOT_CONFIG["MODEL_NAME"],
            temperature=ct.CHATBOT_CONFIG["TEMPERATURE"],
            timeout=ct.CHATBOT_CONFIG["TIMEOUT"]
        )
        
        summary = _build_single_page_context_summary(page_data, structure_summary, evaluation)
        
        prompt = f"""あなたはSEO専門家です。以下のページについて、サイト全体構造を踏まえた具体的な改善提案を行ってください。

{summary}

**重要**: 以下の要素に焦点を当てて提案してください：

## 改善提案項目

1. **タイトルタグ** - 推奨30文字以内（モバイル表示で見切れないように）。キーワード配置、サイト全体との整合性
2. **メタディスクリプションタグ** - 推奨80文字程度（全角で最大80文字まで、SEO3-3より）。魅力的な説明文、CTR向上
3. **H1タグ** - 推奨25～30文字以内（モバイルでの可読性を考慮）。タイトルとの整合性、キーワード使用、わかりやすさ
4. **内部リンク戦略** - リンク数、アンカーテキスト多様度、関連性（アンカーテキストとページtitle・H1との類似度で評価）、サイト平均との比較
5. **画像alt属性** - 設定率、適切性、アクセシビリティ（※リンク画像は評価対象外。ページ内容の説明として使用されている画像のみを評価）
   【重要】不適切なalt属性の改善：
   - 「ブログ画像」「画像1」のような汎用的表現は不適切
   - alt属性の目的: 視覚障害者への情報提供、画像が表示されない場合の代替テキスト、画像検索対策
   - 適切な例: "SEOキーワード調査ツールの管理画面スクリーンショット"
   - 不適切な例: "ブログ画像", "画像1", "photo.jpg"
   - Googleガイドライン: 具体的で説明的なテキスト、キーワード詰め込み禁止、文脈に合った自然な文章、3～125文字推奨
6. **コンテンツ量** - ページ種別により推奨文字数が異なります（SEO3-3より）。**重要: このページがどのタイプに該当するかを判断・推測してはいけません。必ずすべての選択肢を提示してください**：
   【トップページ/メインページの場合】物販サイトなど: 0～800字、来店型ビジネス: 700～2,500字、単品サービスや単品通販: 4,000字以上
   【サブページの場合】単純な概念: 1,500字程度、複雑な事柄: 4,000字以上
   【YMYL分野の場合】上記それぞれの文字数の2倍が推奨
   ※ページがどのタイプに該当するかはユーザーの判断に委ね、すべての選択肢を提示してください
7. **メタキーワードの整合性** - サイト全体キーワードとの乖離度（SEO効果はないが内部品質管理として有用）
8. **E-E-A-T要素** - 専門性(Expertise)、経験(Experience)、権威性(Authoritativeness)、信頼性(Trustworthiness)の観点から評価
9. **コンテンツ品質** - 発見・学び・娯楽・感動の要素。ユーザー価値を満たすか

**除外事項**: H2-H6タグ、canonicalタグ、構造化データ、OGP設定、FAQ/How-to/目次、更新日時表記などは不要です。

**厳守事項**：
- 具体的な数値基準は、上記の解析データに含まれる情報のみを使用してください
- サイト平均との相対評価（「平均〇本に対して〇本」等）は推奨されます
- 絶対的な数値基準（「〇本以上必要」「〇本は少ない」等）は、データに根拠がない限り使用禁止です
- 定性的な推奨（「関連ページへのリンクを増やす」等）を優先してください

上記項目について、すぐに実行できる具体的なアクションプランを提示してください。
"""
        
        response = llm.invoke(prompt)
        return response.content
        
    except Exception as e:
        logger.error(f"[直接LLM] エラー: {e}")
        return f"改善提案の生成中にエラーが発生しました: {str(e)}"

