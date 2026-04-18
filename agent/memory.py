from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import json
import re
import config
import tiktoken

@dataclass
class Message:
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    reasoning_content: Optional[str] = None

class Memory:
    MAX_TOKENS = 128000
    COMPRESSION_THRESHOLD = 0.85
    TARGET_RATIO_AFTER_COMPRESSION = 0.5
    MAX_KNOWLEDGE_PER_CATEGORY = 50
    
    def __init__(self, max_length: int = None):
        self.max_length = max_length or config.MAX_CONTEXT_TOKENS
        self.messages: List[Dict[str, Any]] = []
        self._system_message: Optional[Dict[str, Any]] = None
        self.knowledge: Dict[str, Any] = {}
        self.compressed_summary: Optional[str] = None
        self._encoding = None
    
    def _get_encoding(self):
        if self._encoding is None:
            try:
                self._encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self._encoding = None
        return self._encoding
    
    def set_system_prompt(self, content: str) -> None:
        self._system_message = {"role": "system", "content": content}
    
    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self._trim_if_needed()
    
    def add_assistant_message(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        reasoning_content: Optional[str] = None
    ) -> None:
        message = {"role": "assistant"}
        
        if content and content.strip():
            message["content"] = content
        if tool_calls:
            message["tool_calls"] = tool_calls
        if reasoning_content and reasoning_content.strip():
            message["reasoning_content"] = reasoning_content
        
        self.messages.append(message)
        self._trim_if_needed()
    
    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })
    
    def build_context(self, include_system: bool = True, task_type: str = None) -> List[Dict[str, Any]]:
        context = []
        
        if include_system and self._system_message:
            system_content = self._system_message.get("content", "")
            
            knowledge_summary = self._build_knowledge_summary(task_type)
            if knowledge_summary:
                system_content += f"\n\n---\n\n【上下文知识】\n{knowledge_summary}"
            
            context.append({"role": "system", "content": system_content})
        
        if self.compressed_summary:
            context.append({
                "role": "user",
                "content": f"[历史对话摘要]\n{self.compressed_summary}"
            })
            context.append({
                "role": "assistant",
                "content": "我已了解之前的对话内容，会继续协助您。"
            })
        
        for msg in self.messages:
            msg_copy = {k: v for k, v in msg.items() if k != "reasoning_content"}
            context.append(msg_copy)
        
        return context
    
    def _build_knowledge_summary(self, task_type: str = None) -> str:
        if not self.knowledge:
            return ""
        parts = []
        if "project" in self.knowledge:
            project_info = []
            project_data = self.knowledge["project"]
            if isinstance(project_data, dict):
                if "project_type" in project_data:
                    val = project_data["project_type"]
                    if isinstance(val, dict) and "value" in val:
                        project_info.append(f"项目类型: {val['value']}")
                    elif isinstance(val, str):
                        project_info.append(f"项目类型: {val}")
                if "framework" in project_data:
                    val = project_data["framework"]
                    if isinstance(val, dict) and "value" in val:
                        project_info.append(f"框架: {val['value']}")
                    elif isinstance(val, str):
                        project_info.append(f"框架: {val}")
                if "structure" in project_data:
                    val = project_data["structure"]
                    if isinstance(val, dict) and "value" in val:
                        struct = val["value"]
                        if isinstance(struct, dict) and "content" in struct:
                            project_info.append(f"项目结构:\n{struct['content'][:500]}")
            if project_info:
                parts.append("【项目信息】\n" + "\n".join(project_info))
        if "files" in self.knowledge:
            files_data = self.knowledge["files"]
            if isinstance(files_data, dict) and files_data:
                file_list = []
                for key, val in list(files_data.items())[:10]:
                    if isinstance(val, dict) and "value" in val:
                        file_info = val["value"]
                        if isinstance(file_info, dict):
                            path = file_info.get("path", key)
                            op = file_info.get("operation", "unknown")
                            file_list.append(f"  - {path} ({op})")
                if file_list:
                    parts.append("【文件操作记录】\n" + "\n".join(file_list))
        
        subagent_parts = []
        
        files_read = self.knowledge.get("subagent.files_read", [])
        if files_read:
            display_files = files_read[:10]
            suffix = f"... 共{len(files_read)}个" if len(files_read) > 10 else ""
            subagent_parts.append(f"已读取文件: {', '.join(display_files)}{suffix}")
        
        if task_type in ["refactor", "debugger", "test", "main", None]:
            replaced_files = self.knowledge.get("subagent.replaced_files", [])
            if replaced_files:
                display_files = replaced_files[:10]
                suffix = f"... 共{len(replaced_files)}个" if len(replaced_files) > 10 else ""
                subagent_parts.append(f"已修改文件: {', '.join(display_files)}{suffix}")
        
        if task_type in ["refactor", "main", None]:
            deleted_files = self.knowledge.get("subagent.deleted_files", [])
            if deleted_files:
                display_files = deleted_files[:10]
                suffix = f"... 共{len(deleted_files)}个" if len(deleted_files) > 10 else ""
                subagent_parts.append(f"已删除文件: {', '.join(display_files)}{suffix}")
        
        if task_type in ["refactor", "test", "main", None]:
            created_dirs = self.knowledge.get("subagent.created_dirs", [])
            if created_dirs:
                display_dirs = created_dirs[:10]
                suffix = f"... 共{len(created_dirs)}个" if len(created_dirs) > 10 else ""
                subagent_parts.append(f"已创建目录: {', '.join(display_dirs)}{suffix}")
        
        if task_type in ["main", None]:
            todos = self.knowledge.get("subagent.todos", [])
            if todos:
                todo_summary = []
                for t in todos[:5]:
                    if isinstance(t, dict):
                        todo_summary.append(f"{t.get('id', '?')}:{t.get('status', '?')}")
                suffix = f"... 共{len(todos)}个" if len(todos) > 5 else ""
                if todo_summary:
                    subagent_parts.append(f"任务列表: {', '.join(todo_summary)}{suffix}")
            
            grep_patterns = self.knowledge.get("subagent.grep_patterns", [])
            if grep_patterns:
                display_patterns = grep_patterns[:5]
                suffix = f"... 共{len(grep_patterns)}个" if len(grep_patterns) > 5 else ""
                subagent_parts.append(f"已搜索模式: {', '.join(display_patterns)}{suffix}")
            
            glob_patterns = self.knowledge.get("subagent.glob_patterns", [])
            if glob_patterns:
                display_patterns = glob_patterns[:5]
                suffix = f"... 共{len(glob_patterns)}个" if len(glob_patterns) > 5 else ""
                subagent_parts.append(f"已匹配模式: {', '.join(display_patterns)}{suffix}")
        
        if subagent_parts:
            parts.append("【子代理操作记录】\n" + "\n".join(subagent_parts))
        
        return "\n\n".join(parts)
    
    def _trim_if_needed(self) -> None:
        if len(self.messages) > self.max_length:
            trim_count = len(self.messages) - self.max_length
            self.messages = self.messages[trim_count:]
    
    def clear(self) -> None:
        self.messages = []
        self.compressed_summary = None
    
    def get_last_user_message(self) -> Optional[str]:
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return msg.get("content")
        return None
    
    def get_conversation_summary(self) -> str:
        total = len(self.messages)
        user_msgs = sum(1 for m in self.messages if m.get("role") == "user")
        assistant_msgs = sum(1 for m in self.messages if m.get("role") == "assistant")
        tool_msgs = sum(1 for m in self.messages if m.get("role") == "tool")
        
        return f"对话历史: {total}条消息 (用户: {user_msgs}, 助手: {assistant_msgs}, 工具: {tool_msgs})"
    
    def _fallback_token_count(self) -> int:
        total_chars = 0
        
        if self._system_message:
            total_chars += 4
            total_chars += len(self._system_message.get("content", ""))
        
        if self.compressed_summary:
            total_chars += 4
            total_chars += len(self.compressed_summary)
        
        for msg in self.messages:
            total_chars += 4
            if "name" in msg:
                total_chars += 1
            
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    func_name = func.get("name", "")
                    args = func.get("arguments", "")
                    total_chars += len(func_name)
                    total_chars += len(str(args))
                    total_chars += 4
        
        return total_chars // 4
    
    def get_token_count(self) -> int:
        encoding = self._get_encoding()
        if encoding is None:
            return self._fallback_token_count()
        
        try:
            total_tokens = 0
            
            if self._system_message:
                total_tokens += 4
                content = self._system_message.get("content", "")
                total_tokens += len(encoding.encode(content))
            
            if self.compressed_summary:
                total_tokens += 4
                total_tokens += len(encoding.encode(self.compressed_summary))
            
            for msg in self.messages:
                total_tokens += 4
                if "name" in msg:
                    total_tokens += 1
                
                content = msg.get("content", "")
                if isinstance(content, str):
                    total_tokens += len(encoding.encode(content))
                
                if "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        func = tc.get("function", {})
                        func_name = func.get("name", "")
                        args = func.get("arguments", "")
                        total_tokens += len(encoding.encode(func_name))
                        total_tokens += len(encoding.encode(args))
                        total_tokens += 4
            
            return total_tokens
        except Exception:
            return self._fallback_token_count()
    
    def get_context_usage(self) -> Dict[str, Any]:
        used = self.get_token_count()
        max_tokens = self.MAX_TOKENS
        percent = (used / max_tokens) * 100
        return {
            "used": used,
            "max": max_tokens,
            "percent": percent,
            "needs_compression": percent >= self.COMPRESSION_THRESHOLD * 100
        }
    
    def get_context_usage_percent(self) -> float:
        return self.get_token_count() / self.MAX_TOKENS
    
    def needs_compression(self) -> bool:
        return self.get_context_usage_percent() >= self.COMPRESSION_THRESHOLD
    
    def add_knowledge(self, key: str, value: Any) -> None:
        keys = key.split(".")
        current = self.knowledge
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = {
            "value": value,
            "timestamp": datetime.now().isoformat()
        }
        self._cleanup_knowledge_category(keys[0] if keys else key)
    
    def _cleanup_knowledge_category(self, category: str) -> None:
        if category not in self.knowledge:
            return
        category_data = self.knowledge[category]
        if not isinstance(category_data, dict):
            return
        items = [(k, v) for k, v in category_data.items() if isinstance(v, dict) and "timestamp" in v]
        if len(items) > self.MAX_KNOWLEDGE_PER_CATEGORY:
            items_sorted = sorted(items, key=lambda x: x[1].get("timestamp", ""))
            for key_to_remove, _ in items_sorted[:len(items) - self.MAX_KNOWLEDGE_PER_CATEGORY]:
                del category_data[key_to_remove]
    
    def _extract_knowledge_from_messages(self, messages: List[Dict[str, Any]]) -> None:
        for msg in messages:
            self._extract_file_operations(msg)
            self._extract_project_structure(msg)
            self._extract_tool_results(msg)
    
    def _extract_file_operations(self, msg: Dict[str, Any]) -> None:
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            return
        file_patterns = [
            (r'(?:创建|新建|写入|保存)\s*[文件]?[:：]?\s*["\']?([a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+)["\']?', 'create'),
            (r'(?:修改|编辑|更新)\s*[文件]?[:：]?\s*["\']?([a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+)["\']?', 'modify'),
            (r'(?:删除|移除)\s*[文件]?[:：]?\s*["\']?([a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+)["\']?', 'delete'),
        ]
        for pattern, op_type in file_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for filepath in matches:
                key = f"files.{self._sanitize_key(filepath)}"
                existing = self.get_knowledge(key)
                if existing:
                    existing["operation"] = op_type
                    existing["last_modified"] = datetime.now().isoformat()
                    self.add_knowledge(key, existing)
                else:
                    self.add_knowledge(key, {
                        "path": filepath,
                        "operation": op_type,
                        "created_at": datetime.now().isoformat()
                    })
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            func_name = func.get("name", "")
            if func_name in ["Write", "Edit", "DeleteFile"]:
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    filepath = args.get("file_path", "")
                    if filepath:
                        op_type = {"Write": "create", "Edit": "modify", "DeleteFile": "delete"}.get(func_name, "unknown")
                        key = f"files.{self._sanitize_key(filepath)}"
                        self.add_knowledge(key, {
                            "path": filepath,
                            "operation": op_type,
                            "created_at": datetime.now().isoformat()
                        })
                except json.JSONDecodeError:
                    pass
    
    def _extract_project_structure(self, msg: Dict[str, Any]) -> None:
        content = msg.get("content", "")
        if not content or not isinstance(content, str):
            return
        project_type_patterns = [
            (r'(?:项目类型|project\s*type)[:：]?\s*([a-zA-Z0-9_\-\s]+)', 'project_type'),
            (r'(?:框架|framework)[:：]?\s*([a-zA-Z0-9_\-\s]+)', 'framework'),
        ]
        for pattern, key_suffix in project_type_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                value = match.strip()
                if value:
                    self.add_knowledge(f"project.{key_suffix}", value)
        dir_pattern = r'(?:目录结构|directory\s*structure|项目结构)[:：]?\s*\n([\s\S]*?)(?=\n\n|\n【|$)'
        dir_matches = re.findall(dir_pattern, content, re.IGNORECASE)
        for dir_content in dir_matches:
            if dir_content.strip():
                existing = self.get_knowledge("project.structure")
                if existing:
                    existing["content"] = dir_content.strip()
                    existing["updated_at"] = datetime.now().isoformat()
                    self.add_knowledge("project.structure", existing)
                else:
                    self.add_knowledge("project.structure", {
                        "content": dir_content.strip(),
                        "updated_at": datetime.now().isoformat()
                    })
    
    def _extract_tool_results(self, msg: Dict[str, Any]) -> None:
        if msg.get("role") != "tool":
            return
        tool_call_id = msg.get("tool_call_id", "")
        content = msg.get("content", "")
        if not content:
            return
        content_str = content if isinstance(content, str) else str(content)
        summary = content_str[:500] if len(content_str) > 500 else content_str
        key = f"tools.{tool_call_id}"
        self.add_knowledge(key, {
            "tool_call_id": tool_call_id,
            "result_summary": summary,
            "timestamp": datetime.now().isoformat()
        })
    
    def _sanitize_key(self, key: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_\-]', '_', key)
    
    def extract_and_store_knowledge(self, messages: List[Dict[str, Any]]) -> None:
        self._extract_knowledge_from_messages(messages)
    
    def get_knowledge(self, key: str) -> Optional[Any]:
        keys = key.split(".")
        current = self.knowledge
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        if isinstance(current, dict) and "value" in current:
            return current["value"]
        return current
    
    def save_to_file(self, filepath: Path) -> None:
        data = {
            "messages": self.messages,
            "knowledge": self.knowledge,
            "compressed_summary": self.compressed_summary,
            "saved_at": datetime.now().isoformat()
        }
        
        if self._system_message:
            data["system_message"] = self._system_message
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filepath: Path) -> bool:
        if not filepath.exists():
            return False
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.messages = data.get("messages", [])
            self.knowledge = data.get("knowledge", {})
            self.compressed_summary = data.get("compressed_summary")
            
            if "system_message" in data:
                self._system_message = data["system_message"]
            
            return True
        except Exception:
            return False
