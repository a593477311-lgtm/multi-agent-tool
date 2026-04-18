import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from .base import Tool
from config import get_work_dir


class ProjectPrecheckTool(Tool):
    
    @property
    def name(self) -> str:
        return "project_precheck"
    
    @property
    def description(self) -> str:
        return """项目启动前预检工具。在启动项目前自动检查环境、依赖和兼容性。

支持的项目类型：
- Python (Flask/Django/FastAPI)
- Java/Spring Boot
- Node.js
- Go
- Rust
- .NET

检查内容：
- 运行时版本（Python/JDK/Node.js/Go/Rust/.NET）
- 包管理器状态
- 依赖完整性
- 配置文件检查
- 兼容性警告

参数：
- path: 项目路径（可选，默认当前工作目录）
- project_type: 项目类型（可选，自动识别）

使用场景：
- 用户请求"运行项目"或"启动项目"时
- 用户请求检查项目环境时
- 项目启动失败需要诊断时"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "项目路径，默认为当前工作目录"
                },
                "project_type": {
                    "type": "string",
                    "description": "项目类型（python/java/nodejs/go/rust/dotnet），不指定则自动识别",
                    "enum": ["python", "java", "nodejs", "go", "rust", "dotnet"]
                }
            },
            "required": []
        }
    
    def execute(self, path: str = None, project_type: str = None, **kwargs) -> str:
        project_path = self._resolve_path(path)
        
        if not project_path.exists():
            return f"错误：项目路径不存在: {project_path}"
        
        if not project_path.is_dir():
            return f"错误：路径不是目录: {project_path}"
        
        if not project_type:
            project_type = self._detect_project_type(project_path)
        
        if not project_type:
            return self._generate_report({
                "project_path": str(project_path),
                "project_type": "未知",
                "status": "无法识别项目类型",
                "suggestions": [
                    "请确保项目包含以下标识文件之一：",
                    "- Python: requirements.txt, pyproject.toml, setup.py",
                    "- Java: pom.xml, build.gradle",
                    "- Node.js: package.json",
                    "- Go: go.mod",
                    "- Rust: Cargo.toml",
                    "- .NET: *.csproj, *.sln"
                ]
            })
        
        check_results = {
            "project_path": str(project_path),
            "project_type": project_type,
            "runtime_version": None,
            "package_manager": None,
            "dependencies": {},
            "config_files": {},
            "warnings": [],
            "suggestions": []
        }
        
        if project_type == "python":
            self._check_python_project(project_path, check_results)
        elif project_type == "java":
            self._check_java_project(project_path, check_results)
        elif project_type == "nodejs":
            self._check_nodejs_project(project_path, check_results)
        elif project_type == "go":
            self._check_go_project(project_path, check_results)
        elif project_type == "rust":
            self._check_rust_project(project_path, check_results)
        elif project_type == "dotnet":
            self._check_dotnet_project(project_path, check_results)
        
        return self._generate_report(check_results)
    
    def _resolve_path(self, path: str) -> Path:
        if path:
            p = Path(path)
            if p.is_absolute():
                return p
            return (get_work_dir() / p).resolve()
        return get_work_dir().resolve()
    
    def _detect_project_type(self, project_path: Path) -> Optional[str]:
        if (project_path / "requirements.txt").exists() or \
           (project_path / "pyproject.toml").exists() or \
           (project_path / "setup.py").exists():
            return "python"
        
        if (project_path / "pom.xml").exists() or \
           (project_path / "build.gradle").exists() or \
           (project_path / "build.gradle.kts").exists():
            return "java"
        
        if (project_path / "package.json").exists():
            return "nodejs"
        
        if (project_path / "go.mod").exists():
            return "go"
        
        if (project_path / "Cargo.toml").exists():
            return "rust"
        
        csproj_files = list(project_path.glob("*.csproj"))
        sln_files = list(project_path.glob("*.sln"))
        if csproj_files or sln_files:
            return "dotnet"
        
        return None
    
    def _run_command(self, command: str, timeout: int = 10) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )
            return True, result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "命令执行超时"
        except Exception as e:
            return False, str(e)
    
    def _check_python_project(self, project_path: Path, results: Dict):
        success, version_output = self._run_command("python --version")
        if success and version_output:
            results["runtime_version"] = version_output
            version_match = re.search(r'Python (\d+)\.(\d+)', version_output)
            if version_match:
                major, minor = int(version_match.group(1)), int(version_match.group(2))
                if major >= 3 and minor >= 12:
                    results["warnings"].append("Python 3.12+ 可能存在兼容性问题，部分旧库可能需要升级")
        else:
            results["warnings"].append("Python 未安装或不在 PATH 中")
        
        success, pip_output = self._run_command("pip --version")
        results["package_manager"] = "pip" if success else "未检测到"
        
        requirements_file = project_path / "requirements.txt"
        pyproject_file = project_path / "pyproject.toml"
        
        required_packages = []
        
        if requirements_file.exists():
            try:
                with open(requirements_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            pkg_name = re.split(r'[<>=!~\[]', line)[0].strip().lower()
                            if pkg_name:
                                required_packages.append(pkg_name)
            except Exception:
                pass
        
        if pyproject_file.exists():
            try:
                with open(pyproject_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                    if deps_match:
                        deps_str = deps_match.group(1)
                        pkg_matches = re.findall(r'"([^"]+)"', deps_str)
                        for pkg in pkg_matches:
                            pkg_name = re.split(r'[<>=!~\[]', pkg)[0].strip().lower()
                            if pkg_name:
                                required_packages.append(pkg_name)
            except Exception:
                pass
        
        if required_packages:
            success, pip_list = self._run_command("pip list --format=freeze")
            installed = set()
            if success:
                for line in pip_list.split('\n'):
                    if '==' in line:
                        pkg_name = line.split('==')[0].lower().replace('-', '_')
                        installed.add(pkg_name)
            
            missing = []
            for pkg in required_packages:
                pkg_normalized = pkg.replace('-', '_')
                if pkg_normalized not in installed and pkg not in installed:
                    missing.append(pkg)
            
            results["dependencies"] = {
                "required_count": len(required_packages),
                "missing": missing,
                "missing_count": len(missing)
            }
            
            if missing:
                results["suggestions"].append(f"安装缺失依赖: pip install {' '.join(missing[:5])}")
                if len(missing) > 5:
                    results["suggestions"].append(f"或安装全部依赖: pip install -r requirements.txt")
        
        if requirements_file.exists():
            results["config_files"]["requirements.txt"] = "存在"
        if pyproject_file.exists():
            results["config_files"]["pyproject.toml"] = "存在"
        
        app_files = list(project_path.glob("app.py")) + \
                   list(project_path.glob("main.py")) + \
                   list(project_path.glob("run.py"))
        if app_files:
            results["config_files"]["入口文件"] = [f.name for f in app_files]
        
        if 'sqlalchemy' in str(required_packages).lower():
            success, pip_list = self._run_command("pip show sqlalchemy")
            if success:
                version_match = re.search(r'Version:\s*([\d.]+)', pip_list)
                if version_match:
                    version = version_match.group(1)
                    major_version = int(version.split('.')[0])
                    if major_version < 2:
                        version_match = re.search(r'Python (\d+)\.(\d+)', results.get("runtime_version", ""))
                        if version_match and int(version_match.group(1)) >= 3 and int(version_match.group(2)) >= 12:
                            results["warnings"].append(f"SQLAlchemy {version} 与 Python 3.12+ 不兼容")
                            results["suggestions"].append("升级 SQLAlchemy: pip install --upgrade sqlalchemy>=2.0.0")
    
    def _check_java_project(self, project_path: Path, results: Dict):
        success, version_output = self._run_command("java -version")
        if success and version_output:
            version_match = re.search(r'version "?(\d+)', version_output)
            if version_match:
                version = version_match.group(1)
                results["runtime_version"] = f"JDK {version}"
        else:
            results["warnings"].append("JDK 未安装或不在 PATH 中")
        
        success, maven_output = self._run_command("mvn --version")
        if success:
            version_match = re.search(r'Apache Maven (\d+\.\d+\.\d+)', maven_output)
            if version_match:
                results["package_manager"] = f"Maven {version_match.group(1)}"
        else:
            success, gradle_output = self._run_command("gradle --version")
            if success:
                version_match = re.search(r'Gradle (\d+\.\d+)', gradle_output)
                if version_match:
                    results["package_manager"] = f"Gradle {version_match.group(1)}"
            else:
                results["package_manager"] = "未检测到 Maven 或 Gradle"
                results["warnings"].append("Maven 或 Gradle 未安装")
        
        pom_file = project_path / "pom.xml"
        gradle_file = project_path / "build.gradle"
        gradle_kts_file = project_path / "build.gradle.kts"
        
        if pom_file.exists():
            results["config_files"]["pom.xml"] = "存在"
            try:
                with open(pom_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    artifact_match = re.search(r'<artifactId>([^<]+)</artifactId>', content)
                    if artifact_match:
                        results["config_files"]["项目名称"] = artifact_match.group(1)
                    
                    if 'spring-boot' in content.lower():
                        results["config_files"]["框架"] = "Spring Boot"
            except Exception:
                pass
        
        if gradle_file.exists():
            results["config_files"]["build.gradle"] = "存在"
        if gradle_kts_file.exists():
            results["config_files"]["build.gradle.kts"] = "存在"
        
        app_props = project_path / "src" / "main" / "resources" / "application.properties"
        app_yml = project_path / "src" / "main" / "resources" / "application.yml"
        
        if app_props.exists():
            results["config_files"]["application.properties"] = "存在"
        if app_yml.exists():
            results["config_files"]["application.yml"] = "存在"
        
        if not results["package_manager"].startswith("未"):
            results["suggestions"].append("检查依赖: mvn dependency:tree 或 gradle dependencies")
    
    def _check_nodejs_project(self, project_path: Path, results: Dict):
        success, version_output = self._run_command("node --version")
        if success and version_output:
            results["runtime_version"] = f"Node.js {version_output}"
        else:
            results["warnings"].append("Node.js 未安装或不在 PATH 中")
        
        package_managers = []
        success, npm_output = self._run_command("npm --version")
        if success:
            package_managers.append(f"npm {npm_output}")
        
        success, yarn_output = self._run_command("yarn --version")
        if success:
            package_managers.append(f"yarn {yarn_output}")
        
        success, pnpm_output = self._run_command("pnpm --version")
        if success:
            package_managers.append(f"pnpm {pnpm_output}")
        
        results["package_manager"] = ", ".join(package_managers) if package_managers else "未检测到"
        
        package_json = project_path / "package.json"
        if package_json.exists():
            results["config_files"]["package.json"] = "存在"
            try:
                with open(package_json, 'r', encoding='utf-8', errors='ignore') as f:
                    pkg_data = json.load(f)
                    results["config_files"]["项目名称"] = pkg_data.get("name", "未知")
                    
                    deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                    results["dependencies"] = {
                        "required_count": len(deps),
                        "missing": [],
                        "missing_count": 0
                    }
            except Exception:
                pass
        
        node_modules = project_path / "node_modules"
        if node_modules.exists() and node_modules.is_dir():
            results["config_files"]["node_modules"] = "存在"
        else:
            results["config_files"]["node_modules"] = "不存在"
            results["warnings"].append("node_modules 目录不存在")
            results["suggestions"].append("安装依赖: npm install 或 yarn install 或 pnpm install")
    
    def _check_go_project(self, project_path: Path, results: Dict):
        success, version_output = self._run_command("go version")
        if success and version_output:
            results["runtime_version"] = version_output
        else:
            results["warnings"].append("Go 未安装或不在 PATH 中")
        
        success, go_env = self._run_command("go env GOPATH")
        if success:
            results["package_manager"] = f"Go modules (GOPATH: {go_env})"
        else:
            results["package_manager"] = "Go modules"
        
        go_mod = project_path / "go.mod"
        if go_mod.exists():
            results["config_files"]["go.mod"] = "存在"
            try:
                with open(go_mod, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    module_match = re.search(r'module\s+(\S+)', content)
                    if module_match:
                        results["config_files"]["模块名称"] = module_match.group(1)
            except Exception:
                pass
        
        go_sum = project_path / "go.sum"
        if go_sum.exists():
            results["config_files"]["go.sum"] = "存在"
        
        results["suggestions"].append("下载依赖: go mod download")
        results["suggestions"].append("运行项目: go run . 或 go run main.go")
    
    def _check_rust_project(self, project_path: Path, results: Dict):
        success, rustc_output = self._run_command("rustc --version")
        if success and rustc_output:
            results["runtime_version"] = rustc_output
        else:
            results["warnings"].append("Rust 未安装或不在 PATH 中")
        
        success, cargo_output = self._run_command("cargo --version")
        if success and cargo_output:
            results["package_manager"] = cargo_output
        else:
            results["package_manager"] = "未检测到 Cargo"
            results["warnings"].append("Cargo 未安装")
        
        cargo_toml = project_path / "Cargo.toml"
        if cargo_toml.exists():
            results["config_files"]["Cargo.toml"] = "存在"
            try:
                with open(cargo_toml, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
                    if name_match:
                        results["config_files"]["项目名称"] = name_match.group(1)
            except Exception:
                pass
        
        cargo_lock = project_path / "Cargo.lock"
        if cargo_lock.exists():
            results["config_files"]["Cargo.lock"] = "存在"
        
        results["suggestions"].append("构建项目: cargo build")
        results["suggestions"].append("运行项目: cargo run")
    
    def _check_dotnet_project(self, project_path: Path, results: Dict):
        success, version_output = self._run_command("dotnet --version")
        if success and version_output:
            results["runtime_version"] = f".NET SDK {version_output}"
        else:
            results["warnings"].append(".NET SDK 未安装或不在 PATH 中")
        
        results["package_manager"] = "NuGet"
        
        csproj_files = list(project_path.glob("*.csproj"))
        sln_files = list(project_path.glob("*.sln"))
        
        if csproj_files:
            results["config_files"]["项目文件"] = [f.name for f in csproj_files]
        
        if sln_files:
            results["config_files"]["解决方案文件"] = [f.name for f in sln_files]
        
        appsettings = project_path / "appsettings.json"
        if appsettings.exists():
            results["config_files"]["appsettings.json"] = "存在"
        
        obj_dir = project_path / "obj"
        bin_dir = project_path / "bin"
        
        if obj_dir.exists():
            results["config_files"]["obj 目录"] = "存在"
        if bin_dir.exists():
            results["config_files"]["bin 目录"] = "存在"
        
        results["suggestions"].append("还原依赖: dotnet restore")
        results["suggestions"].append("运行项目: dotnet run")
    
    def _generate_report(self, results: Dict) -> str:
        lines = []
        lines.append("=" * 50)
        lines.append("📋 项目启动预检报告")
        lines.append("=" * 50)
        lines.append("")
        
        lines.append(f"📁 项目路径: {results.get('project_path', '未知')}")
        lines.append(f"🏷️ 项目类型: {results.get('project_type', '未知')}")
        
        if results.get("runtime_version"):
            lines.append(f"🔧 运行时版本: {results['runtime_version']}")
        
        if results.get("package_manager"):
            lines.append(f"📦 包管理器: {results['package_manager']}")
        
        lines.append("")
        lines.append("-" * 50)
        lines.append("📄 配置文件检查")
        lines.append("-" * 50)
        
        config_files = results.get("config_files", {})
        if config_files:
            for name, status in config_files.items():
                if isinstance(status, list):
                    lines.append(f"  {name}: {', '.join(status)}")
                else:
                    lines.append(f"  {name}: {status}")
        else:
            lines.append("  无配置文件信息")
        
        deps = results.get("dependencies", {})
        if deps:
            lines.append("")
            lines.append("-" * 50)
            lines.append("📚 依赖状态")
            lines.append("-" * 50)
            lines.append(f"  需要的依赖: {deps.get('required_count', 0)} 个")
            
            missing = deps.get("missing", [])
            if missing:
                lines.append(f"  ❌ 缺失的依赖: {deps.get('missing_count', 0)} 个")
                for pkg in missing[:10]:
                    lines.append(f"     - {pkg}")
                if len(missing) > 10:
                    lines.append(f"     ... 还有 {len(missing) - 10} 个")
            else:
                lines.append("  ✅ 所有依赖已安装")
        
        warnings = results.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append("-" * 50)
            lines.append("⚠️ 警告")
            lines.append("-" * 50)
            for warning in warnings:
                lines.append(f"  ⚠️ {warning}")
        
        suggestions = results.get("suggestions", [])
        if suggestions:
            lines.append("")
            lines.append("-" * 50)
            lines.append("💡 建议操作")
            lines.append("-" * 50)
            for suggestion in suggestions:
                lines.append(f"  → {suggestion}")
        
        lines.append("")
        lines.append("=" * 50)
        
        return "\n".join(lines)
