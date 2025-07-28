# ====================================================================================
#  Gemini AI 챗봇 (Streamlit) - HTML 파일 처리 기능 추가 버전
# ====================================================================================
# 변경 사항:
# - HTML 파일('text/html')을 업로드하고 텍스트로 읽어 모델에 전달하는 기능 추가
# ====================================================================================

import streamlit as st
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai.types import IncompleteIterationError
import io
from PIL import Image
import fitz  # PyMuPDF

# --- 1. 페이지 기본 설정 ---
st.set_page_config(
    page_title="동동봇",
    page_icon="./images/동동이.PNG",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 2. 콜백 함수 정의 (변경 없음) ---
def auto_apply_system_instructions_on_change():
    new_instructions = st.session_state.get("system_instructions_input", "")
    st.session_state.system_instructions = new_instructions
    st.session_state.chat_session = None
    if new_instructions:
        st.toast("✅ System Instructions가 변경되었습니다. 다음 메시지부터 적용됩니다.")
    else:
        st.toast("ℹ️ System Instructions가 초기화되었습니다.")

def auto_apply_api_key_on_change():
    entered_api_key = st.session_state.get("gemini_api_key_input_sidebar", "")
    st.session_state.api_key_error_text = None
    
    if not entered_api_key:
        if st.session_state.get("api_key_configured", False) or st.session_state.get("current_api_key"):
            st.session_state.api_key_configured = False
            st.session_state.current_api_key = None
            st.session_state.chat_session = None
            st.session_state.messages = []
        return

    if st.session_state.get("api_key_configured", False) and st.session_state.get("current_api_key") == entered_api_key:
        return

    try:
        genai.configure(api_key=entered_api_key)
        st.session_state.api_key_configured = True
        st.session_state.current_api_key = entered_api_key
        st.session_state.chat_session = None
        st.session_state.messages = []
        st.toast("✅ API 키가 성공적으로 적용되었습니다! 새 대화를 시작합니다.")
    except Exception as e:
        st.session_state.api_key_configured = False
        st.session_state.current_api_key = None
        st.session_state.api_key_error_text = f"API 키 적용 중 오류 발생: {type(e).__name__} - {e}"
        st.session_state.chat_session = None
        st.session_state.messages = []


# --- 3. 사이드바 UI 구성 ---
with st.sidebar:
    if not st.session_state.get("api_key_configured", False):
        error_message = st.session_state.get("api_key_error_text")
        if error_message: 
            st.error(error_message)
            st.warning("올바른 API 키인지 확인하거나 새 키를 입력해주세요.")
        elif not st.session_state.get("gemini_api_key_input_sidebar", ""): 
            st.warning("API 키를 입력해주세요.")
        
    st.title("🔑 API 키 설정")
    st.text_input(
        "Gemini API 키:", type="password", placeholder="여기에 API 키를 붙여넣으세요.", 
        help="API 키는 안전하게 보관하세요. 입력 시 자동으로 적용됩니다.", 
        key="gemini_api_key_input_sidebar", on_change=auto_apply_api_key_on_change
    )
    st.markdown("""<div style="text-align: right; font-size: small;"><a href="https://aistudio.google.com/app/apikey" target="_blank">API 키 발급받기</a></div>""", unsafe_allow_html=True)
    
    st.title("📜 System Instructions")
    st.text_area(
        "동동봇의 역할, 말투, 행동 방침을 자유롭게 지시하세요", 
        placeholder="예시: 너는 최고의 인공지능 선생님처럼 행동해. 답변은 친절하고 상세하게 알려줘.", 
        height=150, key="system_instructions_input", on_change=auto_apply_system_instructions_on_change
    )
    
    st.title("📎 파일 첨부")
    # [수정] file_uploader의 type에 'html', 'htm'을 추가하여 HTML 파일을 업로드할 수 있게 합니다.
    st.file_uploader(
        "이미지, PDF, HTML 파일:", type=['png', 'jpg', 'jpeg', 'gif', 'pdf', 'html', 'htm'], 
        accept_multiple_files=True, key="uploaded_files_sidebar"
    )

# --- 4. 챗봇 모델 및 세션 설정 (변경 없음) ---
MODEL_NAME = "gemini-2.5-flash"
SAFETY_SETTINGS_NONE = {
    'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
}

def stream_handler(response_stream):
    for chunk in response_stream:
        if chunk.text:
            yield chunk.text

def initialize_chat_session():
    if not st.session_state.get("api_key_configured", False):
        return None
    
    if "chat_session" not in st.session_state or st.session_state.chat_session is None:
        try:
            system_instructions = st.session_state.get("system_instructions", "")
            model_kwargs = {"safety_settings": SAFETY_SETTINGS_NONE}
            if system_instructions and system_instructions.strip():
                model_kwargs["system_instruction"] = system_instructions
            
            model = genai.GenerativeModel(MODEL_NAME, **model_kwargs)
            
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

# --- 5. 메인 채팅 인터페이스 ---
st.title("💬 동동봇에게 물어보살")

if "messages" not in st.session_state:
    st.session_state.messages = []

chat = initialize_chat_session()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("무엇이 궁금하신가요? (Shift+Enter로 줄바꿈)"):
    if not chat:
        st.error("⚠️ API 키가 설정되지 않았습니다. 사이드바에서 API 키를 먼저 적용해주세요.")
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
            # [추가] HTML 파일 처리 로직
            elif uploaded_file.type == "text/html":
                try:
                    # 파일의 바이트 내용을 읽어 'utf-8'로 디코딩하여 문자열로 변환합니다.
                    html_bytes = uploaded_file.read()
                    html_code = html_bytes.decode('utf-8')
                    # 모델이 HTML 코드임을 명확히 알 수 있도록 구분자를 추가하여 전달합니다.
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
        with st.spinner("동동봇 생각 중... 🤔",show_time=True):
            try:
                response_stream = chat.send_message(content_parts, stream=True)
                response_text = st.write_stream(stream_handler(response_stream))
                
                if response_text:
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                else:
                    st.warning("모델로부터 응답을 받지 못했습니다. 안전 설정에 의해 차단되었을 수 있습니다.")
                    st.session_state.messages.append({"role": "assistant", "content": "⚠️ 응답 없음"})

            except (google_exceptions.GoogleAPIError, IncompleteIterationError, genai.types.BlockedPromptException, genai.types.StopCandidateException) as e:
                error_message = f"오류 발생 ({type(e).__name__}): {e}"
                st.error(error_message, icon="🚨")
                st.session_state.messages.append({"role": "assistant", "content": error_message})
            except Exception as e:
                error_message = f"예상치 못한 오류 발생: {type(e).__name__} - {e}"
                st.error(error_message, icon="💥")
                st.session_state.messages.append({"role": "assistant", "content": error_message})