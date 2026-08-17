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


def load_prompts_config() -> list[dict]:
    """prompts_config.json에서 기능 목록을 로딩"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("features", [])
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("prompts_config.json 로딩 실패: %s", e)
        return []


def load_prompt(filename: str) -> str:
    """prompt 폴더에서 지시문 파일 로딩"""
    prompt_path = PROMPT_DIR / filename
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("프롬프트 파일을 찾을 수 없습니다: %s", filename)
        return ""


# --- 설정 데이터 빌드 ---
FEATURES_CONFIG = load_prompts_config()

# 드롭다운에 표시할 기능 레이블 목록
MODEL_OPTIONS = [f["label"] for f in FEATURES_CONFIG]

# 레이블 → 실제 모델명 매핑
MODEL_NAME_MAP = {f["label"]: f["model"] for f in FEATURES_CONFIG}

# 레이블 → 기능 설정 전체 매핑 (빠른 접근용)
FEATURE_MAP = {f["label"]: f for f in FEATURES_CONFIG}


def get_feature(label: str) -> dict:
    """레이블로 기능 설정 조회, 없으면 기본 모델 설정 반환"""
    return FEATURE_MAP.get(label, FEATURE_MAP.get(MODEL_OPTIONS[0], {}))


def get_prompt_for_feature(label: str) -> str:
    """기능에 매핑된 prompt 파일 내용을 반환"""
    feature = get_feature(label)
    prompt_file = feature.get("prompt_file")
    if prompt_file:
        return load_prompt(prompt_file)
    return ""
