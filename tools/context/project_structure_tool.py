import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from ..base import Tool
from config import get_work_dir


class ProjectStructureTool(Tool):
    PROJECT_TYPE_MARKERS = {
        "Python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock"],
        "Node.js": ["package.json", "yarn.lock", "pnpm-lock.yaml", "package-lock.json"],
        "Java": ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
        "Go": ["go.mod", "go.sum"],
        "Rust": ["Cargo.toml", "Cargo.lock"],
        "Ruby": ["Gemfile", "Gemfile.lock"],
        "PHP": ["composer.json", "composer.lock"],
        "C#": [".csproj", ".sln"],
        "C/C++": ["CMakeLists.txt", "Makefile", "configure.ac"],
        "Docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
    }

    CONFIG_FILES = {
        "package.json": "Node.js 项目配置",
        "pyproject.toml": "Python 项目配置",
        "requirements.txt": "Python 依赖",
        "setup.py": "Python 安装配置",
        "pom.xml": "Maven 项目配置",
        "build.gradle": "Gradle 项目配置",
        "go.mod": "Go 模块配置",
        "Cargo.toml": "Rust 项目配置",
        "Gemfile": "Ruby 依赖配置",
        "composer.json": "PHP 依赖配置",
        "Dockerfile": "Docker 容器配置",
        "docker-compose.yml": "Docker 编排配置",
        ".env": "环境变量配置",
        "README.md": "项目说明文档",
    }

    IGNORE_DIRS = {
        "__pycache__", ".git", ".svn", ".hg", "node_modules", "venv", ".venv",
        "env", ".env", ".idea", ".vscode", "dist", "build", "target", ".tox",
        ".pytest_cache", ".mypy_cache", "eggs", "*.egg-info", ".eggs",
        "vendor", "bower_components", ".gradle", ".mvn", "bin", "obj",
    }

    IGNORE_FILES = {
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe",
        ".class", ".jar", ".war", ".ear", ".log", ".tmp",
    }

    @property
    def name(self) -> str:
        return "project_structure"

    @property
    def description(self) -> str:
        return "分析项目目录结构，识别项目类型，提取关键配置文件信息，生成格式化的项目结构报告。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要分析的项目路径，默认为当前工作目录",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "最大递归深度，默认为5",
                    "default": 5,
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "是否包含隐藏文件（以.开头的文件），默认为False",
                    "default": False,
                },
            },
            "required": [],
        }

    def execute(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_depth = kwargs.get("max_depth", 5)
        include_hidden = kwargs.get("include_hidden", False)

        if path is None or path == "." or path == "":
            project_path = get_work_dir()
        else:
            project_path = Path(path).resolve()
            if not project_path.is_absolute():
                project_path = get_work_dir() / project_path

        if not project_path.exists():
            return f"错误：路径 '{project_path}' 不存在"

        if not project_path.is_dir():
            return f"错误：路径 '{project_path}' 不是目录"

        project_types = self._detect_project_types(project_path)
        config_info = self._extract_config_info(project_path)
        tree_structure = self._generate_tree(project_path, max_depth, include_hidden)
        stats = self._calculate_stats(project_path, include_hidden)

        report = self._format_report(
            project_path, project_types, config_info, tree_structure, stats
        )
        return report

    def _detect_project_types(self, path: Path) -> List[str]:
        detected_types = []
        files_in_root = {f.name for f in path.iterdir() if f.is_file()}
        
        for project_type, markers in self.PROJECT_TYPE_MARKERS.items():
            for marker in markers:
                if marker in files_in_root:
                    if project_type not in detected_types:
                        detected_types.append(project_type)
                    break
        
        if not detected_types:
            py_files = list(path.glob("*.py"))
            if py_files:
                detected_types.append("Python (推测)")
            
            js_files = list(path.glob("*.js")) + list(path.glob("*.ts"))
            if js_files:
                detected_types.append("JavaScript/TypeScript (推测)")
        
        return detected_types if detected_types else ["未知"]

    def _extract_config_info(self, path: Path) -> Dict[str, Any]:
        config_info = {}
        files_in_root = {f.name: f for f in path.iterdir() if f.is_file()}

        for config_file, description in self.CONFIG_FILES.items():
            if config_file in files_in_root:
                file_path = files_in_root[config_file]
                try:
                    info = self._parse_config_file(file_path)
                    config_info[config_file] = {
                        "description": description,
                        "info": info,
                    }
                except Exception as e:
                    config_info[config_file] = {
                        "description": description,
                        "info": f"无法解析: {str(e)}",
                    }

        return config_info

    def _parse_config_file(self, file_path: Path) -> str:
        import json
        import tomllib
        
        file_name = file_path.name
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        if file_name == "package.json":
            try:
                data = json.loads(content)
                name = data.get("name", "未命名")
                version = data.get("version", "未知版本")
                deps = list(data.get("dependencies", {}).keys())
                dev_deps = list(data.get("devDependencies", {}).keys())
                return f"名称: {name}, 版本: {version}, 依赖: {len(deps)}个, 开发依赖: {len(dev_deps)}个"
            except json.JSONDecodeError:
                return "JSON 解析失败"

        elif file_name == "pyproject.toml":
            try:
                data = tomllib.loads(content)
                project = data.get("project", {})
                name = project.get("name", "未命名")
                version = project.get("version", "未知版本")
                deps = project.get("dependencies", [])
                return f"名称: {name}, 版本: {version}, 依赖: {len(deps)}个"
            except Exception:
                return "TOML 解析失败"

        elif file_name == "requirements.txt":
            lines = [l.strip() for l in content.split("\n") if l.strip() and not l.startswith("#")]
            return f"依赖数量: {len(lines)}个"

        elif file_name == "go.mod":
            lines = content.split("\n")
            module_line = next((l for l in lines if l.startswith("module ")), "")
            module_name = module_line.replace("module ", "").strip() if module_line else "未知"
            return f"模块: {module_name}"

        elif file_name == "Cargo.toml":
            try:
                data = tomllib.loads(content)
                package = data.get("package", {})
                name = package.get("name", "未命名")
                version = package.get("version", "未知版本")
                return f"名称: {name}, 版本: {version}"
            except Exception:
                return "TOML 解析失败"

        elif file_name == "pom.xml":
            import re
            group_match = re.search(r"<groupId>(.*?)</groupId>", content)
            artifact_match = re.search(r"<artifactId>(.*?)</artifactId>", content)
            version_match = re.search(r"<version>(.*?)</version>", content)
            return f"GroupId: {group_match.group(1) if group_match else '未知'}, ArtifactId: {artifact_match.group(1) if artifact_match else '未知'}, 版本: {version_match.group(1) if version_match else '未知'}"

        elif file_name == "README.md":
            lines = content.split("\n")
            title = next((l.replace("#", "").strip() for l in lines if l.startswith("#")), "无标题")
            return f"标题: {title}"

        return "已检测到"

    def _generate_tree(self, path: Path, max_depth: int, include_hidden: bool) -> str:
        lines = []
        self._build_tree(path, lines, prefix="", depth=0, max_depth=max_depth, include_hidden=include_hidden)
        return "\n".join(lines)

    def _build_tree(
        self,
        path: Path,
        lines: List[str],
        prefix: str,
        depth: int,
        max_depth: int,
        include_hidden: bool,
    ):
        if depth > max_depth:
            return

        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return

        dirs = []
        files = []

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            
            if entry.is_dir():
                if entry.name in self.IGNORE_DIRS:
                    continue
                if any(entry.name.endswith(ext) for ext in self.IGNORE_DIRS if "*" in ext):
                    continue
                dirs.append(entry)
            else:
                if any(entry.name.endswith(ext) for ext in self.IGNORE_FILES):
                    continue
                files.append(entry)

        all_entries = dirs + files
        total = len(all_entries)

        for i, entry in enumerate(all_entries):
            is_last = i == total - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                new_prefix = prefix + ("    " if is_last else "│   ")
                self._build_tree(entry, lines, new_prefix, depth + 1, max_depth, include_hidden)

    def _calculate_stats(self, path: Path, include_hidden: bool) -> Dict[str, int]:
        stats = {
            "total_dirs": 0,
            "total_files": 0,
            "by_extension": {},
        }

        self._count_recursive(path, stats, include_hidden)
        return stats

    def _count_recursive(self, path: Path, stats: Dict[str, int], include_hidden: bool):
        try:
            for entry in path.iterdir():
                if not include_hidden and entry.name.startswith("."):
                    continue

                if entry.is_dir():
                    if entry.name in self.IGNORE_DIRS:
                        continue
                    stats["total_dirs"] += 1
                    self._count_recursive(entry, stats, include_hidden)
                else:
                    if any(entry.name.endswith(ext) for ext in self.IGNORE_FILES):
                        continue
                    stats["total_files"] += 1
                    ext = entry.suffix.lower() or "无扩展名"
                    stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1
        except PermissionError:
            pass

    def _format_report(
        self,
        path: Path,
        project_types: List[str],
        config_info: Dict[str, Any],
        tree_structure: str,
        stats: Dict[str, int],
    ) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("项目结构分析报告")
        lines.append("=" * 60)
        lines.append("")

        lines.append(f"📁 项目路径: {path}")
        lines.append(f"📋 项目类型: {', '.join(project_types)}")
        lines.append("")

        if config_info:
            lines.append("-" * 40)
            lines.append("📦 配置文件信息")
            lines.append("-" * 40)
            for config_file, info in config_info.items():
                lines.append(f"  • {config_file}")
                lines.append(f"    描述: {info['description']}")
                lines.append(f"    详情: {info['info']}")
            lines.append("")

        lines.append("-" * 40)
        lines.append("📂 目录结构")
        lines.append("-" * 40)
        lines.append(f"{path.name}/")
        lines.append(tree_structure)
        lines.append("")

        lines.append("-" * 40)
        lines.append("📊 统计信息")
        lines.append("-" * 40)
        lines.append(f"  目录数量: {stats['total_dirs']}")
        lines.append(f"  文件数量: {stats['total_files']}")
        
        if stats["by_extension"]:
            sorted_exts = sorted(stats["by_extension"].items(), key=lambda x: x[1], reverse=True)
            top_exts = sorted_exts[:10]
            lines.append("  文件类型分布 (前10):")
            for ext, count in top_exts:
                lines.append(f"    {ext if ext else '(无扩展名)'}: {count}个")
        
        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
