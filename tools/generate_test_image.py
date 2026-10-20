"""生成阶段4测试使用的商品截图样本 (包含清晰的品牌、型号与技术参数)
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUTPUT_PATH = Path(r"D:\ClaimCheck_Pro\screenshots\test_ocr_input.png")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_sample_product_image():
    # 创建 900x450 的白色背景商品参数卡片
    width, height = 900, 450
    image = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 绘制卡片边框和装饰
    draw.rectangle([20, 20, width - 20, height - 20], outline=(226, 232, 240), width=3)
    draw.rectangle([20, 20, width - 20, 80], fill=(241, 245, 249))

    # 使用系统自带宋体/黑体或默认字体绘制文字
    # Windows 默认中文字体路径
    font_path = r"C:\Windows\Fonts\msyh.ttc"  # 微软雅黑
    if not Path(font_path).exists():
        font_path = r"C:\Windows\Fonts\simsun.ttc"  # 宋体

    try:
        title_font = ImageFont.truetype(font_path, 30)
        body_font = ImageFont.truetype(font_path, 24)
        tag_font = ImageFont.truetype(font_path, 20)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()

    # 绘制标题与品牌
    draw.text((40, 32), "极能 PowerMax 旗舰新品发布", fill=(30, 41, 59), font=title_font)
    
    # 绘制商品名称与型号
    draw.text((50, 110), "商品名称：极能闪充 20000mAh 移动电源", fill=(15, 23, 42), font=body_font)
    draw.text((50, 160), "标准型号：PB-20065", fill=(37, 99, 235), font=body_font)
    draw.text((420, 160), "规格配置：65W 商务灰版", fill=(100, 116, 139), font=body_font)
    
    # 绘制核心规格与卖点
    draw.text((50, 220), "• 单口最大输出功率：Type-C1 支持 65W Max", fill=(51, 65, 85), font=body_font)
    draw.text((50, 270), "• 电池额定容量：20000mAh (74Wh 可带上飞机)", fill=(51, 65, 85), font=body_font)
    draw.text((50, 320), "• 接口配置：双向Type-C + USB-A 三口并发快充", fill=(51, 65, 85), font=body_font)

    # 绘制底部质检标记
    draw.text((50, 385), "制造厂商：极能数字科技有限公司 | 执行标准：GB/T 35590-2017", fill=(148, 163, 184), font=tag_font)

    image.save(OUTPUT_PATH, format="PNG")
    print(f"[OK] Generated test image: {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    create_sample_product_image()
