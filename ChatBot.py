# ====================================================================================
#  Gemini AI 챗봇 (Streamlit) - 모델별 조건부 UI 및 API 키 분기 처리
# ====================================================================================

import streamlit as st
import streamlit.components.v1 as components
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai.types import IncompleteIterationError
import io
from PIL import Image
import fitz  # PyMuPDF
import re
from pathlib import Path
import html

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
    "프론트엔드 개발": "gemini-3.5-flash",               # 유료 모델 (프론트엔드 봇)
    "이미지 생성": "gemini-3.1-flash-image"              # 유료 모델 (이미지 봇)
}

# --- 초기 세션 상태 설정 ---
if "selected_gemini_model" not in st.session_state:
    st.session_state.selected_gemini_model = MODEL_OPTIONS[0]
if "system_instructions" not in st.session_state:
    st.session_state.system_instructions = ""

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
# 💡 width="large" 로 가로 폭을 늘리고, 마크다운 코드가 아닌 일반 텍스트로 렌더링하여 줄바꿈을 유도합니다.
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
            st.session_state.messages = []
        return

    api_key, error_msg = load_api_key_from_secrets(entered_password)
    
    if error_msg:
        st.session_state.api_key_configured = False
        st.session_state.current_api_key = None
        st.session_state.api_key_error_text = error_msg
        st.session_state.chat_session = None
        st.session_state.messages = []
        return
    
    if st.session_state.get("api_key_configured", False) and st.session_state.get("current_api_key") == api_key:
        return

    try:
        genai.configure(api_key=api_key)
        st.session_state.api_key_configured = True
        st.session_state.current_api_key = api_key
        st.session_state.chat_session = None
        st.session_state.messages = []
        st.toast("✅ API 키가 성공적으로 적용되었습니다! 새 대화를 시작합니다.")
    except Exception as e:
        st.session_state.api_key_configured = False
        st.session_state.current_api_key = None
        st.session_state.api_key_error_text = f"API 키 적용 중 오류 발생: {type(e).__name__} - {e}"
        st.session_state.chat_session = None
        st.session_state.messages = []

def reset_chat_session_on_model_change():
    """모델 변경 시 세션 초기화 및 지시문 자동 적용"""
    st.session_state.chat_session = None
    st.session_state.messages = []
    
    selected_model = st.session_state.selected_gemini_model
    if selected_model == "Gemini 3.1 Flash Lite":
        st.session_state.api_key_error_text = None
        # 입력된 기존 지시문 복원
        st.session_state.system_instructions = st.session_state.get("system_instructions_input", "")
    elif selected_model == "프론트엔드 개발":
        st.session_state.system_instructions = load_frontend_prompt()
    else: # 이미지 생성
        # 입력된 기존 지시문 복원
        st.session_state.system_instructions = st.session_state.get("system_instructions_input", "")

# --- 사이드바 UI 구성 ---
with st.sidebar:
    current_model = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    is_free_model = (current_model == "Gemini 3.1 Flash Lite")
        
    st.title("🔑 GEMINI 사용 키 설정")
    if is_free_model:
        holder="입력란 비활성화"
        tooltip="해당 모델은 GEMINI 사용 키 입력이 필요 없습니다."
    else:
        holder="GEMINI 사용 키를 입력하세요."
        tooltip="선생님께서 알려주신 GEMINI 사용 키를 입력해주세요."

    st.text_input(
        "Key:", type="password", placeholder=holder, 
        help=tooltip, 
        key="gemini_api_key_input_sidebar", 
        on_change=auto_apply_api_key_on_change,
        disabled=is_free_model 
    )

    if not is_free_model:
        if not st.session_state.get("api_key_configured", False):
            error_message = st.session_state.get("api_key_error_text")
            if error_message: 
                st.warning("올바른 GEMINI 사용 키인지 확인해주세요.")
            elif not st.session_state.get("gemini_api_key_input_sidebar", ""): 
                st.warning("GEMINI 사용 키를 입력해주세요.")

    st.title("📜 System Instructions")
    
    # 💡 모델에 따라 지시문 입력창(text_area)과 모달 버튼을 분기 처리
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
        st.subheader("💻 코드 다운로드")
        latest_html = extract_latest_html_code(st.session_state.get("messages", []))
        if latest_html:
            st.download_button(
                label="📥 HTML 코드 내려받기",
                data=latest_html,
                file_name="index.html",
                mime="text/html",
                use_container_width=True
            )
        else:
            st.button("📥 HTML 코드 내려받기", disabled=True, use_container_width=True, help="생성된 HTML 코드가 없습니다.")

# --- 챗봇 세션 설정 ---
SAFETY_SETTINGS_NONE = {
    'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
}

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

def initialize_chat_session():
    selected_model_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    is_free_model = (selected_model_label == "Gemini 3.1 Flash Lite")

    if is_free_model:
        default_key = st.secrets.get("default_api_key")
        if not default_key:
            st.error("⚠️ 서버(secrets.toml)에 무료 모델을 위한 'default_api_key'가 설정되지 않았습니다.")
            return None
        genai.configure(api_key=default_key)
    else:
        if not st.session_state.get("api_key_configured", False):
            return None
    
    if "chat_session" not in st.session_state or st.session_state.chat_session is None:
        try:
            system_instructions = st.session_state.get("system_instructions", "")
            model_kwargs = {"safety_settings": SAFETY_SETTINGS_NONE}
            if system_instructions and system_instructions.strip():
                model_kwargs["system_instruction"] = system_instructions
            
            model_name = MODEL_NAME_MAP.get(selected_model_label, MODEL_NAME_MAP[MODEL_OPTIONS[0]])
            model = genai.GenerativeModel(model_name, **model_kwargs)
            
            gemini_history = [
                {"role": "model" if msg["role"] == "assistant" else msg["role"], 
                 "parts": [msg["content"]]}
                for msg in st.session_state.get("messages", [])
            ]
            
            st.session_state.chat_session = model.start_chat(history=gemini_history)

        except Exception as e:
            st.session_state.chat_session = None
            err_msg = f"모델 로딩 실패: {type(e).__name__} - {e}"
            st.error(err_msg, icon="💥")
    
    return st.session_state.get("chat_session")

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
        if st.session_state.selected_gemini_model != "Gemini 3.1 Flash Lite":
            st.error("⚠️ 해당 기능을 사용하려면 사이드바에 사용 키를 먼저 입력해주세요.")
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
                selected_model_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
                is_image_model = (selected_model_label == "이미지 생성")

                if is_image_model:
                    response = chat.send_message(content_parts, stream=False)
                    response_text, response_images = extract_response_parts(response)
                    if response_text:
                        st.markdown(response_text)
                else:
                    response = chat.send_message(content_parts, stream=True)
                    response_text = ""
                    
                    message_placeholder = st.empty() 
                    
                    for chunk in response:
                        chunk_text = getattr(chunk, "text", None)
                        if chunk_text:
                            response_text += chunk_text
                            message_placeholder.markdown(response_text + "▌") 
                            
                    response_text = response_text.strip()
                    message_placeholder.markdown(response_text) 
                    
                    _, response_images = extract_response_parts(response)

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

            except (google_exceptions.GoogleAPIError, IncompleteIterationError, genai.types.BlockedPromptException, genai.types.StopCandidateException) as e:
                error_message = f"오류 발생 ({type(e).__name__}): {e}"
                st.error(error_message, icon="🚨")
                st.session_state.messages.append({"role": "assistant", "content": error_message})
            except Exception as e:
                error_message = f"예상치 못한 오류 발생: {type(e).__name__} - {e}"
                st.error(error_message, icon="💥")
                st.session_state.messages.append({"role": "assistant", "content": error_message})