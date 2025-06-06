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
    st.session_state.school_filter_input = ""    # 학교명 검색용 (필요 시 재사용 가능)
    st.session_state.student_name_input = ""     # 학생명 검색용

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
    한국 시간으로 현재 시간, 학교, 이름, 점수를 구글 시트에 append 합니다.
    """
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        now_utc = datetime.datetime.utcnow()
        now_kst = now_utc + datetime.timedelta(hours=9)
        now_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        # '날짜', '학교', '이름', '점수' 순서로 저장
        worksheet.append_row([now_str, school, name, score])
    except Exception as e:
        st.error(f"구글 시트에 결과를 저장하는 도중 오류가 발생했습니다:\n{e}")

def load_rank_data():
    """
    구글 시트에 저장된 모든 데이터를 불러와서,
    '점수' 컬럼을 기준으로 내림차순 정렬한 pandas.DataFrame을 반환합니다.
    기대되는 시트 헤더 순서: ["날짜", "학교", "이름", "점수"]
    """
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
# 3) 화면 구성 함수들
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
        - 퀴즈 종료 시 구글 시트에 (날짜, 학교, 이름, 점수) 저장(한국 시간)
        - ‘순위 보기’ 버튼으로 상위 10위 확인(학교 포함)
        """
    )
    # 학교 먼저 입력
    school = st.text_input("학교 이름을 입력하세요", st.session_state.school)
    st.session_state.school = school
    # 그다음 이름 입력
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
                # 세션 상태 초기화 후 문제 생성
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
                # 버튼 클릭 후 즉시 rerun하여 퀴즈 화면으로 전환
                st.rerun()
    with col2:
        if st.button("순위 보기"):
            st.session_state.show_rank = True
            st.rerun()

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

            # 다음 문제 이동
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

            # 다음 문제 이동
            st.session_state.q_idx += 1
            st.session_state.start_time = time.time()
            st.rerun()

    # 제한 시간 만료 시 종료
    if time_left <= 0:
        st.session_state.finished = True

def show_result():
    """
    퀴즈 종료 후 결과 화면:
    - 최종 점수, 정답 개수, 오답 내역 간략 표시
    - 구글 시트에 저장 안내
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
        if status == "mul_correct":
            st.markdown(f"{i}. ✅ 곱셈 정답 (문제 점수 {base}, 보너스 {bonus}, 소요시간 {int(elapsed)}초)")
        elif status == "mul_wrong":
            st.markdown(f"{i}. ❌ 곱셈 오답 (소요시간 {int(elapsed)}초)")
        elif status == "div_correct":
            st.markdown(f"{i}. ✅ 나눗셈 정답 (문제 점수 {base}, 보너스 {bonus}, 소요시간 {int(elapsed)}초)")
        else:
            st.markdown(f"{i}. ❌ 나눗셈 오답 (소요시간 {int(elapsed)}초)")

    if not st.session_state.saved:
        append_result_to_sheet(st.session_state.name, st.session_state.school, total_score)
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
    - 전체 학생 Top10 (개별 기록 기준)
    - 개인별 총점 Top10 (이름+학교 조합별)
    - 학교별 총점 Top5
    - 학생 이름 검색: 입력된 이름으로 모든 매칭된 정보(여러 학교 포함) 출력,
      각각의 총점, 전체 순위, 학교 내 순위 표시
    """
    st.header("🏆 순위 보기")

    # 구글 시트 데이터 로드
    df = load_rank_data()  # columns: ["날짜", "학교", "이름", "점수"]

    if df.empty:
        st.info("아직 기록이 없습니다.")
    else:
        # 1) 전체 학생 Top10 (개별 기록 기준)
        top10_individual = df.head(10).copy()
        top10_individual.index = top10_individual.index + 1
        top10_individual.reset_index(inplace=True)
        top10_individual.columns = ["순위", "날짜", "학교", "이름", "점수"]
        st.subheader("🔝 전체 학생 Top 10 (개별 기록 기준)")
        st.table(top10_individual)

        # 2) 개인별 총점 Top10 (이름+학교 조합별)
        df_student_school_totals = (
            df.groupby(["이름", "학교"], as_index=False)["점수"]
              .sum()
              .rename(columns={"점수": "총점"})
        )
        df_student_school_totals = df_student_school_totals.sort_values(by="총점", ascending=False).reset_index(drop=True)
        df_student_school_totals["순위"] = df_student_school_totals.index + 1

        # 학교 내 순위 계산 (이름+학교별 총점 DataFrame에서)
        df_student_school_totals["학교내순위"] = (
            df_student_school_totals.groupby("학교")["총점"]
              .rank(method="dense", ascending=False)
              .astype(int)
        )

        df_top10_student_totals = df_student_school_totals[["순위", "이름", "학교", "총점"]].head(10)
        st.markdown("---")
        st.subheader("🥇 개인별 총점 Top 10")
        st.table(df_top10_student_totals)

        # 3) 학교별 총점 Top5
        df_school_totals = (
            df.groupby("학교", as_index=False)["점수"]
              .sum()
              .rename(columns={"점수": "총점"})
        )
        df_school_totals_sorted = df_school_totals.sort_values(by="총점", ascending=False).reset_index(drop=True)
        df_school_totals_sorted["순위(학교)"] = df_school_totals_sorted.index + 1
        df_school_top5 = df_school_totals_sorted[["순위(학교)", "학교", "총점"]].head(5)

        st.markdown("---")
        st.subheader("🏫 학교별 총점 Top 5")
        st.table(df_school_top5)

        # 4) 학생 이름 검색 UI: 텍스트박스와 버튼을 나란히 배치
        st.markdown("---")
        st.subheader("🔍 학생 이름으로 검색")
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_input("▶ 학생 이름을 입력하세요", key="student_name_input")
        with col2:
            search_btn = st.button("검색", key="student_search_btn")

        if search_btn and st.session_state.student_name_input.strip():
            search_name = st.session_state.student_name_input.strip()
            # df_student_school_totals 에서 이름이 동일한 모든 행을 가져옴
            matched = df_student_school_totals[df_student_school_totals["이름"] == search_name]

            if matched.empty:
                st.warning(f"'{search_name}' 학생의 기록이 없습니다.")
            else:
                st.markdown(f"**검색 결과: {search_name}**")
                # 같은 이름이 여러 학교에 있을 수 있으므로, 각 행마다 정보 출력
                for _, row in matched.iterrows():
                    school = row["학교"]
                    total_score = row["총점"]
                    overall_rank = int(row["순위"])
                    school_rank = int(row["학교내순위"])
                    st.markdown(f"- 이름: **{search_name}**, 학교: **{school}**")
                    st.markdown(f"  - 총점: {total_score}점")
                    st.markdown(f"  - 전체 순위: {overall_rank}위")
                    st.markdown(f"  - '{school}' 학교 내 순위: {school_rank}위")

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
    # 검색 입력값은 유지해두어도 무방

# ==============================
# 4) 메인 실행 흐름
# ==============================
def main():
    # 반드시 스크립트 내 첫 번째 Streamlit 호출이어야 합니다.
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지", layout="centered")

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
