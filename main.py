import streamlit as st
import time
import random
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

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

def append_result_to_sheet(name: str, score: int):
    """
    현재 시간, 이름, 점수를 구글 시트에 append 합니다.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([now_str, name, score])
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
            return pd.DataFrame(columns=["날짜", "이름", "점수"])
        df = pd.DataFrame(data[1:], columns=data[0])
        df["점수"] = df["점수"].astype(int)
        df_sorted = df.sort_values(by="점수", ascending=False)
        return df_sorted.reset_index(drop=True)
    except Exception as e:
        st.error(f"구글 시트에서 데이터를 불러오는 도중 오류가 발생했습니다:\n{e}")
        return pd.DataFrame(columns=["날짜", "이름", "점수"])

# ==============================
# 2) 퀴즈 문제 생성 함수 (수정)
# ==============================
def generate_problems():
    """
    10개 문제를 반환:
    1~5: 세자리수 × 두자리수
    6~10: 세자리수 ÷ 두자리수 (몫과 나머지; 나눠 떨어지는 경우와 나머지가 있는 경우 혼합)
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
        # 나눗셈 문제 생성 (몫이 소수점 못 나오도록)
        a = random.randint(100, 999)
        b = random.randint(10, 99)
        # 몫과 나머지 계산
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
# 3) 화면 구성 함수들
# ==============================
def show_title():
    st.title("🔢 곱셈·나눗셈 퀴즈 챌린지")

def show_rules_and_name_input():
    """
    초기 화면: 규칙 설명 + 이름 입력 + 시작/순위 보기 버튼
    """
    st.markdown(
        """
        ### 🎯 규칙
        - 총 10문제
        - 5문제는 세자리수 × 두자리수 곱셈
        - 5문제는 세자리수 ÷ 두자리수 나눗셈 (몫과 나머지)
        - 문제당 제한시간 2분 (120초), 빨리 풀수록 보너스 점수 부여
        - 총 5번의 기회 제공. 오답 시 기회 1개 차감
        - 나눗셈 문제는 몫과 나머지 모두 맞춰야 정답 처리
        - 퀴즈 종료 시 구글 시트에 (날짜, 이름, 점수) 저장
        - ‘순위 보기’ 버튼으로 상위 10위 확인
        """
    )
    name = st.text_input("이름을 입력하세요", st.session_state.name)
    st.session_state.name = name

    col1, col2 = st.columns(2)
    with col1:
        if st.button("시작하기"):
            if name.strip() == "":
                st.warning("이름을 입력해주세요.")
            else:
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
    with col2:
        if st.button("순위 보기"):
            st.session_state.show_rank = True

def show_quiz_interface():
    """
    퀴즈 화면:
    - 문제 번호, 문제 내용(곱셈 or 나눗셈), 현재 점수, 남은 시간, 남은 기회, 입력창, 제출 버튼
    """
    idx = st.session_state.q_idx
    problems = st.session_state.problems

    # 모든 문제 완료 or 기회 소진 시 종료 플래그
    if idx >= len(problems) or st.session_state.lives <= 0:
        st.session_state.finished = True
        return

    prob = problems[idx]
    prob_type = prob["type"]

    # 타이머 계산 (st_autorefresh 덕분에 매초 rerun)
    elapsed = time.time() - st.session_state.start_time
    time_left = max(0, 120 - int(elapsed))
    progress = time_left / 120

    # 사이드바: 점수, 기회, 남은 시간
    with st.sidebar:
        st.markdown("### 사이드바 정보")
        st.markdown(f"- 현재 점수: {st.session_state.score}점")
        st.markdown(f"- 남은 기회: {'❤️' * st.session_state.lives}")
        st.markdown(f"- 남은 시간: {time_left}초")

    # 공통 상단 정보
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
        submit = st.button("제출하기", key=f"mul_btn_{idx}")

        if submit:
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
                st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {gained}점)")
                st.session_state.score += gained
                st.session_state.history.append(("mul_correct", elapsed_final, bonus, base_score))
            else:
                st.error(f"❌ 오답! 정답은 **{answer}** 입니다.")
                st.session_state.lives -= 1
                st.session_state.history.append(("mul_wrong", elapsed_final, bonus, 0))

            # 다음 문제
            st.session_state.q_idx += 1
            st.session_state.start_time = time.time()
            st.rerun()

    else:
        # 나눗셈 문제
        a = prob["a"]
        b = prob["b"]
        quotient = prob["quotient"]
        remainder = prob["remainder"]

        st.markdown(f"## 🔢 **나눗셈 문제: {a} ÷ {b} = ?**")
        st.markdown("※ 몫과 나머지를 모두 입력하세요.")

        col1, col2 = st.columns(2)
        with col1:
            user_quotient = st.text_input("몫", key=f"div_quo_{idx}")
        with col2:
            user_remainder = st.text_input("나머지", key=f"div_rem_{idx}")

        submit = st.button("제출하기", key=f"div_btn_{idx}")

        if submit:
            try:
                user_quo = int(user_quotient.strip())
                user_rem = int(user_remainder.strip())
            except:
                st.error("숫자만 입력해주세요.")
                return

            elapsed_final = time.time() - st.session_state.start_time
            time_left_final = max(0, 120 - int(elapsed_final))
            bonus = time_left_final
            base_score = quotient  # 몫을 기본 점수로 사용

            if user_quo == quotient and user_rem == remainder:
                gained = base_score + bonus
                st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {gained}점)")
                st.session_state.score += gained
                st.session_state.history.append(("div_correct", elapsed_final, bonus, base_score))
            else:
                correct_str = f"{quotient} … 나머지 {remainder}"
                st.error(f"❌ 오답! 정답은 **{correct_str}** 입니다.")
                st.session_state.lives -= 1
                st.session_state.history.append(("div_wrong", elapsed_final, bonus, 0))

            # 다음 문제
            st.session_state.q_idx += 1
            st.session_state.start_time = time.time()
            st.rerun()

    # 제한 시간 만료 시 종료
    if time_left <= 0:
        st.session_state.finished = True

def show_result():
    """
    퀴즈 종료 후 결과 화면:
    - 최종 점수, 정답 개수, 오답 내역 간단 표시
    - 구글 시트 저장 안내
    - 다시 시작하기 / 순위 보기 버튼
    """
    st.header("🎉 퀴즈 결과")
    total_score = st.session_state.score
    total_correct = sum(1 for rec in st.session_state.history if "correct" in rec[0])
    st.markdown(f"**최종 점수: {total_score}점**")
    st.markdown(f"정답 개수: {total_correct}/{len(st.session_state.problems)}")

    st.subheader("📝 문제별 결과")
    for i, rec in enumerate(st.session_state.history, start=1):
        status, elapsed, bonus, base = rec
        if "mul_correct" == status:
            st.markdown(f"{i}. ✅ 곱셈 정답 (문제 점수 {base}, 보너스 {bonus}, 소요시간 {int(elapsed)}초)")
        elif "mul_wrong" == status:
            st.markdown(f"{i}. ❌ 곱셈 오답 (소요시간 {int(elapsed)}초)")
        elif "div_correct" == status:
            st.markdown(f"{i}. ✅ 나눗셈 정답 (문제 점수 {base}, 보너스 {bonus}, 소요시간 {int(elapsed)}초)")
        else:
            st.markdown(f"{i}. ❌ 나눗셈 오답 (소요시간 {int(elapsed)}초)")

    if not st.session_state.saved:
        append_result_to_sheet(st.session_state.name, total_score)
        st.session_state.saved = True
        st.success("✅ 결과가 구글 시트에 저장되었습니다!")

    st.markdown("---")
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
    """
    ‘순위 보기’ 화면:
    - 구글 시트에서 모든 기록을 불러와서 상위 10명(점수 내림차순) 표시
    """
    st.header("🏆 순위 보기 (Top 10)")
    df = load_rank_data()
    if df.empty:
        st.info("아직 기록이 없습니다.")
    else:
        top10 = df.head(10).copy()
        top10.index = top10.index + 1
        top10.reset_index(inplace=True)
        top10.columns = ["순위", "날짜", "이름", "점수"]
        st.table(top10)

    if st.button("◀ 뒤로 가기"):
        st.session_state.show_rank = False
        reset_quiz_state()
        st.rerun()

def reset_quiz_state():
    """
    퀴즈를 다시 초기 상태(인트로 화면)로 돌립니다.
    """
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
# 5) 메인 실행 흐름
# ==============================
def main():
    # 반드시 스크립트 내 첫 번째 Streamlit 호출이어야 합니다.
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지", layout="centered")

    # 세션 상태 초기화
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.name = ""
        st.session_state.problems = []
        st.session_state.q_idx = 0
        st.session_state.lives = 5
        st.session_state.score = 0
        st.session_state.start_time = None
        st.session_state.finished = False
        st.session_state.history = []
        st.session_state.show_rank = False
        st.session_state.saved = False

    show_title()

    # 순위 보기 모드
    if st.session_state.show_rank:
        show_rank()
        return

    # 퀴즈 시작 전
    if st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()

    # 퀴즈 진행 중
    elif not st.session_state.finished:
        # 1초마다 자동 rerun
        st_autorefresh(interval=1000, limit=None, key="quiz_timer")
        show_quiz_interface()

    # 퀴즈 종료 후
    else:
        show_result()


if __name__ == "__main__":
    main()
