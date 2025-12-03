"""
練習問題モード - SEO検定練習問題生成システム
"""

import streamlit as st
import constants as ct
import logging
from typing import Dict, List, Tuple, Optional
import json
import hashlib
import os
from langchain_core.documents import Document

logger = logging.getLogger(ct.LOGGER_NAME)


############################################################
# 1. データ構造定義
############################################################

class QuestionData:
    """問題データの構造（Pydantic不使用版）"""
    
    def __init__(self, question: str, choices: List[str], 
                 correct_index: int, explanations: Dict[str, str],
                 category: str = "", difficulty: str = ""):
        self.question = question
        self.choices = choices  # 4個の選択肢
        self.correct_index = correct_index  # 0-3
        self.explanations = explanations  # {"choice_0": "...", ...}
        self.category = category
        self.difficulty = difficulty
    
    @staticmethod
    def from_dict(data: dict) -> 'QuestionData':
        """辞書から生成"""
        return QuestionData(
            question=data["question"],
            choices=data["choices"],
            correct_index=data["correct_answer"],
            explanations=data["explanations"],
            category=data.get("category", ""),
            difficulty=data.get("difficulty", "")
        )
    
    def validate(self) -> Tuple[bool, str]:
        """データ検証"""
        if not self.question:
            return False, "問題文が空です"
        if len(self.choices) != 4:
            return False, f"選択肢は4つ必要です（現在{len(self.choices)}個）"
        if not (0 <= self.correct_index < 4):
            return False, f"正解インデックスが不正です: {self.correct_index}"
        if len(self.explanations) != 4:
            return False, f"解説は4つ必要です（現在{len(self.explanations)}個）"
        return True, ""


############################################################
# 2. 文書取得関数
############################################################

def get_reference_documents(grade: str, num_docs: int = 3) -> List[Document]:
    """
    級に応じた参考文書を取得
    
    Args:
        grade: "1級", "2級", "3級"
        num_docs: 取得文書数
        
    Returns:
        参考文書リスト
    """
    logger.info(f"[練習問題] get_reference_documents()開始: grade={grade}, num_docs={num_docs}")
    
    # 【Step 3】練習問題専用retriever（k=50）を優先使用
    if hasattr(st.session_state, 'retriever_practice'):
        active_retriever = st.session_state.retriever_practice
        logger.info("[Step 3] 練習問題専用Retriever（k=50）を使用")
    elif hasattr(st.session_state, 'retriever'):
        active_retriever = st.session_state.retriever
        logger.warning("[Step 3] 練習問題専用Retriever未初期化、既存retriever使用")
    else:
        logger.error("[練習問題] ベクターストアが初期化されていません")
        raise RuntimeError("ベクターストアが初期化されていません")
    
    # 【Step 4】検索クエリ生成（トピックランダム方式）
    target_patterns = ct.PRACTICE_QUESTIONS_CONFIG["GRADE_RANGES"][grade]
    
    # トピック候補リスト（grade別）
    import random
    TOPICS = {
        "1級": [
            "モバイルSEO スマートフォン最適化 Core Web Vitals レスポンシブデザイン",
            "ローカルSEO Googleビジネスプロフィール MEO 地域検索最適化",
            "Googleアップデート アルゴリズム変動 検索品質評価 コアアップデート",
            "インデックス促進 クローラビリティ サイトマップ robots.txt",
            "検索順位の復旧 ペナルティ対策 順位変動 リカバリー手法",
            "生成AI活用 ChatGPT SEOツール AI支援コンテンツ作成",
            "SEO環境変化 検索エンジントレンド 将来予測 技術革新"
        ],
        "2級": [
            "コンテンツSEO キーワード選定 E-E-A-T 高品質コンテンツ",
            "テクニカルSEO サイト高速化 構造最適化 技術改善",
            "ローカルSEO 地域ビジネス 店舗集客 ローカル検索",
            "リンクビルディング 被リンク獲得 ドメイン権威 リンク戦略",
            "SEOツール活用 Search Console Analytics データ分析"
        ],
        "3級": [
            "SEO基礎知識 検索エンジン仕組み クローラー インデックス",
            "キーワード調査 検索意図 キーワードプランナー 競合分析",
            "メタタグ最適化 title description 構造化マークアップ",
            "内部リンク サイト構造 ナビゲーション パンくずリスト",
            "外部リンク 被リンク ドメイン評価 リンク品質"
        ],
        "4級": [
            "検索エンジン基礎 Google検索 検索結果表示 SERPs",
            "HTML基礎 タグ構造 見出しタグ 段落タグ",
            "URL最適化 パス構造 パラメータ URLの正規化",
            "画像最適化 alt属性 ファイル名 画像圧縮",
            "モバイル対応 スマートフォン表示 タップ要素 フォント"
        ]
    }
    
    # ランダムトピック選択
    if grade in TOPICS:
        random_topic = random.choice(TOPICS[grade])
        query = f"{grade}のSEO検定 {random_topic}"
        logger.info(f"[Step 4] トピックランダム方式: {random_topic}")
    else:
        query = f"{grade}のSEO検定に関する基礎知識と重要概念"
        logger.info(f"[Step 4] デフォルトクエリ使用（トピック定義なし）")
    
    logger.info(f"[練習問題] 検索クエリ: {query}, 対象パターン: {target_patterns}")
    
    # 全文書取得（練習問題専用retriever使用）
    all_docs = active_retriever.invoke(query)
    logger.info(f"[Step 3] 取得文書総数: {len(all_docs)}（retriever_type={'practice(k=50)' if hasattr(st.session_state, 'retriever_practice') else 'standard'}）")
    
    # 【Phase 1】デバッグログ: 取得文書の文字数分析
    if all_docs:
        sample_doc_lengths = [len(doc.page_content) for doc in all_docs[:5]]
        logger.info(f"[練習問題] サンプル文書文字数（最初5件）: {sample_doc_lengths}")
    
    # メタデータでフィルタリング（級別ファイル絞り込み）
    # Windows環境対応: パス区切り文字を統一して比較
    filtered_docs = []
    for doc in all_docs:
        source = doc.metadata.get('source', '').replace('\\', '/')
        # data/SEO2-1 xxx.pdf のような形式を想定
        if any(pattern in source for pattern in target_patterns):
            filtered_docs.append(doc)
    
    logger.info(f"[練習問題] フィルタ後文書数: {len(filtered_docs)} (対象パターン: {target_patterns})")
    
    # 【Phase 2A】デバッグログ: パターン別の文書数を集計
    pattern_counts = {pattern: 0 for pattern in target_patterns}
    for doc in filtered_docs:
        source = doc.metadata.get('source', '').replace('\\', '/')
        for pattern in target_patterns:
            if pattern in source:
                pattern_counts[pattern] += 1
                break
    logger.info(f"[練習問題] パターン別文書数: {pattern_counts}")
    
    if filtered_docs:
        logger.info(f"[練習問題] サンプルソース: {filtered_docs[0].metadata.get('source', 'N/A')}")
        # 【Phase 1】デバッグログ: フィルタ後文書の文字数分析
        filtered_doc_lengths = [len(doc.page_content) for doc in filtered_docs[:5]]
        logger.info(f"[練習問題] フィルタ後サンプル文字数（最初5件）: {filtered_doc_lengths}")
    else:
        # デバッグ: フィルタリングに失敗した場合、全文書のソースを確認
        logger.warning(f"[練習問題] フィルタリング失敗 - 全文書のソースをサンプル表示:")
        for i, doc in enumerate(all_docs[:5]):  # 最初の5件のみ
            logger.warning(f"  文書{i+1}: {doc.metadata.get('source', 'N/A')}")
    
    # 上位N件を返す
    result_docs = filtered_docs[:num_docs] if filtered_docs else []
    logger.info(f"[練習問題] 最終返却文書数: {len(result_docs)}件")
    
    # 【Phase 1】デバッグログ: 返却文書の詳細文字数
    for i, doc in enumerate(result_docs):
        doc_length = len(doc.page_content)
        doc_source = doc.metadata.get('source', 'N/A').split('/')[-1]  # ファイル名のみ
        logger.info(f"[練習問題] 返却文書{i+1}: {doc_source}, 文字数={doc_length}文字")
    
    # 【Phase 2B】デバッグログ: 平均文字数とchunk_size検証
    if result_docs:
        avg_length = sum(len(doc.page_content) for doc in result_docs) / len(result_docs)
        max_length = max(len(doc.page_content) for doc in result_docs)
        min_length = min(len(doc.page_content) for doc in result_docs)
        logger.info(f"[Phase 2B] チャンク文字数統計: 平均={avg_length:.0f}, 最大={max_length}, 最小={min_length}")
    
    # 上位N件を返す（元のコード）
    result = filtered_docs[:num_docs]
    logger.info(f"[練習問題] {grade}用参考文書: {len(result)}件取得")
    return result


def get_official_problem_samples(grade: str) -> str:
    """
    公式問題集PDFから問題サンプルを取得（Phase 3-1改善版：全ファイル対応）
    
    Args:
        grade: 受験級（"1級", "2級", "3級"）
        
    Returns:
        問題サンプルのテキスト（フォーマット参考用）
    """
    if grade not in ct.PRACTICE_QUESTIONS_CONFIG["OFFICIAL_PDF_PATTERNS"]:
        logger.info(f"[練習問題] {grade}の公式問題集PDFパターンは未定義")
        return ""
    
    try:
        import fitz  # PyMuPDF
        import random
        import glob
        
        # 級別のファイルパターンを取得
        file_patterns = ct.PRACTICE_QUESTIONS_CONFIG["OFFICIAL_PDF_PATTERNS"][grade]
        pdf_dir = ct.PRACTICE_QUESTIONS_CONFIG["OFFICIAL_PDF_DIR"]
        
        # パターンに一致する全PDFファイルを検索
        matching_files = []
        for pattern in file_patterns:
            pattern_path = os.path.join(pdf_dir, f"{pattern}*.pdf")
            matched = glob.glob(pattern_path)
            matching_files.extend(matched)
        
        if not matching_files:
            logger.warning(f"[練習問題] {grade}の公式問題集PDFが見つかりません（パターン: {file_patterns}）")
            return ""
        
        logger.info(f"[練習問題] {grade}用問題集PDF検出: {len(matching_files)}件")
        for f in matching_files:
            logger.info(f"  - {os.path.basename(f)}")
        
        # ランダムに複数ファイルから問題を抽出
        num_samples = ct.PRACTICE_QUESTIONS_CONFIG["NUM_SAMPLE_PROBLEMS"]
        sample_char_length = ct.PRACTICE_QUESTIONS_CONFIG["SAMPLE_CHAR_LENGTH"]
        problem_texts = []
        
        # ファイルをシャッフルして、各ファイルから均等にサンプル抽出
        random.shuffle(matching_files)
        samples_per_file = max(1, num_samples // len(matching_files))
        
        for pdf_path in matching_files[:num_samples]:  # 必要な数だけファイルを処理
            try:
                doc = fitz.open(pdf_path)
                num_pages = len(doc)
                
                if num_pages == 0:
                    logger.warning(f"[練習問題] ページ数0: {os.path.basename(pdf_path)}")
                    doc.close()
                    continue
                
                # ランダムにページを選択（全ページ対象）
                start_page, end_page = ct.PRACTICE_QUESTIONS_CONFIG["SAMPLE_PAGE_RANGE"]
                available_pages = list(range(min(start_page, num_pages-1), min(end_page, num_pages)))
                
                if available_pages:
                    selected_pages = random.sample(available_pages, min(samples_per_file, len(available_pages)))
                    
                    for page_num in selected_pages:
                        page = doc[page_num]
                        text = page.get_text()
                        
                        # 指定文字数を抽出
                        if text.strip():
                            problem_texts.append(
                                f"【公式問題サンプル{len(problem_texts)+1}】"
                                f"（出典: {os.path.basename(pdf_path)}）\n{text[:sample_char_length]}"
                            )
                
                doc.close()
                
                # 目標サンプル数に達したら終了
                if len(problem_texts) >= num_samples:
                    break
                    
            except Exception as e:
                logger.error(f"[練習問題] PDF読み込みエラー（{os.path.basename(pdf_path)}）: {e}")
                continue
        
        if problem_texts:
            result = "\n\n".join(problem_texts)
            logger.info(f"[練習問題] {grade}公式問題サンプル取得成功: {len(problem_texts)}件")
            return result
        else:
            logger.warning(f"[練習問題] {grade}公式問題サンプルを抽出できませんでした")
            return ""
        
    except Exception as e:
        logger.error(f"[練習問題] 公式問題集PDF読み込みエラー: {e}")
        return ""


############################################################
# 3. 問題生成関数
############################################################

def generate_question(grade: str) -> Optional[QuestionData]:
    """
    問題を生成（Phase 3-2: 重複チェック機能付き）
    
    Args:
        grade: 受験級
        
    Returns:
        QuestionData or None（失敗時）
    """
    logger.info(f"[練習問題] generate_question()開始: grade={grade}")
    max_retries = ct.PRACTICE_QUESTIONS_CONFIG["MAX_RETRY_ON_JSON_ERROR"]
    max_duplicate_retry = ct.PRACTICE_QUESTIONS_CONFIG["MAX_DUPLICATE_RETRY"]
    
    # Phase 3-2: 重複チェック付き生成ループ
    for dup_attempt in range(max_duplicate_retry):
        logger.info(f"[練習問題] 重複チェック試行 {dup_attempt+1}/{max_duplicate_retry}")
        
        # 通常の生成処理
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"[練習問題] JSON生成試行{attempt+1}回目開始")
                # 1. 参考文書取得
                ref_docs = get_reference_documents(
                    grade, 
                    ct.PRACTICE_QUESTIONS_CONFIG["NUM_REFERENCE_DOCS"]
                )
                
                if not ref_docs:
                    logger.error("[練習問題] 参考文書が取得できません")
                    return None
                
                logger.info(f"[練習問題] 参考文書取得成功: {len(ref_docs)}件")
                
                # 2. コンテキスト構築（改善版：文字数増加）
                char_length = ct.PRACTICE_QUESTIONS_CONFIG["REFERENCE_DOC_CHAR_LENGTH"]
                logger.info(f"[練習問題] 設定値 REFERENCE_DOC_CHAR_LENGTH={char_length}文字")
                
                # 【Phase 1】デバッグログ: 各参考資料の実際の切り出し文字数
                context_parts = []
                for i, doc in enumerate(ref_docs):
                    original_length = len(doc.page_content)
                    truncated_text = doc.page_content[:char_length]
                    actual_length = len(truncated_text)
                    context_parts.append(f"【参考資料{i+1}】\n{truncated_text}")
                    logger.info(f"[練習問題] 参考資料{i+1}: 元文字数={original_length}, 切り出し後={actual_length}文字")
                
                context = "\n\n---\n\n".join(context_parts)
                logger.info(f"[練習問題] コンテキスト構築完了: 参考資料部分={len(context)}文字")
                
                # 2-1. Phase 3-1改善版: 公式問題サンプルを追加
                official_samples = get_official_problem_samples(grade)
                if official_samples:
                    context = f"{context}\n\n---\n\n{official_samples}"
                    logger.info(f"[練習問題] 公式問題サンプル追加: +{len(official_samples)}文字")
                    logger.info(f"[練習問題] 最終コンテキスト: 総文字数={len(context)}文字（参考資料+公式サンプル）")
                else:
                    logger.info(f"[練習問題] 公式問題サンプルなし（{grade}）")
                    logger.info(f"[練習問題] 最終コンテキスト: 総文字数={len(context)}文字（参考資料のみ）")
                
                # 3. LLM呼び出し（問題生成プロンプト）
                question_json = _call_llm_for_question(grade, context)
                
                # 4. JSON解析
                question_data = _parse_question_json(question_json)
                
                if question_data:
                    # デバッグログ: LLM生成直後の正解位置を記録
                    original_correct_letter = chr(65 + question_data.correct_index)  # 0→A, 1→B, etc.
                    logger.info(f"[練習問題] LLM生成時の正解位置: {original_correct_letter} (index={question_data.correct_index})")
                    
                    # Phase 3-2: 重複チェック（シャッフル前に実行）
                    if is_duplicate_question(question_data.question):
                        logger.warning(f"[練習問題] 重複問題検出 - 再生成します")
                        break  # 内側ループを抜けて外側ループで再試行
                    
                    # 【Phase 1】重複チェック後に正解位置をシャッフル（重要：この順序厳守）
                    import random
                    choices = question_data.choices
                    correct_index = question_data.correct_index
                    
                    # 正解の選択肢を保持
                    correct_choice = choices[correct_index]
                    
                    # 選択肢をランダムシャッフル
                    indices = list(range(len(choices)))
                    random.shuffle(indices)
                    
                    shuffled_choices = [choices[i] for i in indices]
                    new_correct_index = shuffled_choices.index(correct_choice)
                    
                    # データを更新
                    question_data.choices = shuffled_choices
                    question_data.correct_index = new_correct_index
                    
                    # シャッフル後の正解位置をログ出力
                    shuffled_correct_letter = chr(65 + new_correct_index)
                    logger.info(f"[練習問題] シャッフル後の正解位置: {original_correct_letter}→{shuffled_correct_letter} (index={question_data.correct_index})")
                    
                    # 重複していなければ履歴に追加して返す
                    add_to_history(question_data.question)
                    logger.info(f"[練習問題] {grade}問題生成成功（重複なし、最終正解={shuffled_correct_letter}）")
                    return question_data
                else:
                    logger.warning(f"[練習問題] JSON解析失敗（試行{attempt+1}回目）")
                    
            except Exception as e:
                logger.error(f"[練習問題] 生成エラー: {e}")
                if attempt >= max_retries:
                    break  # 内側ループを抜ける
    
    logger.error("[練習問題] 問題生成失敗（全試行完了）")
    return None


def _call_llm_for_question(grade: str, context: str) -> str:
    """LLMを呼び出して問題JSONを生成"""
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    
    llm = ChatOpenAI(
        model=ct.MODEL,
        temperature=ct.PRACTICE_QUESTIONS_CONFIG["QUESTION_GENERATION_TEMPERATURE"]
    )
    
    system_prompt = f"""
あなたはSEO検定{grade}の問題作成の専門家です。
提供された参考資料に基づき、検定試験レベルの4択問題を1問生成してください。

【厳守事項】
1. 問題文・選択肢は参考資料の内容のみを使用すること
2. 参考資料に記載されていない内容を推測・創作しないこと
3. 正解の根拠は必ず資料内に存在すること
4. 選択肢は4つとも明確に区別できること
5. 公式問題サンプルが含まれる場合、その形式・難易度を参考にすること

【正解位置のランダム化】**重要**
- correct_answerは0〜3のいずれかをランダムに選択すること
- 正解が常に選択肢A（0番目）に偏らないよう、均等に分散させること
- 選択肢の順序を工夫し、「正しい情報→間違った情報」という自然な順序にならないようにすること
- 例：correct_answer=2 の場合、選択肢Cが正解となるよう選択肢を配置する

【出力形式】（必ずJSON形式で出力）
{{{{
  "question": "問題文（100-200文字）",
  "choices": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
  "correct_answer": 0,  # ← 0〜3のいずれかをランダムに選択
  "explanations": {{{{
    "choice_0": "選択肢Aの解説（なぜ正解/不正解か）",
    "choice_1": "選択肢Bの解説（なぜ正解/不正解か）",
    "choice_2": "選択肢Cの解説（なぜ正解/不正解か）",
    "choice_3": "選択肢Dの解説（なぜ正解/不正解か）"
  }}}},
  "category": "出題カテゴリ（例: コンテンツSEO）",
  "difficulty": "難易度（基本/応用/発展）"
}}}}

【参考資料】
{context}
"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "上記の参考資料に基づいて、{grade}レベルの4択問題を1問作成してください。")
    ])
    
    messages = prompt.invoke({"grade": grade})
    response = llm.invoke(messages)
    
    return response.content


def _parse_question_json(json_str: str) -> Optional[QuestionData]:
    """JSON文字列を解析してQuestionDataに変換"""
    try:
        # JSONブロック抽出（```json ... ``` 形式に対応）
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        
        data = json.loads(json_str.strip())
        question = QuestionData.from_dict(data)
        
        # バリデーション
        is_valid, error_msg = question.validate()
        if not is_valid:
            logger.error(f"[練習問題] バリデーションエラー: {error_msg}")
            return None
        
        return question
        
    except json.JSONDecodeError as e:
        logger.error(f"[練習問題] JSON解析エラー: {e}")
        return None
    except KeyError as e:
        logger.error(f"[練習問題] 必須キー不足: {e}")
        return None
    except Exception as e:
        logger.error(f"[練習問題] 予期しないエラー: {e}")
        return None


############################################################
# 4. セッション状態管理
############################################################

def initialize_session_state():
    """練習問題モード用のセッション状態を初期化"""
    if "practice_question_count" not in st.session_state:
        st.session_state.practice_question_count = 0
    if "practice_current_question" not in st.session_state:
        st.session_state.practice_current_question = None
    if "practice_user_answer" not in st.session_state:
        st.session_state.practice_user_answer = None
    if "practice_show_explanation" not in st.session_state:
        st.session_state.practice_show_explanation = False
    
    # Phase 3-2: 問題履歴管理
    if "practice_question_history" not in st.session_state:
        st.session_state.practice_question_history = []  # 問題文のハッシュリスト


def reset_current_question():
    """現在の問題をリセット"""
    st.session_state.practice_current_question = None
    st.session_state.practice_user_answer = None
    st.session_state.practice_show_explanation = False


def calculate_question_hash(question_text: str) -> str:
    """
    問題文のハッシュを計算（Phase 3-2）
    
    Args:
        question_text: 問題文
        
    Returns:
        MD5ハッシュ文字列
    """
    return hashlib.md5(question_text.encode('utf-8')).hexdigest()


def is_duplicate_question(question_text: str) -> bool:
    """
    重複問題かどうかをチェック（Phase 3-2）
    
    Args:
        question_text: 問題文
        
    Returns:
        True: 重複, False: 新規
    """
    if not ct.PRACTICE_QUESTIONS_CONFIG["ENABLE_DUPLICATE_CHECK"]:
        return False
    
    question_hash = calculate_question_hash(question_text)
    is_dup = question_hash in st.session_state.practice_question_history
    
    if is_dup:
        logger.warning(f"[練習問題] 重複問題検出: hash={question_hash[:8]}...")
    
    return is_dup


def add_to_history(question_text: str):
    """
    問題を履歴に追加（Phase 3-2）
    
    Args:
        question_text: 問題文
    """
    if ct.PRACTICE_QUESTIONS_CONFIG["ENABLE_DUPLICATE_CHECK"]:
        question_hash = calculate_question_hash(question_text)
        st.session_state.practice_question_history.append(question_hash)
        logger.info(f"[練習問題] 履歴追加: hash={question_hash[:8]}... (総計{len(st.session_state.practice_question_history)}問)")


############################################################
# 5. UI表示関数
############################################################

def display_question(question: QuestionData):
    """問題を表示"""
    st.markdown(f"### 問題 {st.session_state.practice_question_count}")
    st.markdown(f"**{question.question}**")
    st.markdown("")
    
    # 選択肢のクリーニング関数（先頭の記号を削除）
    def clean_choice(text: str) -> str:
        """選択肢から先頭の A. や ① などを削除"""
        import re
        # パターン: "A.", "A .", "A)", "①.", "①)", "1.", "1)" などを削除
        cleaned = re.sub(r'^[A-D①-④1-4][\.\)]\s*', '', text.strip())
        return cleaned
    
    # 選択肢（ラジオボタン）
    choice_labels = [
        f"A. {clean_choice(question.choices[0])}",
        f"B. {clean_choice(question.choices[1])}",
        f"C. {clean_choice(question.choices[2])}",
        f"D. {clean_choice(question.choices[3])}"
    ]
    
    selected = st.radio(
        "選択してください",
        range(4),
        format_func=lambda x: choice_labels[x],
        key="practice_user_answer_radio",
        label_visibility="collapsed"
    )
    
    st.session_state.practice_user_answer = selected


def display_explanation(question: QuestionData, user_answer: int):
    """解説を表示"""
    st.markdown("---")
    st.markdown("### 解答と解説")
    
    # 正解判定
    is_correct = (user_answer == question.correct_index)
    
    if is_correct:
        st.success("✅ 正解です！", icon="✅")
    else:
        st.error("❌ 不正解です", icon="❌")
    
    st.markdown(f"**正解: {chr(65 + question.correct_index)}**")
    st.markdown("")
    
    # 選択肢のクリーニング関数（display_questionと同じ）
    def clean_choice(text: str) -> str:
        """選択肢から先頭の A. や ① などを削除"""
        import re
        cleaned = re.sub(r'^[A-D①-④1-4][\.\)]\s*', '', text.strip())
        return cleaned
    
    # 各選択肢の解説
    st.markdown("#### 各選択肢の解説")
    
    for i in range(4):
        choice_letter = chr(65 + i)
        is_answer = (i == question.correct_index)
        was_selected = (i == user_answer)
        
        # アイコン設定
        if is_answer:
            icon = "✅"
        elif was_selected:
            icon = "❌"
        else:
            icon = "ℹ️"
        
        cleaned_choice = clean_choice(question.choices[i])
        with st.expander(f"{icon} 選択肢{choice_letter}: {cleaned_choice}", expanded=False):
            st.markdown(question.explanations.get(f"choice_{i}", "解説なし"))
    
    # カテゴリ・難易度表示
    if question.category or question.difficulty:
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if question.category:
                st.markdown(f"📚 **カテゴリ**: {question.category}")
        with col2:
            if question.difficulty:
                st.markdown(f"📊 **難易度**: {question.difficulty}")
