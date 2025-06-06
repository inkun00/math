import streamlit as st
import time
import random
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ==============================
# 전역: 세션 상태 초기화
# ==============================
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.name = ""
    st.session_state.school = ""
    st.session_state.problems = []
    st.session_state.q_idx = 0
    st.session_state.lives = 5
    st.session_state.score = 0
    st.session_state.start_time = None
    st.session_state.finished = False
    st.session_state.history = []
    st.session_state.show_rank = False
    st.session_state.saved = False

# ==============================
# 1) Google Sheets 인증 및 시트 열기
# ==============================
GSHEET_KEY = "17cmgNZiG8vyhQjuSOykoRYcyFyTCzhBd_Z12rChueFU"  # 시트 ID

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """
    Streamlit secrets.toml에 저장된 서비스 계정 JSON을 이용해
    gspread 클라이언트를 생성하여 반환합니다.
    """
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def append_result_to_sheet(name: str, school: str, score: int):
    """
    한국 시간으로 현재 시간, 이름, 학교, 점수를 구글 시트에 append 합니다.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([now_str, name, school, score])
    except Exception as e:
        st.error(f"구글 시트에 결과를 저장하는 도중 오류가 발생했습니다:\n{e}")

def load_rank_data():
    """
    구글 시트에 저장된 모든 데이터를 불러와서,
    '점수' 컬럼을 기준으로 내림차순 정렬한 pandas.DataFrame을 반환합니다.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame(columns=["날짜", "이름", "학교", "점수"])
        df = pd.DataFrame(data[1:], columns=data[0])
        df["점수"] = df["점수"].astype(int)
        df_sorted = df.sort_values(by="점수", ascending=False)
        return df_sorted.reset_index(drop=True)
    except Exception as e:
        st.error(f"구글 시트에서 데이터를 불러오는 도중 오류가 발생했습니다:\n{e}")
        return pd.DataFrame(columns=["날짜", "이름", "학교", "점수"])

# ==============================
# 2) 퀴즈 문제 생성 함수
# ==============================
def generate_problems():
    """
    10개 문제를 반환:
    1~5: 세자리수 × 두자리수
    6~10: 세자리수 ÷ 두자리수 (몫과 나머지)
    """
    problems = []
    # 1~5: 세자리수 × 두자리수
    for _ in range(5):
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        answer = a * b
        problems.append({
            "type": "mul",
            "a": a,
            "b": b,
            "answer": answer
        })
    # 6~10: 세자리수 ÷ 두자리수
    for _ in range(5):
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        quotient = a // b
        remainder = a % b
        problems.append({
            "type": "div",
            "a": a,
            "b": b,
            "quotient": quotient,
            "remainder": remainder
        })
    random.shuffle(problems)
    return problems

# ==============================
# 3) 버튼 콜백 함수
# ==============================
def start_quiz():
    """
    '시작하기' 버튼 콜백: 세션 초기화 후 퀴즈 시작
    """
    reset_quiz_state()
    st.session_state.problems = generate_problems()
    st.session_state.q_idx = 0
    st.session_state.lives = 5
    st.session_state.score = 0
    st.session_state.history = []
    st.session_state.finished = False
    st.session_state.saved = False
    st.session_state.show_rank = False
    st.session_state.start_time = time.time()

def view_rank():
    """
    '순위 보기' 버튼 콜백: 순위 페이지로 전환
    """
    st.session_state.show_rank = True

def back_from_rank():
    """
    '뒤로 가기' 버튼 콜백: 순위 페이지 해제 및 퀴즈 초기 화면으로
    """
    st.session_state.show_rank = False
    reset_quiz_state()

def restart_quiz():
    """
    '다시 시작하기' 버튼 콜백: 퀴즈 재시작
    """
    reset_quiz_state()

# ==============================
# 4) 화면 구성 함수들
# ==============================
def show_title():
    st.title("🔢 곱셈·나눗셈 퀴즈 챌린지")

def show_rules_and_name_input():
    """
    초기 화면: 학교 이름 입력 + 사용자 이름 입력 + 시작/순위 보기 버튼
    """
    st.markdown(
        """
        ### 🎯 규칙
        - 총 10문제:
          1. 5문제는 세자리수 × 두자리수 곱셈
          2. 5문제는 세자리수 ÷ 두자리수 나눗셈 (몫과 나머지)
        - 문제당 제한시간 2분(120초), 빨리 풀수록 보너스 점수 부여
        - 총 5번의 기회 제공(오답 시 기회 1개 차감)
        - 나눗셈 문제는 몫과 나머지를 모두 맞춰야 정답 처리
        - 퀴즈 종료 시 구글 시트에 (날짜, 이름, 학교, 점수) 저장(한국 시간)
        - ‘순위 보기’ 버튼으로 상위 10위 확인(학교 포함)
        """
    )
    school = st.text_input("학교 이름을 입력하세요", st.session_state.school)
    st.session_state.school = school
    name = st.text_input("이름을 입력하세요", st.session_state.name)
    st.session_state.name = name

    col1, col2 = st.columns(2)
    with col1:
        st.button("시작하기", on_click=start_quiz)
    with col2:
        st.button("순위 보기", on_click=view_rank)

def show_quiz_interface():
    """
    퀴즈 화면:
    - 문제 번호, 문제 내용(곱셈 or 나눗셈), 현재 점수, 남은 시간, 남은 기회, 입력창, 제출 버튼
    """
    idx = st.session_state.q_idx
    problems = st.session_state.problems

    # 모든 문제 완료 or 기회 소진 시 종료
    if idx >= len(problems) or st.session_state.lives <= 0:
        st.session_state.finished = True
        return

    prob = problems[idx]
    prob_type = prob["type"]

    # 타이머 계산 (st_autorefresh 덕분에 매초 rerun)
    elapsed = time.time() - st.session_state.start_time
    time_left = max(0, 120 - int(elapsed))
    progress = time_left / 120

    # 사이드바: 학교, 점수, 기회, 남은 시간
    with st.sidebar:
        st.markdown("### 사이드바 정보")
        st.markdown(f"- 학교: {st.session_state.school}")
        st.markdown(f"- 현재 점수: {st.session_state.score}점")
        st.markdown(f"- 남은 기회: {'❤️' * st.session_state.lives}")
        st.markdown(f"- 남은 시간: {time_left}초")

    # 본문 상단 정보
    st.markdown(f"**문제 {idx+1}/{len(problems)}**")
    st.progress(progress)
    st.markdown(f"남은 시간: **{time_left}초** (120초 제한)")

    if prob_type == "mul":
        # 곱셈 문제
        a = prob["a"]
        b = prob["b"]
        answer = prob["answer"]

        st.markdown(f"## 🔢 **곱셈 문제: {a} × {b} = ?**")

        user_input = st.text_input("답을 입력하세요", key=f"mul_ans_{idx}")
        if st.button("제출하기", key=f"mul_btn_{idx}"):
            try:
                user_ans = int(user_input.strip())
            except:
                st.error("숫자만 입력해주세요.")
                return

            elapsed_final = time.time() - st.session_state.start_time
            time_left_final = max(0, 120 - int(elapsed_final))
            bonus = time_left_final
            base_score = answer

            if user_ans == answer:
                gained = base_score + bonus
                st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {
