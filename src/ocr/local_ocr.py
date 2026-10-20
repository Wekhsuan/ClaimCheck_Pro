"""ClaimCheck Pro 纯本地轻量离线 OCR 引擎 (Local OCR Engine)

基于 rapidocr-onnxruntime 纯 CPU 推理，零云端调用费用，断网可用。
"""

import logging
from pathlib import Path
from typing import List, Tuple, Union
from PIL import Image

logger = logging.getLogger("claimcheck.local_ocr")


class LocalOCREngine:
    """本地纯 CPU OCR 引擎单例封装"""

    def __init__(self):
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        """延迟按需加载 RapidOCR，避免启动开销"""
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
            logger.info("RapidOCR 纯本地引擎初始化成功 (ONNXRuntime CPU)")
        except ImportError:
            logger.warning("未检测到 rapidocr_onnxruntime，本地 OCR 将处于模拟降级状态")
            self._engine = None
        except Exception as e:
            logger.error(f"RapidOCR 初始化异常: {e}")
            self._engine = None

    def extract_text(self, image_input: Union[str, Path, Image.Image, bytes]) -> Tuple[str, List[dict]]:
        """从图片中提取全部文本行与位置置信度信息
        
        返回: (拼接后的完整文本段落, 结构化识别行列表)
        """
        if self._engine is None:
            # 优雅降级：引擎未就绪时返回空，由上层提示用户手动输入
            return "", []

        # RapidOCR 支持文件路径、numpy array 或图片 bytes
        import numpy as np

        if isinstance(image_input, (str, Path)):
            img = Image.open(str(image_input)).convert("RGB")
            img_np = np.array(img)
        elif isinstance(image_input, Image.Image):
            img_np = np.array(image_input.convert("RGB"))
        elif isinstance(image_input, bytes):
            from io import BytesIO
            img = Image.open(BytesIO(image_input)).convert("RGB")
            img_np = np.array(img)
        else:
            raise TypeError("不支持的 OCR 图像输入格式")

        try:
            result, elapse_list = self._engine(img_np)
            if not result:
                return "", []

            extracted_lines = []
            detailed_items = []

            for item in result:
                # RapidOCR 返回格式: [[dt_boxes], text, score]
                box = item[0]
                text = item[1].strip()
                score = float(item[2])
                if text:
                    extracted_lines.append(text)
                    detailed_items.append({
                        "text": text,
                        "confidence": round(score, 3),
                        "box": box,
                    })

            full_text = "\n".join(extracted_lines)
            return full_text, detailed_items

        except Exception as e:
            logger.error(f"本地 OCR 提取执行失败: {e}")
            return "", []


# 全局单例
local_ocr_engine = LocalOCREngine()
