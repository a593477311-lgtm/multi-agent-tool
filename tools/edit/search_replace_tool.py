from pathlib import Path
from typing import Dict, Any
from ..base import Tool
from config import get_work_dir


class SearchReplaceTool(Tool):
    @property
    def name(self) -> str:
        return "search_replace"
    
    @property
    def description(self) -> str:
        return ("精确字符串查找替换工具。在指定文件中查找精确匹配的字符串并替换为新字符串。【必需参数】path：文件路径（字符串）；old_str：要查找的字符串（字符串）；new_str：替换后的字符串（字符串）。替换前会验证匹配次数：如果匹配数为0则返回错误；如果匹配数大于1且未指定expected_matches，提示用户确认。"
                "示例：{\"path\": \"main.py\", \"old_str\": \"hello\", \"new_str\": \"world\"}")
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要进行替换操作的文件路径（必需）。例如：'main.py'"
                },
                "old_str": {
                    "type": "string",
                    "description": "要查找的字符串（必需，精确匹配）。例如：'hello'"
                },
                "new_str": {
                    "type": "string",
                    "description": "替换后的字符串（必需）。例如：'world'"
                },
                "expected_matches": {
                    "type": "integer",
                    "description": "预期匹配次数，用于验证替换操作的正确性"
                }
            },
            "required": ["path", "old_str", "new_str"]
        }
    
    def execute(self, path: str = None, old_str: str = None, new_str: str = None, 
                expected_matches: int = None, **kwargs) -> str:
        if path is None or path == "":
            return "错误：缺少必需参数 'path'。请提供文件路径。"
        if old_str is None:
            return "错误：缺少必需参数 'old_str'。请提供要查找的字符串。"
        if new_str is None:
            return "错误：缺少必需参数 'new_str'。请提供替换后的字符串。"
        try:
            file_path = self._resolve_path(path)
            
            if not file_path.exists():
                return f"错误：文件不存在: {file_path}"
            
            if not file_path.is_file():
                return f"错误：路径不是文件: {file_path}"
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            match_count = content.count(old_str)
            
            if match_count == 0:
                return f"错误：未找到匹配项。文件 '{file_path}' 中不存在指定的字符串。"
            
            if expected_matches is not None:
                if match_count != expected_matches:
                    return (f"错误：匹配次数验证失败。预期 {expected_matches} 次匹配，"
                            f"实际找到 {match_count} 次匹配。请检查查找字符串是否正确。")
            else:
                if match_count > 1:
                    return (f"警告：找到 {match_count} 处匹配。由于存在多处匹配，"
                            f"请指定 expected_matches 参数以确认要替换的次数，"
                            f"或确保查找字符串足够精确以唯一标识目标位置。")
            
            new_content = content.replace(old_str, new_str)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return (f"替换成功：\n"
                    f"  文件路径: {file_path}\n"
                    f"  替换次数: {match_count}\n"
                    f"  原字符串: {repr(old_str[:50] + '...' if len(old_str) > 50 else old_str)}\n"
                    f"  新字符串: {repr(new_str[:50] + '...' if len(new_str) > 50 else new_str)}")
        
        except Exception as e:
            return f"替换操作失败: {str(e)}"
    
    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return get_work_dir() / p
