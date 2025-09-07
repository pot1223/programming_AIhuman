from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    studentID = StringField(
        "학번",
        validators=[
            DataRequired("학번은 필수입니다."),
            Length(1, 30, "학번 형식으로 입력해주세요.")
        ],
    )
    password = PasswordField(
        "수업 코드", 
        validators=[DataRequired("수업 코드는 필수입니다.")]
    )
    submit = SubmitField("입장하기")