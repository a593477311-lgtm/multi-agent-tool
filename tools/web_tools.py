import requests
from typing import Dict, Any, Optional
from .base import Tool

class HTTPRequestTool(Tool):
    @property
    def name(self) -> str:
        return "http_request"
    
    @property
    def description(self) -> str:
        return "发送HTTP请求。参数：url（请求地址）、method（请求方法，默认GET）、headers（请求头，可选）、body（请求体，可选）"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "请求的URL地址"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP请求方法",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
                },
                "headers": {
                    "type": "object",
                    "description": "请求头（JSON对象）"
                },
                "body": {
                    "type": "string",
                    "description": "请求体内容"
                }
            },
            "required": ["url"]
        }
    
    def execute(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[str] = None,
        **kwargs
    ) -> str:
        try:
            method = method.upper()
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=body,
                timeout=30
            )
            
            result = [
                f"状态码: {response.status_code}",
                f"响应头: {dict(response.headers)}",
            ]
            
            try:
                json_data = response.json()
                result.append(f"响应体 (JSON): {json_data}")
            except:
                result.append(f"响应体: {response.text[:2000]}")
            
            return "\n".join(result)
        except requests.Timeout:
            return "错误：请求超时（30秒）"
        except requests.RequestException as e:
            return f"请求失败: {str(e)}"
        except Exception as e:
            return f"执行请求失败: {str(e)}"
