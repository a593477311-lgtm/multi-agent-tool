from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import os

NVIDIA_PRICE = {"input": 0.0, "output": 0.0}
SILICONFLOW_PRICE = {"input": 2.0, "output": 3.0}
ALIYUN_PRICE = {"input": 0.0, "output": 0.0}
DEFAULT_PRICE = {"input": 2.0, "output": 3.0}

PLATFORM_PRICES = {
    "nvidia": NVIDIA_PRICE,
    "siliconflow": SILICONFLOW_PRICE,
    "aliyun": ALIYUN_PRICE,
}


def get_model_price(model_id: str) -> Dict[str, float]:
    env_input = os.getenv("MODEL_PRICE_INPUT")
    env_output = os.getenv("MODEL_PRICE_OUTPUT")
    
    if env_input is not None and env_output is not None:
        try:
            return {
                "input": float(env_input),
                "output": float(env_output)
            }
        except ValueError:
            pass
    
    from .settings import get_platform
    platform = get_platform()
    
    if platform in PLATFORM_PRICES:
        return PLATFORM_PRICES[platform].copy()
    
    return DEFAULT_PRICE.copy()

@dataclass
class ModelConfig:
    model_id: str
    display_name: str
    provider: str
    supports_thinking: bool = True
    thinking_config: Dict[str, Any] = field(default_factory=dict)
    disable_thinking_config: Dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 8192
    temperature: float = 1.0
    top_p: float = 0.95
    
    def get_extra_body(self, enable_thinking: bool = False) -> Optional[Dict[str, Any]]:
        if enable_thinking and self.supports_thinking:
            return self.thinking_config.copy() if self.thinking_config else None
        elif not enable_thinking and self.disable_thinking_config:
            return self.disable_thinking_config.copy()
        return None

NVIDIA_MODELS: Dict[str, ModelConfig] = {
    "z-ai/glm5": ModelConfig(
        model_id="z-ai/glm5",
        display_name="GLM-5 (智谱)",
        provider="nvidia",
        supports_thinking=True,
        thinking_config={
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False
            }
        },
        disable_thinking_config={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
        max_tokens=16384,
        temperature=1.0,
        top_p=1.0
    ),
    "deepseek-ai/deepseek-v3.2": ModelConfig(
        model_id="deepseek-ai/deepseek-v3.2",
        display_name="DeepSeek-V3.2 (深度求索)",
        provider="nvidia",
        supports_thinking=True,
        thinking_config={
            "chat_template_kwargs": {
                "thinking": True
            }
        },
        max_tokens=8192,
        temperature=1.0,
        top_p=0.95
    ),
    "moonshotai/kimi-k2.5": ModelConfig(
        model_id="moonshotai/kimi-k2.5",
        display_name="Kimi-K2.5 (月之暗面)",
        provider="nvidia",
        supports_thinking=True,
        thinking_config={
            "chat_template_kwargs": {
                "thinking": True
            }
        },
        max_tokens=16384,
        temperature=1.0,
        top_p=1.0
    ),
    "qwen/qwen3.5-397b-a17b": ModelConfig(
        model_id="qwen/qwen3.5-397b-a17b",
        display_name="Qwen3.5 (阿里通义)",
        provider="nvidia",
        supports_thinking=True,
        thinking_config={
            "chat_template_kwargs": {
                "enable_thinking": True
            }
        },
        disable_thinking_config={
            "chat_template_kwargs": {
                "enable_thinking": False
            }
        },
        max_tokens=16384,
        temperature=0.6,
        top_p=0.95
    ),
}

SILICONFLOW_MODELS: Dict[str, ModelConfig] = {
    "deepseek-ai/DeepSeek-V3.2": ModelConfig(
        model_id="deepseek-ai/DeepSeek-V3.2",
        display_name="DeepSeek-V3.2 (深度求索)",
        provider="siliconflow",
        supports_thinking=True,
        thinking_config={},
        max_tokens=8192,
        temperature=0.7,
        top_p=0.95
    ),
}

ALIYUN_MODELS: Dict[str, ModelConfig] = {
    "qwen3.5-plus": ModelConfig(
        model_id="qwen3.5-plus",
        display_name="Qwen3.5-Plus (阿里云通义)",
        provider="aliyun",
        supports_thinking=True,
        thinking_config={
            "enable_thinking": True
        },
        disable_thinking_config={
            "enable_thinking": False
        },
        max_tokens=8192,
        temperature=0.7,
        top_p=0.95
    ),
    "glm-5": ModelConfig(
        model_id="glm-5",
        display_name="GLM-5 (智谱清言)",
        provider="aliyun",
        supports_thinking=True,
        thinking_config={
            "enable_thinking": True
        },
        disable_thinking_config={
            "enable_thinking": False
        },
        max_tokens=8192,
        temperature=0.7,
        top_p=0.95
    ),
}

PLATFORM_MODELS = {
    "nvidia": NVIDIA_MODELS,
    "siliconflow": SILICONFLOW_MODELS,
    "aliyun": ALIYUN_MODELS,
}

def _get_current_platform() -> str:
    from .settings import get_platform
    return get_platform()

def _get_default_model_id() -> str:
    env_default = os.getenv("DEFAULT_MODEL", "")
    platform = _get_current_platform()
    models = PLATFORM_MODELS.get(platform, NVIDIA_MODELS)
    if env_default and env_default in models:
        return env_default
    return list(models.keys())[0] if models else "deepseek-ai/deepseek-v3.2"

DEFAULT_MODEL = _get_default_model_id()

def get_model_config(model_id: str) -> Optional[ModelConfig]:
    platform = _get_current_platform()
    models = PLATFORM_MODELS.get(platform, NVIDIA_MODELS)
    return models.get(model_id)

def get_all_models() -> List[ModelConfig]:
    platform = _get_current_platform()
    models = PLATFORM_MODELS.get(platform, NVIDIA_MODELS)
    return list(models.values())

def get_default_model() -> ModelConfig:
    platform = _get_current_platform()
    models = PLATFORM_MODELS.get(platform, NVIDIA_MODELS)
    model = get_model_config(_get_default_model_id())
    if model:
        return model
    return list(models.values())[0] if models else None

def model_exists(model_id: str) -> bool:
    platform = _get_current_platform()
    models = PLATFORM_MODELS.get(platform, NVIDIA_MODELS)
    return model_id in models

def get_platform_for_model(model_id: str) -> Optional[str]:
    for platform, models in PLATFORM_MODELS.items():
        if model_id in models:
            return platform
    return None
