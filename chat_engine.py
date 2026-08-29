# ====================================================================================
#  chat_engine.py - Gemini Interactions API 호출 (턴 컨텍스트 생성, 응답 처리)
#
#  - 매 턴 전체 히스토리를 재전송하지 않고 previous_interaction_id로 이전 턴을 이어받음
#  - system_instruction은 대화 이력과 달리 매 호출마다 다시 전달해야 함 (interaction-scoped)
#  - 체인이 만료/삭제되면 표시용 히스토리를 담아 stateless로 1회 재시도
# ====================================================================================

import io
import base64
import uuid

import streamlit as st
from google import genai
from PIL import Image

from config import (
    MODEL_OPTIONS,
    MODEL_NAME_MAP,
    get_feature,
    get_prompt_for_feature,
    logger,
)
from utils import (
    extract_interaction_outputs,
    get_field,
    is_invalid_previous_interaction_error,
)


class InteractionStreamError(Exception):
    """스트리밍 중 SSE error 이벤트로 전달된 오류"""

    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


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


def resolve_system_instruction(model_label: str) -> str | None:
    """이번 턴에 적용할 system instruction을 결정

    previous_interaction_id는 대화 이력만 이어받으므로,
    지시문은 매 호출마다 여기서 다시 계산해 전달한다.
    """
    prompt_text = get_prompt_for_feature(model_label)
    instructions = prompt_text if prompt_text else st.session_state.get(
        "system_instructions", ""
    )
    instructions = (instructions or "").strip()
    return instructions or None


def build_input_items(content_parts: list) -> list[dict]:
    """텍스트/PIL 이미지가 섞인 파트 목록을 Interactions input 블록 배열로 변환"""
    items = []
    for part in content_parts:
        if isinstance(part, Image.Image):
            image = part
            if image.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            items.append(
                {
                    "type": "image",
                    "mime_type": "image/png",
                    "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                }
            )
        else:
            text = part if isinstance(part, str) else str(part)
            if text:
                items.append({"type": "text", "text": text})
    return items


def build_history_steps(messages: list) -> list[dict]:
    """표시용 히스토리를 stateless 폴백용 Step 배열로 변환 (기존과 동일하게 텍스트만 전송)"""
    steps = []
    for msg in messages:
        content = msg.get("content", "")
        if not content:
            continue
        step_type = "model_output" if msg.get("role") == "assistant" else "user_input"
        steps.append(
            {"type": step_type, "content": [{"type": "text", "text": content}]}
        )
    return steps


def initialize_chat_session():
    """필요 시 턴 컨텍스트(클라이언트 + 모델 정보)를 초기화하고 반환

    이전의 client.chats 세션 객체 대신, 매 턴 interactions.create 호출에 필요한
    최소 정보만 담은 컨텍스트 dict를 st.session_state.chat_session에 보관한다.
    """
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

            client = genai.Client(api_key=api_key)
            st.session_state.gemini_client = client
            st.session_state.chat_session = {
                "client": client,
                "model_label": model_label,
                "model_name": model_name,
                "project_type": project_type,
            }
            st.session_state.active_project_type = project_type
            st.session_state.active_model_label = model_label
            logger.info(
                "chat_context_created project=%s model=%s", project_type, model_name
            )

        except Exception as error:
            st.session_state.chat_session = None
            st.session_state.gemini_client = None
            err_msg = f"모델 로딩 실패: {type(error).__name__} - {error}"
            st.error(err_msg, icon="💥")

    return st.session_state.get("chat_session")


def _create_interaction(
    client,
    *,
    model_name: str,
    input_payload,
    system_instruction: str | None,
    previous_interaction_id: str | None,
    stream: bool,
):
    """interactions.create 호출 래퍼 (store=True 유지)"""
    kwargs = {"model": model_name, "input": input_payload, "store": True}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if previous_interaction_id:
        kwargs["previous_interaction_id"] = previous_interaction_id
    if stream:
        kwargs["stream"] = True
    return client.interactions.create(**kwargs)


def _consume_stream(stream, placeholder) -> tuple[str, list, str | None]:
    """스트림 이벤트를 소비하며 텍스트를 점진 렌더링하고 최종 interaction id를 수집"""
    response_text = ""
    image_outputs = []
    interaction_id = None

    for event in stream:
        event_type = get_field(event, "event_type")
        if event_type == "step.delta":
            delta = get_field(event, "delta")
            delta_type = get_field(delta, "type") if delta is not None else None
            if delta_type == "text":
                chunk_text = get_field(delta, "text")
                if chunk_text:
                    response_text += chunk_text
                    placeholder.markdown(response_text + "▌")
            elif delta_type == "image":
                data = get_field(delta, "data")
                if data:
                    if isinstance(data, (bytes, bytearray)):
                        image_bytes = bytes(data)
                    else:
                        try:
                            image_bytes = base64.b64decode(data)
                        except Exception:
                            image_bytes = None
                    if image_bytes:
                        image_outputs.append(
                            (image_bytes, get_field(delta, "mime_type") or "image/png")
                        )
        elif event_type in ("interaction.created", "interaction.completed"):
            interaction = get_field(event, "interaction")
            new_id = get_field(interaction, "id") if interaction is not None else None
            if new_id:
                interaction_id = new_id
        elif event_type == "error":
            error = get_field(event, "error")
            code = get_field(error, "code") if error is not None else None
            message = get_field(error, "message") if error is not None else str(event)
            raise InteractionStreamError(code, message)

    response_text = response_text.strip()
    placeholder.markdown(response_text)
    return response_text, image_outputs, interaction_id


def send_chat_response(chat_context, content_parts: list, model_label: str) -> tuple[str, list]:
    """이번 턴의 입력만 Interactions API로 전송하고 응답을 처리

    이전 대화 맥락은 previous_interaction_id로 서버가 이어받으며,
    응답 후 최종 interaction id를 st.session_state.last_interaction_id에 저장한다.
    """
    feature = get_feature(model_label)
    is_image_model = feature.get("type") == "paid_only" and "image" in feature.get(
        "model", ""
    )

    client = chat_context["client"]
    model_name = chat_context["model_name"]
    project_type = chat_context.get(
        "project_type", st.session_state.get("active_project_type", "unknown")
    )
    system_instruction = resolve_system_instruction(model_label)
    input_items = build_input_items(content_parts)
    previous_id = st.session_state.get("last_interaction_id")

    request_id = uuid.uuid4().hex[:12]
    logger.info(
        "request_started request_id=%s project=%s model=%s previous_interaction_id=%s",
        request_id,
        project_type,
        model_name,
        previous_id or "-",
    )

    def _run(input_payload, prev_id) -> tuple[str, list, str | None]:
        if is_image_model:
            interaction = _create_interaction(
                client,
                model_name=model_name,
                input_payload=input_payload,
                system_instruction=system_instruction,
                previous_interaction_id=prev_id,
                stream=False,
            )
            text, images = extract_interaction_outputs(interaction)
            if text:
                st.markdown(text)
            return text, images, get_field(interaction, "id")

        stream = _create_interaction(
            client,
            model_name=model_name,
            input_payload=input_payload,
            system_instruction=system_instruction,
            previous_interaction_id=prev_id,
            stream=True,
        )
        placeholder = st.empty()
        return _consume_stream(stream, placeholder)

    try:
        response_text, response_images, interaction_id = _run(input_items, previous_id)
    except Exception as error:
        # 체인 끊김(보관 기간 경과/삭제 등) → id 리셋 후 표시용 히스토리를 담아 stateless로 1회 재시도
        if previous_id and is_invalid_previous_interaction_error(error):
            logger.warning(
                "previous_interaction_invalid request_id=%s previous_interaction_id=%s error=%s",
                request_id,
                previous_id,
                error,
            )
            st.session_state.last_interaction_id = None
            st.info("이전 대화 맥락이 만료되어 새로 이어갑니다.")
            # messages 마지막 항목은 이번 턴의 사용자 입력이므로 제외하고 이력 구성
            history_steps = build_history_steps(
                st.session_state.get("messages", [])[:-1]
            )
            stateless_payload = history_steps + [
                {"type": "user_input", "content": input_items}
            ]
            response_text, response_images, interaction_id = _run(
                stateless_payload, None
            )
        else:
            raise

    if interaction_id:
        st.session_state.last_interaction_id = interaction_id

    logger.info(
        "request_succeeded request_id=%s project=%s model=%s interaction_id=%s response_chars=%d",
        request_id,
        project_type,
        model_name,
        interaction_id or "-",
        len(response_text),
    )
    return response_text, response_images