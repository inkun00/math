import time
import random
import datetime

import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ==============================
# 구글시트 서비스 계정 키를 secrets.toml에서 불러옴
# ==============================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    info = dict(st.secrets["gcp_service_account"])  # gspread_service_account 대신 gcp_service_account로!
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_worksheet():
    client = get_gspread_client()
    sh = client.open_by_key(GSHEET_KEY)
    return sh.sheet1

# ==============================
# 설정값
# ==============================
GSHEET_KEY = "17cmgNZiG8vyhQjuSOykoRYcyFyTCzhBd_Z12rChueFU"

# ==============================
# 결과 저장(append) 함수 (중복 방지 포함)
# ==============================
def append_result_to_sheet(name: str, school: str, score: int):
    ws = get_worksheet()
    try:
        now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        ts = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        all_rows = ws.get_all_values()
        if len(all_rows) > 1:
            last = all_rows[-1]
            if last[1] == school and last[2] == name and last[3] == str(score):
                return
        ws.append_row([ts, school, name, score])
    except Exception as e:
        st.error(f"구글 시트에 결과 저장 실패: {e}")

# ==============================
# 랭크 데이터 로드 (캐시)
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def load_rank_data():
    ws = get_worksheet()
    try:
        data = ws.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame(columns=["날짜","학교","이름","점수"])
        df = pd.DataFrame(data[1:], columns=data[0])
        df["점수"] = df["점수"].astype(int)
        return df.sort_values(by="점수", ascending=False).reset_index(drop=True)
    except Exception as e:
        st.error(f"구글 시트 데이터 로드 실패: {e}")
        return pd.DataFrame(columns=["날짜","학교","이름","점수"])

# ==============================
# 문제 생성
# ==============================
def generate_problems():
    probs = []
    for _ in range(5):
        a, b = random.randint(100,999), random.randint(10,99)
        probs.append({"type":"mul","a":a,"b":b,"answer":a*b})
    for _ in range(5):
        a, b = random.randint(100,999), random.randint(10,99)
        probs.append({
            "type":"div","a":a,"b":b,
            "quotient":a//b,"remainder":a%b
        })
    random.shuffle(probs)
    return probs

# ==============================
# 상태 초기화
# ==============================
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

# ==============================
# UI 구성
# ==============================
def show_title():
    st.title("🔢 곱셈·나눗셈 퀴즈 챌린지")

def show_rules_and_name_input():
    st.markdown("""
        ### 🎯 규칙
        - 총 10문제: 5 곱셈, 5 나눗셈
        - 제한시간 2분, 빠를수록 보너스
        - 오답 시 기회 차감 (총 5회)
        - ‘순위 보기’로 상위 기록 확인
        - 도담초 4학년 2반 화이팅!
    """)
    st.session_state.school = st.text_input(
        "학교 이름", st.session_state.get("school","")
    )
    st.session_state.name = st.text_input(
        "학생 이름", st.session_state.get("name","")
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("시작하기"):
            if not st.session_state.school.strip():
                st.warning("학교를 입력하세요.")
            elif not st.session_state.name.strip():
                st.warning("이름을 입력하세요.")
            else:
                reset_quiz_state()
                st.session_state.problems = generate_problems()
                st.session_state.start_time = time.time()
                st.rerun()
    with c2:
        if st.button("순위 보기"):
            st.session_state.show_rank = True
            st.rerun()

def show_quiz_interface():
    if st.session_state.lives <= 0 or st.session_state.q_idx >= len(st.session_state.problems):
        st.session_state.finished = True
        return
    elapsed = time.time() - st.session_state.start_time
    rem_time = max(0, 120 - int(elapsed))
    st.sidebar.markdown(
        f"- 학교: {st.session_state.school}\n"
        f"- 점수: {st.session_state.score}점\n"
        f"- 기회: {'❤'*st.session_state.lives}\n"
        f"- 남은시간: {rem_time}초"
    )
    st.markdown(f"**문제 {st.session_state.q_idx+1}/{len(st.session_state.problems)}**")
    st.progress(rem_time/120)
    prob = st.session_state.problems[st.session_state.q_idx]
    if prob['type'] == 'mul':
        st.markdown(f"## {prob['a']} × {prob['b']} = ?")
        ans = st.text_input("답 입력", key=f"mul_{st.session_state.q_idx}")
        if st.button("제출", key=f"mul_btn_{st.session_state.q_idx}"):
            handle_mul(ans, prob, elapsed)
    else:
        st.markdown(f"## {prob['a']} ÷ {prob['b']} = ? (몫/나머지)")
        q = st.text_input("몫", key=f"quo_{st.session_state.q_idx}")
        r = st.text_input("나머지", key=f"rem_{st.session_state.q_idx}")
        if st.button("제출", key=f"div_btn_{st.session_state.q_idx}"):
            handle_div(q, r, prob, elapsed)
    if rem_time <= 0:
        st.session_state.finished = True

def handle_mul(inp, prob, elapsed):
    try:
        ua = int(inp)
    except:
        st.error("숫자만 가능")
        return
    bonus = max(0, 120 - int(elapsed))
    base = 10
    if ua == prob['answer']:
        st.success(f"✅ +{base}+{bonus}={base+bonus}점")
        st.session_state.score += base + bonus
        st.session_state.history.append(True)
    else:
        st.error(f"❌ 정답 {prob['answer']}")
        st.session_state.lives -= 1
        st.session_state.history.append(False)
    st.session_state.q_idx += 1
    st.session_state.start_time = time.time()
    st.rerun()

def handle_div(q, r, prob, elapsed):
    try:
        uq, ur = int(q), int(r)
    except:
        st.error("숫자만 가능")
        return
    bonus = max(0, 120 - int(elapsed))
    base = prob['quotient']
    if uq == prob['quotient'] and ur == prob['remainder']:
        st.success(f"✅ +{base}+{bonus}={base+bonus}점")
        st.session_state.score += base + bonus
        st.session_state.history.append(True)
    else:
        st.error(f"❌ 정답 {prob['quotient']}…{prob['remainder']}")
        st.session_state.lives -= 1
        st.session_state.history.append(False)
    st.session_state.q_idx += 1
    st.session_state.start_time = time.time()
    st.rerun()

def show_result():
    st.header("🎉 결과")
    total = st.session_state.score
    corrects = sum(st.session_state.history)
    st.markdown(f"**점수: {total}점, 정답 {corrects}/{len(st.session_state.problems)}**")
    if not st.session_state.saved:
        append_result_to_sheet(
            st.session_state.name, st.session_state.school, total
        )
        st.session_state.saved = True
        st.success("구글 시트에 저장됨")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("다시"):
            reset_quiz_state()
            st.rerun()
    with c2:
        if st.button("순위"):
            st.session_state.show_rank = True
            st.rerun()

def show_rank():
    st.header("🏆 순위")
    df = load_rank_data()
    if df.empty:
        st.info("기록 없음")
        if st.button("뒤로"):
            st.session_state.show_rank = False
            reset_quiz_state()
            st.rerun()
        return

    # Top10 전체
    top10 = df.head(10).reset_index(drop=True)
    top10.index += 1
    top10.columns = ["날짜","학교","이름","점수"]
    st.subheader("Top10")
    st.table(top10)

    # 개인 총점
    df["이름"] = df["이름"].str.strip()
    df["학교"] = df["학교"].str.strip()
    df = df.dropna(subset=["이름","학교","점수"])
    agg = df.groupby(["이름","학교"])["점수"].sum().reset_index()
    agg = agg.sort_values("점수", ascending=False).reset_index(drop=True)
    agg.index += 1
    agg.rename(columns={"점수":"총점"}, inplace=True)
    st.markdown("---")
    st.subheader("개인 총점 Top10")
    st.table(agg.head(10))

    # 학교별 총점
    school_tot = df.groupby("학교")["점수"].sum().reset_index()
    school_tot = school_tot.sort_values("점수", ascending=False).reset_index(drop=True)
    school_tot.index += 1
    school_tot.rename(columns={"점수":"총점"}, inplace=True)
    st.markdown("---")
    st.subheader("학교별 총점 Top5")
    st.table(school_tot.head(5))

    # 학교 선택 콤보박스
    st.markdown("---")
    st.subheader("학교별 학생 순위 및 시도 기록")
    if school_tot.empty:
        st.info("학교 데이터가 없습니다.")
        if st.button("뒤로"):
            st.session_state.show_rank = False
            reset_quiz_state()
            st.rerun()
        return

    selected = st.selectbox(
        "학교 선택",
        options=list(school_tot.index),
        format_func=lambda i: school_tot.loc[i-1, "학교"]
    )
    sel_name = school_tot.loc[selected-1, "학교"]
    students = agg[agg["학교"] == sel_name].reset_index(drop=True)
    if not students.empty:
        students.index += 1
        st.table(students)
        st.markdown(f"**{sel_name} 학교 전체 시도 기록**")
        att = df[df["학교"] == sel_name][["날짜","이름","점수"]].sort_values("날짜")
        st.table(att.reset_index(drop=True))
    else:
        st.info("선택한 학교의 기록이 없습니다.")

    # 개인 검색
    st.markdown("---")
    st.subheader("개인 기록 검색")
    name_search = st.text_input("검색 이름")
    if st.button("검색") and name_search.strip():
        m = agg[agg["이름"] == name_search]
        if m.empty:
            st.warning("기록없음")
        else:
            for idx, row in m.iterrows():
                st.markdown(
                    f"**{row['이름']} ({row['학교']}) - 총점 {row['총점']}점 "
                    f"(순위 {idx+1})**"
                )

    if st.button("뒤로"):
        st.session_state.show_rank = False
        reset_quiz_state()
        st.rerun()

def main():
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지", layout="centered")

    # ─── 세션 상태 초기화 ──────────────────────────
    if "initialized" not in st.session_state:
        reset_quiz_state()
        st.session_state.school = ""
        st.session_state.name = ""
        st.session_state.initialized = True
    # ────────────────────────────────────────────────

    show_title()
    if st.session_state.show_rank:
        show_rank()
    elif st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()
    elif not st.session_state.finished:
        st_autorefresh(interval=10000, limit=None, key="timer")
        show_quiz_interface()
    else:
        show_result()

if __name__ == "__main__":
    main()
