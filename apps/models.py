from datetime import datetime 

from apps.app import db, login_manager
from flask_login import UserMixin 
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key = True)
    username = db.Column(db.String, index = True)
    studentid = db.Column(db.String, unique=True)
    password_hash = db.Column(db.String)
    created_at = db.Column(db.DateTime, default = datetime.now)
    updated_at = db.Column(db.DateTime, default = datetime.now, onupdate= datetime.now)

    @property
    def password(self):
        raise AttributeError("읽어 들일 수 없음")
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_duplicate_studentid(self):
        return User.query.filter_by(studentid =self.studentid).first() is not None
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))


class ChatLog(db.Model):
    __tablename__ = "chat_logs"
    
    # Supabase 스키마와 일치하는 컬럼 정의
    id = db.Column(db.BigInteger, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user_query = db.Column(db.Text, nullable=False)
    assistant_response = db.Column(db.Text, nullable=False)
    
    # users 테이블의 id를 참조하는 외래 키 설정
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    StudentID = db.Column(db.String, db.ForeignKey('users.studentid'), nullable=True)

    def __repr__(self):
        return f'<ChatLog {self.id}>'
    


class UserSession(db.Model):
    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    # users 테이블의 id를 참조하는 외래 키
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    studentid = db.Column(db.String, db.ForeignKey('users.studentid'), nullable=True)
    login_time = db.Column(db.DateTime, default=datetime.now)
    logout_time = db.Column(db.DateTime, nullable=True) # 로그아웃 시점에 업데이트되므로 처음엔 NULL 허용
    
    # User 모델과 관계 설정 (User 객체에서 user.sessions 형태로 접근 가능)
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('sessions', lazy='dynamic'))

    def __repr__(self):
        return f'<UserSession id={self.id} user_id={self.user_id}>'