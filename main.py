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
    st.session_state.saved = False  # 결과 저장 여부
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
# 2) 퀴즈 문제 생성 함수
# ==============================
def generate_problems():
    problems = []
    for _ in range(5):
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        problems.append({"type": "mul", "a": a, "b": b, "answer": a * b})
    for _ in range(5):
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        problems.append({
            "type": "div",
            "a": a,
            "b": b,
            "quotient": a // b,
            "remainder": a % b
        })
    random.shuffle(problems)
    return problems

# ==============================
# 3) 화면 구성 함수들
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
        - 퀴즈 종료 시 구글 시트에 (날짜, 학교, 이름, 점수) 저장(한국 시간)
        - ‘순위 보기’ 버튼으로 상위 10위 확인(학교 포함)
        """
    )
    school = st.text_input("학교 이름을 입력하세요", st.session_state.school)
    st.session_state.school = school
    name = st.text_input("이름을 입력하세요", st.session_state.name)
    st.session_state.name = name

    col1, col2 = st.columns(2)
    with col1:
        if st.button("시작하기"):
            if not school.strip():
                st.warning("학교 이름을 입력해주세요.")
            elif not name.strip():
                st.warning("이름을 입력해주세요.")
            else:
                # 퀴즈 시작 시에만 saved 초기화
                reset_quiz_state()
                st.session_state.saved = False
                st.session_state.problems = generate_problems()
                st.session_state.start_time = time.time()
                st.session_state.show_rank = False
                st.rerun()
    with col2:
        if st.button("순위 보기"):
            st.session_state.show_rank = True
            st.rerun()

def show_quiz_interface():
    idx = st.session_state.q_idx
    problems = st.session_state.problems

    if idx >= len(problems) or st.session_state.lives <= 0:
        st.session_state.finished = True
        return

    elapsed = time.time() - st.session_state.start_time
    time_left = max(0, 120 - int(elapsed))
    progress = time_left / 120

    with st.sidebar:
        st.markdown("### 사이드바 정보")
        st.markdown(f"- 학교: {st.session_state.school}")
        st.markdown(f"- 현재 점수: {st.session_state.score}점")
        st.markdown(f"- 남은 기회: {'❤️' * st.session_state.lives}")
        st.markdown(f"- 남은 시간: {time_left}초")

    st.markdown(f"**문제 {idx+1}/{len(problems)}**")
    st.progress(progress)
    st.markdown(f"남은 시간: **{time_left}초** (120초 제한)")

    prob = problems[idx]
    if prob["type"] == "mul":
        a, b, answer = prob["a"], prob["b"], prob["answer"]
        st.markdown(f"## 🔢 **곱셈 문제: {a} × {b} = ?**")
        user_input = st.text_input("답을 입력하세요", key=f"mul_ans_{idx}")
        if st.button("제출하기", key=f"mul_btn_{idx}"):
            try:
                user_ans = int(user_input.strip())
            except:
                st.error("숫자만 입력해주세요.")
                return
            elapsed_final = time.time() - st.session_state.start_time
            bonus = max(0, 120 - int(elapsed_final))
            base_score = 10
            if user_ans == answer:
                gained = base_score + bonus
                st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {gained}점)")
                st.session_state.score += gained
                st.session_state.history.append(("mul_correct", elapsed_final, bonus, base_score))
            else:
                st.error(f"❌ 오답! 정답은 **{answer}** 입니다.")
                st.session_state.lives -= 1
                st.session_state.history.append(("mul_wrong", elapsed_final, bonus, 0))
            st.session_state.q_idx += 1
            st.session_state.start_time = time.time()
            st.rerun()
    else:
        a, b = prob["a"], prob["b"]
        quotient, remainder = prob["quotient"], prob["remainder"]
        st.markdown(f"## 🔢 **나눗셈 문제: {a} ÷ {b} = ?**")
        st.markdown("※ 몫과 나머지를 모두 입력하세요.")
        col1, col2 = st.columns(2)
        with col1:
            user_quo = st.text_input("몫", key=f"div_quo_{idx}")
        with col2:
            user_rem = st.text_input("나머지", key=f"div_rem_{idx}")
        if st.button("제출하기", key=f"div_btn_{idx}"):
            try:
                u_quo = int(user_quo.strip())
                u_rem = int(user_rem.strip())
            except:
                st.error("숫자만 입력해주세요.")
                return
            elapsed_final = time.time() - st.session_state.start_time
            bonus = max(0, 120 - int(elapsed_final))
            base_score = quotient
            if u_quo == quotient and u_rem == remainder:
                gained = base_score + bonus
                st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {gained}점)")
                st.session_state.score += gained
                st.session_state.history.append(("div_correct", elapsed_final, bonus, base_score))
            else:
                st.error(f"❌ 오답! 정답은 **{quotient} … 나머지 {remainder}** 입니다.")
                st.session_state.lives -= 1
                st.session_state.history.append(("div_wrong", elapsed_final, bonus, 0))
            st.session_state.q_idx += 1
            st.session_state.start_time = time.time()
            st.rerun()

    if time_left <= 0:
        st.session_state.finished = True

def show_result():
    st.header("🎉 퀴즈 결과")
    total_score = st.session_state.score
    total_correct = sum(1 for rec in st.session_state.history if "correct" in rec[0])
    st.markdown(f"**최종 점수: {total_score}점**")
    st.markdown(f"정답 개수: {total_correct}/{len(st.session_state.problems)}")

    st.subheader("📝 문제별 결과")
    for i, rec in enumerate(st.session_state.history, start=1):
        status, elapsed, bonus, base = rec
        if status.endswith("correct"):
            st.markdown(f"{i}. ✅ {'곱셈' if status.startswith('mul') else '나눗셈'} 정답 (문제 점수 {base}, 보너스 {bonus}, 소요시간 {int(elapsed)}초)")
        else:
            st.markdown(f"{i}. ❌ {'곱셈' if status.startswith('mul') else '나눗셈'} 오답 (소요시간 {int(elapsed)}초)")

    # 한 번만 저장
    if not st.session_state.saved:
        append_result_to_sheet(st.session_state.name, st.session_state.school, total_score)
        st.session_state.saved = True
        st.success("✅ 결과가 구글 시트에 저장되었습니다!")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 다시 시작하기"):
            # 퀴즈 재시작 시에는 saved 다시 False
            reset_quiz_state()
            st.session_state.saved = False
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
        # 전체 학생 Top10
        top10 = df.head(10).copy()
        top10.index += 1
        top10.reset_index(inplace=True)
        top10.columns = ["순위", "날짜", "학교", "이름", "점수"]
        st.subheader("🔝 전체 학생 Top 10")
        st.table(top10)

        # 개인별 총점 Top10
        student_totals = (
            df.groupby(["이름","학교"], as_index=False)["점수"].sum().rename(columns={"점수":"총점"})
        ).sort_values(by="총점", ascending=False).reset_index(drop=True)
        student_totals["순위"] = student_totals.index + 1
        student_totals["학교내순위"] = student_totals.groupby("학교")["총점"].rank(method="dense", ascending=False).astype(int)
        st.markdown("---")
        st.subheader("🥇 개인별 총점 Top 10")
        st.table(student_totals[["순위","이름","학교","총점"]].head(10))

        # 학교별 총점 Top5
        school_totals = (
            df.groupby("학교", as_index=False)["점수"].sum().rename(columns={"점수":"총점"})
        ).sort_values(by="총점", ascending=False).reset_index(drop=True)
        school_totals["순위(학교)"] = school_totals.index + 1
        st.markdown("---")
        st.subheader("🏫 학교별 총점 Top 5")
        st.table(school_totals[["순위(학교)","학교","총점"]].head(5))

        # 학생 검색
        st.markdown("---")
        st.subheader("🔍 학생 이름으로 검색")
        col1, col2 = st.columns([3,1])
        with col1:
            st.text_input("▶ 학생 이름을 입력하세요", key="student_name_input")
        with col2:
            if st.button("검색", key="student_search_btn") and st.session_state.student_name_input.strip():
                search_name = st.session_state.student_name_input.strip()
                matched = student_totals[student_totals["이름"] == search_name]
                if matched.empty:
                    st.warning(f"'{search_name}' 학생의 기록이 없습니다.")
                else:
                    for _, row in matched.iterrows():
                        html = f"""
                        <div style="border:1px solid #ddd; padding:10px; margin-bottom:10px; border-radius:5px; background-color:#f9f9f9;">
                          <ul style="margin:0; padding-left:20px;">
                            <li><strong>이름:</strong> {row['이름']}</li>
                            <li><strong>학교:</strong> {row['학교']}</li>
                            <li><strong>총점:</strong> {row['총점']}점</li>
                            <li><strong>전체 순위:</strong> {int(row['순위'])}위</li>
                            <li><strong>학교 내 순위:</strong> {int(row['학교내순위'])}위</li>
                          </ul>
                        </div>
                        """
                        st.markdown(html, unsafe_allow_html=True)

    if st.button("◀ 뒤로 가기"):
        st.session_state.show_rank = False
        reset_quiz_state()
        st.rerun()

def reset_quiz_state():
    """
    퀴즈 초기 상태(인트로 화면)로 되돌리기.
    * saved는 초기화하지 않음! (한 번 저장된 이후엔 유지)
    """
    st.session_state.q_idx = 0
    st.session_state.lives = 5
    st.session_state.score = 0
    st.session_state.start_time = None
    st.session_state.finished = False
    st.session_state.history = []
    st.session_state.problems = []
    st.session_state.show_rank = False
    # st.session_state.saved 는 유지

def main():
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지", layout="centered")
    show_title()

    if st.session_state.show_rank:
        show_rank()
        return

    if st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()
    elif not st.session_state.finished:
        st_autorefresh(interval=1000, limit=None, key="quiz_timer")
        show_quiz_interface()
    else:
        show_result()

if __name__ == "__main__":
    main()
