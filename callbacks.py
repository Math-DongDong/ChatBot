# ====================================================================================
#  callbacks.py - 콜백 함수 (API키, 모델 변경, 지시문 변경)
# ====================================================================================

import streamlit as st
from config import get_prompt_for_feature


def load_api_key_from_secrets(password: str) -> tuple[str | None, str | None]:
    """secrets에서 비밀번호 검증 후 API 키 반환"""
    try:
        db_credentials = st.secrets.get("db_credentials", {})
        if db_credentials.get("Password") == password:
            api_key = db_credentials.get("APIKEY")
            if api_key:
                return api_key, None
            else:
                return None, "Secrets에 APIKEY가 없습니다."
        else:
            return None, "비밀번호가 일치하지 않습니다."
    except Exception as e:
        return None, f"Secrets 읽기 중 오류: {e}"


def auto_apply_system_instructions_on_change():
    """사용자가 텍스트 영역에 지시문을 입력할 때 감지하는 콜백"""
    new_instructions = st.session_state.get("system_instructions_input", "")
    st.session_state.system_instructions = new_instructions
    st.session_state.chat_session = None
    st.session_state.gemini_client = None
    if new_instructions:
        st.toast("✅ System Instructions가 변경되었습니다. 다음 메시지부터 적용됩니다.")
    else:
        st.toast("ℹ️ System Instructions가 초기화되었습니다.")


def auto_apply_api_key_on_change():
    """API 키 입력 변경 시 검증 및 적용하는 콜백"""
    entered_password = st.session_state.get("gemini_api_key_input_sidebar", "")
    st.session_state.api_key_error_text = None

    if not entered_password:
        if st.session_state.get("api_key_configured", False) or st.session_state.get(
            "current_api_key"
        ):
            st.session_state.api_key_configured = False
            st.session_state.current_api_key = None
            st.session_state.chat_session = None
            st.session_state.gemini_client = None
            st.session_state.messages = []
        return

    api_key, error_msg = load_api_key_from_secrets(entered_password)

    if error_msg:
        st.session_state.api_key_configured = False
        st.session_state.current_api_key = None
        st.session_state.api_key_error_text = error_msg
        st.session_state.chat_session = None
        st.session_state.gemini_client = None
        st.session_state.messages = []
        return

    if st.session_state.get(
        "api_key_configured", False
    ) and st.session_state.get("current_api_key") == api_key:
        return

    try:
        st.session_state.api_key_configured = True
        st.session_state.current_api_key = api_key
        st.session_state.chat_session = None
        st.session_state.gemini_client = None
        st.session_state.messages = []
        st.toast("✅ API 키가 성공적으로 적용되었습니다! 새 대화를 시작합니다.")
    except Exception as e:
        st.session_state.api_key_configured = False
        st.session_state.current_api_key = None
        st.session_state.api_key_error_text = (
            f"API 키 적용 중 오류 발생: {type(e).__name__} - {e}"
        )
        st.session_state.chat_session = None
        st.session_state.gemini_client = None
        st.session_state.messages = []


def reset_chat_session_on_model_change():
    """모델 변경 시 세션 초기화 및 지시문 자동 적용 콜백"""
    st.session_state.chat_session = None
    st.session_state.gemini_client = None
    st.session_state.messages = []

    selected_model = st.session_state.selected_gemini_model

    # config에서 해당 기능의 prompt_file 확인
    prompt_text = get_prompt_for_feature(selected_model)
    if prompt_text:
        # prompt 파일이 매핑된 기능 → 자동 적용
        st.session_state.system_instructions = prompt_text
    else:
        # prompt 파일이 없는 기능 → 사용자 입력 지시문 복원
        st.session_state.system_instructions = st.session_state.get(
            "system_instructions_input", ""
        )
