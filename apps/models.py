from datetime import datetime
from apps.app import db, login_manager
from flask_login import UserMixin

class User(db.Model, UserMixin):

    __tablename__ = "users"
    id = db.Column(db.String, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now)


    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):

    return User.query.get(user_id)

class ChatLog(db.Model):

    __tablename__ = "chat_logs"
    id = db.Column(db.BigInteger, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user_query = db.Column(db.Text, nullable=False)
    assistant_response = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text, nullable=True)

 
    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('chat_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<ChatLog {self.id}>'

class UserSession(db.Model):

    __tablename__ = "user_sessions"
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.String, db.ForeignKey('users.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=datetime.now)
    logout_time = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('sessions', lazy='dynamic'))

    def __repr__(self):
        return f'<UserSession id={self.id} user_id={self.user_id}>'