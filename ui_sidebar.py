# ====================================================================================
#  ui_sidebar.py - 사이드바 UI 렌더링
# ====================================================================================

import urllib.parse
import streamlit as st
import streamlit.components.v1 as components

from config import get_feature
from callbacks import (
    auto_apply_api_key_on_change,
    auto_apply_system_instructions_on_change,
)
from utils import extract_latest_html_code, render_copy_button


@st.dialog("현재 적용된 System Instructions", width="large")
def show_system_instructions_modal():
    """지시문 확인 모달 다이얼로그"""
    instructions = st.session_state.get("system_instructions", "")
    if instructions:
        st.markdown(instructions)
        render_copy_button(instructions)
    else:
        st.info("현재 모델에 적용된 특별한 지시문이 없습니다.")


def _render_api_key_section(current_model: str, feature: dict):
    """API 키 입력 섹션 렌더링"""
    feature_type = feature.get("type", "free")
    is_free_model = feature_type == "free"

    st.title("🔑 GEMINI 사용 키 설정")

    if is_free_model:
        holder = "입력란 비활성화 상태"
        tooltip = "무료 버전으로 운영됩니다."
    else:
        holder = "키 입력란"
        tooltip = "선생님께서 알려주신 GEMINI 사용 키를 입력해주세요."

    st.text_input(
        "Key:",
        type="password",
        placeholder=holder,
        help=tooltip,
        key="gemini_api_key_input_sidebar",
        on_change=auto_apply_api_key_on_change,
        disabled=is_free_model,
    )

    if is_free_model:
        st.info("현재 무료 버전 사용 중...")
    elif not st.session_state.get("api_key_configured", False):
        error_message = st.session_state.get("api_key_error_text")
        if error_message:
            st.warning("올바른 GEMINI 사용 키인지 확인해주세요.")
        elif feature_type == "paid_or_free":
            st.info("현재 무료 버전 사용 중...")


def _render_system_instructions_section(current_model: str, feature: dict):
    """System Instructions 섹션 렌더링"""
    st.title("📜 System Instructions")

    prompt_file = feature.get("prompt_file")
    if prompt_file:
        # prompt 파일이 매핑된 기능 → 확인 버튼만 표시
        if st.button("적용된 지시문 확인", use_container_width=True):
            show_system_instructions_modal()
    else:
        # prompt 파일 없는 기능 → 자유 입력 텍스트 영역
        st.text_area(
            "동동봇의 역할, 말투, 행동 방침을 자유롭게 지시하세요",
            placeholder="예시: 너는 최고의 인공지능 선생님처럼 행동해. 답변은 친절하고 상세하게 알려줘.",
            height=150,
            key="system_instructions_input",
            on_change=auto_apply_system_instructions_on_change,
        )


def _render_file_upload_section():
    """파일 첨부 섹션 렌더링"""
    st.title("📎 파일 첨부")
    st.file_uploader(
        "이미지, PDF, HTML 파일:",
        type=["png", "jpg", "jpeg", "gif", "pdf", "html", "htm"],
        accept_multiple_files=True,
        key="uploaded_files_sidebar",
    )


def _render_html_preview_section():
    """HTML 코드 미리보기 및 다운로드 섹션 렌더링"""
    st.subheader("💻 코드 미리보기 및 다운로드")
    latest_html = extract_latest_html_code(st.session_state.get("messages", []))

    if latest_html:
        # 새 창 렌더링을 위한 HTML 미리보기 버튼
        encoded_html = urllib.parse.quote(latest_html)
        preview_btn_html = f"""
        <style>
        .preview-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            padding: 0.5rem 0.75rem;
            background-color: #ffffff;
            color: #31333f;
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 0.5rem;
            font-family: "Source Sans Pro", sans-serif;
            font-size: 1rem;
            cursor: pointer;
            text-decoration: none;
            transition: border-color 0.15s, color 0.15s;
            box-sizing: border-box;
        }}
        .preview-btn:hover {{
            border-color: #FF4B4B;
            color: #FF4B4B;
        }}
        </style>
        <button class="preview-btn" onclick="
            const newWindow = window.open('', '_blank');
            if(newWindow) {{
                newWindow.document.write(decodeURIComponent('{encoded_html}'));
                newWindow.document.close();
            }} else {{
                alert('팝업이 차단되었습니다. 브라우저 설정에서 팝업을 허용해주세요.');
            }}
        ">🌐 HTML 코드 미리보기</button>
        """
        components.html(preview_btn_html, height=50)

        # 다운로드 버튼
        st.download_button(
            label="📥 HTML 코드 내려받기",
            data=latest_html,
            file_name="index.html",
            mime="text/html",
            use_container_width=True,
        )
    else:
        st.button(
            "🌐 HTML 코드 미리보기", disabled=True, use_container_width=True
        )
        st.button(
            "📥 HTML 코드 내려받기",
            disabled=True,
            use_container_width=True,
            help="생성된 HTML 코드가 없습니다.",
        )


def render_sidebar():
    """사이드바 전체 렌더링"""
    with st.sidebar:
        current_model = st.session_state.get("selected_gemini_model", "")
        feature = get_feature(current_model)

        _render_api_key_section(current_model, feature)
        _render_system_instructions_section(current_model, feature)
        _render_file_upload_section()

        # HTML 미리보기는 해당 기능에만 표시
        if feature.get("has_html_preview", False):
            _render_html_preview_section()
