import streamlit as st
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from google.generativeai.types import IncompleteIterationError

#====================================================================================================================
# 페이지 환경 설정
st.set_page_config(
    initial_sidebar_state="expanded",
    page_icon="./images/동동이.PNG",
    layout="centered",
    page_title="DongDongBot"
)

#====================================================================================================================
# --- 콜백 함수 정의 ---

def auto_apply_system_instructions_on_change():
    """System Instructions 입력값이 변경될 때 호출되는 콜백 함수"""
    new_instructions = st.session_state.get("system_instructions_input", "")
    st.session_state.system_instructions = new_instructions
    
    st.session_state.chat_session = None
    st.session_state.messages = []

    if new_instructions:
        st.toast("✅ System Instructions가 적용되었습니다. 새 대화를 시작합니다.")
    else:
        st.toast("ℹ️ System Instructions가 초기화되었습니다.")


def auto_apply_api_key_on_change():
    entered_api_key = st.session_state.get("gemini_api_key_input_sidebar", "")
    st.session_state.api_key_error_text = None
    if entered_api_key:
        if st.session_state.get("api_key_configured", False) and \
           st.session_state.get("current_api_key") == entered_api_key:
            return
        try:
            genai.configure(api_key=entered_api_key)
            st.session_state.api_key_configured = True
            st.session_state.current_api_key = entered_api_key
            st.session_state.chat_session = None
            st.session_state.messages = []
        except Exception as e:
            st.session_state.api_key_configured = False
            st.session_state.current_api_key = None
            st.session_state.api_key_error_text = f"API 키 적용 중 오류 발생: {type(e).__name__} - {e}"
            st.session_state.chat_session = None
            st.session_state.messages = []
    else:
        if st.session_state.get("api_key_configured", False) or st.session_state.get("current_api_key"):
            st.session_state.api_key_configured = False
            st.session_state.current_api_key = None
            st.session_state.chat_session = None
            st.session_state.messages = []

with st.sidebar:
    st.title("🔑 API 키 설정")
    st.text_input(
        "Gemini API 키:", type="password", placeholder="여기에 API 키를 붙여넣으세요.",
        help="API 키는 안전하게 보관하세요. 입력 시 자동으로 적용 시도됩니다.",
        key="gemini_api_key_input_sidebar", on_change=auto_apply_api_key_on_change
    )
    st.markdown("""
    <div style="text-align: right; font-size: small;">
        <a href="https://aistudio.google.com/app/apikey" target="_blank">API 키 발급받기</a>
    </div>
    """, unsafe_allow_html=True)
    
    st.title("📜 System Instructions")
    st.text_area(
        "동동봇의 역할, 말투, 행동 방침을 자유롭게 지시하세요",
        placeholder="예시: 너는 최고의 인공지능 선생님처럼 행동해. 모든 답변은 친절하고 상세하게 알려줘.",
        height=150,
        key="system_instructions_input",
        on_change=auto_apply_system_instructions_on_change
    )

    if st.session_state.get("api_key_configured", False):
        st.success("✅ API 키가 성공적으로 적용되었습니다!")
        st.info("새로운 대화를 시작할 수 있습니다.")
    else:
        error_message = st.session_state.get("api_key_error_text")
        if error_message:
            st.error(error_message)
            st.warning("올바른 API 키인지 확인하거나 새 키를 입력해주세요.")
        elif st.session_state.get("current_api_key") is None and \
             not st.session_state.get("gemini_api_key_input_sidebar", ""):
            st.warning("API 키를 입력해주세요.")

#====================================================================================================================
# --- 챗봇 모델 및 세션 설정 ---
MODEL_NAME = "gemini-1.5-flash-latest"
SAFETY_SETTINGS_NONE = {
    'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE', 'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE', 'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
}

#====================================================================================================================
# 채팅 세션 초기화 및 가져오기 함수
def initialize_chat_session():
    if st.session_state.get("api_key_configured", False):
        if "chat_session" not in st.session_state or st.session_state.chat_session is None:
            try:
                system_instructions = st.session_state.get("system_instructions", "")

                # [수정] system_instructions가 비어있지 않을 때만 파라미터로 전달
                if system_instructions and system_instructions.strip():
                    model = genai.GenerativeModel(
                        MODEL_NAME,
                        safety_settings=SAFETY_SETTINGS_NONE,
                        system_instruction=system_instructions
                    )
                else:
                    # system_instructions가 비어있으면 파라미터 없이 모델 생성
                    model = genai.GenerativeModel(
                        MODEL_NAME,
                        safety_settings=SAFETY_SETTINGS_NONE
                    )
                # [수정 끝]

                st.session_state.chat_session = model.start_chat(history=[])
            except Exception as e: 
                st.session_state.chat_session = None
                # [수정] ValueError를 처리하는 로직 추가
                err_type_msg = f"{type(e).__name__} - {e}"
                specific_user_msg = f"[모델 로딩 실패] {err_type_msg}."
                icon = "💥"
                if isinstance(e, google_exceptions.PermissionDenied):
                    specific_user_msg = f"[모델 로딩 실패] API 접근 권한 오류: {e}. 사이드바에서 유효한 API 키를 다시 입력해주세요."
                    st.session_state.api_key_configured = False
                    st.session_state.api_key_error_text = f"API 접근 권한 오류: {e}"
                    icon = "🚫"
                elif isinstance(e, google_exceptions.NotFound):
                    specific_user_msg = f"[모델 로딩 실패] 모델('{MODEL_NAME}')을 찾을 수 없습니다: {e}. 모델 이름을 확인해주세요."
                    icon = "🤷"
                elif isinstance(e, ValueError): # Gemini가 잘못된 인자값에 대해 ValueError를 발생시킴
                    specific_user_msg = f"[모델 로딩 실패] {err_type_msg}"
                    icon = "🚨"
                elif isinstance(e, google_exceptions.GoogleAPIError):
                    specific_user_msg = f"[모델 로딩 실패] Gemini API 오류: {e}. 잠시 후 다시 시도해주세요."
                    icon = "☁️"
                elif isinstance(e, AttributeError):
                     specific_user_msg = "API 키가 올바르게 설정되지 않은 것 같습니다. 사이드바에서 확인해주세요."
                st.error(specific_user_msg, icon=icon)
    else:
        st.session_state.chat_session = None
    return st.session_state.get("chat_session")

#====================================================================================================================
# --- Streamlit 앱 메인 인터페이스 (이하 코드는 변경 없음) ---
st.title("💬 동동봇과 대화하기")
if "messages" not in st.session_state: st.session_state.messages = []
# API 키가 적용된 후, 자동으로 initialize_chat_session이 호출됨
if st.session_state.get("api_key_configured"):
    chat = initialize_chat_session()

for message in st.session_state.messages:
    with st.chat_message(message["role"]): st.markdown(message["content"])

# --- 사용자 입력 및 챗봇 응답 처리 ---
if prompt := st.chat_input("무엇이 궁금하신가요?"):
    if not st.session_state.get("api_key_configured", False):
        st.error("⚠️ API 키가 설정되지 않았습니다. 사이드바에서 API 키를 먼저 적용해주세요."); st.stop()

    chat = st.session_state.get("chat_session") # 세션에서 chat 객체를 다시 가져옴
    if chat is None:
        chat = initialize_chat_session()
        if chat is None: st.error("⚠️ 동동봇을 시작할 수 없습니다. API 키, 모델, 네트워크를 확인해주세요."); st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            response_stream = chat.send_message(prompt, stream=True)
            
            streamed_text_parts = []

            def ui_text_stream_generator(response_stream_obj):
                for chunk in response_stream_obj:
                    text_part = ""
                    if chunk.parts:
                        for part in chunk.parts:
                            if hasattr(part, 'text') and part.text:
                                text_part += part.text
                    elif hasattr(chunk, 'text') and chunk.text:
                        text_part = chunk.text
                    
                    if text_part:
                        streamed_text_parts.append(text_part)
                        yield text_part
            
            st.write_stream(ui_text_stream_generator(response_stream))

            all_streamed_text = "".join(streamed_text_parts)

            if all_streamed_text:
                st.session_state.messages.append({"role": "assistant", "content": all_streamed_text})
            else: 
                try:
                    response_stream.resolve() 
                    
                    if response_stream.prompt_feedback and response_stream.prompt_feedback.block_reason:
                        block_reason_str = str(response_stream.prompt_feedback.block_reason).split('.')[-1]
                        error_message = f"⚠️ 요청 처리 불가 (프롬프트 차단: {block_reason_str}). 다른 질문을 시도해주세요."
                        st.warning(error_message)
                        st.session_state.messages.append({"role": "assistant", "content": error_message})

                    elif response_stream.candidates:
                        candidate = response_stream.candidates[0]
                        finish_reason_str = str(candidate.finish_reason).split('.')[-1].upper()
                        if finish_reason_str == "SAFETY":
                            error_message = f"⚠️ 콘텐츠 생성 중단 (안전 문제). 다른 질문을 시도해주세요."
                            st.warning(error_message)
                            st.session_state.messages.append({"role": "assistant", "content": error_message})
                        elif finish_reason_str in ["STOP", "MAX_TOKENS"]:
                            no_response_msg = "응답 내용이 없습니다."
                            st.info(no_response_msg)
                            st.session_state.messages.append({"role": "assistant", "content": no_response_msg})
                        else:
                            no_response_msg = f"응답을 생성하지 못했습니다 (사유: {finish_reason_str})."
                            st.info(no_response_msg)
                            st.session_state.messages.append({"role": "assistant", "content": no_response_msg})
                    else:
                        default_no_response_msg = "모델로부터 응답을 받지 못했습니다 (내용 없음)."
                        st.info(default_no_response_msg)
                        st.session_state.messages.append({"role": "assistant", "content": default_no_response_msg})

                except IncompleteIterationError as e_final_resolve:
                    err_msg = f"스트림 최종 처리 중 오류 (IncompleteIterationError): {e_final_resolve}."
                    st.error(err_msg, icon="🔄")
                    st.session_state.messages.append({"role": "assistant", "content": err_msg})
                except Exception as e_post_process:
                    err_msg_other = f"응답 후처리 중 오류: {type(e_post_process).__name__} - {e_post_process}"
                    st.error(err_msg_other, icon="🔥")
                    st.session_state.messages.append({"role": "assistant", "content": err_msg_other})
        
        except google_exceptions.GoogleAPIError as e:
            detailed_error_message = getattr(e, 'message', str(e))
            err_msg = f"API 오류 ({type(e).__name__}): {detailed_error_message}."
            icon = "☁️"
            if isinstance(e, google_exceptions.PermissionDenied): icon = "🚫"; st.session_state.api_key_configured = False; st.session_state.api_key_error_text = err_msg
            elif isinstance(e, google_exceptions.ResourceExhausted): icon = "ამო"
            elif isinstance(e, google_exceptions.InvalidArgument): icon = "🚨"
            elif isinstance(e, google_exceptions.FailedPrecondition): icon = "⚙️"
            elif isinstance(e, google_exceptions.DeadlineExceeded): icon = "⏱️"
            st.error(err_msg, icon=icon)
            st.session_state.messages.append({"role": "assistant", "content": err_msg})
        except IncompleteIterationError as e_incomplete:
            err_msg = f"스트림 처리 오류 (IncompleteIterationError): {e_incomplete}. 다시 시도해주세요."
            st.error(err_msg, icon="🔄")
            st.session_state.messages.append({"role": "assistant", "content": err_msg})
        except genai.types.BlockedPromptException as e:
            err_msg = "⚠️ 질문이 안전상의 이유로 처리될 수 없습니다. 다른 질문으로 시도해주세요."
            st.warning(err_msg)
            st.session_state.messages.append({"role": "assistant", "content": err_msg})
        except genai.types.StopCandidateException as e:
            st.info("응답 생성이 중간에 중단되었습니다.")
        except Exception as e:
            err_msg = f"예상치 못한 오류 ({type(e).__name__}): {e}. 관리자에게 문의해주세요."
            st.error(err_msg, icon="💥")
            st.session_state.messages.append({"role": "assistant", "content": f"오류 ({type(e).__name__})."})