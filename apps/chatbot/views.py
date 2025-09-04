import os
from flask import Blueprint, render_template, flash, url_for, redirect, request, jsonify, Response, current_app, session
from apps.app import db 
from apps.chatbot.forms import SignUpForm, LoginForm
from apps.models import User, ChatLog,  UserSession
from flask_login import login_user, logout_user
from flask_login import login_required, current_user
import time
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain.schema import HumanMessage, AIMessage
import re 
from datetime import datetime

program_chat = Blueprint(
    "program_chat",
    __name__,
    template_folder="templates",
    static_folder = "static",
)


@program_chat.route("/", methods= ["GET", "POST"])
def index():

    if current_user.is_authenticated:
    
        return redirect(url_for("program_chat.chat"))

    # --- 이하 기존 코드 ---
    form = LoginForm()
    if form.validate_on_submit():
        user= User.query.filter_by(studentid = form.studentID.data).first()

        if user is not None and user.verify_password(form.password.data):
            login_user(user)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # AJAX 요청이면, JSON 형태로 성공 여부와 이동할 URL을 알려줍니다.
                return jsonify(success=True, redirect_url=url_for("program_chat.chat"))
            
            # 일반적인 Form 제출이면, 기존처럼 redirect합니다.
            return redirect(url_for("program_chat.chat"))
        flash("학번 또는 비밀번호가 일치하지 않습니다.")

    return render_template("chatbot/login.html", form =form )


@program_chat.route("/sign", methods = ["GET", "POST"])
def sign():
    form = SignUpForm()
    if form.validate_on_submit():
        user = User(
            username = form.username.data,
            studentid = form.studentID.data,
            password = form.password.data,
        )

        if user.is_duplicate_studentid():
            flash("해당 학번은 이미 등록되어 있습니다")
            return redirect(url_for("program_chat.sign"))
        
        db.session.add(user)
        db.session.commit()

        login_user(user)

        next_ = request.args.get("next")
        if next_ is None or not next_.startswith("/"):
            next_ = url_for("program_chat.index")
        return redirect(next_)
    
    return render_template("chatbot/checkin.html", form = form)


@program_chat.route("/chat")
@login_required
def chat():
    return render_template("chatbot/chat.html")

@program_chat.route("/logout")
@login_required # 로그아웃도 로그인 상태에서만 가능하도록 추가
def logout():
    logout_user()
    return redirect(url_for("program_chat.index"))

@program_chat.route("/track-logout", methods=["POST"])
@login_required
def track_logout():
    # 세션에서 현재 user_session의 id를 가져옵니다.
    session_id = session.get('user_session_id')
    if session_id:
        user_session = UserSession.query.get(session_id)
        # 로그아웃 시간이 아직 기록되지 않은 경우에만 업데이트합니다.
        # (이미 로그아웃 버튼을 눌렀을 수 있기 때문)
        if user_session and user_session.logout_time is None:
            user_session.logout_time = datetime.now()
            db.session.commit()
    # sendBeacon은 응답을 기다리지 않으므로 간단한 응답을 보냅니다.
    return "", 204


llm = ChatOpenAI(
    model_name=os.getenv("OPENAI_API_MODEL", "gpt-4-turbo"),
    temperature=float(os.getenv("OPENAI_API_TEMPERATURE", 0.7)),
)
# --- ▼▼▼ 새로 추가된 챗봇 API 엔드포인트 ▼▼▼ ---

@program_chat.route("/process_chat", methods=["POST"])
@login_required
def process_chat():
    data = request.get_json()
    user_message = data.get("message")
    history_data = data.get("history", [])

    if not user_message:
        return jsonify({"error": "메시지가 없습니다."}), 400

    app = current_app._get_current_object()
    user_id = current_user.id
    student_id = current_user.studentid

    # 1. 이전 대화 기록을 LangChain 메시지 객체 리스트로 변환
    chat_history_messages = []
    for message in history_data:
        if message["role"] == "user":
            chat_history_messages.append(HumanMessage(content=message["content"]))
        elif message["role"] == "assistant":
            chat_history_messages.append(AIMessage(content=message["content"]))
    
    messages_for_llm = chat_history_messages + [HumanMessage(content=user_message)]

    # 2. LLM으로부터 완전한 응답을 '미리' 받습니다.
    try:
        full_response = llm.invoke(messages_for_llm).content
    except Exception as e:
        print(f"Error during LangChain invoke: {e}")
        # 오류 발생 시에는 스트리밍이 아니므로 JSON으로 응답합니다.
        return jsonify({"response": "죄송합니다. 응답 생성 중 오류가 발생했습니다.", "is_code": False}), 500

    # 3. 데이터베이스에 전체 로그를 먼저 저장합니다.
    with app.app_context():
        try:
            chatlog = ChatLog(
                user_query=user_message,
                assistant_response=full_response,
                user_id=user_id,
                StudentID=student_id,
            )
            db.session.add(chatlog)
            db.session.commit()
            print("Chat log saved successfully.")
        except Exception as e:
            print(f"Error saving chat log to database: {e}")
            db.session.rollback()

    # ▼▼▼ 여기가 핵심! 하이브리드 스트리밍 로직입니다. ▼▼▼
    
    # 4. 정규식을 사용하여 응답을 '텍스트 부분'과 '코드 부분'으로 분리합니다.
    #    re.split은 괄호로 묶인 구분자(코드블록)를 결과 리스트에 포함시킵니다.
    parts = re.split(r'(```[\s\S]*?```)', full_response)

    def generate_hybrid_stream():
        # 5. 분리된 각 부분에 대해 반복합니다.
        for part in parts:
            if part.startswith('```') and part.endswith('```'):
                # 이 부분이 코드 블록인 경우, 한 번에 전송합니다.
                yield part
            else:
                # 이 부분이 일반 텍스트인 경우, 한 글자씩 딜레이를 주어 전송합니다.
                for char in part:
                    yield char
                    time.sleep(0.02)
    
    # 6. 위에서 정의한 하이브리드 스트리밍 제너레이터를 사용하여 응답합니다.
    return Response(generate_hybrid_stream(), mimetype='text/plain')