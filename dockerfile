# 1) 베이스 이미지로 슬림한 Python 사용
FROM python:3.9-slim

# 2) 작업 디렉터리 설정
WORKDIR /app

# 3) 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) 소스 복사
COPY . .

# 5) Streamlit 실행 명령
CMD ["streamlit", "run", "main.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
