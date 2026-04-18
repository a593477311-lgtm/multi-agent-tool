import sys
import json
import re
from typing import Optional, Callable
from dataclasses import dataclass, field

@dataclass
class StreamState:
    reasoning_content: str = ""
    content: str = ""
    tool_calls: list = field(default_factory=list)
    current_tool_call: dict = field(default_factory=dict)
    current_tool_name: str = ""
    current_tool_args: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

class StreamHandler:
    def __init__(
        self,
        on_reasoning: Optional[Callable[[str], None]] = None,
        on_content: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[dict], None]] = None,
        on_complete: Optional[Callable[[StreamState], None]] = None,
    ):
        self.on_reasoning = on_reasoning or self._default_reasoning_handler
        self.on_content = on_content or self._default_content_handler
        self.on_tool_call = on_tool_call or self._default_tool_call_handler
        self.on_complete = on_complete or self._default_complete_handler
        self.state = StreamState()
    
    def _default_reasoning_handler(self, chunk: str):
        print(f"\033[90m{chunk}\033[0m", end="", flush=True)
    
    def _default_content_handler(self, chunk: str):
        print(f"\033[32m{chunk}\033[0m", end="", flush=True)
    
    def _default_tool_call_handler(self, tool_call: dict):
        print(f"\n\033[33m[工具调用] {tool_call.get('function', {}).get('name', 'unknown')}\033[0m")
    
    def _default_complete_handler(self, state: StreamState):
        pass
    
    def process_chunk(self, chunk) -> StreamState:
        if not chunk.choices:
            if hasattr(chunk, 'usage') and chunk.usage:
                self.state.input_tokens = getattr(chunk.usage, 'prompt_tokens', 0)
                self.state.output_tokens = getattr(chunk.usage, 'completion_tokens', 0)
            return self.state
        
        delta = chunk.choices[0].delta
        
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            self.state.reasoning_content += delta.reasoning_content
            self.on_reasoning(delta.reasoning_content)
        
        if hasattr(delta, "content") and delta.content:
            self.state.content += delta.content
            self.on_content(delta.content)
        
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            for tool_call_delta in delta.tool_calls:
                self._process_tool_call_delta(tool_call_delta)
        
        if hasattr(chunk, 'usage') and chunk.usage:
            self.state.input_tokens = getattr(chunk.usage, 'prompt_tokens', 0)
            self.state.output_tokens = getattr(chunk.usage, 'completion_tokens', 0)
        
        return self.state
    
    def _process_tool_call_delta(self, delta):
        idx = delta.index
        
        while len(self.state.tool_calls) <= idx:
            self.state.tool_calls.append({
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""}
            })
        
        current = self.state.tool_calls[idx]
        
        if delta.id:
            current["id"] = delta.id
        
        if delta.function:
            if delta.function.name:
                current["function"]["name"] = delta.function.name
                self.on_tool_call(current)
            if delta.function.arguments:
                current["function"]["arguments"] += delta.function.arguments
    
    def _fix_truncated_json(self, json_str: str) -> str:
        if not json_str:
            return "{}"
        
        json_str = json_str.strip()
        
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError:
            pass
        
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')
        open_quotes = json_str.count('"') % 2
        
        fixed = json_str
        if open_quotes:
            fixed += '"'
        if open_brackets > 0:
            fixed += ']' * open_brackets
        if open_braces > 0:
            fixed += '}' * open_braces
        
        try:
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError:
            pass
        
        pattern = r'"([^"]+)"\s*:\s*"([^"]*)"$'
        match = re.search(pattern, json_str)
        if match:
            key = match.group(1)
            value = match.group(2)
            return json.dumps({key: value})
        
        return "{}"
    
    def finalize(self) -> StreamState:
        valid_tool_calls = []
        for tc in self.state.tool_calls:
            tc_id = tc.get("id", "")
            tc_func = tc.get("function", {})
            tc_name = tc_func.get("name", "")
            tc_args = tc_func.get("arguments", "")
            
            if tc_id and tc_name:
                fixed_args = self._fix_truncated_json(tc_args)
                tc["function"]["arguments"] = fixed_args
                valid_tool_calls.append(tc)
            else:
                pass
        self.state.tool_calls = valid_tool_calls
        
        if self.state.input_tokens == 0 or self.state.output_tokens == 0:
            self._estimate_tokens()
        
        self.on_complete(self.state)
        return self.state
    
    def _estimate_tokens(self) -> None:
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            
            if self.state.output_tokens == 0:
                output_text = self.state.content or ""
                if self.state.reasoning_content:
                    output_text += self.state.reasoning_content
                if output_text:
                    self.state.output_tokens = len(encoding.encode(output_text))
        except Exception:
            pass
    
    def reset(self):
        self.state = StreamState()
