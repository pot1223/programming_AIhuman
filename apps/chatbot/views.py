import os
import re
import time
from datetime import datetime

from flask import (Blueprint, Response, current_app, flash, jsonify,
                   redirect, render_template, request, session, url_for)
from flask_login import (current_user, login_required, login_user,
                         logout_user)
from langchain.schema import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from apps.app import db
from apps.chatbot.forms import LoginForm
from apps.models import ChatLog, User, UserSession

# 새로 추가되는 라이브러리
from langchain_chroma import Chroma
from langchain_community.embeddings import OpenAIEmbeddings
from langchain.chains import ConversationalRetrievalChain
from langchain.prompts import PromptTemplate

program_chat = Blueprint(
    "program_chat",
    __name__,
    template_folder="templates",
    static_folder="static",
)


llm = ChatOpenAI(
    model_name=os.getenv("OPENAI_API_MODEL", "gpt-4-turbo"),
    temperature=float(os.getenv("OPENAI_API_TEMPERATURE", 0.7)),
)

# chunking 작업이 완료된 database 불러오기
embeddings = OpenAIEmbeddings(
    model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
)

# --- ❗ 배포 시 중요: Render의 영구 디스크 경로로 수정 ---
# 로컬 테스트 시에는 "./chroma"를 사용하세요.
# 배포 직전에 아래 경로로 변경해야 합니다.
PERSIST_DIRECTORY = "/data/chroma" if os.getenv("RENDER") else "./chroma"


# 기존 DB 불러오기
vectordb = Chroma(
    persist_directory=PERSIST_DIRECTORY,
    collection_name="AIhuman-programming-3-14",
    embedding_function=embeddings
)

# Retriever => 검색기
retriever = vectordb.as_retriever(search_kwargs={"k": 4})

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
    return_source_documents=False,                  # 근거 문서 미사용
    combine_docs_chain_kwargs={"prompt": QA_PROMPT} # {question}, {context} 프롬프트 사용
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

    # 프론트 히스토리 → [(human, ai), ...] 변환
    def to_chat_pairs(history):
        pairs, last_user = [], None
        for m in history:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                if last_user is not None:
                    pairs.append((last_user, ""))
                last_user = content
            else:  # assistant
                if last_user is None:
                    pairs.append(("", content))
                else:
                    pairs.append((last_user, content))
                    last_user = None
        if last_user is not None:
            pairs.append((last_user, ""))
        return pairs

    chat_pairs = to_chat_pairs(history_data)

    try:
        res = conv_qa({
            "question": user_message,
            "chat_history": chat_pairs
        })
        full_response = res["answer"].strip()
    except Exception as e:
        current_app.logger.error(f"Error during Conversational RAG invoke: {e}")
        return jsonify({"response": "죄송합니다. 응답 생성 중 오류가 발생했습니다."}), 500

    # 이하 기존 로깅/스트리밍 로직 그대로 유지
    code_blocks = re.findall(r'```[\s\S]*?```', full_response)
    extracted_code = "\n\n".join(code_blocks) if code_blocks else None

    try:
        chat_log = ChatLog(
            user_query=user_message,
            assistant_response=full_response,
            code=extracted_code,
            user_id=current_user.id
        )
        db.session.add(chat_log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Error saving chat log to DB: {e}")
        db.session.rollback()

    parts = re.split(r'(```[\s\S]*?```)', full_response)
    def generate_hybrid_stream():
        for part in parts:
            if part.strip().startswith('```') and part.strip().endswith('```'):
                yield part
            else:
                for char in part:
                    yield char
                    time.sleep(0.05)

    return Response(generate_hybrid_stream(), mimetype='text/plain')