import os
import shutil
from pathlib import Path
from typing import Dict, Any
from .base import Tool
from config import get_work_dir

CONFIRMATION_REQUIRED_PREFIX = "[CONFIRMATION_REQUIRED]"

class FileDeleteTool(Tool):
    @property
    def name(self) -> str:
        return "file_delete"
    
    @property
    def description(self) -> str:
        return "安全删除文件或目录。参数：path（要删除的路径）、confirmed（是否已确认，默认false）。删除操作需要用户确认。"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要删除的文件或目录路径"
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "用户是否已确认删除，默认为false"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str, confirmed: bool = False, **kwargs) -> str:
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return f"错误：路径不存在: {file_path}"
            
            if not self._is_within_work_dir(file_path):
                return f"错误：安全限制 - 只能删除工作目录内的文件: {file_path}"
            
            if not confirmed:
                return self._request_confirmation(file_path)
            
            if file_path.is_file():
                os.remove(file_path)
                return f"文件删除成功: {file_path}"
            elif file_path.is_dir():
                file_count = sum(1 for _ in file_path.rglob('*'))
                shutil.rmtree(file_path)
                return f"目录删除成功: {file_path} (包含 {file_count} 个项目)"
            else:
                return f"错误：未知类型: {file_path}"
        except Exception as e:
            return f"删除失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (get_work_dir() / p).resolve()
    
    def _is_within_work_dir(self, path: Path) -> bool:
        work_dir = get_work_dir().resolve()
        try:
            path.relative_to(work_dir)
            return True
        except ValueError:
            return False
    
    def _request_confirmation(self, file_path: Path) -> str:
        if file_path.is_file():
            size = file_path.stat().st_size
            return f"{CONFIRMATION_REQUIRED_PREFIX}删除文件\n路径: {file_path}\n大小: {size} bytes\n⚠️ 此操作不可撤销！\n请在对话中确认是否继续删除。"
        elif file_path.is_dir():
            file_count = sum(1 for _ in file_path.rglob('*') if _.is_file())
            dir_count = sum(1 for _ in file_path.rglob('*') if _.is_dir())
            return f"{CONFIRMATION_REQUIRED_PREFIX}删除目录\n路径: {file_path}\n包含: {file_count} 个文件, {dir_count} 个子目录\n⚠️ 此操作不可撤销！\n请在对话中确认是否继续删除。"
        return f"{CONFIRMATION_REQUIRED_PREFIX}删除\n路径: {file_path}\n⚠️ 此操作不可撤销！\n请在对话中确认是否继续删除。"

class FileReadTool(Tool):
    @property
    def name(self) -> str:
        return "file_read"
    
    @property
    def description(self) -> str:
        return "读取指定文件的内容。【必需参数】path：文件路径（字符串）。示例：{\"path\": \"main.py\"} 或 {\"path\": \"src/app.py\"}"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要读取的文件路径（必需）。可以是绝对路径或相对于工作目录的相对路径。例如：'main.py' 或 'src/app.py'"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str = None, **kwargs) -> str:
        if path is None or path == "":
            return "错误：缺少必需参数 'path'。请提供文件路径。示例：file_read(path=\"main.py\")"
        try:
            file_path = self._resolve_path(path)
            
            if not self._is_within_work_dir(file_path):
                return "安全限制：只能访问工作区目录内的文件"
            
            if not file_path.exists():
                return f"错误：文件不存在: {file_path}"
            
            if not file_path.is_file():
                return f"错误：路径不是文件: {file_path}"
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            return f"文件内容 ({file_path}):\n{content}"
        except Exception as e:
            return f"读取文件失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (get_work_dir() / p).resolve()
    
    def _is_within_work_dir(self, path: Path) -> bool:
        work_dir = get_work_dir().resolve()
        try:
            path.relative_to(work_dir)
            return True
        except ValueError:
            return False

class FileWriteTool(Tool):
    @property
    def name(self) -> str:
        return "file_write"
    
    @property
    def description(self) -> str:
        return "将内容写入指定文件。【必需参数】path：文件路径（字符串）；content：写入内容（字符串）。示例：{\"path\": \"main.py\", \"content\": \"print('hello')\"}"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要写入的文件路径（必需）。例如：'main.py' 或 'src/app.py'"
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容（必需）。例如：'print(\"hello\")'"
                }
            },
            "required": ["path", "content"]
        }
    
    def execute(self, path: str = None, content: str = None, **kwargs) -> str:
        if path is None or path == "":
            return "错误：缺少必需参数 'path'。请提供文件路径。"
        if content is None:
            return "错误：缺少必需参数 'content'。请提供写入内容。"
        try:
            file_path = self._resolve_path(path)
            
            if not self._is_within_work_dir(file_path):
                return "安全限制：只能访问工作区目录内的文件"
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            return f"文件写入成功: {file_path}"
        except Exception as e:
            return f"写入文件失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (get_work_dir() / p).resolve()
    
    def _is_within_work_dir(self, path: Path) -> bool:
        work_dir = get_work_dir().resolve()
        try:
            path.relative_to(work_dir)
            return True
        except ValueError:
            return False

class ListDirTool(Tool):
    @property
    def name(self) -> str:
        return "list_dir"
    
    @property
    def description(self) -> str:
        return "列出指定目录下的所有文件和子目录。参数：path（目录路径，默认为当前工作目录）"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径，默认为当前工作目录"
                }
            },
            "required": []
        }
    
    def execute(self, path: str = ".", **kwargs) -> str:
        try:
            dir_path = self._resolve_path(path)
            
            if not dir_path.exists():
                return f"错误：目录不存在: {dir_path}"
            
            if not dir_path.is_dir():
                return f"错误：路径不是目录: {dir_path}"
            
            items = []
            for item in sorted(dir_path.iterdir()):
                item_type = "[目录]" if item.is_dir() else "[文件]"
                size = item.stat().st_size if item.is_file() else "-"
                items.append(f"{item_type} {item.name} ({size} bytes)")
            
            if not items:
                return f"目录为空: {dir_path}"
            
            return f"目录内容 ({dir_path}):\n" + "\n".join(items)
        except Exception as e:
            return f"列出目录失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p

class MkdirTool(Tool):
    @property
    def name(self) -> str:
        return "mkdir"
    
    @property
    def description(self) -> str:
        return "创建指定目录。如果父目录不存在，会自动创建。参数：path（目录路径）"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要创建的目录路径"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str, **kwargs) -> str:
        try:
            dir_path = self._resolve_path(path)
            dir_path.mkdir(parents=True, exist_ok=True)
            return f"目录创建成功: {dir_path}"
        except Exception as e:
            return f"创建目录失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p
