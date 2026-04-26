import os
from dotenv import load_dotenv
import json

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_ENV_PATH)

siliconflow_apikey = os.getenv('SILICONFLOW_APIKEY')
tavily_apikey = os.getenv('Tavily_APIKEY')
deepseek_apikey = os.getenv('DeepSeek_APIKEY')

_raw_chat_system = os.getenv('SYSTEM_PROMPT') or os.getenv('system_prompt') or ''
chat_system_prompt = _raw_chat_system.strip()

def _env_strip(name: str) -> str | None:
    v = os.getenv(name)
    if v is None:
        return None
    return v.strip().rstrip(",")  # 防止 .env 里误加尾部逗号


model_name = _env_strip("MODEL_NAME")
model_provider = _env_strip("MODEL_PROVIDER")
base_url = _env_strip("BASE_URL")
api_key = _env_strip("API_KEY")
# API_KEY=某环境变量名 时解析为实际密钥
if api_key and not api_key.strip().lower().startswith("sk-") and os.getenv(api_key):
    api_key = os.getenv(api_key)
temperature = _env_strip("TEMPERATURE")

max_messages = os.getenv('MAX_MESSAGES') or 100

def _env_bool(name: str, default: str = "false") -> bool:
    v = (os.getenv(name) or default).strip().lower()
    return v in ("1", "true", "yes", "on")


# QBY 模式启动默认值；运行时可由 /qby 切换（见 llm_chat.qby_mode_active）
qby_model_default = _env_bool("qby_model", "false")

_raw_qby_system = os.getenv("QBY_SYSTEM_PROMPT") or os.getenv("qby_system_prompt") or ""
qby_system_prompt = _raw_qby_system.strip()

# 获取当前文件所在目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(CURRENT_DIR, "cookie.json")


def get_header():
    # 打开JSON文件并转换为字典（with语句自动关闭文件，避免资源泄漏）
    try:
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            headers = json.load(f)
        return headers
    except FileNotFoundError:
        # 如果 cookie.json 不存在，返回空字典
        print(f"Warning: cookie.json not found at {COOKIE_FILE}, returning empty headers")
        return {}
    except Exception as e:
        # 其他错误也返回空字典
        print(f"Warning: Error loading cookie.json: {e}, returning empty headers")
        return {}