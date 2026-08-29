# ====================================================================================
#  utils.py - 유틸리티 함수 (HTML 추출, 복사 버튼, 파일 처리, Interactions 응답 파싱)
# ====================================================================================

import re
import io
import html
import base64
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import fitz  # PyMuPDF

from config import logger


def extract_latest_html_code(messages: list) -> str | None:
    """채팅 히스토리에서 가장 최근 HTML 코드 블록을 추출"""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            matches = re.findall(
                r"```(?:html)?\s*[\r\n]+(.*?)```", content, re.DOTALL | re.IGNORECASE
            )
            for code in reversed(matches):
                code_stripped = code.strip()
                if "<html" in code_stripped.lower() or "<!doctype" in code_stripped.lower() or "</div>" in code_stripped.lower():
                    return code_stripped
            # 코드 블록 없이 HTML 태그로 직접 시작하는 경우
            stripped = content.strip()
            if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
                return stripped
    return None


def render_copy_button(text: str):
    """클립보드 복사 버튼을 HTML 컴포넌트로 렌더링"""
    textarea_value = html.escape(text)
    html_code = (
        ""
        '<div style="font-family: Arial, sans-serif; margin-bottom: 0.75rem;">'
        '    <button id="copyButton" style="padding: 0.5rem 0.9rem; border: 1px solid #2563eb; border-radius: 0.5rem; background: #2563eb; color: #ffffff; font-size: 0.95rem; cursor: pointer;">'
        "        📋 지시문 복사하기"
        "    </button>"
        '    <span id="copyStatus" style="margin-left: 0.75rem; color: #2563eb; font-size: 0.95rem;"></span>'
        '    <textarea id="copySource" style="position:absolute; left:-9999px; top:0;">'
        + textarea_value
        + "</textarea>"
        "</div>"
        "<script>"
        "    const button = document.getElementById('copyButton');"
        "    const status = document.getElementById('copyStatus');"
        "    const source = document.getElementById('copySource');"
        "    button.addEventListener('click', async () => {{"
        "        try {{"
        "            if (navigator.clipboard && navigator.clipboard.writeText) {{"
        "                await navigator.clipboard.writeText(source.value);"
        "            }} else {{"
        "                source.select();"
        "                document.execCommand('copy');"
        "            }}"
        "            status.innerText = '복사되었습니다.';"
        "        }} catch (error) {{"
        "            status.innerText = '복사에 실패했습니다.';"
        "        }}"
        "    }});"
        "</script>"
        ""
    )
    components.html(html_code, height=120)


def process_uploaded_files(staged_files: list) -> tuple[list, list[Image.Image], list[str]]:
    """
    업로드된 파일들을 처리하여 content_parts, 표시용 이미지, 파일명 목록을 반환

    Returns:
        (content_parts, pil_images_for_display, uploaded_filenames)
    """
    content_parts = []
    pil_images_for_display = []
    uploaded_filenames = []

    for uploaded_file in staged_files:
        uploaded_filenames.append(uploaded_file.name)
        uploaded_file.seek(0)

        if uploaded_file.type.startswith("image/"):
            try:
                image = Image.open(uploaded_file)
                content_parts.append(image)
                pil_images_for_display.append(image)
            except Exception as e:
                st.error(f"이미지 파일 '{uploaded_file.name}' 처리 중 오류: {e}")

        elif uploaded_file.type == "application/pdf":
            try:
                pdf_bytes = uploaded_file.read()
                pdf_text = "".join(
                    page.get_text()
                    for page in fitz.open(stream=pdf_bytes, filetype="pdf")
                )
                pdf_content = (
                    f"--- PDF 내용 시작: {uploaded_file.name} ---\n\n"
                    f"{pdf_text}\n\n"
                    f"--- PDF 내용 끝 ---"
                )
                content_parts.append(pdf_content)
            except Exception as e:
                st.error(f"PDF 파일 '{uploaded_file.name}' 처리 중 오류: {e}")

        elif uploaded_file.type == "text/html":
            try:
                html_bytes = uploaded_file.read()
                html_code = html_bytes.decode("utf-8")
                html_content = (
                    f"--- HTML 코드 시작: {uploaded_file.name} ---\n\n"
                    f"{html_code}\n\n"
                    f"--- HTML 코드 끝 ---"
                )
                content_parts.append(html_content)
            except Exception as e:
                st.error(f"HTML 파일 '{uploaded_file.name}' 처리 중 오류: {e}")

    return content_parts, pil_images_for_display, uploaded_filenames


def build_conversation_text(messages: list) -> str:
    """채팅 히스토리를 텍스트 형태로 변환"""
    lines = []
    for msg in messages:
        role = "선생님" if msg["role"] == "user" else "AI"
        content = msg.get("content", "")
        lines.append(f"[{role}]\n{content}")
    return "\n\n---\n\n".join(lines)


# ------------------------------------------------------------------------------------
#  Interactions API 응답 파싱 헬퍼
# ------------------------------------------------------------------------------------

def get_field(obj, name: str):
    """SDK 응답 객체(속성 접근)와 dict 모두에서 필드 값을 안전하게 조회"""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def is_invalid_previous_interaction_error(error) -> bool:
    """previous_interaction_id가 보관 기간 경과/삭제 등으로 무효할 때의 오류인지 판별"""
    code = None
    for attr in ("code", "status_code", "status"):
        value = getattr(error, attr, None)
        if value is not None:
            code = value
            break
    if code in (400, 404):
        return True
    text = f"{code} {error}".lower()
    return (
        "not_found" in text
        or "not found" in text
        or "previous_interaction" in text
    )


def extract_interaction_outputs(interaction) -> tuple[str, list]:
    """Interaction 응답의 model_output 스텝에서 텍스트와 이미지 데이터를 추출

    Returns:
        (text_output, image_outputs) — image_outputs는 (bytes, mime_type) 튜플 목록
    """
    text_parts: list[str] = []
    image_outputs: list[tuple[bytes, str]] = []

    for step in get_field(interaction, "steps") or []:
        if get_field(step, "type") != "model_output":
            continue
        for item in get_field(step, "content") or []:
            item_type = get_field(item, "type")
            if item_type == "text":
                text = get_field(item, "text")
                if text:
                    text_parts.append(text)
            elif item_type == "image":
                data = get_field(item, "data")
                if not data:
                    continue
                if isinstance(data, (bytes, bytearray)):
                    image_bytes = bytes(data)
                else:
                    try:
                        image_bytes = base64.b64decode(data)
                    except Exception:
                        continue
                image_outputs.append(
                    (image_bytes, get_field(item, "mime_type") or "image/png")
                )

    text_output = "\n".join(text_parts).strip()
    if not text_output:
        # 단순 텍스트 응답은 SDK 편의 속성으로도 확인
        text_output = (get_field(interaction, "output_text") or "").strip()
    return text_output, image_outputs


def summarize_conversation(
    messages: list,
    summarize_prompt: str,
    api_key: str,
    model_name: str,
    previous_interaction_id: str | None = None,
) -> tuple[str | None, str | None]:
    """
    대화 요약 HTML을 Interactions API로 생성

    previous_interaction_id가 있으면 서버측 대화 맥락에 요약 지시만 이어붙여 전송해
    대화 전문 재전송 없이 요약한다(토큰 절약). 체인이 없거나 만료된 경우에는
    대화 전문을 동봉해 stateless 방식으로 호출한다.
    요약 호출의 interaction id는 대화 체인에 저장하지 않으므로,
    이후 채팅 턴은 기존 대화 흐름을 그대로 이어간다.

    Returns:
        (html_code, error_message) — 성공 시 html_code, 실패 시 error_message
    """
    from google import genai

    if not messages:
        return None, "요약할 대화 내용이 없습니다."
    if not api_key:
        return None, "API 키가 없습니다. 사이드바에 키를 등록하거나 무료 키를 서버에 설정해주세요."

    chained_prompt = (
        f"{summarize_prompt}\n\n"
        f"# 지금까지 이 대화에서 나눈 전체 내용을 위 지시에 따라 정리해줘."
    )
    stateless_prompt = (
        f"{summarize_prompt}\n\n"
        f"# 아래는 지금까지의 대화 전체 기록입니다.\n\n"
        f"{build_conversation_text(messages)}"
    )

    try:
        client = genai.Client(api_key=api_key)
        interaction = None

        if previous_interaction_id:
            try:
                interaction = client.interactions.create(
                    model=model_name,
                    input=chained_prompt,
                    previous_interaction_id=previous_interaction_id,
                    store=True,
                )
            except Exception as chain_error:
                if is_invalid_previous_interaction_error(chain_error):
                    logger.warning(
                        "summary_chain_invalid previous_interaction_id=%s error=%s",
                        previous_interaction_id,
                        chain_error,
                    )
                    interaction = None  # 아래에서 stateless로 폴백
                else:
                    raise

        if interaction is None:
            interaction = client.interactions.create(
                model=model_name,
                input=stateless_prompt,
                store=True,
            )

        raw_text, _ = extract_interaction_outputs(interaction)
        # 응답에서 HTML 코드 블록 추출
        matches = re.findall(
            r"```html\n(.*?)\n```", raw_text, re.DOTALL | re.IGNORECASE
        )
        if matches:
            return matches[-1].strip(), None
        # 코드 블록 없이 HTML 태그가 직접 있는 경우도 허용
        if raw_text.strip().startswith("<!DOCTYPE") or raw_text.strip().startswith("<html"):
            return raw_text.strip(), None
        return None, "AI 응답에서 HTML 코드를 찾을 수 없습니다. 다시 시도해주세요."
    except Exception as e:
        return None, f"요약 생성 중 오류: {type(e).__name__} - {e}"