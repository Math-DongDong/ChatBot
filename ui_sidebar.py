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
from config import load_prompt
from utils import extract_latest_html_code, render_copy_button, summarize_conversation


def get_preview_html_source(messages: list, summary_html: str | None = None) -> str | None:
    """미리보기 대상 HTML을 우선순위에 따라 반환한다."""
    if summary_html and summary_html.strip():
        return summary_html.strip()
    return extract_latest_html_code(messages)


def has_summary_content(messages: list) -> bool:
    """요약 버튼이 활성화될 수 있는지 판단한다. (항상 활성화)"""
    return True


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
    messages = st.session_state.get("messages", [])
    preview_html = get_preview_html_source(messages, st.session_state.get("summary_html"))

    if preview_html:
        encoded_html = urllib.parse.quote(preview_html)
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

        download_label = "📥 대화 내용 HTML 내려받기" if st.session_state.get("summary_html") else "📥 HTML 코드 내려받기"
        download_filename = "대화_요약.html" if st.session_state.get("summary_html") else "index.html"
        st.download_button(
            label=download_label,
            data=preview_html,
            file_name=download_filename,
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


def _render_summary_export_section(feature: dict):
    """대화내용 요약 → 미리보기 → 다운로드 버튼을 순서대로 렌더링"""
    from config import MODEL_NAME_MAP, MODEL_OPTIONS

    st.subheader("📄 대화내용 요약하기")

    messages = st.session_state.get("messages", [])
    has_messages = has_summary_content(messages)
    summary_html = st.session_state.get("summary_html")

    if st.button(
        "✨ 대화 내용 HTML로 요약하기",
        use_container_width=True,
    ):
        summarize_prompt_file = feature.get("summarize_prompt_file", "")
        summarize_prompt = load_prompt(summarize_prompt_file) if summarize_prompt_file else ""

        if not summarize_prompt:
            st.error("요약 지시문 파일을 찾을 수 없습니다.")
        else:
            api_key = (
                st.session_state.get("current_api_key")
                if st.session_state.get("api_key_configured", False)
                else st.secrets.get("default_api_key")
            )
            selected_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
            if st.session_state.get("api_key_configured", False):
                model_name = MODEL_NAME_MAP.get(selected_label, MODEL_NAME_MAP.get(MODEL_OPTIONS[0], ""))
            else:
                model_name = MODEL_NAME_MAP.get(MODEL_OPTIONS[0], "")

            with st.spinner("AI가 대화 내용을 분석하여 HTML 문서를 생성 중입니다... ⏳"):
                html_code, error_msg = summarize_conversation(
                    messages=messages,
                    summarize_prompt=summarize_prompt,
                    api_key=api_key,
                    model_name=model_name,
                )

            if error_msg:
                st.error(f"요약 실패: {error_msg}")
            else:
                st.session_state.summary_html = html_code
                st.success("HTML 문서가 생성되었습니다! 아래에서 확인하고 내려받을 수 있습니다.")

    summary_html = st.session_state.get("summary_html")
    if summary_html:
        encoded_html = urllib.parse.quote(summary_html)
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
        ">🌐 대화 내용 HTML 미리보기</button>
        """
        components.html(preview_btn_html, height=50)

        st.download_button(
            label="📥 대화 내용 HTML 내려받기",
            data=summary_html,
            file_name="대화_요약.html",
            mime="text/html",
            use_container_width=True,
        )
    else:
        st.button(
            "🌐 대화 내용 HTML 미리보기",
            disabled=True,
            use_container_width=True,
            help="요약 버튼을 먼저 눌러주세요.",
        )
        st.button(
            "📥 대화 내용 HTML 내려받기",
            disabled=True,
            use_container_width=True,
            help="요약 버튼을 먼저 눌러주세요.",
        )


def render_sidebar():
    """사이드바 전체 렌더링"""
    with st.sidebar:
        current_model = st.session_state.get("selected_gemini_model", "")
        feature = get_feature(current_model)

        _render_api_key_section(current_model, feature)
        _render_system_instructions_section(current_model, feature)
        _render_file_upload_section()

        # 프론트엔드 개발 기능은 별도 HTML 미리보기 섹션을 유지
        if feature.get("has_html_preview", False) and not feature.get("has_summary_export", False):
            _render_html_preview_section()

        # 대화 요약 내보내기는 수학수업 기능에서 요약/미리보기/다운로드를 연속 배치
        if feature.get("has_summary_export", False):
            _render_summary_export_section(feature)
