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
    # 순위 보기 화면용
    st.session_state.school_filter_input = ""
    st.session_state.student_name_input = ""

# ==============================
# 1) Google Sheets 인증 및 시트 열기
# ==============================
GSHEET_KEY = "17cmgNZiG8vyhQjuSOykoRYcyFyTCzhBd_Z12rChueFU"

@st.cache_resource(show_spinner=False)
def get_gspread_client():
    # 서비스 계정 인증
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# Append 결과 저장
def append_result_to_sheet(name: str, school: str, score: int):
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        now_kst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        ts = now_kst.strftime("%Y-%m-%d %H:%M:%S")
        worksheet.append_row([ts, school, name, score])
    except Exception as e:
        st.error(f"구글 시트에 결과 저장 실패: {e}")

# ==============================
# 2) 캐시 적용된 데이터 로드 (쿼터 방지)
# ==============================
@st.cache_data(ttl=60, show_spinner=False)
def load_rank_data():
    try:
        client = get_gspread_client()
        sh = client.open_by_key(GSHEET_KEY)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        if len(data) <= 1:
            return pd.DataFrame(columns=["날짜","학교","이름","점수"])
        df = pd.DataFrame(data[1:], columns=data[0])
        df["점수"] = df["점수"].astype(int)
        return df.sort_values(by="점수", ascending=False).reset_index(drop=True)
    except Exception as e:
        st.error(f"구글 시트 데이터 로드 실패: {e}")
        return pd.DataFrame(columns=["날짜","학교","이름","점수"])

# ==============================
# 3) 문제 생성
# ==============================
def generate_problems():
    probs = []
    for _ in range(5):
        a,b = random.randint(100,999), random.randint(10,99)
        probs.append({"type":"mul","a":a,"b":b,"answer":a*b})
    for _ in range(5):
        a,b = random.randint(100,999), random.randint(10,99)
        probs.append({
            "type":"div","a":a,"b":b,
            "quotient":a//b,"remainder":a%b
        })
    random.shuffle(probs)
    return probs

# ==============================
# 4) UI 구성
# ==============================
def show_title():
    st.title("🔢 곱셈·나눗셈 퀴즈 챌린지")


def show_rules_and_name_input():
    st.markdown(
        """
        ### 🎯 규칙
        - 총 10문제: 5 곱셈, 5 나눗셈
        - 제한시간 2분, 빠를수록 보너스
        - 오답 시 기회 1회 차감, 총 5회 기회
        - 종료 후 구글 시트에 기록 저장
        - ‘순위 보기’로 상위 기록 확인
        """
    )
    st.session_state.school = st.text_input("학교 이름", st.session_state.school)
    st.session_state.name   = st.text_input("학생 이름", st.session_state.name)
    c1,c2 = st.columns(2)
    with c1:
        if st.button("시작하기"):
            if not st.session_state.school.strip(): st.warning("학교를 입력하세요.")
            elif not st.session_state.name.strip():  st.warning("이름을 입력하세요.")
            else:
                reset_quiz_state()
                st.session_state.problems = generate_problems()
                st.session_state.start_time = time.time()
                st.rerun()
    with c2:
        if st.button("순위 보기"):
            st.session_state.show_rank=True
            st.rerun()


def show_quiz_interface():
    if st.session_state.lives<=0 or st.session_state.q_idx>=len(st.session_state.problems):
        st.session_state.finished=True
        return
    elapsed = time.time()-st.session_state.start_time
    rem_time = max(0,120-int(elapsed))
    st.sidebar.markdown(f"- 학교: {st.session_state.school}\n- 점수: {st.session_state.score}점\n- 기회: {'❤️'*st.session_state.lives}\n- 남은시간: {rem_time}초")
    st.markdown(f"**문제 {st.session_state.q_idx+1}/{len(st.session_state.problems)}**")
    st.progress(rem_time/120)
    prob = st.session_state.problems[st.session_state.q_idx]
    if prob['type']=='mul':
        st.markdown(f"## {prob['a']} × {prob['b']} = ?")
        ans = st.text_input("답 입력", key=f"mul_{st.session_state.q_idx}")
        if st.button("제출",key=f"mul_btn_{st.session_state.q_idx}"):
            handle_mul(ans,prob,elapsed)
    else:
        st.markdown(f"## {prob['a']} ÷ {prob['b']} = ? (몫/나머지)")
        q = st.text_input("몫",key=f"quo_{st.session_state.q_idx}")
        r = st.text_input("나머지",key=f"rem_{st.session_state.q_idx}")
        if st.button("제출",key=f"div_btn_{st.session_state.q_idx}"):
            handle_div(q,r,prob,elapsed)
    if rem_time<=0: st.session_state.finished=True


def handle_mul(inp,prob,elapsed):
    try:ua=int(inp)
    except: st.error("숫자만 가능") ; return
    bonus=max(0,120-int(elapsed)); base=10
    if ua==prob['answer']:
        st.success(f"✅ +{base}+{bonus}={base+bonus}점")
        st.session_state.score+=base+bonus
        st.session_state.history.append(True)
    else:
        st.error(f"❌ 정답 {prob['answer']}")
        st.session_state.lives-=1
        st.session_state.history.append(False)
    st.session_state.q_idx+=1
    st.session_state.start_time=time.time()
    st.rerun()


def handle_div(q,r,prob,elapsed):
    try:uq,ur=int(q),int(r)
    except: st.error("숫자만 가능") ; return
    bonus=max(0,120-int(elapsed)); base=prob['quotient']
    if uq==prob['quotient'] and ur==prob['remainder']:
        st.success(f"✅ +{base}+{bonus}={base+bonus}점")
        st.session_state.score+=base+bonus
        st.session_state.history.append(True)
    else:
        st.error(f"❌ 정답 {prob['quotient']}…{prob['remainder']}")
        st.session_state.lives-=1
        st.session_state.history.append(False)
    st.session_state.q_idx+=1
    st.session_state.start_time=time.time()
    st.rerun()


def show_result():
    st.header("🎉 결과")
    total=st.session_state.score
    corrects=sum(1 for x in st.session_state.history if x)
    st.markdown(f"**점수: {total}점, 정답 {corrects}/{len(st.session_state.problems)}**")
    if not st.session_state.saved:
        append_result_to_sheet(st.session_state.name,st.session_state.school,total)
        st.session_state.saved=True
        st.success("구글 시트에 저장됨")
    c1,c2=st.columns(2)
    with c1:
        if st.button("다시"):reset_quiz_state();st.rerun()
    with c2:
        if st.button("순위"):st.session_state.show_rank=True;st.rerun()


def show_rank():
    st.header("🏆 순위")
    df=load_rank_data()
    if df.empty:st.info("기록 없음")
    else:
        t10=df.head(10).reset_index();t10.columns=["순위","날짜","학교","이름","점수"]
        st.subheader("Top10")
        st.table(t10)
        agg=df.groupby(["이름","학교"])['점수'].sum().reset_index()
        agg=agg.sort_values('점수',ascending=False).reset_index(drop=True)
        agg['순위']=agg.index+1
        st.markdown("---")
        st.subheader("개인 총점 Top10")
        st.table(agg.head(10)[["순위","이름","학교","점수"]])
        school_tot=df.groupby('학교')['점수'].sum().reset_index().sort_values('점수',ascending=False)
        school_tot['순위(학교)']=school_tot.index+1
        st.markdown("---")
        st.subheader("학교별 총점 Top5")
        st.table(school_tot.head(5)[["순위(학교)","학교","점수"]])
        st.markdown("---")
        name_input=st.text_input("검색 이름",key="student_name_input")
        if st.button("검색",key="search_btn") and name_input.strip():
            m=agg[agg['이름']==name_input]
            if m.empty: st.warning("기록없음")
            else:
                for _,r in m.iterrows(): st.markdown(f"**{r['이름']}({r['학교']}) {r['점수']}점 순위{r['순위']}**")
    if st.button("뒤로"): st.session_state.show_rank=False;reset_quiz_state();st.rerun()


def reset_quiz_state():
    st.session_state.q_idx=0;st.session_state.lives=5;st.session_state.score=0
    st.session_state.start_time=None;st.session_state.finished=False
    st.session_state.history=[];st.session_state.problems=[]
    st.session_state.saved=False;st.session_state.show_rank=False


def main():
    st.set_page_config(page_title="곱셈·나눗셈 퀴즈 챌린지",layout="centered")
    show_title()
    if st.session_state.show_rank:
        show_rank()
    elif st.session_state.start_time is None and not st.session_state.finished:
        show_rules_and_name_input()
    elif not st.session_state.finished:
        # 10초마다 자동 새로고침
        st_autorefresh(interval=10000,limit=None,key="timer")
        show_quiz_interface()
    else:
        show_result()

if __name__ == "__main__":
    main()
