"""
MCP (Model Context Protocol) 模块

提供MCP服务器连接和工具适配功能，将MCP工具集成到骤雨OS的工具系统中。
"""

from .config import MCPConfig, MCPServerConfig
from .adapter import MCPToolAdapter
from .client import MCPClientManager

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPToolAdapter",
    "MCPClientManager",
]
