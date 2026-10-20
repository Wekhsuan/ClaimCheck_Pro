"""ClaimCheck Pro 本地图像预处理模块 (Image Processor)

使用 Pillow 进行格式校验、安全尺寸检测与本地压缩
"""

import base64
import io
from pathlib import Path
from typing import Tuple, Union
from PIL import Image
from pydantic import BaseModel, Field


class ProcessedImageResult(BaseModel):
    """图像处理结果"""
    format: str
    width: int
    height: int
    file_size_bytes: int
    is_resized: bool
    base64_data: str
    privacy_notice: str = Field(
        default="⚠️ 隐私安全提醒：上传商品截图前，请务必自行裁剪或遮盖收货地址、个人姓名、联系电话、聊天记录及订单编号等隐私敏感信息。"
    )


ALLOWED_FORMATS = ["PNG", "JPEG", "JPG", "WEBP"]


def process_and_optimize_image(
    image_input: Union[str, Path, bytes, io.BytesIO],
    max_dimension: int = 1920,
    jpeg_quality: int = 85,
) -> ProcessedImageResult:
    """对用户上传的商品截图进行本地格式校验、质量检查与尺寸优化压缩"""
    if isinstance(image_input, (str, Path)):
        img = Image.open(str(image_input))
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, io.BytesIO):
        img = Image.open(image_input)
    else:
        raise TypeError("不支持的图像输入类型")

    fmt = (img.format or "PNG").upper()
    if fmt == "JPG":
        fmt = "JPEG"

    if fmt not in ALLOWED_FORMATS:
        raise ValueError(f"不支持的图像格式 '{fmt}'，仅支持 PNG、JPG、JPEG、WEBP 格式截图。")

    orig_w, orig_h = img.size
    if orig_w < 100 or orig_h < 100:
        raise ValueError(f"图片尺寸过小 ({orig_w}x{orig_h})，无法准确识别文字与技术参数，请上传清晰截图。")

    # 转为 RGB 模式进行兼容性保存
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    is_resized = False
    # 若尺寸超大则按比例等比缩放
    if orig_w > max_dimension or orig_h > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        is_resized = True

    # 本地压缩为高质量 JPEG 字节流
    out_buffer = io.BytesIO()
    img.save(out_buffer, format="JPEG", quality=jpeg_quality, optimize=True)
    compressed_bytes = out_buffer.getvalue()
    b64_str = base64.b64encode(compressed_bytes).decode("ascii")

    return ProcessedImageResult(
        format="JPEG",
        width=img.size[0],
        height=img.size[1],
        file_size_bytes=len(compressed_bytes),
        is_resized=is_resized,
        base64_data=b64_str,
    )
