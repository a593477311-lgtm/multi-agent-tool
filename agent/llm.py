import os
from typing import Optional, List, Dict, Any, Generator
from openai import OpenAI
from openai.types.chat import ChatCompletionChunk
import config
from config import settings
from config.models import ModelConfig, get_model_config, get_default_model, model_exists, get_platform_for_model

_nim_cache_initialized = False

def setup_nim_cache() -> None:
    global _nim_cache_initialized
    if _nim_cache_initialized:
        return
    
    if config.get_platform() == "nvidia" and settings.ENABLE_PREFIX_CACHE:
        os.environ["NIM_ENABLE_KV_CACHE_REUSE"] = "1"
        if settings.NIM_KV_CACHE_HOST_OFFLOAD:
            os.environ["NIM_ENABLE_KV_CACHE_HOST_OFFLOAD"] = "1"
    
    _nim_cache_initialized = True

class LLMClient:
    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        setup_nim_cache()
        
        if model_id:
            self.model_config = get_model_config(model_id)
            if not self.model_config:
                raise ValueError(f"未知的模型: {model_id}")
        else:
            self.model_config = get_default_model()
        
        self.api_key = api_key or config.get_api_key()
        self.base_url = base_url or config.get_base_url()
        
        if not self.api_key:
            raise ValueError("API Key 未设置，请在 .env 文件中配置 API Key")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
    
    @property
    def model_id(self) -> str:
        return self.model_config.model_id
    
    @property
    def model_name(self) -> str:
        return self.model_config.model_id
    
    @property
    def supports_thinking(self) -> bool:
        return self.model_config.supports_thinking
    
    def switch_model(self, model_id: str) -> bool:
        target_platform = get_platform_for_model(model_id)
        if target_platform:
            current_platform = config.get_platform()
            if target_platform != current_platform:
                config.set_platform(target_platform)
                self.api_key = config.get_api_key()
                self.base_url = config.get_base_url()
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
        
        new_config = get_model_config(model_id)
        if not new_config:
            return False
        self.model_config = new_config
        return True
    
    def _build_prefix_cache_messages(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        if not settings.ENABLE_PREFIX_CACHE:
            return messages
        
        system_messages = []
        other_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)
        
        if tools and config.get_platform() == "openai":
            tool_definitions = {
                "role": "system",
                "content": "Available tools:\n" + self._format_tools_for_cache(tools)
            }
            system_messages.append(tool_definitions)
        
        return system_messages + other_messages
    
    def _format_tools_for_cache(self, tools: List[Dict[str, Any]]) -> str:
        import json
        formatted = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                formatted.append(f"- {func.get('name', 'unknown')}: {func.get('description', '')}")
        return "\n".join(formatted)
    
    def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enable_thinking: bool = False,
        **kwargs
    ) -> Generator[ChatCompletionChunk, None, None]:
        optimized_messages = self._build_prefix_cache_messages(messages, tools)
        
        params = {
            "model": self.model_config.model_id,
            "messages": optimized_messages,
            "max_tokens": max_tokens or self.model_config.max_tokens,
            "stream": True,
        }
        
        extra_body = self.model_config.get_extra_body(enable_thinking)
        if extra_body:
            params["extra_body"] = extra_body
        
        if not enable_thinking or not self.model_config.supports_thinking:
            params["temperature"] = temperature if temperature is not None else self.model_config.temperature
            if self.model_config.top_p:
                params["top_p"] = self.model_config.top_p
        
        if tools:
            params["tools"] = tools
        
        try:
            response = self.client.chat.completions.create(**params)
            for chunk in response:
                yield chunk
        except Exception as e:
            raise RuntimeError(f"API 调用失败: {str(e)}")

def stream_completion(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    **kwargs
) -> Generator[ChatCompletionChunk, None, None]:
    client = LLMClient()
    return client.stream_completion(messages, tools, **kwargs)
