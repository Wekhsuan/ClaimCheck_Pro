"""ClaimCheck Pro Mock AI Provider (离线预置演示)

继承统一基类 AIProvider，供无网无Key答辩演示使用
"""

import json
import time
from typing import Optional
from src.providers.base import AIProvider, ConnectionTestResult


class MockAIProvider(AIProvider):
    """Mock 离线 AI 服务适配器"""

    def test_connection(self) -> ConnectionTestResult:
        """模拟连通性测试，离线环境始终快速响应成功"""
        start = time.perf_counter()
        time.sleep(0.02)  # 模拟 20ms 极低本地延迟
        elapsed = (time.perf_counter() - start) * 1000

        return ConnectionTestResult(
            success=True,
            response_time_ms=round(elapsed, 1),
            supports_text=True,
            supports_json_mode=True,
            supports_vision=True,
            error_message=None,
            details={
                "provider_type": "Mock 离线知识库",
                "status": "已就绪",
                "notes": "无需外部网络，不消耗任何第三方额度",
            },
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        """生成模拟文本或模拟 JSON 结构"""
        if json_mode:
            return json.dumps({
                "status": "mock_success",
                "brand": "声学极客",
                "model": "SoundPro X1",
                "claims": [
                    "主动降噪最大深度达到48dB",
                    "支持LHDC 5.0高清解码",
                    "综合续航达到40小时"
                ]
            }, ensure_ascii=False)
        return (
            "【Mock演示响应】根据离线知识库核验，该商品宣传声明与同型号A级官方规格参数完全吻合，"
            "未发现矛盾点。当前处于Mock演示模式，未产生外部API调用费用。"
        )

    def supports_json_mode(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        return (
            "【Mock视觉识别结果】识别到商品包装盒主图，提取到文字：‘SoundPro X1 旗舰主动降噪耳机’，"
            "型号编码：SPX1-2024，条形码：6971234567890。"
        )
