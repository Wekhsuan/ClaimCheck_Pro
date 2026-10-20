"""ClaimCheck Pro 报告生成与导出模块 (Report Generator)

支持生成 Markdown 与 TXT 格式报告，并保存至 output/ 目录
严格遵循零费用原则与脱敏要求，标记演示数据水印
"""

from pathlib import Path
from streamlit_app.config import OUTPUT_DIR
from streamlit_app.schemas import VerificationReport


class ReportGenerator:
    """报告生成器"""

    @staticmethod
    def generate_markdown(report: VerificationReport) -> str:
        """生成 Markdown 格式报告文本"""
        lines = []
        lines.append(f"# ClaimCheck Pro 商品真实性与一致性核验报告")
        lines.append(f"")
        lines.append(f"> **报告编号**：`{report.report_id}`  ")
        lines.append(f"> **核验时间**：{report.task_timestamp}  ")
        lines.append(f"> **运行模式**：`{report.service_mode.upper()}`  ")
        if report.is_mock:
            lines.append(f"> **数据模式**：当前为Mock演示数据，未执行实时网络核验 (is_mock=True)  ")
        else:
            lines.append(f"> **数据模式**：实时网络核验 (is_mock=False)  ")

        if getattr(report, "input_type", "") == "image" or "截图" in (report.evidence_scope or ""):
            lines.append(f"> **检索方式**：基于图片文字与商品特征的联网检索 (非传统反向图片搜索)  ")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        
        # 1. 商品身份卡片
        lines.append(f"## 一、商品身份确认 (Product Identity)")
        lines.append(f"| 项目 | 确认结果 |")
        lines.append(f"| :--- | :--- |")
        lines.append(f"| **品牌 (Brand)** | {report.product.brand} |")
        lines.append(f"| **型号 (Model)** | {report.product.model} |")
        lines.append(f"| **版本/规格 (Version)** | {report.product.version} |")
        lines.append(f"| **关键参数 (Specs)** | {report.product.specs or '无'} |")
        lines.append(f"| **销售地区 (Region)** | {report.product.sales_region} |")
        lines.append(f"| **身份抽取置信度** | {int(report.product.confidence * 100)}% |")
        lines.append(f"")
        
        # 2. 四级核验结论分布摘要
        lines.append(f"## 二、总体综合摘要与四级结论统计 (Summary)")
        if report.overall_summary:
            lines.append(f"> 📝 **总体综合摘要**：{report.overall_summary}")
            lines.append(f"")
        lines.append(f"| 核验结论类型 | 涉及声明数量 | 判定规则释义 |")
        lines.append(f"| :--- | :---: | :--- |")
        lines.append(f"| 🟢 **有证据支持** | {report.conclusion_summary.get('有证据支持', 0)} | 同型号A级官方证据充分支持，无实质冲突 |")
        lines.append(f"| 🟡 **部分支持** | {report.conclusion_summary.get('部分支持', 0)} | 核心宣称成立，但省略前置条件、扩大范围或实测有轻度差异 |")
        lines.append(f"| 🔴 **存在冲突** | {report.conclusion_summary.get('存在冲突', 0)} | 同型号高可信权威资料与宣传直接相左矛盾 |")
        lines.append(f"| ⚪ **证据不足** | {report.conclusion_summary.get('证据不足', 0)} | 缺少同型号有效佐证，保持客观中立（不判定为虚假） |")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")
        
        # 3. 逐项声明核验详情 (最多5条)
        lines.append(f"## 三、宣传声明拆解与多源证据核验明细 (最多5条)")
        for idx, item in enumerate(report.claims_results, 1):
            claim = item.claim
            conclusion_tag = {
                "有证据支持": "🟢 【有证据支持】",
                "部分支持": "🟡 【部分支持】",
                "存在冲突": "🔴 【存在冲突】",
                "证据不足": "⚪ 【证据不足】"
            }.get(item.conclusion.value if hasattr(item.conclusion, 'value') else str(item.conclusion), str(item.conclusion))
            
            lines.append(f"### 声明 {idx}：{claim.atomic_statement}")
            lines.append(f"- **宣传原文摘录**：*“{claim.original_text}”*")
            lines.append(f"- **单一可验证事实**：`{claim.single_verifiable_fact or claim.atomic_statement}`")
            lines.append(f"- **声明类别 / 核验指标**：`{claim.category}` / `{claim.verification_target}`")
            lines.append(f"- **核验结论**：{conclusion_tag} (置信度: {int(item.confidence * 100)}%)")
            lines.append(f"- **核验理由分析**：{item.analysis_reason}")
            lines.append(f"- **二次事实自检**：{'✅ 通过自检' if item.self_check_passed else '🛡️ 自检纠偏'} ({item.self_check_notes})")
            if item.self_check_rules_evaluated:
                lines.append(f"  - *评估规则*：{' | '.join(item.self_check_rules_evaluated)}")
            if item.pre_purchase_tips:
                for tip in item.pre_purchase_tips:
                    lines.append(f"- **购买核验提示**：💡 {tip}")
            lines.append(f"")
            lines.append(f"#### 支撑证据列表 (8项记录规范)：")
            if not item.evidences:
                lines.append(f"> *暂无可用的外部有效证据。*")
            else:
                for e_idx, e in enumerate(item.evidences, 1):
                    # 取 8 规范字段
                    e_title = e.title or e.source_title or "公开证据"
                    e_url = e.url or e.source_url or ""
                    e_type = e.source_type or "官方资料"
                    e_level = e.source_level.value if hasattr(e.source_level, 'value') else str(e.source_level)
                    e_date = e.published_at or e.published_date or "未标注日期"
                    e_match = e.model_match or ("exact" if e.model_matched else "mismatch")
                    e_excerpt = e.excerpt or e.snippet or ""
                    e_dir = e.evidence_direction or "support"
                    
                    match_badge = "✅ 严格同型号对齐" if e_match == "exact" else f"⚠️ 型号状态: {e_match}"
                    url_str = f" [🔗 来源链接]({e_url})" if e_url else " *(本地或未公开URL)*"
                    dir_tag = {"support": "支持", "contradict": "冲突", "partial": "部分支持", "neutral": "中立"}.get(e_dir, e_dir)
                    
                    lines.append(f"{e_idx}. **[{e_level}] {e_title}**{url_str}")
                    lines.append(f"   - **来源类型**：`{e_type}` | **证据倾向**：`{dir_tag}` | **型号对齐**：`{match_badge}`")
                    lines.append(f"   - **发布时间**：{e_date}")
                    lines.append(f"   - **核心证据摘录**：> *{e_excerpt}*")
            lines.append(f"")
        
        lines.append(f"---")
        lines.append(f"")
        
        # 4. 人工确认项与购买前建议
        lines.append(f"## 四、人工确认项与购买前建议")
        lines.append(f"### 4.1 人工确认清单 (Human Verification Checklist)")
        items_list = report.human_verification_items or report.human_verification_notes or []
        if items_list:
            for note in items_list:
                lines.append(f"- ⚠️ {note}")
        else:
            lines.append(f"- 暂无特殊人工确认提示。")
        lines.append(f"")
        
        lines.append(f"### 4.2 购买前决策与防坑建议 (Pre-Purchase Advice)")
        if report.pre_purchase_advice:
            for advice in report.pre_purchase_advice:
                lines.append(f"- 💡 {advice}")
        else:
            lines.append(f"- 建议优先选择官方旗舰店或授权经销商，索取正规发票以保障售后权益。")
        lines.append(f"")
        
        lines.append(f"## 五、法律合规与客观中立声明")
        lines.append(f"> {report.disclaimer}")
        lines.append(f"")
        lines.append(f"*(本报告由 ClaimCheck Pro 智能引擎离线生成)*")
        
        return "\n".join(lines)

    @staticmethod
    def generate_text(report: VerificationReport) -> str:
        """生成纯文本 TXT 格式报告"""
        md_text = ReportGenerator.generate_markdown(report)
        # 简易文本清洗去除部分 markdown 标记
        text = md_text.replace("## ", "").replace("### ", "--- ").replace("#### ", "")
        text = text.replace("**", "").replace("*", "")
        return text

    @staticmethod
    def save_report_to_disk(report: VerificationReport) -> Path:
        """将报告保存到 output 目录中"""
        md_content = ReportGenerator.generate_markdown(report)
        file_path = OUTPUT_DIR / f"{report.report_id}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        return file_path
