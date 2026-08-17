# ====================================================================================
#  session.py - 세션 상태 초기화 & 관리
# ====================================================================================

import streamlit as st
from config import MODEL_OPTIONS


def init_session_state():
    """앱 시작 시 필요한 세션 상태를 초기화"""
    defaults = {
        "selected_gemini_model": MODEL_OPTIONS[0] if MODEL_OPTIONS else "",
        "system_instructions": "",
        "gemini_client": None,
        "api_key_configured": False,
        "messages": [],
        "chat_session": None,
        "current_api_key": None,
        "api_key_error_text": None,
        "active_project_type": None,
        "active_model_label": None,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

    # 선택된 모델이 유효한지 검증
    if st.session_state.selected_gemini_model not in MODEL_OPTIONS:
        st.session_state.selected_gemini_model = MODEL_OPTIONS[0] if MODEL_OPTIONS else ""


def reset_session_for_new_chat():
    """채팅 세션을 완전히 초기화"""
    st.session_state.chat_session = None
    st.session_state.gemini_client = None
    st.session_state.messages = []
