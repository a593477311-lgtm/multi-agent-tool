import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

SILICONFLOW_API_KEY = os.getenv("siliconflow_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("siliconflow_BASE_URL", "https://api.siliconflow.cn/v1")

ALIYUN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
ALIYUN_BASE_URL = os.getenv("ALIYUN_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1")

_current_platform: str = "nvidia"

def set_platform(platform: str) -> None:
    global _current_platform
    _current_platform = platform

def get_platform() -> str:
    return _current_platform

def get_api_key() -> str:
    if _current_platform == "siliconflow":
        return SILICONFLOW_API_KEY
    if _current_platform == "aliyun":
        return ALIYUN_API_KEY
    return NVIDIA_API_KEY

def get_base_url() -> str:
    if _current_platform == "siliconflow":
        return SILICONFLOW_BASE_URL
    if _current_platform == "aliyun":
        return ALIYUN_BASE_URL
    return NVIDIA_BASE_URL

def validate_config() -> None:
    nvidia_key = NVIDIA_API_KEY.strip()
    siliconflow_key = SILICONFLOW_API_KEY.strip()
    aliyun_key = ALIYUN_API_KEY.strip()
    
    if not nvidia_key and not siliconflow_key and not aliyun_key:
        raise ValueError("请至少配置一个平台的 API Key:\n"
                       "  - NVIDIA_API_KEY\n"
                       "  - siliconflow_API_KEY\n"
                       "  - DASHSCOPE_API_KEY (阿里云)")
    
    if _current_platform == "nvidia" and not nvidia_key:
        raise ValueError("NVIDIA_API_KEY 未配置")
    
    if _current_platform == "siliconflow" and not siliconflow_key:
        raise ValueError("siliconflow_API_KEY 未配置")
    
    if _current_platform == "aliyun" and not aliyun_key:
        raise ValueError("DASHSCOPE_API_KEY 未配置")

_work_dir: Optional[Path] = None

def get_work_dir() -> Path:
    if _work_dir is None:
        return Path.cwd()
    return _work_dir

def set_work_dir(path: Path) -> None:
    global _work_dir
    _work_dir = path

def get_agent_data_dir() -> Path:
    return get_work_dir() / ".agent_data"

def get_sessions_dir() -> Path:
    return get_agent_data_dir() / "sessions"

def get_logs_dir() -> Path:
    return get_agent_data_dir() / "logs"

def get_knowledge_dir() -> Path:
    return get_agent_data_dir() / "knowledge"

MAX_CONTEXT_TOKENS = 128000
CONTEXT_COMPRESSION_THRESHOLD = 0.85
MAX_TURNS_BEFORE_COMPRESSION = 50

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

ENABLE_PREFIX_CACHE: bool = os.getenv("ENABLE_PREFIX_CACHE", "true").lower() == "true"
NIM_KV_CACHE_HOST_OFFLOAD: bool = os.getenv("NIM_KV_CACHE_HOST_OFFLOAD", "false").lower() == "true"
