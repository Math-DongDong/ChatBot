# ====================================================================================
#  ui_main.py - 메인 채팅 인터페이스 렌더링
# ====================================================================================

import io
import base64
import uuid
import streamlit as st
from PIL import Image

from config import MODEL_OPTIONS, MODEL_NAME_MAP, get_feature, logger
from callbacks import reset_chat_session_on_model_change
from chat_engine import initialize_chat_session, send_chat_response
from utils import process_uploaded_files


def _render_header():
    """타이틀 + 기능 선택 드롭다운 렌더링"""
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("💬 동동봇")
    with col2:
        st.selectbox(
            "기능 선택",
            options=MODEL_OPTIONS,
            key="selected_gemini_model",
            help="사용할 봇의 기능을 선택하세요.",
            on_change=reset_chat_session_on_model_change,
        )


def _render_initial_guide():
    """API 키 미등록 시 초기 안내 메시지 표시"""
    selected_model = st.session_state.selected_gemini_model
    feature = get_feature(selected_model)
    feature_type = feature.get("type", "free")

    # free 타입은 안내 불필요
    if feature_type == "free":
        return

    # API 키 등록 완료 또는 이미 메시지가 있으면 안내 불필요
    if st.session_state.api_key_configured or st.session_state.messages:
        return

    with st.chat_message("assistant", avatar="./images/동동이.PNG"):
        description = feature.get("description", "")
        if description:
            st.info(description)


def _render_chat_history():
    """채팅 히스토리 렌더링"""
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message.get("content", ""))
            if message.get("files"):
                st.caption(f"📎 첨부 파일: {', '.join(message['files'])}")
            if message["role"] == "assistant" and message.get("images"):
                for image_item in message["images"]:
                    try:
                        image_bytes = base64.b64decode(image_item["data"])
                        st.image(
                            Image.open(io.BytesIO(image_bytes)),
                            use_container_width=True,
                        )
                    except Exception:
                        st.warning("이미지 응답을 표시하는 중 문제가 발생했습니다.")


def _handle_user_input(chat):
    """사용자 입력 처리 및 응답 생성"""
    prompt = st.chat_input("무엇이 궁금하신가요? (Shift+Enter로 줄바꿈)")
    if not prompt:
        return

    if not chat:
        selected_model = st.session_state.selected_gemini_model
        feature = get_feature(selected_model)
        if feature.get("type") == "paid_only":
            st.error(
                "⚠️ 이 기능을 사용하려면 사이드바에 사용 키를 먼저 입력해주세요."
            )
        else:
            st.error(
                "⚠️ 무료 모델을 사용할 수 없습니다. 서버의 default_api_key를 확인해주세요."
            )
        st.stop()

    # 파일 처리
    content_parts = [prompt]
    pil_images_for_display = []
    uploaded_filenames = []

    staged_files = st.session_state.get("uploaded_files_sidebar", [])
    if staged_files:
        file_parts, pil_images_for_display, uploaded_filenames = (
            process_uploaded_files(staged_files)
        )
        content_parts.extend(file_parts)

    # 사용자 메시지 표시
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "files": uploaded_filenames}
    )
    with st.chat_message("user"):
        st.markdown(prompt)
        if pil_images_for_display:
            st.image(pil_images_for_display, width=100)
        if uploaded_filenames:
            file_info_str = ", ".join([f"'{f}'" for f in uploaded_filenames])
            st.info(f"📄 다음 파일과 함께 질문: {file_info_str}")

    # 어시스턴트 응답 생성
    with st.chat_message("assistant"):
        with st.spinner("동동봇 생각 중... 🤔"):
            try:
                selected_model_label = st.session_state.get(
                    "active_model_label", MODEL_OPTIONS[0] if MODEL_OPTIONS else ""
                )
                response_text, response_images = send_chat_response(
                    chat, content_parts, selected_model_label
                )

                assistant_content = response_text if response_text else (
                    "이미지 응답이 생성되었습니다."
                    if response_images
                    else "⚠️ 응답 없음"
                )
                message_payload = {
                    "role": "assistant",
                    "content": assistant_content,
                }

                if response_images:
                    encoded_images = []
                    for image_bytes, mime_type in response_images:
                        try:
                            encoded_images.append(
                                {
                                    "data": base64.b64encode(image_bytes).decode(
                                        "ascii"
                                    ),
                                    "mime_type": mime_type,
                                }
                            )
                        except Exception:
                            continue
                    if encoded_images:
                        message_payload["images"] = encoded_images

                st.session_state.messages.append(message_payload)

                if uploaded_filenames:
                    st.toast(
                        "📎 파일 업로드 완료! 사이드바에 업로드한 첨부파일을 비우세요.",
                        icon="ℹ️",
                    )

            except Exception as error:
                request_id = uuid.uuid4().hex[:12]
                project_type = st.session_state.get(
                    "active_project_type", "unknown"
                )
                model_name = MODEL_NAME_MAP.get(selected_model_label, "unknown")
                logger.exception(
                    "request_failed request_id=%s project=%s model=%s",
                    request_id,
                    project_type,
                    model_name,
                )
                error_message = (
                    f"오류 발생 ({type(error).__name__}): {error}"
                )
                st.error(error_message, icon="💥")
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_message}
                )


def render_main_chat():
    """메인 채팅 인터페이스 전체 렌더링"""
    _render_header()
    _render_initial_guide()

    chat = initialize_chat_session()

    _render_chat_history()
    _handle_user_input(chat)
