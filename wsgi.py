import os
from apps.app import create_app
from waitress import serve
from dotenv import load_dotenv

load_dotenv()


config_key = os.getenv("dev")
app = create_app(config_key)# waitress 서버로 애플리케이션 실행

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000)