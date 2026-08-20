# ====================================================================================
#  utils.py - 유틸리티 함수 (HTML 추출, 복사 버튼, 파일 처리)
# ====================================================================================

import re
import io
import html
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import fitz  # PyMuPDF


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


def summarize_conversation(
    messages: list,
    summarize_prompt: str,
    api_key: str,
    model_name: str,
) -> tuple[str | None, str | None]:
    """
    대화 히스토리 + summarize 프롬프트를 Gemini API에 단발성 전송하여 HTML 코드를 반환

    Returns:
        (html_code, error_message) — 성공 시 html_code, 실패 시 error_message
    """
    from google import genai
    from google.genai import types as genai_types

    if not messages:
        return None, "요약할 대화 내용이 없습니다."
    if not api_key:
        return None, "API 키가 없습니다. 사이드바에 키를 등록하거나 무료 키를 서버에 설정해주세요."

    conversation_text = build_conversation_text(messages)
    full_prompt = (
        f"{summarize_prompt}\n\n"
        f"# 아래는 지금까지의 대화 전체 기록입니다.\n\n"
        f"{conversation_text}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=None
            ),
        )
        raw_text = response.text or ""
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
