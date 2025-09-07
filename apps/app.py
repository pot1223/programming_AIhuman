from apps.config import config
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

from flask import Flask, redirect, url_for, session

db = SQLAlchemy()


login_manager = LoginManager()
login_manager.login_view = "program_chat.index"
login_manager.login_message = ""



def create_app(config_key='dev'):
    app = Flask(__name__)
    app.config.from_object(config[config_key])
    login_manager.init_app(app)
    app.config['SESSION_PERMANENT'] = False
    db.init_app(app)
    Migrate(app,db)
    
    from apps import models
    from apps.chatbot import views as chat_views
    from apps.models import UserSession
    from flask_login import user_logged_in, user_logged_out # 시그널 핸들러 추가
    from datetime import datetime # datetime 추가

    # 사용자가 로그인할 때 실행될 함수
    @user_logged_in.connect_via(app)
    def _logged_in_handler(sender, user, **extra):
        new_session = UserSession(user_id=user.id)
        db.session.add(new_session)
        db.session.commit()
        session['user_session_id'] = new_session.id

    # 사용자가 로그아웃할 때 실행될 함수
    @user_logged_out.connect_via(app)
    def _logged_out_handler(sender, user, **extra):
        session_id = session.pop('user_session_id', None)
        if session_id:
            user_session = UserSession.query.get(session_id)
            if user_session:
                user_session.logout_time = datetime.now()
                db.session.commit()


    app.register_blueprint(chat_views.program_chat, url_prefix="/program_chat") 

    @app.route("/")
    def redirect_to_program_chat():
        return redirect(url_for('program_chat.index')) 
    
    return app 

