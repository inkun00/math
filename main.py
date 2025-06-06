import streamlit as st
import time
import random
import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ─────────────────────────────────────────────────────────────────
# 이 한 줄만 있으면, 매 1000밀리초(=1초)마다 자동 rerun 됩니다.
count = st_autorefresh(interval=1000, limit=None, key="timer")

# ─────────── 나머지 로직은 위 예시와 동일 ───────────
# (세션 초기화, show_title, show_rules_and_name_input, get_gspread_client, append_result_to_sheet, etc.)

def show_quiz_interface():
    idx = st.session_state.q_idx
    problems = st.session_state.problems

    # ‣ 남은 시간 계산 (st_autorefresh 덕에 1초마다 rerun)
    elapsed = time.time() - st.session_state.start_time
    time_left = max(0, 120 - int(elapsed))
    progress = time_left / 120

    # 사이드바
    with st.sidebar:
        st.markdown("### 사이드바 정보")
        st.markdown(f"- 현재 점수: {st.session_state.score}점")
        st.markdown(f"- 남은 기회: {'❤️' * st.session_state.lives}")
        st.markdown(f"- 남은 시간: {time_left}초")

    # 본문
    st.markdown(f"**문제 {idx+1}/{len(problems)}**")
    st.markdown(f"## 🔢 문제: {problems[idx][0]} × {problems[idx][1]} = ?")
    st.progress(progress)
    st.markdown(f"남은 시간: **{time_left}초** (120초 제한)")

    user_input = st.text_input("답을 입력하세요", key=f"ans_{idx}")
    submit = st.button("제출하기")

    if submit:
        # 정답 처리 후 rerun
        elapsed_final = time.time() - st.session_state.start_time
        time_left_final = max(0, 120 - int(elapsed_final))
        bonus = time_left_final
        base_score = problems[idx][2]

        if int(user_input) == base_score:
            gained = base_score + bonus
            st.success(f"✅ 정답! (+{base_score} + 보너스 {bonus} = 총 {gained}점)")
            st.session_state.score += gained
            st.session_state.history.append(("정답", elapsed_final, bonus, base_score))
        else:
            st.error(f"❌ 오답! 정답은 **{base_score}** 입니다.")
            st.session_state.lives -= 1
            st.session_state.history.append(("오답", elapsed_final, bonus, 0))

        st.session_state.q_idx += 1
        st.session_state.start_time = time.time()
        st.experimental_rerun()

    if time_left <= 0 or st.session_state.lives <= 0 or st.session_state.q_idx >= len(problems):
        st.session_state.finished = True

# ─────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="곱셈 퀴즈 챌린지", layout="centered")
    show_title()

    if st.session_state.show_rank:
        show_rank()
        return

    if st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()
    elif not st.session_state.finished:
        show_quiz_interface()
    else:
        show_result()

if __name__ == "__main__":
    main()
