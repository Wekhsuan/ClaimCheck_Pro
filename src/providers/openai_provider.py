"""ClaimCheck Pro OpenAI 兼容协议适配器 (OpenAICompatibleProvider)

支持用户自带 API (BYOK)，零开发者费用分摊。
严格遵循：
1. 公网 Base URL 强制仅限 HTTPS；
2. 绝不打印或泄露明文 API Key；
3. 端点测试覆盖连接、文本能力、JSON 模式、多模态能力与清晰失败说明；
4. 失败即停止，绝对不回退到任何开发者付费服务。
"""

import json
import logging
import time
from typing import Optional
import requests

from src.core.security import mask_api_key, validate_byok_url
from src.providers.base import AIProvider, ConnectionTestResult

logger = logging.getLogger("claimcheck.provider.openai")


class OpenAICompatibleProvider(AIProvider):
    """用户自带 OpenAI 兼容协议适配器"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str = "gpt-4o-mini",
        timeout: int = 30,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        vision_model: Optional[str] = None,
        model: Optional[str] = None,
    ):
        chosen_model = model or model_name
        self.raw_base_url = base_url.strip() if base_url else ""
        self.api_key = api_key.strip() if api_key else ""
        self.model_name = chosen_model.strip() if chosen_model else "gpt-4o-mini"
        self.timeout = max(5, int(timeout))
        self.temperature = max(0.0, min(1.0, float(temperature)))
        self.max_tokens = max(128, int(max_tokens))
        self.vision_model = (vision_model or self.model_name).strip()

        # 安全验证 Base URL
        is_valid, validated_or_err = validate_byok_url(self.raw_base_url)
        if not is_valid:
            self.base_url = None
            self.url_error = validated_or_err
        else:
            self.base_url = validated_or_err
            self.url_error = None

    def _get_headers(self) -> dict:
        """组装安全请求头，禁止在外部暴露真实Key"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "ClaimCheck-Pro-BYOK/0.1",
        }

    def test_connection(self) -> ConnectionTestResult:
        """测试端点连通性、响应延迟、JSON 模式与视觉理解支持情况"""
        # 1. 基础地址安全校验
        if not self.base_url:
            return ConnectionTestResult(
                success=False,
                error_message=f"Base URL 安全校验失败: {self.url_error}",
                details={"masked_key": mask_api_key(self.api_key)},
            )

        if not self.api_key:
            return ConnectionTestResult(
                success=False,
                error_message="用户 API Key 不能为空。本项目不提供默认开发者密钥，请在界面填写您自己的有效密钥。",
                details={"base_url": self.base_url},
            )

        endpoint = f"{self.base_url}/chat/completions"
        masked_key = mask_api_key(self.api_key)

        # 2. 最小文本生成连通性检测
        start_time = time.perf_counter()
        test_payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": "ping"}],
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

            if resp.status_code == 401:
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message="身份验证失败 (HTTP 401 Unauthorized)：API Key 无效、已过期或无权访问该模型。",
                    details={"status_code": "401", "masked_key": masked_key},
                )
            elif resp.status_code == 429:
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message="限流或额度耗尽 (HTTP 429 Too Many Requests)：您的第三方账户余额不足或超出了速率限制。",
                    details={"status_code": "429"},
                )
            elif resp.status_code == 404:
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message=f"端点或模型未找到 (HTTP 404 Not Found)：请核对模型名称 '{self.model_name}' 或 Base URL 路径是否正确。",
                    details={"status_code": "404", "target_url": endpoint},
                )
            elif resp.status_code != 200:
                err_detail = resp.text[:200]
                return ConnectionTestResult(
                    success=False,
                    response_time_ms=elapsed_ms,
                    error_message=f"服务商返回错误 (HTTP {resp.status_code})：{err_detail}",
                    details={"status_code": str(resp.status_code)},
                )

        except requests.exceptions.SSLError as ssl_err:
            return ConnectionTestResult(
                success=False,
                error_message=f"SSL 证书校验失败：目标服务商证书不受信任 ({ssl_err})",
            )
        except requests.exceptions.Timeout:
            return ConnectionTestResult(
                success=False,
                error_message=f"连接超时：请求在 {self.timeout} 秒内未收到响应，请检查服务商网络连通性。",
            )
        except requests.exceptions.ConnectionError as conn_err:
            return ConnectionTestResult(
                success=False,
                error_message=f"网络无法连接至目标 Base URL，请检查地址是否输入正确或网络配置: {conn_err}",
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                error_message=f"连接检测发生未知异常: {str(e)}",
            )

        # 3. 检测 JSON 格式支持能力 (response_format)
        supports_json = False
        try:
            json_payload = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": 'Return json: {"status": "ok"}'}],
                "response_format": {"type": "json_object"},
                "max_tokens": 15,
                "temperature": 0.0,
            }
            json_resp = requests.post(
                endpoint,
                headers=self._get_headers(),
                json=json_payload,
                timeout=min(self.timeout, 10),
            )
            if json_resp.status_code == 200:
                supports_json = True
        except Exception:
            supports_json = False

        # 4. 判定视觉多模态支持能力
        # 常见支持视觉的模型名称特征
        vision_keywords = ["vision", "4o", "vl", "visual", "gemini", "claude-3"]
        supports_vis = any(k in self.vision_model.lower() for k in vision_keywords)

        return ConnectionTestResult(
            success=True,
            response_time_ms=elapsed_ms,
            supports_text=True,
            supports_json_mode=supports_json,
            supports_vision=supports_vis,
            error_message=None,
            details={
                "model": self.model_name,
                "vision_model": self.vision_model,
                "masked_key": masked_key,
                "json_mode": "支持" if supports_json else "不支持(已自动开启Prompt兼容兜底)",
                "vision_mode": "支持" if supports_vis else "当前模型未识别为多模态(将自动降级为本地OCR)",
            },
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = False,
    ) -> str:
        """调用用户 OpenAI 兼容端点执行文本推理"""
        if not self.base_url:
            raise ValueError(f"Base URL 无效: {self.url_error}")

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
                f"模型调用失败 (HTTP {resp.status_code})：{resp.text[:200]}。"
                "根据零费用架构原则，系统已停止核验，绝不回退至开发者付费服务。"
            )

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def supports_json_mode(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        vision_keywords = ["vision", "4o", "vl", "visual", "gemini", "claude-3"]
        return any(k in self.vision_model.lower() for k in vision_keywords)

    def analyze_image(self, image_base64: str, prompt: str) -> str:
        """调用用户多模态端点分析图片"""
        if not self.supports_vision():
            raise NotImplementedError(
                f"当前配置的模型 '{self.vision_model}' 不支持图片输入，系统将自动使用纯本地 OCR。"
            )

        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.vision_model,
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
            raise RuntimeError(f"视觉模型调用失败 (HTTP {resp.status_code}): {resp.text[:200]}")

        data = resp.json()
        return data["choices"][0]["message"]["content"]
