import os
import time
from dotenv import load_dotenv
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

# 0. 환경 변수 로드
load_dotenv()

# --- ❗ 중요: 아래 설정들을 본인의 환경에 맞게 확인하세요 ---

# 1. 원본 데이터가 있는 폴더 경로 설정
SOURCE_DIRECTORY_PATH = "./data" 

# 2. Pinecone 설정 정보 (.env 파일에서 불러옵니다)
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

# 3. 사용할 임베딩 모델 설정 (.env 파일과 동일하게)
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

# 4. Pinecone 인덱스가 생성될 클라우드 및 지역 설정 (무료 버전은 보통 aws/us-east-1)
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"

# ----------------------------------------------------------------

def main():
    print("--- Pinecone 데이터베이스 생성을 시작합니다 (최신 Serverless 버전) ---")
    
    # Pinecone 클라이언트 초기화
    pc = Pinecone(api_key=PINECONE_API_KEY)

    # 임베딩 모델의 차원 수 확인 (text-embedding-3-large는 3072)
    try:
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        dimension = 3072 # 모델에 맞는 차원 수 고정
        print(f"사용할 임베딩 모델: '{EMBEDDING_MODEL}', 벡터 차원: {dimension}")
    except Exception as e:
        print(f"🚨 오류: 임베딩 모델을 초기화할 수 없습니다. OpenAI API 키를 확인하세요. 오류: {e}")
        return

    # Pinecone 인덱스가 없으면 새로 생성 (ServerlessSpec 사용)
    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f"\n'{PINECONE_INDEX_NAME}' 인덱스가 존재하지 않아 새로 생성합니다.")
        try:
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=PINECONE_CLOUD,
                    region=PINECONE_REGION
                )
            )
            print("인덱스 생성을 시작했습니다. 활성화까지 잠시 기다립니다...")
            while not pc.describe_index(PINECONE_INDEX_NAME).status['ready']:
                time.sleep(1)
            print("인덱스가 성공적으로 생성되고 활성화되었습니다.")
        except Exception as e:
            print(f"🚨 오류: Pinecone 인덱스 생성에 실패했습니다. API 키와 설정을 확인하세요. 오류: {e}")
            return
    else:
        print(f"\n기존 인덱스 '{PINECONE_INDEX_NAME}'를 사용합니다.")
        # 데이터가 꼬이는 것을 방지하기 위해 기존 인덱스의 모든 내용을 지웁니다.
        print("기존 인덱스의 모든 벡터를 삭제합니다...")
        try:
            index = pc.Index(PINECONE_INDEX_NAME)
            index.delete(delete_all=True)
            print("모든 벡터를 삭제했습니다.")
        except Exception as e:
            print(f"🚨 오류: 기존 벡터 삭제에 실패했습니다. 오류: {e}")


    # 1단계: PPTX 파일 로드 (Load)
    # (이하 로직은 이전과 동일)
    print(f"\n1단계: '{SOURCE_DIRECTORY_PATH}' 폴더에서 모든 PPTX 파일을 로드합니다...")
    all_documents = []
    # ... (이하 파일 로딩, 분할, 업로드 코드는 이전과 동일하게 작동합니다) ...
    if not os.path.exists(SOURCE_DIRECTORY_PATH):
        print(f"🚨 오류: '{SOURCE_DIRECTORY_PATH}' 폴더를 찾을 수 없습니다.")
        return

    for filename in os.listdir(SOURCE_DIRECTORY_PATH):
        if filename.endswith(".pptx"):
            file_path = os.path.join(SOURCE_DIRECTORY_PATH, filename)
            try:
                print(f"  - '{filename}' 파일 로딩 중...")
                loader = UnstructuredPowerPointLoader(file_path)
                all_documents.extend(loader.load())
            except Exception as e:
                print(f"🚨 오류: '{filename}' 파일 로드 중 문제가 발생했습니다. 오류: {e}")

    if not all_documents:
        print("🚨 오류: 로드할 PPTX 파일이 없거나 모든 파일을 로드하는 데 실패했습니다.")
        return
    print(f"성공! 총 {len(all_documents)}개의 슬라이드/문서를 로드했습니다.")

    print("\n2단계: 로드된 문서를 청크(chunk) 단위로 분할합니다...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = text_splitter.split_documents(all_documents)
    print(f"성공! 문서를 총 {len(split_docs)}개의 청크로 분할했습니다.")

    print("\n3단계: 분할된 청크를 임베딩하여 Pinecone에 업로드합니다...")
    print("이 작업은 문서의 양에 따라 몇 분 정도 소요될 수 있습니다.")
    try:
        PineconeVectorStore.from_documents(
            documents=split_docs,
            embedding=embeddings,
            index_name=PINECONE_INDEX_NAME
        )
        print("성공! 모든 청크를 Pinecone에 업로드했습니다.")
    except Exception as e:
        print(f"🚨 오류: Pinecone에 데이터를 업로드하는 중 실패했습니다. 오류: {e}")
        return

    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()
    vector_count = stats.get('total_vector_count', 0)

    print(f"\n--- ✅ Pinecone 데이터베이스 설정 완료 ---")
    print(f"인덱스 이름: '{PINECONE_INDEX_NAME}'")
    print(f"업로드된 총 벡터(청크) 수: {vector_count}")

if __name__ == "__main__":
    main()