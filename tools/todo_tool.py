from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json
from .base import Tool
from config import get_work_dir


class TodoWriteTool(Tool):
    @property
    def name(self) -> str:
        return "TodoWrite"

    @property
    def description(self) -> str:
        return "创建和管理结构化任务列表，用于跟踪复杂任务的进度。当处理多步骤任务时，应先使用此工具创建任务列表，然后逐步执行并更新状态。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "任务列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "任务唯一标识符"
                            },
                            "content": {
                                "type": "string",
                                "description": "任务内容描述"
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "任务状态：pending(待处理), in_progress(进行中), completed(已完成)"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                                "description": "任务优先级：high(高), medium(中), low(低)"
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "该任务需要使用的工具列表（可选）"
                            },
                            "result": {
                                "type": "string",
                                "description": "任务执行结果说明（可选）"
                            }
                        },
                        "required": ["id", "content", "status"]
                    }
                },
                "source": {
                    "type": "string",
                    "description": "任务来源标识，可选值：main(主Agent)、explore、debugger、architect、reviewer、test、refactor。用于区分任务由哪个Agent创建。"
                }
            },
            "required": ["todos"]
        }

    def execute(self, todos: List[Dict[str, Any]], source: str = "main") -> str:
        if isinstance(todos, str):
            try:
                todos = json.loads(todos)
            except json.JSONDecodeError:
                pass
        
        if not isinstance(todos, list):
            return "错误：todos 参数必须是列表"
        
        work_dir = get_work_dir()
        todo_file = work_dir / ".agent_data" / "todos.json"
        log_file = work_dir / ".agent_data" / "todo_logs.json"
        todo_file.parent.mkdir(parents=True, exist_ok=True)

        existing_todos = {}
        old_status_map = {}
        if todo_file.exists():
            try:
                with open(todo_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t in data.get("todos", []):
                        existing_todos[t["id"]] = t
                        old_status_map[t["id"]] = t.get("status", "pending")
            except Exception:
                pass

        status_changes = []
        now = datetime.now()
        
        for todo in todos:
            todo_id = todo.get("id", "")
            old_status = old_status_map.get(todo_id)
            new_status = todo.get("status", "pending")
            
            if "priority" not in todo:
                todo["priority"] = "medium"
            
            todo["source"] = source
            
            if old_status and old_status != new_status:
                status_changes.append({
                    "id": todo_id,
                    "content": todo.get("content", ""),
                    "old_status": old_status,
                    "new_status": new_status,
                    "source": source,
                    "timestamp": now.isoformat()
                })
            
            existing_todos[todo_id] = todo

        save_data = {
            "todos": list(existing_todos.values()),
            "source": source,
            "updated_at": now.isoformat(),
            "created_at": now.isoformat()
        }

        if todo_file.exists():
            try:
                with open(todo_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    if "created_at" in old_data:
                        save_data["created_at"] = old_data["created_at"]
            except Exception:
                pass

        with open(todo_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        if status_changes:
            self._append_logs(log_file, status_changes)

        summary = self._format_summary(list(existing_todos.values()))
        change_notification = self._format_status_changes(status_changes)
        
        source_label = self._get_source_label(source)
        if change_notification:
            return f"📋 [{source_label}] 任务列表已更新:\n{summary}\n\n{change_notification}"
        return f"📋 [{source_label}] 任务列表已更新:\n{summary}"
    
    def _get_source_label(self, source: str) -> str:
        source_labels = {
            "main": "主Agent",
            "explore": "Explore",
            "debugger": "Debugger",
            "architect": "Architect",
            "reviewer": "Reviewer",
            "test": "Test",
            "refactor": "Refactor",
        }
        return source_labels.get(source, source)

    def _append_logs(self, log_file: Path, changes: List[Dict]) -> None:
        logs = []
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                pass
        
        logs.extend(changes)
        
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs[-100:], f, ensure_ascii=False, indent=2)

    def _format_summary(self, todos: List[Dict[str, Any]]) -> str:
        status_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅"
        }
        priority_icons = {
            "high": "🔴",
            "medium": "🟡",
            "low": "🟢"
        }

        lines = []
        completed = 0
        total = len(todos)

        for todo in todos:
            if not isinstance(todo, dict):
                continue
            status = todo.get("status", "pending")
            priority = todo.get("priority", "medium")
            status_icon = status_icons.get(status, "❓")
            priority_icon = priority_icons.get(priority, "🟡")
            content = todo.get("content", "")
            tools = todo.get("tools", [])
            result = todo.get("result", "")
            
            line = f"  {status_icon} {priority_icon} {content}"
            if tools and status != "pending":
                line += f" [工具: {', '.join(tools)}]"
            if result and status == "completed":
                line += f" → {result}"
            lines.append(line)
            
            if status == "completed":
                completed += 1

        progress = f"\n📊 进度: {completed}/{total} 完成 ({completed/total*100:.0f}%)" if total > 0 else ""
        return "\n".join(lines) + progress

    def _format_status_changes(self, changes: List[Dict]) -> str:
        if not changes:
            return ""
        
        status_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅"
        }
        
        lines = ["📝 任务状态变更:"]
        for change in changes:
            if not isinstance(change, dict):
                continue
            old_icon = status_icons.get(change.get("old_status", ""), "❓")
            new_icon = status_icons.get(change.get("new_status", ""), "❓")
            lines.append(f"  - {change.get('content', '')}: {old_icon} {change.get('old_status', '')} → {new_icon} {change.get('new_status', '')}")
        
        return "\n".join(lines)

    @staticmethod
    def load_todos() -> List[Dict[str, Any]]:
        work_dir = get_work_dir()
        todo_file = work_dir / ".agent_data" / "todos.json"
        if not todo_file.exists():
            return []
        try:
            with open(todo_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("todos", [])
        except Exception:
            return []

    @staticmethod
    def load_logs() -> List[Dict[str, Any]]:
        work_dir = get_work_dir()
        log_file = work_dir / ".agent_data" / "todo_logs.json"
        if not log_file.exists():
            return []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @staticmethod
    def get_current_task() -> Optional[Dict[str, Any]]:
        todos = TodoWriteTool.load_todos()
        for todo in todos:
            if todo.get("status") == "in_progress":
                return todo
        return None
