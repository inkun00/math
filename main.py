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

    # 순위 보기 화면에서 사용할 입력값 미리 등록
    st.session_state.school_filter_input = ""
    st.session_state.student_name_input = ""

# ==============================
# 1) Google Sheets 인증 및 시트 열기
# ==============================
GSHEET_KEY = "17cmgNZiG8vyhQjuSOykoRYcyFyTCzhBd_Z12rChueFU"

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# 구글 시트 결과 append 함수
def append_result_to_sheet(name: str, school: str, score: int):
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([now_str, school, name, score])
    except Exception as e:
        st.error(f"구글 시트에 결과를 저장하는 도중 오류가 발생했습니다:\n{e}")

# ==============================
# 2) 캐시 적용된 데이터 로드 함수 (쿼터 초과 방지)
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def load_rank_data():
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame(columns=["날짜", "학교", "이름", "점수"])
        df = pd.DataFrame(data[1:], columns=data[0])
        df["점수"] = df["점수"].astype(int)
        df_sorted = df.sort_values(by="점수", ascending=False)
        return df_sorted.reset_index(drop=True)
    except Exception as e:
        st.error(f"구글 시트에서 데이터를 불러오는 도중 오류가 발생했습니다:\n{e}")
        return pd.DataFrame(columns=["날짜", "학교", "이름", "점수"])

# ==============================
# 3) 퀴즈 문제 생성 함수
# ==============================
def generate_problems():
    problems = []
    for _ in range(5):
        a, b = random.randint(100, 999), random.randint(10, 99)
        problems.append({"type": "mul", "a": a, "b": b, "answer": a * b})
    for _ in range(5):
        a, b = random.randint(100, 999), random.randint(10, 99)
        problems.append({
            "type": "div", "a": a, "b": b,
            "quotient": a // b, "remainder": a % b
        })
    random.shuffle(problems)
    return problems

# ==============================
# 4) 화면 구성 함수들
# ==============================

def show_title():
    st.title("🔢 곱셈·나눗셈 퀴즈 챌린지")


def show_rules_and_name_input():
    st.markdown(
        """
        ### 🎯 규칙
        - 총 10문제:
          1. 5문제는 세자리수 × 두자리수 곱셈
          2. 5문제는 세자리수 ÷ 두자리수 나눗셈 (몫과 나머지)
        - 문제당 제한시간 2분(120초), 빨리 풀수록 보너스 점수 부여
        - 총 5번의 기회 제공(오답 시 기회 1개 차감)
        - 나눗셈 문제는 몫과 나머지를 모두 맞춰야 정답 처리
        - 퀴즈 종료 시 구글 시트에 (날짜, 학교, 이름, 점수) 저장(한국 시간)
        - ‘순위 보기’ 버튼으로 상위 10위 확인(학교 포함)
        """
    )
    st.session_state.school = st.text_input("학교 이름을 입력하세요", st.session_state.school)
    st.session_state.name = st.text_input("이름을 입력하세요", st.session_state.name)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("시작하기"):
            if not st.session_state.school.strip():
                st.warning("학교 이름을 입력해주세요.")
            elif not st.session_state.name.strip():
                st.warning("이름을 입력해주세요.")
            else:
                reset_quiz_state()
                st.session_state.problems = generate_problems()
                st.session_state.start_time = time.time()
                st.rerun()
    with col2:
        if st.button("순위 보기"):
            st.session_state.show_rank = True
            st.rerun()


def show_quiz_interface():
    if st.session_state.lives <= 0 or st.session_state.q_idx >= len(st.session_state.problems):
        st.session_state.finished = True
        return
    elapsed = time.time() - st.session_state.start_time
    time_left = max(0, 120 - int(elapsed))
    progress = time_left / 120
    st.sidebar.markdown("### 사이드바 정보")
    st.sidebar.markdown(f"- 학교: {st.session_state.school}")
    st.sidebar.markdown(f"- 현재 점수: {st.session_state.score}점")
    st.sidebar.markdown(f"- 남은 기회: {'❤️'*st.session_state.lives}")
    st.sidebar.markdown(f"- 남은 시간: {time_left}초")
    st.markdown(f"**문제 {st.session_state.q_idx+1}/{len(st.session_state.problems)}**")
    st.progress(progress)
    st.markdown(f"남은 시간: **{time_left}초** (120초 제한)")
    prob = st.session_state.problems[st.session_state.q_idx]
    if prob["type"] == "mul":
        st.markdown(f"## 🔢 곱셈 문제: {prob['a']} × {prob['b']} = ?")
        user_input = st.text_input("답을 입력하세요", key=f"mul_ans_{st.session_state.q_idx}")
        if st.button("제출하기", key=f"mul_btn_{st.session_state.q_idx}"):
            _handle_mul(user_input, prob, elapsed)
    else:
        st.markdown(f"## 🔢 나눗셈 문제: {prob['a']} ÷ {prob['b']} = ? (몫과 나머지 입력)")
        quo = st.text_input("몫", key=f"quo_{st.session_state.q_idx}")
        rem = st.text_input("나머지", key=f"rem_{st.session_state.q_idx}")
        if st.button("제출하기", key=f"div_btn_{st.session_state.q_idx}"):
            _handle_div(quo, rem, prob, elapsed)
    if time_left <= 0:
        st.session_state.finished = True


def _handle_mul(user_input, prob, elapsed):
    try:
        ans = int(user_input)
    except:
        st.error("숫자만 입력해주세요.")
        return
    time_left = max(0, 120 - int(elapsed))
    bonus = time_left
    base = 10
    if ans == prob["answer"]:
        gained = base + bonus
        st.success(f"✅ 정답! (+{base}+보너스 {bonus}={gained}점)")
        st.session_state.score += gained
        st.session_state.history.append(('correct', True))
    else:
        st.error(f"❌ 오답! 정답은 {prob['answer']}입니다.")
        st.session_state.lives -= 1
        st.session_state.history.append(('correct', False))
    st.session_state.q_idx += 1
    st.session_state.start_time = time.time()
    st.rerun()


def _handle_div(quo, rem, prob, elapsed):
    try:
        u_quo, u_rem = int(quo), int(rem)
    except:
        st.error("숫자만 입력해주세요.")
        return
    time_left = max(0, 120 - int(elapsed))
    bonus = time_left
    base = prob['quotient']
    if u_quo == prob['quotient'] and u_rem == prob['remainder']:
        gained = base + bonus
        st.success(f"✅ 정답! (+{base}+보너스 {bonus}={gained}점)")
        st.session_state.score += gained
        st.session_state.history.append(('correct', True))
    else:
        st.error(f"❌ 오답! 정답은 {prob['quotient']}…나머지 {prob['remainder']}입니다.")
        st.session_state.lives -= 1
        st.session_state.history.append(('correct', False))
    st.session_state.q_idx += 1
    st.session_state.start_time = time.time()
    st.rerun()


def show_result():
    st.header("🎉 퀴즈 결과")
    total = st.session_state.score
    correct_count = sum(1 for c in st.session_state.history if c[1])
    st.markdown(f"**최종 점수: {total}점**")
    st.markdown(f"정답 개수: {correct_count}/{len(st.session_state.problems)}")
    append_result_to_sheet(st.session_state.name, st.session_state.school, total)
    st.success("✅ 결과가 구글 시트에 저장되었습니다!")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 다시 시작하기"):
            reset_quiz_state()
            st.rerun()
    with col2:
        if st.button("📊 순위 보기"):
            st.session_state.show_rank = True
            st.rerun()


def show_rank():
    st.header("🏆 순위 보기")
    df = load_rank_data()
    if df.empty:
        st.info("아직 기록이 없습니다.")
    else:
        top10 = df.head(10).reset_index()
        top10.columns = ["순위","날짜","학교","이름","점수"]
        st.subheader("🔝 전체 학생 Top 10")
        st.table(top10)
        totals = df.groupby(["이름","학교"]).점수.sum().reset_index().sort_values(by="점수",ascending=False)
        totals["순위"] = range(1,len(totals)+1)
        st.markdown("---")
        st.subheader("🥇 개인별 총점 Top 10")
        st.table(totals.head(10)[["순위","이름","학교","점수"]])
        school_totals = df.groupby("학교").점수.sum().reset_index().sort_values(by="점수",ascending=False)
        school_totals["순위(학교)"] = range(1,len(school_totals)+1)
        st.markdown("---")
        st.subheader("🏫 학교별 총점 Top 5")
        st.table(school_totals.head(5)[["순위(학교)","학교","점수"]])
        st.markdown("---")
        st.subheader("🔍 학생 이름 검색")
        name = st.text_input("학생 이름을 입력하세요", key="student_name_input")
        if st.button("검색", key="search_btn") and name.strip():
            matched = totals[totals["이름"]==name]
            if matched.empty:
                st.warning(f"'{name}' 기록이 없습니다.")
            else:
                for _,r in matched.iterrows():
                    st.markdown(f"**{r['이름']} ({r['학교']}) - 총점 {r['점수']}점 (순위 {r['순위']})**")
    if st.button("◀ 뒤로 가기"):
        st.session_state.show_rank = False
        reset_quiz_state()
        st.rerun()


def reset_quiz_state():
    st.session_state.q_idx = 0
    st.session_state.lives = 5
    st.session_state.score = 0
    st.session_state.start_time = None
    st.session_state.finished = False
    st.session_state.history = []
    st.session_state.problems = []
    st.session_state.saved = False
    st.session_state.show_rank = False


def main():
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지", layout="centered")
    show_title()
    if st.session_state.show_rank:
        show_rank()
        return
    if st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()
    elif not st.session_state.finished:
        st_autorefresh(interval=1000, limit=None, key="timer")
        show_quiz_interface()
    else:
        show_result()

if __name__ == "__main__":
    main()
