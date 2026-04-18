"""
MCP配置管理模块

提供MCP服务器配置的加载和管理功能。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from utils.logger import get_logger

logger = get_logger()


@dataclass
class MCPServerConfig:
    """单个MCP服务器的配置"""
    
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""
    timeout: int = 30
    
    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "MCPServerConfig":
        """从字典创建配置对象"""
        return cls(
            name=name,
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            description=data.get("description", ""),
            timeout=data.get("timeout", 30),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "enabled": self.enabled,
            "description": self.description,
            "timeout": self.timeout,
        }


@dataclass
class MCPConfig:
    """MCP整体配置管理类"""
    
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)
    config_path: Optional[Path] = None
    
    @classmethod
    def from_json_file(cls, config_path: Path) -> "MCPConfig":
        """从JSON文件加载配置
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            MCPConfig实例
            
        Raises:
            FileNotFoundError: 配置文件不存在
            json.JSONDecodeError: JSON格式错误
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            logger.warning(f"MCP配置文件不存在: {config_path}")
            return cls(config_path=config_path)
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"MCP配置文件JSON格式错误: {e}")
            raise
        
        servers = {}
        servers_data = data.get("mcpServers", {})
        
        for name, server_data in servers_data.items():
            try:
                server_config = MCPServerConfig.from_dict(name, server_data)
                servers[name] = server_config
                logger.debug(f"加载MCP服务器配置: {name}")
            except Exception as e:
                logger.error(f"加载MCP服务器配置失败 [{name}]: {e}")
        
        logger.info(f"成功加载 {len(servers)} 个MCP服务器配置")
        return cls(servers=servers, config_path=config_path)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        """从字典创建配置对象"""
        servers = {}
        servers_data = data.get("mcpServers", {})
        
        for name, server_data in servers_data.items():
            server_config = MCPServerConfig.from_dict(name, server_data)
            servers[name] = server_config
        
        return cls(servers=servers)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "mcpServers": {
                name: config.to_dict() 
                for name, config in self.servers.items()
            }
        }
    
    def save_to_file(self, config_path: Optional[Path] = None) -> None:
        """保存配置到JSON文件
        
        Args:
            config_path: 保存路径，默认使用加载时的路径
        """
        path = config_path or self.config_path
        if path is None:
            raise ValueError("未指定配置文件保存路径")
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"MCP配置已保存到: {path}")
    
    def add_server(self, config: MCPServerConfig) -> None:
        """添加服务器配置"""
        self.servers[config.name] = config
        logger.info(f"添加MCP服务器配置: {config.name}")
    
    def remove_server(self, name: str) -> bool:
        """移除服务器配置
        
        Returns:
            是否成功移除
        """
        if name in self.servers:
            del self.servers[name]
            logger.info(f"移除MCP服务器配置: {name}")
            return True
        return False
    
    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """获取指定服务器配置"""
        return self.servers.get(name)
    
    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """获取所有已启用的服务器配置"""
        return [s for s in self.servers.values() if s.enabled]
    
    def create_default_config(self, config_path: Path) -> None:
        """创建默认配置文件模板
        
        Args:
            config_path: 配置文件路径
        """
        default_config = {
            "mcpServers": {
                "example-server": {
                    "command": "python",
                    "args": ["-m", "example_mcp_server"],
                    "env": {},
                    "enabled": False,
                    "description": "示例MCP服务器（已禁用）",
                    "timeout": 30
                }
            }
        }
        
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"已创建默认MCP配置文件: {config_path}")
