# ====================================================================================
#  Gemini AI 챗봇 (Streamlit) - 모델별 조건부 UI 및 API 키 분기 처리
# ====================================================================================

import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
import io
import logging
from PIL import Image
import fitz  # PyMuPDF
import re
from pathlib import Path
import html
import uuid
import urllib.parse  # HTML 인코딩을 위해 추가

# --- 1. 페이지 기본 설정 ---
st.set_page_config(
    page_title="동동봇",
    page_icon="./images/동동이.PNG",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 시스템 지시문(Prompt) 로더 ---
def load_frontend_prompt():
    prompt_path = Path(__file__).resolve().parent / "prompt" / "Frontend.txt"
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

FRONTEND_DEV_PROMPT = load_frontend_prompt()

# --- 모델 설정 ---
MODEL_OPTIONS = ["Gemini 3.1 Flash Lite", "프론트엔드 개발", "이미지 생성"]
MODEL_NAME_MAP = {
    "Gemini 3.1 Flash Lite": "gemini-3.1-flash-lite",    # 무료/기본 모델
    "프론트엔드 개발": "gemini-3.6-flash",               # 키 등록 시 유료 모델
    "이미지 생성": "gemini-3.1-flash-image"              # 유료 모델 (이미지 봇)
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dongdongbot")

# --- 초기 세션 상태 설정 ---
if "selected_gemini_model" not in st.session_state:
    st.session_state.selected_gemini_model = MODEL_OPTIONS[0]
elif st.session_state.selected_gemini_model not in MODEL_OPTIONS:
    st.session_state.selected_gemini_model = MODEL_OPTIONS[0]
if "system_instructions" not in st.session_state:
    st.session_state.system_instructions = ""
if "gemini_client" not in st.session_state:
    st.session_state.gemini_client = None

# --- 유틸리티 함수 ---
def load_api_key_from_secrets(password):
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

def extract_latest_html_code(messages):
    for msg in reversed(messages):
        if msg["role"] == "assistant":
            matches = re.findall(r"```html\n(.*?)\n```", msg["content"], re.DOTALL | re.IGNORECASE)
            if matches:
                return matches[-1].strip()
    return None

def render_copy_button(text):
    textarea_value = html.escape(text)
    html_code = (
        ""
        "<div style=\"font-family: Arial, sans-serif; margin-bottom: 0.75rem;\">"
        "    <button id=\"copyButton\" style=\"padding: 0.5rem 0.9rem; border: 1px solid #2563eb; border-radius: 0.5rem; background: #2563eb; color: #ffffff; font-size: 0.95rem; cursor: pointer;\">"
        "        📋 지시문 복사하기"
        "    </button>"
        "    <span id=\"copyStatus\" style=\"margin-left: 0.75rem; color: #2563eb; font-size: 0.95rem;\"></span>"
        "    <textarea id=\"copySource\" style=\"position:absolute; left:-9999px; top:0;\">" + textarea_value + "</textarea>"
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

# --- 모달(Dialog) 창 설정 ---
@st.dialog("현재 적용된 System Instructions", width="large")
def show_system_instructions_modal():
    instructions = st.session_state.get("system_instructions", "")
    if instructions:
        st.markdown(instructions)
        render_copy_button(instructions)
    else:
        st.info("현재 모델에 적용된 특별한 지시문이 없습니다.")

# --- 콜백 함수 ---
def auto_apply_system_instructions_on_change():
    """사용자가 텍스트 영역에 지시문을 입력할 때 감지하는 함수"""
    new_instructions = st.session_state.get("system_instructions_input", "")
    st.session_state.system_instructions = new_instructions
    st.session_state.chat_session = None
    st.session_state.gemini_client = None
    if new_instructions:
        st.toast("✅ System Instructions가 변경되었습니다. 다음 메시지부터 적용됩니다.")
    else:
        st.toast("ℹ️ System Instructions가 초기화되었습니다.")

def auto_apply_api_key_on_change():
    entered_password = st.session_state.get("gemini_api_key_input_sidebar", "")
    st.session_state.api_key_error_text = None
    
    if not entered_password:
        if st.session_state.get("api_key_configured", False) or st.session_state.get("current_api_key"):
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
    
    if st.session_state.get("api_key_configured", False) and st.session_state.get("current_api_key") == api_key:
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
        st.session_state.api_key_error_text = f"API 키 적용 중 오류 발생: {type(e).__name__} - {e}"
        st.session_state.chat_session = None
        st.session_state.gemini_client = None
        st.session_state.messages = []

def reset_chat_session_on_model_change():
    """모델 변경 시 세션 초기화 및 지시문 자동 적용"""
    st.session_state.chat_session = None
    st.session_state.gemini_client = None
    st.session_state.messages = []
    
    selected_model = st.session_state.selected_gemini_model
    if selected_model == "프론트엔드 개발":
        st.session_state.system_instructions = load_frontend_prompt()
    else:
        # 입력된 기존 지시문 복원
        st.session_state.system_instructions = st.session_state.get("system_instructions_input", "")

# --- 사이드바 UI 구성 ---
with st.sidebar:
    current_model = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    is_free_model = current_model == "Gemini 3.1 Flash Lite"

    st.title("🔑 GEMINI 사용 키 설정")
    if is_free_model:
        holder = "입력란 비활성화 상태"
        tooltip = "무료 버전으로 운영됩니다."
    elif current_model == "이미지 생성":
        holder = "키 입력란"
        tooltip = "선생님께서 알려주신 GEMINI 사용 키를 입력해주세요."
    else:
        holder = "키 입력란"
        tooltip = "선생님께서 알려주신 GEMINI 사용 키를 입력해주세요."

    st.text_input(
        "Key:", type="password", placeholder=holder, 
        help=tooltip, 
        key="gemini_api_key_input_sidebar", 
        on_change=auto_apply_api_key_on_change,
        disabled=is_free_model,
    )

    if is_free_model:
        st.info("현재 Gemini 무료 모델을 통해 운영됩니다.")
    elif not st.session_state.get("api_key_configured", False):
        error_message = st.session_state.get("api_key_error_text")
        if error_message:
            st.warning("올바른 GEMINI 사용 키인지 확인해주세요.")
        elif current_model == "프론트엔드 개발":
            st.info("현재 Gemini 무료 모델을 통해 운영됩니다.")

    st.title("📜 System Instructions")
    
    if current_model == "프론트엔드 개발":
        if st.button("적용된 지시문 확인", use_container_width=True):
            show_system_instructions_modal()
    else:
        st.text_area(
            "동동봇의 역할, 말투, 행동 방침을 자유롭게 지시하세요", 
            placeholder="예시: 너는 최고의 인공지능 선생님처럼 행동해. 답변은 친절하고 상세하게 알려줘.", 
            height=150, 
            key="system_instructions_input", 
            on_change=auto_apply_system_instructions_on_change
        )
    
    st.title("📎 파일 첨부")
    st.file_uploader(
        "이미지, PDF, HTML 파일:", type=['png', 'jpg', 'jpeg', 'gif', 'pdf', 'html', 'htm'], 
        accept_multiple_files=True, key="uploaded_files_sidebar"
    )

    if current_model == "프론트엔드 개발":
        st.subheader("💻 코드 미리보기 및 다운로드")
        latest_html = extract_latest_html_code(st.session_state.get("messages", []))
        if latest_html:
            # 1. 새 창 렌더링을 위한 HTML 미리보기 버튼 (components.html 활용)
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
            ">🌐 HTML 코드 새창에서 미리보기</button>
            """
            components.html(preview_btn_html, height=50)

            # 2. 다운로드 버튼
            st.download_button(
                label="📥 HTML 코드 내려받기",
                data=latest_html,
                file_name="index.html",
                mime="text/html",
                use_container_width=True
            )
        else:
            # HTML 코드가 없을 때 비활성화된 버튼 표시
            st.button("🌐 HTML 코드 새창에서 미리보기", disabled=True, use_container_width=True)
            st.button("📥 HTML 코드 내려받기", disabled=True, use_container_width=True, help="생성된 HTML 코드가 없습니다.")

# --- 챗봇 세션 설정 ---
def extract_response_parts(response):
    text_output = []
    image_outputs = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if content is None: continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text: text_output.append(part_text)
            inline_data = getattr(part, "inline_data", None)
            if inline_data is not None and getattr(inline_data, "data", None):
                image_outputs.append((inline_data.data, getattr(inline_data, "mime_type", "image/png")))
    return "\n".join(text_output).strip(), image_outputs

def resolve_runtime_model():
    selected_model_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    paid_api_key = st.session_state.get("current_api_key")

    if selected_model_label == "프론트엔드 개발":
        if paid_api_key and st.session_state.get("api_key_configured", False):
            return "프론트엔드 개발", MODEL_NAME_MAP["프론트엔드 개발"], paid_api_key, "paid"
        return "Gemini 3.1 Flash Lite", MODEL_NAME_MAP["Gemini 3.1 Flash Lite"], st.secrets.get("default_api_key"), "free"

    if selected_model_label == "이미지 생성":
        if paid_api_key and st.session_state.get("api_key_configured", False):
            return "이미지 생성", MODEL_NAME_MAP["이미지 생성"], paid_api_key, "paid"
        return "이미지 생성", MODEL_NAME_MAP["이미지 생성"], None, "paid"

    return "Gemini 3.1 Flash Lite", MODEL_NAME_MAP["Gemini 3.1 Flash Lite"], st.secrets.get("default_api_key"), "free"

def create_chat_session(model_label, model_name, api_key, project_type, history_messages):
    if not api_key:
        return None, None

    system_instructions = (
        FRONTEND_DEV_PROMPT
        if model_label == "프론트엔드 개발"
        else st.session_state.get("system_instructions", "")
    )
    config = types.GenerateContentConfig(
        system_instruction=system_instructions if system_instructions.strip() else None
    )
    
    client = genai.Client(api_key=api_key)
    gemini_history = [
        types.Content(
            role="model" if msg["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=msg["content"])]
        )
        for msg in history_messages
    ]
    logger.info("chat_session_created project=%s model=%s", project_type, model_name)
    st.session_state.active_project_type = project_type
    st.session_state.active_model_label = model_label
    
    chat = client.chats.create(model=model_name, config=config, history=gemini_history)
    return client, chat

def initialize_chat_session():
    if "chat_session" not in st.session_state or st.session_state.chat_session is None:
        try:
            model_label, model_name, api_key, project_type = resolve_runtime_model()
            if not api_key:
                if model_label == "이미지 생성":
                    st.warning("이미지 생성을 사용하려면 GEMINI 사용 키를 등록해주세요.")
                else:
                    st.error("⚠️ 서버(secrets.toml)에 무료 모델용 'default_api_key'가 설정되지 않았습니다.")
                return None
                
            client, chat = create_chat_session(
                model_label, model_name, api_key, project_type,
                st.session_state.get("messages", [])
            )
            st.session_state.gemini_client = client
            st.session_state.chat_session = chat
            
        except Exception as error:
            st.session_state.chat_session = None
            st.session_state.gemini_client = None
            err_msg = f"모델 로딩 실패: {type(error).__name__} - {error}"
            st.error(err_msg, icon="💥")

    return st.session_state.get("chat_session")

def send_chat_response(chat, content_parts, model_label):
    is_image_model = model_label == "이미지 생성"
    request_id = uuid.uuid4().hex[:12]
    project_type = st.session_state.get("active_project_type", "unknown")
    model_name = MODEL_NAME_MAP.get(model_label, MODEL_NAME_MAP["Gemini 3.1 Flash Lite"])
    logger.info("request_started request_id=%s project=%s model=%s", request_id, project_type, model_name)
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
        request_id, project_type, model_name, len(response_text)
    )
    return response_text, response_images

# --- 메인 채팅 인터페이스 ---
col1, col2 = st.columns([4, 1])
with col1:
    st.title("💬 동동봇")
with col2:
    st.selectbox(
        "기능 선택",
        options=MODEL_OPTIONS,
        key="selected_gemini_model",
        help="사용할 봇의 기능을 선택하세요.",
        on_change=reset_chat_session_on_model_change
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

chat = initialize_chat_session()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("무엇이 궁금하신가요? (Shift+Enter로 줄바꿈)"):
    if not chat:
        if st.session_state.selected_gemini_model == "이미지 생성":
            st.error("⚠️ 이미지 생성을 사용하려면 사이드바에 사용 키를 먼저 입력해주세요.")
        else:
            st.error("⚠️ 무료 모델을 사용할 수 없습니다. 서버의 default_api_key를 확인해주세요.")
        st.stop()

    content_parts = [prompt]
    pil_images_for_display = []
    uploaded_filenames = []
    
    staged_files = st.session_state.get("uploaded_files_sidebar", [])
    if staged_files:
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
                    pdf_text = "".join(page.get_text() for page in fitz.open(stream=pdf_bytes, filetype="pdf"))
                    pdf_content = f"--- PDF 내용 시작: {uploaded_file.name} ---\n\n{pdf_text}\n\n--- PDF 내용 끝 ---"
                    content_parts.append(pdf_content)
                except Exception as e:
                    st.error(f"PDF 파일 '{uploaded_file.name}' 처리 중 오류: {e}")
            elif uploaded_file.type == "text/html":
                try:
                    html_bytes = uploaded_file.read()
                    html_code = html_bytes.decode('utf-8')
                    html_content = f"--- HTML 코드 시작: {uploaded_file.name} ---\n\n{html_code}\n\n--- HTML 코드 끝 ---"
                    content_parts.append(html_content)
                except Exception as e:
                    st.error(f"HTML 파일 '{uploaded_file.name}' 처리 중 오류: {e}")


    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        if pil_images_for_display:
            st.image(pil_images_for_display, width=100)
        if uploaded_filenames:
            file_info_str = ", ".join([f"'{f}'" for f in uploaded_filenames])
            st.info(f"📄 다음 파일과 함께 질문: {file_info_str}")

    with st.chat_message("assistant"):
        with st.spinner("동동봇 생각 중... 🤔"):
            try:
                selected_model_label = st.session_state.get(
                    "active_model_label", "Gemini 3.1 Flash Lite"
                )
                response_text, response_images = send_chat_response(
                    chat, content_parts, selected_model_label
                )

                if response_images:
                    for image_bytes, mime_type in response_images:
                        try:
                            st.image(Image.open(io.BytesIO(image_bytes)), use_container_width=True)
                        except Exception:
                            st.warning("이미지 응답을 표시하는 중 문제가 발생했습니다.")

                assistant_content = response_text if response_text else (
                    "이미지 응답이 생성되었습니다." if response_images else "⚠️ 응답 없음"
                )
                st.session_state.messages.append({"role": "assistant", "content": assistant_content})
                
                # 새로운 응답 후 HTML 버튼 상태 업데이트를 위해 페이지 재실행
                st.rerun()

            except Exception as error:
                request_id = uuid.uuid4().hex[:12]
                project_type = st.session_state.get("active_project_type", "unknown")
                model_name = MODEL_NAME_MAP.get(selected_model_label, "unknown")
                logger.exception(
                    "request_failed request_id=%s project=%s model=%s",
                    request_id, project_type, model_name
                )
                error_message = f"오류 발생 ({type(error).__name__}): {error}"
                st.error(error_message, icon="💥")
                st.session_state.messages.append({"role": "assistant", "content": error_message})
