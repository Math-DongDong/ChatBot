# ====================================================================================
#  config.py - 상수, 모델 설정, prompt 설정 로딩
# ====================================================================================

import json
import logging
from pathlib import Path

# --- 경로 설정 ---
BASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = BASE_DIR / "prompt"
CONFIG_PATH = PROMPT_DIR / "prompts_config.json"

# --- 로깅 설정 ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dongdongbot")


def load_prompts_config() -> dict:
    """prompts_config.json 전체(용도별 모델 + 기능 목록)를 로딩"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("prompts_config.json 로딩 실패: %s", e)
        return {}


def load_prompt(filename: str) -> str:
    """prompt 폴더에서 지시문 파일 로딩"""
    prompt_path = PROMPT_DIR / filename
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("프롬프트 파일을 찾을 수 없습니다: %s", filename)
        return ""


# --- 설정 데이터 빌드 ---
CONFIG_DATA = load_prompts_config()

# 용도별 모델명 (free: 무료, paid: 유료, image: 이미지 생성)
MODELS = CONFIG_DATA.get("models", {})

FEATURES_CONFIG = CONFIG_DATA.get("features", [])

# 드롭다운에 표시할 기능 레이블 목록
MODEL_OPTIONS = [f["label"] for f in FEATURES_CONFIG]

# 레이블 → 기능 설정 전체 매핑 (빠른 접근용)
FEATURE_MAP = {f["label"]: f for f in FEATURES_CONFIG}


def get_feature(label: str) -> dict:
    """레이블로 기능 설정 조회, 없으면 기본 모델 설정 반환"""
    return FEATURE_MAP.get(label, FEATURE_MAP.get(MODEL_OPTIONS[0], {}))


def get_model_name(label: str, paid: bool) -> str:
    """기능과 유료 키 사용 여부에 맞는 모델명 반환 (model_role이 있으면 그 용도의 모델로 고정)"""
    feature = get_feature(label)
    if feature.get("type") == "free":
        paid = False
    role = feature.get("model_role") or ("paid" if paid else "free")
    return MODELS.get(role, MODELS.get("free", ""))


def get_prompt_for_feature(label: str) -> str:
    """기능에 매핑된 prompt 파일 내용을 반환"""
    feature = get_feature(label)
    prompt_file = feature.get("prompt_file")
    if prompt_file:
        return load_prompt(prompt_file)
    return ""
