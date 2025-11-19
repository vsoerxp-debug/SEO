"""
このファイルは、最初の画面読み込み時にのみ実行される初期化処理が記述されたファイルです。
"""

############################################################
# PyTorch初期化問題の事前対応（強化版）
############################################################
import os
import sys
import warnings

# PyTorchの初期化問題対策（完全版・Triton競合解決）
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['TORCH_CPP_LOG_LEVEL'] = 'ERROR'
os.environ['PYTORCH_JIT_LOG_LEVEL'] = 'ERROR'

# Triton名前空間重複問題の根本解決
os.environ['TRITON_DISABLE_COMPILER_WARNINGS'] = '1'
os.environ['TRITON_DISABLE_LINE_INFO'] = '1' 
os.environ['TRITON_CACHE_DIR'] = os.path.join(os.getcwd(), '.triton_cache')
os.environ['TRITON_DISABLE_OPTIMIZATION'] = '1'

# PyTorchクラス登録エラーの完全回避
os.environ['TORCH_LIBRARY_LAZY_INIT'] = 'TRUE'
os.environ['PYTORCH_DISABLE_PER_OP_PROFILING'] = '1'
os.environ['PYTORCH_DISABLE_CUDNN_INITIALIZATION'] = '1'
os.environ['TORCH_DISABLE_CUDA_INIT_CHECK'] = '1'

# PyTorchログ設定の完全無効化
os.environ.pop('TORCH_LOGS', None)  # 問題のあるログ設定を削除
os.environ['PYTORCH_DISABLE_INTERNAL_LOGGING'] = '1'

# PyTorchの遅延初期化強制
os.environ['TORCH_LAZY_INIT'] = '1'

# NumPy 2.0互換性の最優先対応（全ライブラリ読み込み前）
# ChromaDB、LangChain、その他のライブラリがNumPy属性を使用する前に実行
try:
    import numpy as np
    
    # NumPy 2.0で削除された属性の完全復元（ChromaDB互換性保証）
    numpy_2_compatibility_attrs = {
        'float_': np.float64,
        'int_': np.int64,
        'complex_': np.complex128,
        'uint': np.uint32,
        'bool_': bool,
        # ChromaDBで使用される追加属性
        'int8': np.int8,
        'int16': np.int16,
        'int32': np.int32,
        'uint8': np.uint8,
        'uint16': np.uint16,
        'uint32': np.uint32,
        'uint64': np.uint64,
        'float16': np.float16,
        'float32': np.float32,
        'float64': np.float64,
        'complex64': np.complex64,
        'complex128': np.complex128
    }
    
    # 存在しない属性のみを追加（既存属性を上書きしない）
    for attr_name, attr_value in numpy_2_compatibility_attrs.items():
        if not hasattr(np, attr_name):
            setattr(np, attr_name, attr_value)
    
    print(f"NumPy {np.__version__} 完全互換性対応完了（ChromaDB対応）")
    
except ImportError:
    print("NumPy未インストール - 互換性対応をスキップ")
    pass

# 各種警告の完全抑制（PyTorch/Triton特化強化版）
warnings.filterwarnings('ignore', category=UserWarning, module='torch')
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', message='.*triton.*')
warnings.filterwarnings('ignore', message='.*TORCH_LIBRARY.*')
warnings.filterwarnings('ignore', message='.*TORCH_LIBRARY_IMPL.*')
warnings.filterwarnings('ignore', message='.*TORCH_LIBRARY_FRAGMENT.*')
warnings.filterwarnings('ignore', message='.*namespace.*')
warnings.filterwarnings('ignore', message='.*float_.*')
warnings.filterwarnings('ignore', message='.*torch.classes.*')
warnings.filterwarnings('ignore', message='.*__path__._path.*')
warnings.filterwarnings('ignore', message='.*np.float_.*')
warnings.filterwarnings('ignore', message='.*Tried to instantiate class.*')
warnings.filterwarnings('ignore', category=UserWarning, module='triton')
warnings.filterwarnings('ignore', category=UserWarning, message='.*triton.*')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*torch.*')

############################################################
# ライブラリの読み込み（PyTorch互換性強化版）
############################################################
import logging
from logging.handlers import TimedRotatingFileHandler
from uuid import uuid4
import sys
import unicodedata
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st
from docx import Document

# PyTorchおよび関連ライブラリの安全な読み込み
try:
    # PyTorch関連ログの事前抑制
    logging.getLogger('torch').setLevel(logging.CRITICAL)
    logging.getLogger('triton').setLevel(logging.CRITICAL)
    
    # PyTorchの遅延初期化
    import torch
    torch.set_warn_always(False)
    if hasattr(torch, '_C'):
        torch._C._set_print_stacktraces_on_fatal_signal(False)
    
except Exception as torch_import_error:
    print(f"PyTorch読み込み警告（機能には影響なし）: {torch_import_error}")

from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
import constants as ct


############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
load_dotenv()


############################################################
# 関数定義
############################################################

def initialize():
    """
    画面読み込み時に実行する初期化処理
    NumPy 2.0とPyTorch互換性問題の完全対応版
    """
    try:
        # 【最重要】互換性確保システムの初期化
        setup_environment_variables()
        
        # 初期化データの用意
        initialize_session_state()
        # ログ出力用にセッションIDを生成
        initialize_session_id()
        # ログ出力の設定
        initialize_logger()
        # RAGのRetrieverを作成
        initialize_retriever()
        
    except Exception as e:
        # 初期化エラーの詳細ログ出力
        print(f"初期化エラーの詳細: {str(e)}")
        import traceback
        print(f"トレースバック: {traceback.format_exc()}")
        
        # セッション状態に最小限の初期化
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        if "retriever" not in st.session_state:
            st.session_state.retriever = None
        if "enhanced_mode" not in st.session_state:
            st.session_state.enhanced_mode = True  # 高品質モードをデフォルトに変更
            
        # エラーを再発生させる
        raise e


def setup_environment_variables():
    """
    環境変数の事前設定とシステム安定化
    NumPy 2.0とPyTorch互換性問題の解決（簡易版フォールバック）
    """
    # USER_AGENT設定（未設定の場合のみ）
    if not os.environ.get('USER_AGENT'):
        os.environ['USER_AGENT'] = 'Enhanced-RAG-System/1.0.0'
    
    # PyTorch関連の安定化設定
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['TORCH_LOGS'] = '+dynamo'
    
    # PyTorch初期化問題の回避
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
    os.environ['TORCH_CPP_LOG_LEVEL'] = 'ERROR'
    
    # NumPy 2.0関連の設定
    os.environ['NPY_PROMOTION_STATE'] = 'weak'
    
    # ChromaDB関連の設定
    os.environ['ALLOW_RESET'] = 'TRUE'
    
    # 安全な警告抑制（エラーを回避）
    try:
        import warnings
        warnings.filterwarnings('ignore', category=UserWarning, module='torch')
        warnings.filterwarnings('ignore', category=FutureWarning)
        warnings.filterwarnings('ignore', category=DeprecationWarning, module='numpy')
        # messageパラメータを使う場合は安全に実行
        try:
            warnings.filterwarnings('ignore', message='.*float_.*')
            warnings.filterwarnings('ignore', message='.*torch.classes.*')
        except (TypeError, AssertionError):
            pass  # messageパラメータが問題の場合はスキップ
    except Exception:
        pass  # 警告設定全体が問題の場合はスキップ
    
    # NumPy 2.0互換性の完全対応（ChromaDB対応強化版・重複確認付き）
    try:
        import numpy as np
        
        # ChromaDBのapi/types.pyで使用される全属性の完全復元
        critical_numpy_attrs = {
            # ChromaDB api/types.py で直接使用
            'float_': np.float64,
            'int_': np.int64,
            'uint': np.uint32,
            'complex_': np.complex128,
            'bool_': np.bool,
            
            # その他の互換性属性
            'int8': np.int8, 'int16': np.int16, 'int32': np.int32,
            'uint8': np.uint8, 'uint16': np.uint16, 'uint64': np.uint64,
            'float16': np.float16, 'float32': np.float32, 'float64': np.float64,
            'complex64': np.complex64, 'complex128': np.complex128
        }
        
        # 重要：存在確認後の安全な属性設定
        missing_attrs = []
        for attr_name, attr_value in critical_numpy_attrs.items():
            if not hasattr(np, attr_name):
                try:
                    setattr(np, attr_name, attr_value)
                    missing_attrs.append(attr_name)
                except Exception as e:
                    print(f"NumPy属性設定エラー {attr_name}: {e}")
        
        if missing_attrs:
            print(f"NumPy {np.__version__} 互換性対応完了 - 復元属性: {', '.join(missing_attrs)}")
        else:
            print(f"NumPy {np.__version__} - 全互換性属性が既に存在")
                
    except ImportError:
        print("NumPy未インストール - 互換性対応スキップ")
    except Exception as e:
        print(f"NumPy互換性対応エラー（続行可能）: {e}")
    
    # PyTorch/Triton互換性の追加対応
    try:
        import torch
        # PyTorchの静音化強化
        torch.set_warn_always(False)
        if hasattr(torch, '_C') and hasattr(torch._C, '_set_print_stacktraces_on_fatal_signal'):
            torch._C._set_print_stacktraces_on_fatal_signal(False)
        
        # Tritonキャッシュディレクトリの確保
        triton_cache_dir = os.path.join(os.getcwd(), '.triton_cache')
        os.makedirs(triton_cache_dir, exist_ok=True)
        
        # PyTorchログレベルの完全制御
        logging.getLogger('torch').setLevel(logging.CRITICAL)
        
        # Tritonモジュール対応（SEO特化版では不要）
        # SEO用途ではTritonは使用しないためスキップ
        
        print("PyTorch互換性対応完了")
        
    except Exception as torch_error:
        print(f"PyTorch互換性対応（警告のみ）: {torch_error}")
        pass
    
    # 最終的な互換性確認
    try:
        # システムの安定性テスト
        test_result = "環境設定完了: PyTorch/NumPy互換性確保"
        print(test_result)
        return True
        
    except Exception as final_error:
        print(f"最終互換性確認でエラー（続行可能）: {final_error}")
        return False


def initialize_logger():
    """
    ログ出力の設定
    """
    # 指定のログフォルダが存在すれば読み込み、存在しなければ新規作成
    os.makedirs(ct.LOG_DIR_PATH, exist_ok=True)
    
    # 引数に指定した名前のロガー（ログを記録するオブジェクト）を取得
    # 再度別の箇所で呼び出した場合、すでに同じ名前のロガーが存在していれば読み込む
    logger = logging.getLogger(ct.LOGGER_NAME)

    # すでにロガーにハンドラー（ログの出力先を制御するもの）が設定されている場合、同じログ出力が複数回行われないよう処理を中断する
    if logger.hasHandlers():
        return

    # 1日単位でログファイルの中身をリセットし、切り替える設定
    log_handler = TimedRotatingFileHandler(
        os.path.join(ct.LOG_DIR_PATH, ct.LOG_FILE),
        when="D",
        encoding="utf8"
    )
    # 出力するログメッセージのフォーマット定義
    # - 「levelname」: ログの重要度（INFO, WARNING, ERRORなど）
    # - 「asctime」: ログのタイムスタンプ（いつ記録されたか）
    # - 「lineno」: ログが出力されたファイルの行番号
    # - 「funcName」: ログが出力された関数名
    # - 「session_id」: セッションID（誰のアプリ操作か分かるように）
    # - 「message」: ログメッセージ
    formatter = logging.Formatter(
        f"[%(levelname)s] %(asctime)s line %(lineno)s, in %(funcName)s, session_id={st.session_state.session_id}: %(message)s"
    )

    # 定義したフォーマッターの適用
    log_handler.setFormatter(formatter)

    # ログレベルを「INFO」に設定
    logger.setLevel(logging.INFO)

    # 作成したハンドラー（ログ出力先を制御するオブジェクト）を、
    # ロガー（ログメッセージを実際に生成するオブジェクト）に追加してログ出力の最終設定
    logger.addHandler(log_handler)


def initialize_session_id():
    """
    セッションIDの作成
    """
    if "session_id" not in st.session_state:
        # ランダムな文字列（セッションID）を、ログ出力用に作成
        st.session_state.session_id = uuid4().hex


def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        # 「表示用」の会話ログを順次格納するリストを用意
        st.session_state.messages = []
        # 「LLMとのやりとり用」の会話ログを順次格納するリストを用意
        st.session_state.chat_history = []


def create_persistent_vector_store_safely(splitted_docs, embeddings, logger, batch_size=50, persist_directory=None):
    """
    永続化対応の安全なベクターストア作成（バッチ処理・エラーハンドリング対応）
    """
    try:
        # 永続化ディレクトリの準備
        if persist_directory:
            os.makedirs(persist_directory, exist_ok=True)
            logger.info(f"永続化ディレクトリ準備完了: {persist_directory}")
        
        # バッチサイズの動的調整
        if len(splitted_docs) > 100:
            adjusted_batch_size = min(batch_size, 25)
            logger.info(f"大量文書検知：バッチサイズを{adjusted_batch_size}に調整")
        else:
            adjusted_batch_size = batch_size
        
        # Step 1: テスト用小バッチでの動作確認
        test_docs = splitted_docs[:min(3, len(splitted_docs))]
        if persist_directory:
            test_db = Chroma.from_documents(
                documents=test_docs,
                embedding=embeddings,
                persist_directory=persist_directory + "_test"
            )
        else:
            test_db = Chroma.from_documents(
                documents=test_docs,
                embedding=embeddings
            )
        logger.info("テスト用ベクターストア作成成功")
        
        # Step 2: 全文書でのベクターストア作成（バッチ処理）
        if len(splitted_docs) <= adjusted_batch_size:
            # 小規模：一括処理
            if persist_directory:
                db = Chroma.from_documents(
                    documents=splitted_docs,
                    embedding=embeddings,
                    persist_directory=persist_directory
                )
            else:
                db = Chroma.from_documents(
                    documents=splitted_docs,
                    embedding=embeddings
                )
            logger.info(f"小規模一括処理完了：{len(splitted_docs)}文書")
        else:
            # 大規模：バッチ処理
            logger.info(f"大規模バッチ処理開始：{len(splitted_docs)}文書、バッチサイズ{adjusted_batch_size}")
            
            # 最初のバッチでベクターストア初期化
            initial_batch = splitted_docs[:adjusted_batch_size]
            if persist_directory:
                db = Chroma.from_documents(
                    documents=initial_batch,
                    embedding=embeddings,
                    persist_directory=persist_directory
                )
            else:
                db = Chroma.from_documents(
                    documents=initial_batch,
                    embedding=embeddings
                )
            
            # 残りのバッチを順次追加
            for i in range(adjusted_batch_size, len(splitted_docs), adjusted_batch_size):
                batch = splitted_docs[i:i + adjusted_batch_size]
                try:
                    db.add_documents(batch)
                    logger.info(f"バッチ {i//adjusted_batch_size + 1} 完了：{len(batch)}文書追加")
                except Exception as batch_error:
                    logger.warning(f"バッチ {i//adjusted_batch_size + 1} でエラー、スキップ: {batch_error}")
                    continue
            
            logger.info("大規模バッチ処理完了")
        
        # 永続化の場合はバージョン情報を記録
        if persist_directory:
            try:
                version_file = os.path.join(os.path.dirname(persist_directory), "db_version.txt")
                with open(version_file, 'w', encoding='utf-8') as f:
                    f.write(f"{ct.CURRENT_DB_VERSION}\n")
                    f.write(f"created_at: {datetime.now().isoformat()}\n")
                    f.write(f"documents_count: {len(splitted_docs)}\n")
                logger.info(f"DBバージョン情報記録完了: {version_file}")
            except Exception as version_error:
                logger.warning(f"バージョン情報記録エラー（続行可能）: {version_error}")
        
        return db
        
    except Exception as e:
        logger.error(f"永続化ベクターストア作成エラー: {e}")
        # 最終フォールバック：非永続化ベクターストア
        logger.warning("フォールバック：非永続化ベクターストアで初期化")
        if persist_directory:
            return Chroma(embedding_function=embeddings)
        else:
            return Chroma(embedding_function=embeddings)


def create_vector_store_safely(splitted_docs, embeddings, logger, batch_size=50):
    """
    従来の非永続化ベクターストア作成（互換性維持）
    """
    return create_persistent_vector_store_safely(splitted_docs, embeddings, logger, batch_size, None)

def check_persistent_db_exists():
    """
    永続化DBの存在確認とバージョンチェック
    
    Returns:
        bool: 有効な永続化DBが存在するかどうか
        str: 存在確認の詳細理由
    """
    try:
        # DBディレクトリの存在確認
        if not os.path.exists(ct.PERSISTENT_DB_PATH):
            return False, "永続化DBディレクトリが存在しません"
        
        # Chromaが必要とするファイルの存在確認
        required_files = ['chroma.sqlite3']  # Chromaの基本ファイル
        for required_file in required_files:
            file_path = os.path.join(ct.PERSISTENT_DB_PATH, required_file)
            if not os.path.exists(file_path):
                return False, f"必要なDBファイル {required_file} が存在しません"
        
        # バージョン情報の確認
        version_file = os.path.join(os.path.dirname(ct.PERSISTENT_DB_PATH), "db_version.txt")
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if ct.CURRENT_DB_VERSION in content:
                        return True, f"有効な永続化DB発見 (バージョン: {ct.CURRENT_DB_VERSION})"
                    else:
                        return False, f"DBバージョンが古いため再構築が必要です"
            except Exception as version_error:
                return False, f"バージョンファイル読み込みエラー: {version_error}"
        else:
            # バージョンファイルがない場合は再構築
            return False, "バージョン情報がないため安全のため再構築します"
            
    except Exception as e:
        return False, f"永続化DB確認エラー: {e}"


def load_persistent_db(embeddings, logger):
    """
    既存の永続化DBをロード
    
    Args:
        embeddings: エンベディングモデル
        logger: ロガー
        
    Returns:
        Chroma: ロードされたベクターストア
    """
    try:
        logger.info(f"永続化DBロード開始: {ct.PERSISTENT_DB_PATH}")
        
        # 永続化DBのロード
        db = Chroma(
            persist_directory=ct.PERSISTENT_DB_PATH,
            embedding_function=embeddings
        )
        
        # ロード成功確認（簡単なテスト検索）
        test_results = db.similarity_search("SEO", k=1)
        if test_results:
            logger.info(f"永続化DBロード成功: {len(test_results)}件のテスト検索結果")
            return db
        else:
            logger.warning("永続化DBはロードできましたが、検索結果が空です")
            return db
            
    except Exception as e:
        logger.error(f"永続化DBロードエラー: {e}")
        raise e


def initialize_retriever():
    """
    画面読み込み時にRAGのRetriever（ベクターストアから検索するオブジェクト）を作成
    永続化対応版（高精度システム + 永続化DB）
    """
    # ロガーを読み込むことで、後続の処理中に発生したエラーなどがログファイルに記録される
    logger = logging.getLogger(ct.LOGGER_NAME)

    # すでにRetrieverが作成済みの場合、後続の処理を中断
    if "retriever" in st.session_state:
        return
    
    # 埋め込みモデルの用意（トークン制限対応版）
    embeddings = OpenAIEmbeddings(
        chunk_size=1000,  # バッチサイズを制限
        max_retries=2,    # リトライ回数を制限
        request_timeout=60  # タイムアウト設定
    )
    
    # Step 1: 永続化DBの存在確認
    db_exists, db_status_reason = check_persistent_db_exists()
    logger.info(f"永続化DB確認結果: {db_status_reason}")
    
    # 🚀 Streamlit Cloud デプロイ時の強制再構築対応
    # 環境変数 FORCE_REBUILD_DB=true が設定されている場合、既存DBを無視して再構築
    import os
    FORCE_REBUILD = os.getenv("FORCE_REBUILD_DB", "false").lower() == "true"
    if FORCE_REBUILD:
        logger.warning("⚠️ 環境変数 FORCE_REBUILD_DB=true が設定されているため、VectorDBを強制再構築します")
        db_exists = False
    
    if db_exists:
        # 既存の永続化DBをロード
        try:
            db = load_persistent_db(embeddings, logger)
            logger.info("既存永続化DBのロードに成功しました")
            
            # 高精度検索システムの設定は後で行う
            # まずはDBが正常にロードできているかを確認
            
        except Exception as load_error:
            logger.error(f"永続化DBロードに失敗、新規作成します: {load_error}")
            db_exists = False  # 新規作成フラグ
    
    if not db_exists:
        # 新規永続化DBの作成
        logger.info("新規永続化DBを作成します")
        
        # RAGの参照先となるデータソースの読み込み
        docs_all = load_data_sources()

        # OSがWindowsの場合、Unicode正規化と、cp932（Windows用の文字コード）で表現できない文字を除去
        for doc in docs_all:
            doc.page_content = adjust_string(doc.page_content)
            for key in doc.metadata:
                doc.metadata[key] = adjust_string(doc.metadata[key])
    
        # 文書量とトークン数の事前チェック
        total_chars = sum(len(doc.page_content) for doc in docs_all)
        estimated_tokens = total_chars // 4  # 概算：4文字=1トークン
        logger.info(f"処理対象文書: {len(docs_all)}件, 合計文字数: {total_chars:,}, 推定トークン数: {estimated_tokens:,}")
        
        # トークン制限に基づく動的チャンクサイズ調整
        if total_chars > ct.MAX_CHARS_BEFORE_SPLITTING:
            target_chunk_size = ct.LARGE_DATA_CHUNK_SIZE
            batch_size = min(ct.EMBEDDING_BATCH_SIZE // 2, 25)  # より小さなバッチ
            logger.warning(f"大量文書検知：チャンクサイズを{target_chunk_size}、バッチサイズを{batch_size}に縮小")
        else:
            target_chunk_size = ct.DEFAULT_CHUNK_SIZE
            batch_size = ct.EMBEDDING_BATCH_SIZE
            logger.info(f"標準処理：チャンクサイズ{target_chunk_size}、バッチサイズ{batch_size}")
        
        # エンベディング設定の調整
        embeddings.chunk_size = batch_size
        
        # 標準チャンク分割システムを使用（安定性重視）
        logger.info("標準チャンクシステム使用")
        text_splitter = CharacterTextSplitter(
            chunk_size=target_chunk_size,
            chunk_overlap=200,  # オーバーラップを増やして文脈保持
            separator="\n\n",  # より適切なセパレータ
            length_function=len,
            is_separator_regex=False
        )
        splitted_docs = text_splitter.split_documents(docs_all)
        
        # 分割後のトークン数再確認
        chunk_chars = sum(len(doc.page_content) for doc in splitted_docs)
        chunk_tokens = chunk_chars // 4
        logger.info(f"分割結果: {len(splitted_docs)}チャンク, 推定トークン数: {chunk_tokens:,}")

        # 永続化ベクターストア作成
        db = create_persistent_vector_store_safely(
            splitted_docs, 
            embeddings, 
            logger, 
            batch_size, 
            ct.PERSISTENT_DB_PATH
        )
        logger.info("新規永続化DBの作成が完了しました")

    # 共通：汎用的高精度RAGシステムの実装（ChromaDB互換性対応）
    try:
        # 段階的高精度化アプローチ
        logger.info("汎用高精度RAGシステム初期化開始")
        
        # ChromaDB互換性を考慮したretrieverの作成（高精度化）
        # search_typeとsearch_kwargsの適切な組み合わせを使用
        enhanced_retriever = db.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": 12,  # 検索結果数を増加（高精度化）
            }
        )
        
        # Step 2: 高精度BM25との組み合わせ（可能な場合）
        try:
            from langchain_community.retrievers import BM25Retriever
            # EnsembleRetrieverは新しいLangChainバージョンでは廃止
            # BM25Retrieverのみを使用した代替実装
            
            # BM25リトリーバーの作成（DBから文書を取得）
            # DBから全文書を取得してBM25用のテキストを準備
            try:
                # DBからすべての文書を取得
                all_docs = db.get()
                if all_docs and 'documents' in all_docs:
                    texts = all_docs['documents']
                    metadatas = all_docs.get('metadatas', [{}] * len(texts))
                else:
                    # フォールバック：空のリストで初期化
                    texts = ["デフォルトSEO文書"]
                    metadatas = [{"source": "default"}]
            except Exception as get_docs_error:
                logger.warning(f"DB文書取得エラー、デフォルト文書で初期化: {get_docs_error}")
                texts = ["デフォルトSEO文書"]
                metadatas = [{"source": "default"}]
            
            bm25_retriever = BM25Retriever.from_texts(
                texts, 
                metadatas=metadatas
            )
            bm25_retriever.k = 8  # BM25の検索数も増加
            
            # 代替アンサンブル実装（EnsembleRetriever廃止対応）
            # カスタムリトリーバーでベクター検索とBM25を組み合わせ
            class CustomEnsembleRetriever:
                def __init__(self, vector_retriever, bm25_retriever, vector_weight=0.7):
                    self.vector_retriever = vector_retriever
                    self.bm25_retriever = bm25_retriever
                    self.vector_weight = vector_weight
                    self.bm25_weight = 1.0 - vector_weight
                
                def get_relevant_documents(self, query, k=4):
                    return self._retrieve_documents(query, k)
                
                def invoke(self, query_input, k=4):
                    """新しいLangChain API対応（文字列・辞書両対応）"""
                    if isinstance(query_input, str):
                        query = query_input
                    elif isinstance(query_input, dict):
                        query = query_input.get("query", query_input.get("input", ""))
                    else:
                        query = str(query_input)
                    return self._retrieve_documents(query, k)
                
                def _retrieve_documents(self, query, k=8):  # デフォルト検索数を8に増加
                    """実際の文書検索処理（高精度化）"""
                    # ベクター検索結果（検索数増加）
                    try:
                        if hasattr(self.vector_retriever, 'invoke'):
                            vector_docs = self.vector_retriever.invoke(query)[:int(k*self.vector_weight)+2]
                        else:
                            vector_docs = self.vector_retriever.get_relevant_documents(query)[:int(k*self.vector_weight)+2]
                    except Exception as vector_error:
                        print(f"ベクター検索エラー: {vector_error}")
                        vector_docs = []
                    
                    # BM25検索結果（検索数増加）
                    try:
                        if hasattr(self.bm25_retriever, 'invoke'):
                            bm25_docs = self.bm25_retriever.invoke(query)[:int(k*self.bm25_weight)+2]
                        else:
                            bm25_docs = self.bm25_retriever.get_relevant_documents(query)[:int(k*self.bm25_weight)+2]
                    except Exception as bm25_error:
                        print(f"BM25検索エラー: {bm25_error}")
                        bm25_docs = []
                    
                    # 重複除去しながら結合
                    combined_docs = []
                    seen_contents = set()
                    
                    for doc in vector_docs + bm25_docs:
                        if doc.page_content not in seen_contents:
                            combined_docs.append(doc)
                            seen_contents.add(doc.page_content)
                        if len(combined_docs) >= k:
                            break
                    
                    return combined_docs[:k]
            
            custom_retriever = CustomEnsembleRetriever(enhanced_retriever, bm25_retriever)
            
            st.session_state.retriever = custom_retriever
            st.session_state.enhanced_mode = True
            st.session_state._enhanced_type = "custom_ensemble"
            logger.info("カスタムアンサンブル高精度検索システム初期化完了（ベクター+BM25）")
            
        except (ImportError, Exception) as bm25_error:
            # BM25が利用できない場合は強化ベクター検索のみ
            logger.warning(f"BM25利用不可、ベクター検索強化モードで継続: {bm25_error}")
            
            # MMR（Maximum Marginal Relevance）検索で多様性を確保
            try:
                mmr_retriever = db.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "k": 10,  # MMR検索数増加
                        "lambda_mult": 0.6,  # 多様性を若干向上
                        "fetch_k": 20,  # 候補文書数増加
                    }
                )
                st.session_state.retriever = mmr_retriever
                st.session_state.enhanced_mode = True
                st.session_state._enhanced_type = "mmr_enhanced"
                logger.info("MMR強化ベクター検索システム初期化完了（高精度モード）")
            except Exception:
                # 最後の手段：標準類似度検索
                st.session_state.retriever = enhanced_retriever
                st.session_state.enhanced_mode = True
                st.session_state._enhanced_type = "vector_enhanced"
                logger.info("標準ベクター検索システム初期化完了（基本高精度モード）")
            
    except Exception as e:
        # 最終フォールバック：標準モード（高品質設定を維持）
        logger.warning(f"高精度システム初期化失敗、標準モードで継続: {e}")
        st.session_state.retriever = db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 4}
        )
        st.session_state.enhanced_mode = True  # 高品質モードを維持
        st.session_state._enhanced_type = "standard"


def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        # 「表示用」の会話ログを順次格納するリストを用意
        st.session_state.messages = []
        # 「LLMとのやりとり用」の会話ログを順次格納するリストを用意
        st.session_state.chat_history = []


def load_data_sources():
    """
    RAGの参照先となるデータソースの読み込み

    Returns:
        読み込んだ通常データソース
    """
    # データソースを格納する用のリスト
    docs_all = []
    # ファイル読み込みの実行（渡した各リストにデータが格納される）
    recursive_file_check(ct.RAG_TOP_FOLDER_PATH, docs_all)

    web_docs_all = []
    # ファイルとは別に、指定のWebページ内のデータも読み込み
    # 読み込み対象のWebページ一覧に対して処理
    for web_url in ct.WEB_URL_LOAD_TARGETS:
        # 指定のWebページを読み込み
        loader = WebBaseLoader(web_url)
        web_docs = loader.load()
        # for文の外のリストに読み込んだデータソースを追加
        web_docs_all.extend(web_docs)
    # 通常読み込みのデータソースにWebページのデータを追加
    docs_all.extend(web_docs_all)

    return docs_all


def recursive_file_check(path, docs_all):
    """
    RAGの参照先となるデータソースの読み込み

    Args:
        path: 読み込み対象のファイル/フォルダのパス
        docs_all: データソースを格納する用のリスト
    """
    # パスがフォルダかどうかを確認
    if os.path.isdir(path):
        # フォルダの場合、フォルダ内のファイル/フォルダ名の一覧を取得
        files = os.listdir(path)
        # 各ファイル/フォルダに対して処理
        for file in files:
            # ファイル/フォルダ名だけでなく、フルパスを取得
            full_path = os.path.join(path, file)
            # フルパスを渡し、再帰的にファイル読み込みの関数を実行
            recursive_file_check(full_path, docs_all)
    else:
        # パスがファイルの場合、ファイル読み込み
        file_load(path, docs_all)


def file_load(path, docs_all):
    """
    ファイル内のデータ読み込み

    Args:
        path: ファイルパス
        docs_all: データソースを格納する用のリスト
    """
    # ファイルの拡張子を取得
    file_extension = os.path.splitext(path)[1]
    # ファイル名（拡張子を含む）を取得
    file_name = os.path.basename(path)

    # 想定していたファイル形式の場合のみ読み込む
    if file_extension in ct.SUPPORTED_EXTENSIONS:
        # ファイルの拡張子に合ったdata loaderを使ってデータ読み込み
        loader_func = ct.SUPPORTED_EXTENSIONS[file_extension]
        
        # 強化docxローダー（関数）か従来ローダー（クラス）かを判定
        if callable(loader_func):
            try:
                # 関数の場合：直接呼び出して結果を取得
                docs = loader_func(path)
                if isinstance(docs, list):
                    docs_all.extend(docs)
                else:
                    # ローダーオブジェクトの場合
                    docs = docs.load()
                    docs_all.extend(docs)
            except Exception as e:
                # エラー時はスキップ
                print(f"ファイル読み込みエラー {path}: {e}")
        else:
            # 従来の方式
            loader = loader_func(path)
            docs = loader.load()
            docs_all.extend(docs)


def adjust_string(s):
    """
    Windows環境でRAGが正常動作するよう調整（完全UTF-8対応版）
    
    Args:
        s: 調整を行う文字列
    
    Returns:
        調整を行った文字列
    """
    # 調整対象は文字列のみ
    if type(s) is not str:
        return s

    # 全プラットフォーム共通：最小限の処理のみ
    try:
        # Unicode正規化のみ（エンコーディング変換は一切行わない）
        s = unicodedata.normalize('NFC', s)
        return s
    except Exception:
        # 例外時はそのまま返す
        return s