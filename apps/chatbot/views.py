import os
import re
import time
from datetime import datetime

from flask import (Blueprint, Response, current_app, flash, jsonify,
                   redirect, render_template, request, session, url_for, stream_with_context)
from flask_login import (current_user, login_required, login_user,
                         logout_user)
from langchain.schema import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from apps.app import db
from apps.chatbot.forms import LoginForm
from apps.models import ChatLog, User, UserSession

# --- ❗ Pinecone으로 변경된 라이브러리 ---
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate

program_chat = Blueprint(
    "program_chat",
    __name__,
    template_folder="templates",
    static_folder="static",
)


# --- ❗ 실시간 스트리밍을 위해 llm 설정 변경 ---
llm = ChatOpenAI(
    streaming=True, # 스트리밍 활성화
    model_name=os.getenv("OPENAI_API_MODEL", "gpt-4-turbo"),
    temperature=float(os.getenv("OPENAI_API_TEMPERATURE", 0.7)),
)

# 1. 임베딩 모델 준비 (동일)
embeddings = OpenAIEmbeddings(
    model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
)


# --- ❗ ChromaDB에서 Pinecone 클라우드 DB로 변경된 부분 ---

# 2. Pinecone 인덱스 이름 설정 (.env 파일에서 불러옵니다)
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

# 3. 기존 Pinecone 인덱스에 연결하여 VectorStore(검색기능이 포함된 DB객체) 생성
vectorstore = PineconeVectorStore.from_existing_index(
    index_name=PINECONE_INDEX_NAME,
    embedding=embeddings
)

# 4. Retriever(검색기) 생성 (VectorStore만 Pinecone으로 교체)
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# --- (이하 프롬프트 및 체인 설정은 기존과 동일합니다) ---


# 수업 맥락 + 적대적 프롬프트 차단 + 컨텍스트 없으면 일반 지식 사용
QA_PROMPT = PromptTemplate(
    input_variables=["question", "context"],
    template="""
당신은 한국어를 사용하는 조교형 AI입니다. 우리는 'AIhuman'을 활용하는 강의를 진행 중이며,
학생은 수업을 들으며 모르는 부분을 질문합니다.

[역할/목표]
- 가능한 경우 아래 문서 컨텍스트를 우선 활용해 간결·정확하게 설명하세요.
- 컨텍스트가 없거나 부족하면, 당신의 일반 지식으로 안전하고 책임감 있게 답하세요.
- 답은 5~8문장 이내로 요점을 먼저 말하고, 필요하면 짧은 예시를 덧붙입니다.

[금지/거절 규칙]
- 욕설/혐오/괴롭힘/비하 표현, 수업 범위를 벗어난 정치·종교·성적 주제 선동/논쟁,
  불법·위험 행위, 광고/스팸/오프토픽은 답변하지 말고
  "수업 목적상 답변할 수 없습니다. 수업 관련 질문으로 구체적으로 알려 주세요."라고 한 문장으로 정중히 거절하세요.

질문:
{question}

문서 컨텍스트(있을 때만 참고):
{context}

답변:
"""
)

# RetrievalQA 체인 (근거 문서 반환 X)
conv_qa = ConversationalRetrievalChain.from_llm(
    llm=llm,
    retriever=retriever,
    return_source_documents=False,
    combine_docs_chain_kwargs={"prompt": QA_PROMPT}
)

@program_chat.route("/", methods=["GET", "POST"])
def index():
    """로그인 처리"""
    if current_user.is_authenticated:
        return redirect(url_for("program_chat.chat"))

    form = LoginForm()
    if form.validate_on_submit():
        common_password = os.getenv("COMMON_PASSWORD")
        student_id = form.studentID.data
        form_password = form.password.data

        if form_password == common_password:
            user = User.query.get(student_id)
            if user is None:
                user = User(id=student_id)
                db.session.add(user)
                db.session.commit()

            login_user(user)
            return redirect(url_for("program_chat.chat"))
        else:
            flash("비밀번호가 일치하지 않습니다.")

    return render_template("chatbot/login.html", form=form)


@program_chat.route("/chat")
@login_required
def chat():
    """채팅 페이지 렌더링"""
    return render_template("chatbot/chat.html")


@program_chat.route("/logout")
@login_required
def logout():
    """로그아웃 처리"""
    logout_user()
    return redirect(url_for("program_chat.index"))


@program_chat.route("/track-logout", methods=["POST"])
@login_required
def track_logout():
    """브라우저 종료 시 로그아웃 시간 기록"""
    session_id = session.get('user_session_id')
    if session_id:
        user_session = UserSession.query.get(session_id)
        if user_session and user_session.logout_time is None:
            user_session.logout_time = datetime.now()
            db.session.commit()
    return "", 204


@program_chat.route("/process_chat", methods=["POST"])
@login_required
def process_chat():
    data = request.get_json()
    user_message = data.get("message")
    history_data = data.get("history", [])

    if not user_message:
        return jsonify({"error": "메시지가 없습니다."}), 400

    def to_chat_pairs(history):
        pairs, last_user = [], None
        for m in history:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                if last_user is not None:
                    pairs.append((last_user, ""))
                last_user = content
            else:
                if last_user is None:
                    pairs.append(("", content))
                else:
                    pairs.append((last_user, content))
                    last_user = None
        if last_user is not None:
            pairs.append((last_user, ""))
        return pairs

    chat_pairs = to_chat_pairs(history_data)

    @stream_with_context
    def generate_response_stream():
        yield "잠시만 기다려주세요..."
        
        full_response = ""
        CLEAR_SIGNAL = "<!--CLEAR-->"

        try:
            # 1단계: LLM으로부터 전체 답변을 스트리밍으로 받아와 full_response에 저장
            for chunk in conv_qa.stream({"question": user_message, "chat_history": chat_pairs}):
                if "answer" in chunk:
                    full_response += chunk["answer"]

            # 2단계: "기다려주세요" 메시지를 지우라는 신호를 먼저 보냄
            yield CLEAR_SIGNAL

            # 3단계: 완성된 답변을 텍스트와 코드 블록으로 분리
            parts = re.split(r'(```[\s\S]*?```)', full_response)

            # 4단계: 분리된 조각들을 프론트엔드로 스트리밍
            for part in parts:
                if not part: continue

                # 코드 블록이면 한 번에 전송
                if part.strip().startswith('```') and part.strip().endswith('```'):
                    yield part
                # 텍스트이면 타이핑 효과를 위해 한 글자씩 전송
                else:
                    for char in part:
                        yield char
                        time.sleep(0.02)

            # 5단계: 전체 답변을 DB에 저장
            code_blocks = re.findall(r'```[\s\S]*?```', full_response)
            text_blocks = re.sub(r'```[\s\S]*?```', '', full_response).strip()
            extracted_code = "".join(code_blocks) if code_blocks else None
            
            chat_log = ChatLog(
                user_query=user_message,
                assistant_response= text_blocks ,
                code=extracted_code,
                user_id=current_user.id
            )
            db.session.add(chat_log)
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during RAG stream or DB logging: {e}")
            yield CLEAR_SIGNAL
            yield "죄송합니다. 응답 생성 중 오류가 발생했습니다."

    return Response(generate_response_stream(), mimetype='text/plain')
