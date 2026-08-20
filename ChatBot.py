# ====================================================================================
#  Gemini AI 챗봇 (Streamlit) - 엔트리포인트
# ====================================================================================

import streamlit as st

# --- 페이지 기본 설정 (반드시 최상단) ---
st.set_page_config(
    page_title="동동봇",
    page_icon="./images/동동이.PNG",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- 모듈 임포트 ---
from session import init_session_state
from ui_sidebar import render_sidebar
from ui_main import render_main_chat

# --- 앱 실행 ---
init_session_state()
render_sidebar()
render_main_chat()
