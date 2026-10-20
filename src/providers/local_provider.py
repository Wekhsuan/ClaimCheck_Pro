"""ClaimCheck Pro 本地模型兼容适配器 (LocalModelProvider)

适用于用户电脑或局域网内运行的 Ollama / vLLM / LocalAI 等兼容接口。
严格遵循：
1. 仅允许 localhost、127.0.0.1 及合法局域网地址；
2. 禁止将未经认证的本地端口指向公网；
3. 本地模型无需云端 API Key，完全保障隐私与零外部调用费用。
"""

import json
import logging
import time
from typing import Optional
import requests

from src.core.security import validate_local_url
from src.providers.base import AIProvider, ConnectionTestResult

logger = logging.getLogger("claimcheck.provider.local")


class LocalModelProvider(AIProvider):
    """用户本地模型服务适配器"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model_name: str = "qwen2.5:7b",
        api_key: Optional[str] = None,
        timeout: int = 45,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ):
        chosen_model = model or model_name
        self.raw_base_url = base_url.strip() if base_url else "http://127.0.0.1:11434/v1"
        self.model_name = chosen_model.strip() if chosen_model else "qwen2.5:7b"
        self.api_key = api_key.strip() if api_key else "local-key-not-required"
        self.timeout = max(5, int(timeout))
        self.temperature = max(0.0, min(1.0, float(temperature)))
        self.max_tokens = max(128, int(max_tokens))

        # 安全验证本地地址
        is_valid, validated_or_err = validate_local_url(self.raw_base_url)
        if not is_valid:
            self.base_url = None
            self.url_error = validated_or_err
        else:
            self.base_url = validated_or_err
            self.url_error = None

    def _get_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClaimCheck-Pro-Local/0.1",
        }
        if self.api_key and self.api_key != "local-key-not-required":
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def test_connection(self) -> ConnectionTestResult:
        """测试本地模型服务连通性与兼容性"""
        if not self.base_url:
            return ConnectionTestResult(
                success=False,
                error_message=f"本地端点地址校验未通过: {self.url_error}",
                details={"target_url": self.raw_base_url},
            )

        endpoint = f"{self.base_url}/chat/completions"
        start_time = time.perf_counter()

        test_payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "temperature": 0.0,
        }

        try:
            resp = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=test_payload,
                timeout=self.timeout,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 1)

            if resp.status_code == 404:
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message=f"本地端点响应 404：模型 '{self.model_name}' 未安装或 Base URL 路径错误。请确认已在本地执行了 `ollama run {self.model_name}`。",
                    details={"status_code": "404", "endpoint": endpoint},
                )
            elif resp.status_code != 200:
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message=f"本地服务返回错误状态码 HTTP {resp.status_code}：{resp.text[:200]}",
                    details={"status_code": str(resp.status_code)},
                )

        except requests.exceptions.ConnectionError:
            return ConnectionTestResult(
                success=False,
                error_message=(
                    f"无法连接到本地服务 ({self.base_url})。请确认：\n"
                    "1. 本地 Ollama / vLLM / LocalAI 服务是否已在电脑后台启动；\n"
                    "2. 端口号（如 11434）是否正确，未被防火墙阻拦。"
                ),
                details={"base_url": self.base_url},
            )
        except requests.exceptions.Timeout:
            return ConnectionTestResult(
                success=False,
                error_message=f"本地模型响应超时（超过 {self.timeout} 秒），请检查本地硬件推理负载。",
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                error_message=f"本地模型检测未知异常: {str(e)}",
            )

        # 检查本地模型视觉特征
        supports_vis = "vl" in self.model_name.lower() or "vision" in self.model_name.lower()

        return ConnectionTestResult(
            success=True,
            response_time_ms=elapsed_ms,
            supports_text=True,
            supports_json_mode=True,  # 绝大多数本地兼容端点支持JSON模式
            supports_vision=supports_vis,
            error_message=None,
            details={
                "model": self.model_name,
                "base_url": self.base_url,
                "environment": "本地局域网私有环境",
                "privacy": "数据完全留存在本地硬件",
            },
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        if not self.base_url:
            raise ValueError(f"本地端点地址非法: {self.url_error}")

        endpoint = f"{self.base_url}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = requests.post(
            endpoint,
            headers=self._get_headers(),
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"本地模型推理失败 (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def supports_json_mode(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return "vl" in self.model_name.lower() or "vision" in self.model_name.lower()

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        if not self.supports_vision():
            raise NotImplementedError(
                f"本地模型 '{self.model_name}' 未启用视觉支持，已自动切换为纯本地离线 OCR。"
            )
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                    ],
                }
            ],
            "max_tokens": self.max_tokens,
        }
        resp = requests.post(
            endpoint,
            headers=self._get_headers(),
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"本地视觉模型调用失败: {resp.text[:200]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]
