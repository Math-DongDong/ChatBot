# ====================================================================================
#  chat_engine.py - Gemini 채팅 세션 생성, 응답 처리
# ====================================================================================

import uuid
import streamlit as st
from google import genai
from google.genai import types

from config import (
    MODEL_OPTIONS,
    MODEL_NAME_MAP,
    get_feature,
    get_prompt_for_feature,
    logger,
)


def extract_response_parts(response) -> tuple[str, list]:
    """응답에서 텍스트와 이미지 데이터를 추출"""
    text_output = []
    image_outputs = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                text_output.append(part_text)
            inline_data = getattr(part, "inline_data", None)
            if inline_data is not None and getattr(inline_data, "data", None):
                image_outputs.append(
                    (inline_data.data, getattr(inline_data, "mime_type", "image/png"))
                )
    return "\n".join(text_output).strip(), image_outputs


def resolve_runtime_model() -> tuple[str, str, str | None, str]:
    """
    현재 선택된 모델과 API 키 상태에 따라 실제 사용할 모델 정보를 결정

    Returns:
        (model_label, model_name, api_key, project_type)
    """
    selected_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    paid_api_key = st.session_state.get("current_api_key")
    feature = get_feature(selected_label)
    feature_type = feature.get("type", "free")

    if feature_type == "paid_or_free":
        if paid_api_key and st.session_state.get("api_key_configured", False):
            return selected_label, MODEL_NAME_MAP[selected_label], paid_api_key, "paid"
        # 유료키 없으면 무료 모델로 폴백
        free_label = MODEL_OPTIONS[0]
        return (
            free_label,
            MODEL_NAME_MAP[free_label],
            st.secrets.get("default_api_key"),
            "free",
        )

    if feature_type == "paid_only":
        if paid_api_key and st.session_state.get("api_key_configured", False):
            return selected_label, MODEL_NAME_MAP[selected_label], paid_api_key, "paid"
        return selected_label, MODEL_NAME_MAP[selected_label], None, "paid"

    # free 타입
    free_label = MODEL_OPTIONS[0]
    return (
        free_label,
        MODEL_NAME_MAP[free_label],
        st.secrets.get("default_api_key"),
        "free",
    )


def create_chat_session(
    model_label: str,
    model_name: str,
    api_key: str,
    project_type: str,
    history_messages: list,
):
    """Gemini 채팅 세션을 생성"""
    if not api_key:
        return None, None

    # config 기반으로 지시문 결정
    prompt_text = get_prompt_for_feature(model_label)
    system_instructions = (
        prompt_text if prompt_text else st.session_state.get("system_instructions", "")
    )

    config = types.GenerateContentConfig(
        system_instruction=system_instructions if system_instructions.strip() else None
    )

    client = genai.Client(api_key=api_key)
    gemini_history = [
        types.Content(
            role="model" if msg["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=msg["content"])],
        )
        for msg in history_messages
    ]
    logger.info(
        "chat_session_created project=%s model=%s", project_type, model_name
    )
    st.session_state.active_project_type = project_type
    st.session_state.active_model_label = model_label

    chat = client.chats.create(
        model=model_name, config=config, history=gemini_history
    )
    return client, chat


def initialize_chat_session():
    """필요 시 채팅 세션을 초기화하고 반환"""
    if (
        "chat_session" not in st.session_state
        or st.session_state.chat_session is None
    ):
        try:
            model_label, model_name, api_key, project_type = resolve_runtime_model()
            if not api_key:
                feature = get_feature(model_label)
                if feature.get("type") != "paid_only":
                    st.error(
                        "⚠️ 서버(secrets.toml)에 무료 모델용 'default_api_key'가 설정되지 않았습니다."
                    )
                return None

            client, chat = create_chat_session(
                model_label,
                model_name,
                api_key,
                project_type,
                st.session_state.get("messages", []),
            )
            st.session_state.gemini_client = client
            st.session_state.chat_session = chat

        except Exception as error:
            st.session_state.chat_session = None
            st.session_state.gemini_client = None
            err_msg = f"모델 로딩 실패: {type(error).__name__} - {error}"
            st.error(err_msg, icon="💥")

    return st.session_state.get("chat_session")


def send_chat_response(chat, content_parts: list, model_label: str) -> tuple[str, list]:
    """채팅 메시지를 전송하고 응답을 처리"""
    feature = get_feature(model_label)
    is_image_model = feature.get("type") == "paid_only" and "image" in feature.get("model", "")

    request_id = uuid.uuid4().hex[:12]
    project_type = st.session_state.get("active_project_type", "unknown")
    model_name = MODEL_NAME_MAP.get(model_label, MODEL_NAME_MAP.get(MODEL_OPTIONS[0], ""))
    logger.info(
        "request_started request_id=%s project=%s model=%s",
        request_id,
        project_type,
        model_name,
    )

    response = (
        chat.send_message(message=content_parts)
        if is_image_model
        else chat.send_message_stream(message=content_parts)
    )

    response_text = ""
    response_images = []

    if is_image_model:
        response_text, response_images = extract_response_parts(response)
        if response_text:
            st.markdown(response_text)
    else:
        message_placeholder = st.empty()
        for chunk in response:
            chunk_text = chunk.text
            if chunk_text:
                response_text += chunk_text
                message_placeholder.markdown(response_text + "▌")
        response_text = response_text.strip()
        message_placeholder.markdown(response_text)
        _, response_images = extract_response_parts(response)

    logger.info(
        "request_succeeded request_id=%s project=%s model=%s response_chars=%d",
        request_id,
        project_type,
        model_name,
        len(response_text),
    )
    return response_text, response_images
