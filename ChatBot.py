# ====================================================================================
#  Gemini AI 챗봇 (Streamlit) - HTML 파일 처리 & 로컬 저장소(채팅 기록 유지) 추가 버전
# ====================================================================================
import streamlit as st
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai.types import IncompleteIterationError
import io
from PIL import Image
import fitz  # PyMuPDF

# 💡 [추가] 브라우저 로컬 저장소 라이브러리 임포트
from streamlit_local_storage import LocalStorage 

# --- 1. 페이지 기본 설정 ---
st.set_page_config(
    page_title="동동봇",
    page_icon="./images/동동이.PNG",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 💡 [추가] 로컬 저장소 객체 생성
localS = LocalStorage()

# --- 1-1. Streamlit Secrets에서 API 키 로드 함수 ---
# 아래 secrets.toml 예시:
# [api_keys]
# nano_banana = "YOUR_NANO_BANANA_KEY"
# gemini_3_5_flash_lite = "YOUR_GEMINI_3_5_FLASH_LITE_KEY"
def get_secret_api_key(key_name):
    return st.secrets.get("api_keys", {}).get(key_name)

def validate_nano_banana_access_key(access_key):
    expected = st.secrets.get("api_keys", {}).get("nano_banana_access_key")
    if not expected or not access_key:
        return False
    return access_key.strip() == expected.strip()

def get_model_api_key(model_label):
    if model_label == "Nano Banana":
        access_key = st.session_state.get("nano_banana_access_key_input", "")
        if validate_nano_banana_access_key(access_key):
            return st.secrets.get("api_keys", {}).get("nano_banana_paid_api_key")
        return None
    if model_label == "Gemini 3.5 Flash Lite":
        return get_secret_api_key("gemini_3_5_flash_lite")
    return None

MODEL_OPTIONS = ["Nano Banana", "Gemini 3.5 Flash Lite"]
MODEL_NAME_MAP = {
    "Nano Banana": "gemini-2.5-flash-image",
    "Gemini 3.5 Flash Lite": "gemini-3.5-flash-lite"
}

# --- 2. 콜백 함수 정의 ---
def auto_apply_system_instructions_on_change():
    new_instructions = st.session_state.get("system_instructions_input", "")
    st.session_state.system_instructions = new_instructions
    st.session_state.chat_session = None
    if new_instructions:
        st.toast("✅ System Instructions가 변경되었습니다. 다음 메시지부터 적용됩니다.")
    else:
        st.toast("ℹ️ System Instructions가 초기화되었습니다.")

def reset_chat_session_on_model_change():
    st.session_state.chat_session = None
    # 모델 변경 시에도 기존 대화 내역은 유지하도록 messages 초기화 제거

# --- 3. 사이드바 UI 구성 ---
with st.sidebar:
    st.title("🔑 GEMINI API 키 설정")
    st.markdown(
        "각 모델은 서로 다른 API 키를 사용합니다. `Nano Banana`는 교사에게 받은 고유 키를 입력해야 하며, "
        "입력이 올바르면 secrets에서 유료 Gemini API 키를 가져옵니다. `Gemini 3.5 Flash Lite`는 "
        "별도 입력 없이 secrets에서 바로 로드됩니다."
    )
    st.caption(
        "secrets.toml에 `api_keys.nano_banana_access_key`, `api_keys.nano_banana_paid_api_key`, "
        "그리고 `api_keys.gemini_3_5_flash_lite`를 설정하세요."
    )

    selected_model = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
    if selected_model == "Nano Banana":
        st.text_input(
            "Nano Banana 사용 키", 
            type="password",
            placeholder="선생님이 알려준 고유 Nano Banana 키를 입력하세요.",
            key="nano_banana_access_key_input",
            on_change=reset_chat_session_on_model_change,
        )

        access_key = st.session_state.get("nano_banana_access_key_input", "")
        if access_key:
            if validate_nano_banana_access_key(access_key):
                secret_key = get_model_api_key(selected_model)
                if secret_key:
                    st.success("Nano Banana용 유료 Gemini API 키가 secrets에서 로드되었습니다.")
                else:
                    st.error("Nano Banana용 유료 Gemini API 키가 secrets에 없습니다.")
            else:
                st.error("Nano Banana 사용 키가 일치하지 않습니다.")
        else:
            st.info("Nano Banana를 사용할 때는 고유 사용 키를 입력해야 합니다.")
    else:
        secret_key = get_model_api_key(selected_model)
        if secret_key:
            st.success(f"{selected_model} API 키가 secrets에서 로드되었습니다.")
        else:
            st.error(f"{selected_model} API 키가 secrets에 없습니다.")

    st.title("📜 System Instructions")
    st.text_area(
        "동동봇의 역할, 말투, 행동 방침을 자유롭게 지시하세요", 
        placeholder="예시: 너는 최고의 인공지능 선생님처럼 행동해. 답변은 친절하고 상세하게 알려줘.", 
        height=150, key="system_instructions_input", on_change=auto_apply_system_instructions_on_change
    )
    
    st.title("📎 파일 첨부")
    st.file_uploader(
        "이미지, PDF, HTML 파일:", type=['png', 'jpg', 'jpeg', 'gif', 'pdf', 'html', 'htm'], 
        accept_multiple_files=True, key="uploaded_files_sidebar"
    )

    # 💡 [추가] 파일 첨부 아래에 '대화 기록 초기화' 버튼 생성
    st.divider()
    if st.button("🗑️ 대화 기록 초기화", type="primary", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_session = None
        localS.deleteItem("dongdong_chat_history") # 로컬 저장소 캐시 삭제
        st.toast("✅ 대화 기록이 모두 초기화되었습니다.")
        st.rerun()


SAFETY_SETTINGS_NONE = {
    'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
}

def stream_handler(response_stream):
    for chunk in response_stream:
        if getattr(chunk, "text", None):
            yield chunk.text

def extract_response_parts(response):
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
                image_outputs.append((inline_data.data, getattr(inline_data, "mime_type", "image/png")))
    return "\n".join(text_output).strip(), image_outputs

def initialize_chat_session():
    if "chat_session" not in st.session_state or st.session_state.chat_session is None:
        try:
            system_instructions = st.session_state.get("system_instructions", "")
            model_kwargs = {"safety_settings": SAFETY_SETTINGS_NONE}
            if system_instructions and system_instructions.strip():
                model_kwargs["system_instruction"] = system_instructions
            
            selected_model_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
            api_key = get_model_api_key(selected_model_label)
            if not api_key:
                st.error(f"선택된 모델({selected_model_label})의 API 키가 설정되지 않았습니다.")
                return None

            genai.configure(api_key=api_key)
            model_name = MODEL_NAME_MAP.get(selected_model_label, MODEL_NAME_MAP[MODEL_OPTIONS[0]])
            model = genai.GenerativeModel(model_name, **model_kwargs)
            
            # 기존 대화 내역이 있다면 Gemini 모델에 주입하여 기억하게 만듭니다.
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


# 💡 [추가] 앱 시작 시 로컬 저장소에서 대화 기록 불러오기
if "messages" not in st.session_state:
    saved_history = localS.getItem("dongdong_chat_history")
    
    # 로컬 저장소에 저장된 리스트가 존재하면 그대로 복구
    if saved_history and isinstance(saved_history, list):
        st.session_state.messages = saved_history
    else:
        st.session_state.messages = []


# --- 5. 메인 채팅 인터페이스 ---
col1, col2 = st.columns([4, 1])
with col1:
    st.title("💬 동동봇")
with col2:
    st.selectbox(
        "모델 선택",
        options=MODEL_OPTIONS,
        key="selected_gemini_model",
        help="Gemini 모델을 선택하세요.",
        on_change=reset_chat_session_on_model_change
    )

chat = initialize_chat_session()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("무엇이 궁금하신가요? (Shift+Enter로 줄바꿈)"):
    if not chat:
        st.error("⚠️ GEMINI 사용 키가 설정되지 않았습니다. 사이드바에서 사용 키를 먼저 적용해주세요.")
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

    # 유저의 메시지 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    # 💡 [추가] 메시지가 추가될 때마다 로컬 저장소 덮어쓰기 (업데이트)
    localS.setItem("dongdong_chat_history", st.session_state.messages)

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
                selected_model_label = st.session_state.get("selected_gemini_model", MODEL_OPTIONS[0])
                is_image_model = selected_model_label == "Nano Banana"

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
                
                # 어시스턴트의 메시지 저장
                st.session_state.messages.append({"role": "assistant", "content": assistant_content})
                # 💡 [추가] 메시지가 추가될 때마다 로컬 저장소 덮어쓰기 (업데이트)
                localS.setItem("dongdong_chat_history", st.session_state.messages)

            except (google_exceptions.GoogleAPIError, IncompleteIterationError, genai.types.BlockedPromptException, genai.types.StopCandidateException) as e:
                error_message = f"오류 발생 ({type(e).__name__}): {e}"
                st.error(error_message, icon="🚨")
                st.session_state.messages.append({"role": "assistant", "content": error_message})
            except Exception as e:
                error_message = f"예상치 못한 오류 발생: {type(e).__name__} - {e}"
                st.error(error_message, icon="💥")
                st.session_state.messages.append({"role": "assistant", "content": error_message})