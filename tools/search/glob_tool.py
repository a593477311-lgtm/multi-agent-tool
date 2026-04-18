from pathlib import Path
from typing import Dict, Any, List
from ..base import Tool
from config import get_work_dir


class GlobTool(Tool):
    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "使用 glob 模式匹配查找文件。【必需参数】pattern：glob 模式（字符串）。示例：{\"pattern\": \"*.py\"} 或 {\"pattern\": \"**/*.txt\"}"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式（必需）。例如：'*.py'、'**/*.txt'、'data/*.json'"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果的最大数量，默认为 100",
                    "default": 100
                }
            },
            "required": ["pattern"]
        }

    def execute(self, pattern: str = None, max_results: int = 100, **kwargs) -> str:
        if pattern is None or pattern == "":
            return "错误：缺少必需参数 'pattern'。请提供 glob 模式。示例：glob(pattern=\"*.py\")"
        try:
            search_path = self._resolve_search_path(pattern)
            glob_pattern = self._extract_glob_pattern(pattern)

            matched_files: List[Path] = list(search_path.glob(glob_pattern))

            files_only = [f for f in matched_files if f.is_file()]

            files_sorted = sorted(
                files_only,
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            limited_files = files_sorted[:max_results]

            if not limited_files:
                return f"未找到匹配 '{pattern}' 的文件"

            result_lines = [f"找到 {len(files_only)} 个匹配文件（显示前 {len(limited_files)} 个）:"]
            for file_path in limited_files:
                rel_path = self._get_display_path(file_path)
                mtime = file_path.stat().st_mtime
                from datetime import datetime
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                result_lines.append(f"  {rel_path} (修改时间: {mtime_str})")

            return "\n".join(result_lines)
        except Exception as e:
            return f"glob 搜索失败: {str(e)}"

    def _resolve_search_path(self, pattern: str) -> Path:
        p = Path(pattern)

        if p.is_absolute():
            return p.parent if p.name else p

        if "/" in pattern or "\\" in pattern:
            parts = Path(pattern)
            if parts.parts:
                first_part = parts.parts[0]
                potential_path = Path(first_part)
                if potential_path.is_absolute():
                    return potential_path.parent if len(parts.parts) > 1 else potential_path

        return get_work_dir()

    def _extract_glob_pattern(self, pattern: str) -> str:
        p = Path(pattern)

        if p.is_absolute():
            return p.name if p.name else "*"

        if "/" in pattern or "\\" in pattern:
            parts = Path(pattern)
            if parts.parts:
                first_part = parts.parts[0]
                potential_path = Path(first_part)
                if potential_path.is_absolute():
                    return str(Path(*parts.parts[1:])) if len(parts.parts) > 1 else "*"
            return pattern

        return pattern

    def _get_display_path(self, file_path: Path) -> str:
        work_dir = get_work_dir()
        try:
            return str(file_path.relative_to(work_dir))
        except ValueError:
            return str(file_path)
