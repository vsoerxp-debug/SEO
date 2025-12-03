"""
このファイルは、Googleサジェストキーワード取得機能を提供します。
APIキー不要・無料で利用可能なGoogle Suggest API + Bingフォールバックを使用します。

【注意事項】
- 社内専用ツールとして利用することを前提としています
- 公式な商用APIではないため、外部提供サービスとしての利用は推奨されません
- レート制限対策として3秒間隔を設けていますが、連続大量実行は避けてください
"""

############################################################
# ライブラリの読み込み
############################################################
import requests
import json
import time
import logging
from urllib.parse import quote
import constants as ct
from typing import List, Dict, Tuple


############################################################
# サジェストキーワード取得関数
############################################################

def fetch_google_suggest(keyword: str, max_retries: int = 3) -> List[str]:
    """
    Googleサジェストキーワードを取得（単一キーワード）
    
    Args:
        keyword: 検索キーワード
        max_retries: 最大リトライ回数
        
    Returns:
        List[str]: サジェストキーワードのリスト（最大10件）
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    # 入力値のバリデーション
    if not keyword or not keyword.strip():
        logger.warning("空のキーワードが入力されました")
        return []
    
    keyword = keyword.strip()
    
    # Google Suggest API エンドポイント（Firefox client）
    base_url = "https://www.google.com/complete/search"
    
    # パラメータ（地域パーソナライゼーション抑制版）
    params = {
        'q': keyword,
        'client': 'firefox',
        'hl': 'ja',  # 日本語
        'gl': 'jp'   # 地域: 日本全体（個別地域バイアスを抑制）
    }
    
    # User-Agent設定（Streamlit Cloud対策・macOS Safari仕様）
    headers = {
        'User-Agent': ct.SUGGEST_USER_AGENT,
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'DNT': '1',  # Do Not Track（トラッキング拒否）
        'Cookie': '',  # Cookieを送信しない（セッション情報排除）
        'Cache-Control': 'no-cache',  # キャッシュ無効化
        'X-Forwarded-For': '203.0.113.0'  # 匿名IPアドレス（RFC 5737 TEST-NET-3）
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[Google] サジェスト取得: '{keyword}' (試行 {attempt + 1}/{max_retries})")
            
            # リクエスト送信（タイムアウト10秒）
            response = requests.get(
                base_url,
                params=params,
                headers=headers,
                timeout=ct.SUGGEST_KEYWORDS_CONFIG["TIMEOUT"]
            )
            
            # ステータスコード確認
            response.raise_for_status()
            
            # JSONレスポンスをパース
            # フォーマット: [query, [suggestions]]
            data = response.json()
            
            if isinstance(data, list) and len(data) >= 2:
                suggestions = data[1]
                if isinstance(suggestions, list):
                    logger.info(f"[Google] サジェスト取得成功: {len(suggestions)}件")
                    return suggestions[:10]  # 最大10件
            
            logger.warning(f"[Google] 予期しないレスポンス形式: {data}")
            return []
            
        except requests.exceptions.Timeout:
            logger.warning(f"[Google] タイムアウト: '{keyword}' (試行 {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)  # 2秒待機してリトライ
            
        except requests.exceptions.HTTPError as e:
            # 403/429エラーの場合は特別処理
            if response.status_code in [403, 429]:
                logger.warning(f"[Google] アクセス制限検出 (HTTP {response.status_code}): '{keyword}'")
                # すぐにBingフォールバックに切り替えるため、リトライせずに抜ける
                break
            else:
                logger.error(f"[Google] HTTPエラー ({response.status_code}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[Google] リクエストエラー: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            
        except json.JSONDecodeError as e:
            logger.error(f"[Google] JSON解析エラー: {e}")
            return []
            
        except Exception as e:
            logger.error(f"[Google] 予期しないエラー: {e}")
            return []
    
    logger.warning(f"[Google] 最大リトライ回数到達: '{keyword}'")
    return []


def fetch_bing_suggest(keyword: str, max_retries: int = 3) -> List[str]:
    """
    Bingサジェストキーワードを取得（Googleフォールバック用）
    
    Args:
        keyword: 検索キーワード
        max_retries: 最大リトライ回数
        
    Returns:
        List[str]: サジェストキーワードのリスト（最大10件）
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    # 入力値のバリデーション
    if not keyword or not keyword.strip():
        logger.warning("[Bing] 空のキーワードが入力されました")
        return []
    
    keyword = keyword.strip()
    
    # Bing Suggest API エンドポイント
    base_url = "https://api.bing.com/osjson.aspx"
    
    # パラメータ（地域パーソナライゼーション抑制版）
    params = {
        'query': keyword,
        'language': 'ja-JP',
        'market': 'ja-JP'  # 市場: 日本全体（地域バイアスを抑制）
    }
    
    # User-Agent設定（Googleと同じ）
    headers = {
        'User-Agent': ct.SUGGEST_USER_AGENT,
        'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Cookie': '',  # Cookieを送信しない
        'Cache-Control': 'no-cache',  # キャッシュ無効化
        'X-Forwarded-For': '203.0.113.0'  # 匿名IPアドレス
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[Bing] サジェスト取得: '{keyword}' (試行 {attempt + 1}/{max_retries})")
            
            # リクエスト送信（タイムアウト10秒）
            response = requests.get(
                base_url,
                params=params,
                headers=headers,
                timeout=ct.SUGGEST_KEYWORDS_CONFIG["TIMEOUT"]
            )
            
            # ステータスコード確認
            response.raise_for_status()
            
            # JSONレスポンスをパース
            # フォーマット: [query, [suggestions]]（Googleと同じ）
            data = response.json()
            
            if isinstance(data, list) and len(data) >= 2:
                suggestions = data[1]
                if isinstance(suggestions, list):
                    logger.info(f"[Bing] サジェスト取得成功: {len(suggestions)}件")
                    return suggestions[:10]  # 最大10件
            
            logger.warning(f"[Bing] 予期しないレスポンス形式: {data}")
            return []
            
        except requests.exceptions.Timeout:
            logger.warning(f"[Bing] タイムアウト: '{keyword}' (試行 {attempt + 1})")
            if attempt < max_retries - 1:
                time.sleep(2)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[Bing] リクエストエラー: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            
        except json.JSONDecodeError as e:
            logger.error(f"[Bing] JSON解析エラー: {e}")
            return []
            
        except Exception as e:
            logger.error(f"[Bing] 予期しないエラー: {e}")
            return []
    
    logger.warning(f"[Bing] 最大リトライ回数到達: '{keyword}'")
    return []


def fetch_suggest_with_fallback(keyword: str) -> Tuple[List[str], str]:
    """
    サジェスト取得（Google → Bingフォールバック）
    
    Args:
        keyword: 検索キーワード
        
    Returns:
        Tuple[List[str], str]: (サジェストリスト, 取得元='google'/'bing'/'none')
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    # まずGoogleで取得
    suggestions = fetch_google_suggest(keyword)
    
    if suggestions:
        return suggestions, 'google'
    
    # Google失敗時、Bingフォールバックが有効なら実行
    if ct.SUGGEST_KEYWORDS_CONFIG.get("USE_BING_FALLBACK", True):
        logger.info(f"[Fallback] Googleで取得失敗。Bingでリトライ: '{keyword}'")
        suggestions = fetch_bing_suggest(keyword)
        
        if suggestions:
            return suggestions, 'bing'
    
    logger.warning(f"[Fallback] すべてのサジェスト取得失敗: '{keyword}'")
    return [], 'none'


def fetch_combined_suggests(keyword1: str, keyword2: str) -> Dict[str, Dict]:
    """
    2つのキーワードを組み合わせてサジェストを取得（2パターン）
    
    Args:
        keyword1: メインキーワード①
        keyword2: メインキーワード②
        
    Returns:
        Dict[str, Dict]: パターン別サジェスト結果
            {
                "pattern_1_2": {
                    "query": "キーワード1 キーワード2",
                    "suggests": [...],
                    "source": "google"/"bing"/"none"
                },
                "pattern_2_1": {
                    "query": "キーワード2 キーワード1",
                    "suggests": [...],
                    "source": "google"/"bing"/"none"
                }
            }
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    
    # 入力値バリデーション
    if not keyword1 or not keyword1.strip():
        logger.error("キーワード①が空です")
        return {}
    if not keyword2 or not keyword2.strip():
        logger.error("キーワード②が空です")
        return {}
    
    keyword1 = keyword1.strip()
    keyword2 = keyword2.strip()
    
    delay_seconds = ct.SUGGEST_KEYWORDS_CONFIG["REQUEST_DELAY"]
    results = {}
    
    # パターン1: キーワード① + キーワード②
    query1 = f"{keyword1} {keyword2}"
    logger.info(f"パターン1取得開始: '{query1}'")
    suggests1, source1 = fetch_suggest_with_fallback(query1)
    results["pattern_1_2"] = {
        "query": query1,
        "suggests": suggests1,
        "source": source1
    }
    time.sleep(delay_seconds)  # レート制限対策（3秒）
    
    # パターン2: キーワード② + キーワード①
    query2 = f"{keyword2} {keyword1}"
    logger.info(f"パターン2取得開始: '{query2}'")
    suggests2, source2 = fetch_suggest_with_fallback(query2)
    results["pattern_2_1"] = {
        "query": query2,
        "suggests": suggests2,
        "source": source2
    }
    
    # 結果サマリーのログ出力
    total_suggests = sum(len(r["suggests"]) for r in results.values())
    google_count = sum(1 for r in results.values() if r["source"] == "google")
    bing_count = sum(1 for r in results.values() if r["source"] == "bing")
    
    logger.info(f"サジェスト取得完了: 合計 {total_suggests}件 (Google:{google_count}パターン, Bing:{bing_count}パターン)")
    
    return results


def format_suggest_results(results: Dict[str, Dict], 
                          keyword1: str, keyword2: str) -> str:
    """
    サジェスト結果を見やすくフォーマット
    
    Args:
        results: fetch_combined_suggests()の戻り値
        keyword1: メインキーワード①
        keyword2: メインキーワード②
        
    Returns:
        str: フォーマット済みテキスト
    """
    if not results:
        return (
            "⚠️ サジェストキーワードを取得できませんでした。\n\n"
            "**考えられる原因**:\n"
            "- Google / Bing 側で一時的なアクセス制限がかかっている可能性があります\n"
            "- キーワードのスペルミスや特殊文字が含まれている可能性があります\n"
            "- ネットワーク接続に問題がある可能性があります\n\n"
            "しばらく時間をおいてから再度お試しください。"
        )
    
    output = []
    output.append("### 🔍 サジェストキーワード調査結果\n")
    output.append(f"**メインキーワード①**: `{keyword1}`")
    output.append(f"**メインキーワード②**: `{keyword2}`")
    output.append("\n---\n")
    
    # パターン1: キーワード① + キーワード②
    pattern1 = results.get("pattern_1_2", {})
    if pattern1.get("suggests"):
        source_label = "🟢 Google" if pattern1["source"] == "google" else "🔵 Bing"
        output.append(f"#### 📌 パターン1: 『{pattern1['query']}』のサジェスト ({source_label})")
        for i, suggest in enumerate(pattern1["suggests"], 1):
            output.append(f"{i}. {suggest}")
        output.append("")
    else:
        output.append(f"#### 📌 パターン1: 『{pattern1.get('query', '')}』のサジェスト")
        output.append("（取得できませんでした）")
        output.append("")
    
    # パターン2: キーワード② + キーワード①
    pattern2 = results.get("pattern_2_1", {})
    if pattern2.get("suggests"):
        source_label = "🟢 Google" if pattern2["source"] == "google" else "🔵 Bing"
        output.append(f"#### 📌 パターン2: 『{pattern2['query']}』のサジェスト ({source_label})")
        for i, suggest in enumerate(pattern2["suggests"], 1):
            output.append(f"{i}. {suggest}")
        output.append("")
    else:
        output.append(f"#### 📌 パターン2: 『{pattern2.get('query', '')}』のサジェスト")
        output.append("（取得できませんでした）")
        output.append("")
    
    # 統計情報
    total_count = sum(len(r.get("suggests", [])) for r in results.values())
    google_patterns = sum(1 for r in results.values() if r.get("source") == "google" and r.get("suggests"))
    bing_patterns = sum(1 for r in results.values() if r.get("source") == "bing" and r.get("suggests"))
    
    output.append("---")
    output.append(f"**合計取得数**: {total_count}件")
    output.append(f"**取得元**: Google {google_patterns}パターン、Bing {bing_patterns}パターン")
    output.append(f"**取得日時**: {time.strftime('%Y年%m月%d日 %H:%M:%S')}")
    output.append("\n*※ 社内専用ツールとして利用してください。連続大量実行はお控えください。*")
    
    return "\n".join(output)


def format_suggest_results_to_csv(results: Dict[str, Dict], 
                                  keyword1: str, keyword2: str) -> str:
    """
    サジェスト結果をCSV形式に変換
    
    Args:
        results: fetch_combined_suggests()の戻り値
        keyword1: メインキーワード①
        keyword2: メインキーワード②
        
    Returns:
        str: CSV形式の文字列（BOM付きUTF-8でExcel互換）
    """
    import csv
    import io
    
    # CSV出力用のStringIOバッファ
    output = io.StringIO()
    
    # BOM（Byte Order Mark）を追加してExcelで正しく開けるようにする
    output.write('\ufeff')
    
    # CSVライター作成
    writer = csv.writer(output, lineterminator='\n')
    
    # ヘッダー行
    writer.writerow([
        'パターン',
        '検索クエリ',
        '取得元',
        '順位',
        'サジェストキーワード'
    ])
    
    # データがない場合
    if not results:
        writer.writerow([
            '-',
            '-',
            '-',
            '-',
            'サジェストを取得できませんでした'
        ])
        return output.getvalue()
    
    # パターン1: キーワード① + キーワード②
    pattern1 = results.get("pattern_1_2", {})
    pattern_name = "パターン1"
    query = pattern1.get("query", "")
    source = pattern1.get("source", "none")
    source_label = "Google" if source == "google" else "Bing" if source == "bing" else "取得失敗"
    suggests = pattern1.get("suggests", [])
    
    if suggests:
        for rank, suggest in enumerate(suggests, 1):
            writer.writerow([
                pattern_name,
                query,
                source_label,
                rank,
                suggest
            ])
    else:
        writer.writerow([
            pattern_name,
            query,
            source_label,
            '-',
            '（取得できませんでした）'
        ])
    
    # パターン2: キーワード② + キーワード①
    pattern2 = results.get("pattern_2_1", {})
    pattern_name = "パターン2"
    query = pattern2.get("query", "")
    source = pattern2.get("source", "none")
    source_label = "Google" if source == "google" else "Bing" if source == "bing" else "取得失敗"
    suggests = pattern2.get("suggests", [])
    
    if suggests:
        for rank, suggest in enumerate(suggests, 1):
            writer.writerow([
                pattern_name,
                query,
                source_label,
                rank,
                suggest
            ])
    else:
        writer.writerow([
            pattern_name,
            query,
            source_label,
            '-',
            '（取得できませんでした）'
        ])
    
    # 統計情報を最後に追加
    writer.writerow([])  # 空行
    writer.writerow(['統計情報', '', '', '', ''])
    
    total_count = sum(len(r.get("suggests", [])) for r in results.values())
    google_patterns = sum(1 for r in results.values() if r.get("source") == "google" and r.get("suggests"))
    bing_patterns = sum(1 for r in results.values() if r.get("source") == "bing" and r.get("suggests"))
    
    writer.writerow(['メインキーワード①', keyword1, '', '', ''])
    writer.writerow(['メインキーワード②', keyword2, '', '', ''])
    writer.writerow(['合計取得数', f'{total_count}件', '', '', ''])
    writer.writerow(['Google取得', f'{google_patterns}パターン', '', '', ''])
    writer.writerow(['Bing取得', f'{bing_patterns}パターン', '', '', ''])
    writer.writerow(['取得日時', time.strftime('%Y年%m月%d日 %H:%M:%S'), '', '', ''])
    
    return output.getvalue()


def validate_keywords(keyword1: str, keyword2: str) -> Tuple[bool, str]:
    """
    キーワード入力のバリデーション
    
    Args:
        keyword1: メインキーワード①
        keyword2: メインキーワード②
        
    Returns:
        Tuple[bool, str]: (バリデーション成功, エラーメッセージ)
    """
    # 空チェック
    if not keyword1 or not keyword1.strip():
        return False, "❌ メインキーワード①を入力してください"
    
    if not keyword2 or not keyword2.strip():
        return False, "❌ メインキーワード②を入力してください"
    
    # 長さチェック
    max_length = ct.SUGGEST_KEYWORDS_CONFIG["MAX_KEYWORD_LENGTH"]
    if len(keyword1.strip()) > max_length:
        return False, f"❌ メインキーワード①は{max_length}文字以内で入力してください"
    
    if len(keyword2.strip()) > max_length:
        return False, f"❌ メインキーワード②は{max_length}文字以内で入力してください"
    
    # 同一キーワードチェック
    if keyword1.strip().lower() == keyword2.strip().lower():
        return False, "❌ 異なるキーワードを入力してください"
    
    return True, ""
