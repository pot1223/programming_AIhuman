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
            flash("학번 또는 비밀번호가 일치하지 않습니다.")

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
    """챗봇 메시지 처리 및 스트리밍 응답"""
    data = request.get_json()
    user_message = data.get("message")
    history_data = data.get("history", [])

    if not user_message:
        return jsonify({"error": "메시지가 없습니다."}), 400

    chat_history = [HumanMessage(content=msg["content"]) if msg["role"] == "user"
                    else AIMessage(content=msg["content"]) for msg in history_data]
    messages_for_llm = chat_history + [HumanMessage(content=user_message)]

    try:
        full_response = llm.invoke(messages_for_llm).content
    except Exception as e:
        current_app.logger.error(f"Error during LangChain invoke: {e}")
        return jsonify({"response": "죄송합니다. 응답 생성 중 오류가 발생했습니다."}), 500

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
