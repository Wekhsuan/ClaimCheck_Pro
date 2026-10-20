"""ClaimCheck Pro 统一 AI 网关抽象基类 (Provider Base)

规范 Provider 统一行为：
1. 连通性测试 (test_connection)
2. 文本生成 (generate_text)
3. JSON 格式输出检测 (supports_json_mode)
4. 多模态视觉理解检测 (supports_vision)
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from pydantic import BaseModel, Field


class ConnectionTestResult(BaseModel):
    """端点连通性与能力检测综合结果"""
    success: bool = Field(..., description="连接是否成功")
    response_time_ms: float = Field(default=0.0, description="响应耗时(毫秒)")
    supports_text: bool = Field(default=False, description="是否支持文本生成能力")
    supports_json_mode: bool = Field(default=False, description="是否支持标准 JSON 模式")
    supports_vision: bool = Field(default=False, description="是否支持图片输入多模态能力")
    error_message: Optional[str] = Field(default=None, description="清晰的失败原因说明")
    details: Dict[str, str] = Field(default_factory=dict, description="测试诊断明细")


class AIProvider(ABC):
    """统一 AI 网关抽象基类"""

    def get_name(self) -> str:
        """获取 Provider 标准类型名称"""
        return self.__class__.__name__

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        """执行端点连通性与能力检测，返回延迟与能力支持矩阵"""
        pass

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        """调用文本模型生成内容"""
        pass

    @abstractmethod
    def supports_json_mode(self) -> bool:
        """是否支持标准 JSON Mode"""
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """是否支持视觉图像理解"""
        pass

    @abstractmethod
    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """调用多模态视觉能力理解图片"""
        pass
