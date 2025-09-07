# create_database.py (PowerPoint 파일용)

import os
from dotenv import load_dotenv
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# 0. 환경 변수 로드
load_dotenv()

# --- ❗ 중요: 아래 설정들을 본인의 환경에 맞게 확인하세요 ---

# 1. 원본 데이터가 있는 폴더 경로 설정
SOURCE_DIRECTORY_PATH = "./data" 

# 2. ChromaDB를 저장할 폴더 경로 설정
PERSIST_DIRECTORY = "/data/chroma" 

# 3. DB 컬렉션 이름 설정 (views.py와 반드시 동일해야 함)
COLLECTION_NAME = "AIhuman-programming-3-14"

# 4. 사용할 임베딩 모델 설정 (.env 파일과 동일하게)
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

# ----------------------------------------------------------------

def main():
    print("--- 데이터베이스 생성을 시작합니다 (PPTX 파일용) ---")
    
    all_documents = []

    # 1단계: 지정된 폴더에서 모든 PPTX 파일 로드 (Load)
    print(f"1단계: '{SOURCE_DIRECTORY_PATH}' 폴더에서 모든 PPTX 파일을 로드합니다...")
    if not os.path.exists(SOURCE_DIRECTORY_PATH):
        print(f"🚨 오류: '{SOURCE_DIRECTORY_PATH}' 폴더를 찾을 수 없습니다.")
        return

    # 폴더 내의 모든 파일을 순회
    for filename in os.listdir(SOURCE_DIRECTORY_PATH):
        if filename.endswith(".pptx"):
            file_path = os.path.join(SOURCE_DIRECTORY_PATH, filename)
            try:
                print(f"  - '{filename}' 파일 로딩 중...")
                loader = UnstructuredPowerPointLoader(file_path)
                # loader.load()는 문서 리스트를 반환하므로 extend 사용
                all_documents.extend(loader.load())
            except Exception as e:
                print(f"🚨 오류: '{filename}' 파일 로드 중 문제가 발생했습니다. 오류: {e}")
                continue # 문제가 있는 파일은 건너뛰고 계속 진행

    if not all_documents:
        print("🚨 오류: 로드할 PPTX 파일이 없거나 모든 파일을 로드하는 데 실패했습니다.")
        return
    print(f"성공! 총 {len(all_documents)}개의 슬라이드/문서를 로드했습니다.")


    # 2단계: 문서 분할 (Split)
    print("\n2단계: 로드된 문서를 청크(chunk) 단위로 분할합니다...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = text_splitter.split_documents(all_documents)
    print(f"성공! 문서를 총 {len(split_docs)}개의 청크로 분할했습니다.")

    # 3단계: 임베딩 및 DB 저장 (Embed & Store)
    print("\n3단계: 분할된 청크를 임베딩하여 ChromaDB에 저장합니다...")
    try:
        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
        
        # 기존 DB가 있다면 삭제하고 새로 생성 (선택사항)
        if os.path.exists(PERSIST_DIRECTORY):
            print(f"  - 기존 '{PERSIST_DIRECTORY}' 폴더를 삭제합니다.")
            import shutil
            shutil.rmtree(PERSIST_DIRECTORY)

        vectordb = Chroma.from_documents(
            documents=split_docs, 
            embedding=embeddings, 
            persist_directory=PERSIST_DIRECTORY,
            collection_name=COLLECTION_NAME
        )
        print("성공! 데이터베이스에 모든 청크를 저장했습니다.")
    except Exception as e:
        print(f"🚨 오류: 임베딩 또는 DB 저장에 실패했습니다. OpenAI API 키를 확인해주세요. 오류: {e}")
        return
        
    # 4단계: 최종 검증
    count = vectordb._collection.count()
    print(f"\n--- ✅ 데이터베이스 생성 완료 ---")
    print(f"저장된 폴더: '{PERSIST_DIRECTORY}'")
    print(f"컬렉션 이름: '{COLLECTION_NAME}'")
    print(f"저장된 총 문서 청크 수: {count}")


if __name__ == "__main__":
    main()