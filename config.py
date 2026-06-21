import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "zhiwen.db"
MATERIAL_DIR = DATA_DIR / "materials"
MATERIAL_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = DATA_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

API_HOST = "127.0.0.1"
API_PORT = 9721
WS_PATH = "/ws"

TASK_MAX_CONCURRENT = 4


class AIConfig:
    provider = os.getenv("ZHIWEN_AI_PROVIDER", "openai")
    api_key = os.getenv("ZHIWEN_AI_API_KEY", "")
    base_url = os.getenv("ZHIWEN_AI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("ZHIWEN_AI_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("ZHIWEN_AI_TEMPERATURE", "0.4"))
    max_tokens = int(os.getenv("ZHIWEN_AI_MAX_TOKENS", "2048"))
    timeout = float(os.getenv("ZHIWEN_AI_TIMEOUT", "60"))
    fallback_local = True


class GWFormatConfig:
    page_width_cm = 21.0
    page_height_cm = 29.7
    margin_top_cm = 3.7
    margin_bottom_cm = 3.5
    margin_left_cm = 2.8
    margin_right_cm = 2.6
    body_font_cn = "仿宋"
    body_font_size_pt = 16
    body_line_spacing_lines = 28.0
    heading1_font_cn = "方正小标宋简体"
    heading1_font_size_pt = 22
    heading2_font_cn = "黑体"
    heading2_font_size_pt = 16
    heading3_font_cn = "黑体"
    heading3_font_size_pt = 16
    page_number_font_cn = "宋体"
    page_number_font_size_pt = 14


APP_TITLE = "智文公文工作台"
APP_VERSION = "1.0.0"
ORG_NAME = "Zhiwen Studio"
