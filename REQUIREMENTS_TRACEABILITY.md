# ClaimCheck Pro 需求跟踪矩阵 (Requirements Traceability Matrix)

> **文档状态**：全阶段（阶段 1 ~ 阶段 5）需求跟踪与验收测试 100% 全部通过已闭环。  
> **更新时间**：2026-10-18 23:00  
> **当前阶段**：`V0.1.8 Final` - 最终产品整合与终验结项交付完成

---

## 1. 需求状态定义
- `Planning`：已规划，正处于架构设计与环境准备阶段。
- `Not Started`：未开始开发。
- `In Progress`：开发中。
- `Verifying`：开发完成，测试验证中。
- `Done`：已通过测试并验收。

---

## 2. 核心架构与费用控制需求 (REQ-ARCH & REQ-COST)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-COST-01** | **零费用原则**：开发者不承担用户的模型、搜索、OCR、存储或云服务器调用费用；不得内置开发者付费Key；调用失败绝不回退至开发者付费服务。 | 概述 1.2 / 实施 1 | V0.1~V2.0 | 配置与网关 | `src/core/config.py`<br>`src/providers/base.py` | Unit: test_no_fallback_to_dev | Done |
| **REQ-COST-02** | **调用预算控制**：单次最多核验5条声明；每条声明搜索3~5条；文本模型最多调3~5次；视觉模型最多调1次；自动重试1~2次；单任务超时60~120s；默认关闭后台自动任务。 | 概述 八 / 实施 5.2 | V0.1 | 流程编排调度 | `src/providers/budget.py` | Unit: test_budget_tracker_enforcement | Done |
| **REQ-COST-03** | **分析前开销提示与确认**：每次任务开始前向用户明确显示预计调用步骤、次数、预估开销及费用承担方（用户API账户），支持用户随时取消。 | 概述 2.2, 八 / 实施 5.3 | V0.1 | UI交互 & 编排器 | `streamlit_app/app.py` | UI/Integration: test_preflight_prompt | Done |
| **REQ-ARCH-01** | **数据本地化与工作区隔离**：所有代码、环境、缓存、下载、测试报告、截图与Mock数据严格保存在 `D:\ClaimCheck_Pro` 子目录中；敏感配置与Key仅在本地处理。 | 实施说明 / 用户指令 | V0.1~V2.0 | 基础路径管理 | `streamlit_app/config.py`<br>`.env.example` | System: test_paths_confinement | Done |

---

## 3. 三种服务模式需求 (REQ-SRV)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-SRV-01** | **Mock离线演示模式**：内置4~6个预置案例（蓝牙耳机、充电宝、多候选、证据不足等），无Key无网下全流程跑通；界面与报告必须显著标注“演示数据”。 | 概述 2.1 / 实施 2.3 | V0.1 | Mock数据源 & Provider | `mock_data/*.json`<br>`streamlit_app/mock_provider.py` | **T01** (固定测试) | Done |
| **REQ-SRV-02** | **用户自带API模式 (BYOK)**：用户填写OpenAI兼容Base URL、API Key、Model；支持文本/视觉/搜索分别配置；默认仅当前会话使用，勾选记住时本机加密存储。 | 概述 2.2 / 实施 3.1 | V0.1 | OpenAI适配器 | `src/providers/openai_provider.py`<br>`src/core/security.py` | **T02** (固定测试) | Done |
| **REQ-SRV-03** | **用户本地模型模式**：支持配置localhost或局域网内的兼容模型接口（如Ollama/vLLM/LocalAI）及本地OCR；禁止将无认证端口暴露到公网。 | 概述 2.3 / 实施 3.2 | V0.1 | 本地模型适配器 | `src/providers/local_provider.py`<br>`src/core/security.py` | **T03** (固定测试) | Done |
| **REQ-SRV-04** | **Provider适配层与能力检测**：统一接口（test_connection, generate_text, analyze_image, supports_json_mode, supports_vision），支持发送最小请求检测连通性、响应时间与错误原因；不支持视觉时自动降级到本地OCR。 | 实施 3.2, 3.3 / 概述 5.2 | V0.1 | AI网关抽象层 | `src/providers/base.py`<br>`src/providers/openai_provider.py` | Unit: test_providers.py | Done |
| **REQ-SRV-05** | **真实模式与Mock数据彻底物理隔离**：BYOK与Local模式严禁调用MockProvider；反爬或异常直接报错降级，绝不回退至Mock案例；输入指纹失效比对；强安全门禁双重拦截。 | 零费用与数据真实性红线 | V0.1.2 | 核验流水线调度器 | `src/verifier/pipeline.py`<br>`streamlit_app/app.py` | Unit: `tests/test_byok_mock_isolation.py` (16项专项) | Done |

---

## 4. 三种输入方式与商品识别需求 (REQ-INP & REQ-IDENT)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-INP-01** | **公开商品链接输入**：仅允许http/https；防御SSRF（阻止局域网/内网IP）；优先requests+bs4解析JSON-LD Product数据；遇复杂渲染可调Playwright。 | 概述 1.1 / 实施 4.1 | V0.1 | 爬取与网页解析 | `src/crawlers/url_extractor.py`<br>`src/crawlers/ssrf_filter.py` | **T04** (`tests/test_stage4_inputs.py`) | Done |
| **REQ-INP-02** | **防爬反自动化优雅降级**：遇登录墙、验证码、滑块或App专属限制页面时，停止自动抓取，绝不绕过限制，主动提示并降级切换至文本或截图模式。 | 概述 十, 开发规则 / 实施 4.1 | V0.1 | 降级机制 | `src/crawlers/url_extractor.py`<br>`streamlit_app/app.py` | **T08** (`tests/test_stage4_inputs.py`) | Done |
| **REQ-INP-03** | **商品详情文本输入**：支持用户直接粘贴标题、规格与宣传卖点，清洗重复行、多余空白及无关推荐语；提供长度校验与敏感隐私提示。 | 概述 四 / 实施 4.2 | V0.1 | 文本清洗处理器 | `src/parsers/text_parser.py` | Unit: `tests/test_stage4_inputs.py` | Done |
| **REQ-INP-04** | **商品截图输入与本地预处理**：本地Pillow进行图像压缩、尺寸优化与合规质量检查；提供上传前隐私裁剪提示。 | 概述 三 / 实施 4.3 | V0.1 | 图像处理 | `src/ocr/image_processor.py` | Unit: `tests/test_stage4_inputs.py` | Done |
| **REQ-INP-05** | **本地OCR优先文字提取**：默认采用纯本地OCR（避免产生云端OCR费用），从商品截图提取品牌、型号、技术参数。 | 概述 五 / 实施 4.3 | V0.1 | 本地OCR模块 | `src/ocr/local_ocr.py` | Unit: `tests/test_stage4_inputs.py` | Done |
| **REQ-IDENT-01** | **商品身份结构化抽取**：准确识别提取品牌(Brand)、型号(Model)、版本/规格(Version)、容量/颜色、销售地区。 | 概述 四, 六 / 实施 4.3, 六 | V0.1 | 身份抽取模型 | `src/verifier/identity_extractor.py` | Unit: `tests/test_stage4_inputs.py` | Done |
| **REQ-IDENT-02** | **多相似型号候选确认机制**：当截图或文本包含多个相似型号或模糊表述时，列出最多3个候选商品，**强制由用户交互确认后方可开展核验**。 | 概述 3.1, 十 / 实施 4.3, 六 | V0.1 | 候选确认交互 | `src/verifier/identity_extractor.py`<br>`streamlit_app/app.py` | **T05** (`tests/test_stage4_inputs.py`) | Done |
| **REQ-INP-06** | **受限页面结构化降级与继续核验闭环**：遇到平台安全策略拦截时，结构化解析错误码与元数据，呈现白色降级卡片与3项快捷操作；支持自动切至详情文本预填6部分模板，保留原始URL与ID并在真实BYOK模式下无缝继续核验。 | 实施 4.1 / 用户指令 | V0.1.3 | 爬虫与交互调度 | `src/crawlers/url_extractor.py`<br>`streamlit_app/app.py` | `tests/test_restricted_fallback_continuation.py` | Done |
| **REQ-UI-01** | **白色高对比度专业 SaaS 视觉体系**：主背景 `#F6F8FB`，卡片 `#FFFFFF`，文字 `#152033`，两行状态步进器，服务模式抽屉中严格区隔 AI 语言模型与网络搜索服务。 | UI 设计规范 / 用户指令 | V0.1.3 | UI 组件与样式 | `streamlit_app/ui/styles.py`<br>`streamlit_app/ui/components.py` | `tests/test_restricted_fallback_continuation.py` | Done |

---

## 5. 声明拆解、证据检索与交叉验证需求 (REQ-CLAIM, REQ-EVID, REQ-VERIF)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-CLAIM-01** | **最多5条宣传声明拆解**：智能拆解宣传文案，提炼至多5条原子化核验声明（涵盖规格参数、核心功能、实测性能、兼容性、用户体验）。 | 概述 四, 八 / 实施 5.2, 六 | V0.1 | 声明拆解模块 | `src/verifier/claim_decomposer.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-CLAIM-02** | **有效声明质量过滤与门禁**：过滤截图占位符、OCR提示符、空值字段、模板变量及主观营销词；品牌与商品编号元数据物理隔离；质量打分（>=0.65门禁）；归一化至7标准类别；0条有效声明中断拦截与按钮禁用；提供声明确认交互卡片。 | 声明质量专项重构 | V0.1.4 | 声明过滤与确认交互 | `src/verifier/claim_decomposer.py`<br>`streamlit_app/ui/components.py` | `tests/test_claim_quality_phase1.py` (15项) | Done |
| **REQ-SEARCH-01** | **Search Provider 抽象与多源实现**：SearchProvider 抽象类定义 6 大核心方法；NoSearchProvider 零造假空列表保证；TavilySearchProvider 固定 HTTPS 官方端点与 ping 轻量测试；ManualEvidenceProvider 增删改查与 URL 校验。 | 实施计划第二阶段 | V0.1.5 | 搜索抽象与适配器 | `src/search/base.py`<br>`src/search/tavily_provider.py`<br>`src/search/manual_provider.py` | `tests/test_search_provider_phase2.py` (21项) | Done |
| **REQ-SEARCH-02** | **搜索服务与 LLM 彻底分离及预算联动**：Session State 独立解耦；设置抽屉独立搜索模块与密码掩码；三服务边界隔离卡片；预算条动态显示搜索请求数与自理承担方；异常堆栈全脱敏。 | 实施计划第二阶段 | V0.1.5 | UI交互与预算编排 | `streamlit_app/app.py`<br>`streamlit_app/ui/layout.py`<br>`src/providers/budget.py` | `tests/test_search_provider_phase2.py` | Done |
| **REQ-SEARCH-03** | **分层检索词生成与零信任安全正文提取**：实现官方(P1)/评测(P2)/体验(P3)分层规划与4~6条限额；策略B防御（SSRF拦截、5跳手动重定向、2MB流式限额、8s熔断、反爬合规降级）；高密度事实正文段落定位（200~450字）；Tavily Extract 端点接入与 A/B/C/D 证据结构化装配；UI前置显式确认卡片与结果看板审计。 | 实施计划第三阶段 | V0.1.6 | 检索词规划、安全抓取与证据结构化 | `src/search/query_generator.py`<br>`src/crawlers/evidence_fetcher.py`<br>`src/search/evidence_structurer.py`<br>`src/search/tavily_provider.py` | `tests/test_search_execution_phase3.py` (16项) | Done |
| **REQ-EVID-01** | **网络证据检索支持**：配置搜索API（用户自带）时执行实时检索；无搜索API时支持用户手动录入参考链接；Mock模式使用预置证据；严禁伪造实时检索数据。 | 概述 四, 五 / 实施 5.1 | V0.1 | 证据检索适配层 | `src/search/search_adapter.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-EVID-02** | **证据来源A/B/C/D分级体系**：对收集到的证据按权威度严格分级（A级官方/说明书/国标，B级专业实验室/科技媒体，C级垂直自媒体，D级买家评价）。 | 实施 六 / 概述 四 | V0.1 | 证据分级器 | `src/verifier/evidence_classifier.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-EVID-03** | **同型号对齐检查**：严格核对每条检索到的证据是否归属于同品牌、同型号、同版本，防止“拿A型号参数否定B型号宣传”。 | 概述 六 / 实施 六 | V0.1 | 型号对齐器 | `src/verifier/model_alignment.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-VERIF-01** | **四级核验结论判定**：输出“有证据支持”、“部分支持”、“存在冲突”、“证据不足”，对应逻辑必须严格遵循文档标准；无检索到证据不得判定为虚假宣传。 | 概述 七 / 实施 六 | V0.1 | 交叉验证引擎 | `src/verifier/cross_verifier.py` | **T06**, **T07** (`tests/test_stage5_verification.py`) | Done |
| **REQ-VERIF-02** | **二次事实自检 (Self-Consistency)**：在输出结论前执行自检回路，核对引用的证据摘录与推论是否存在逻辑矛盾或大模型幻觉，修正过激断言。 | 概述 六 / 实施 六 | V0.1 | 事实自检器 | `src/verifier/fact_checker.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-VERIF-03** | **法律免责与非鉴定声明**：明确界定工具性质，不得输出正式法律结论、商业欺诈认定或行政质量鉴定，结论页附人工复核提醒与免责条款。 | 概述 四, 开发规则 | V0.1 | 法律免责模块 | `src/verifier/fact_checker.py`<br>`streamlit_app/app.py` | Unit: `tests/test_stage5_verification.py` | Done |
| **REQ-VERIF-04** | **五态型号对齐与十项证据有效性**：严格判定 exact/probable/series_only/mismatch/unknown；排除 mismatch 与 D级营销软文；正文有效摘录必须 >= 20字；反爬拦截页排除；SHA-256 指纹去重归一。 | 实施计划第四阶段 | V0.1.7 | 型号对齐与证据有效性 | `src/verifier/model_alignment.py`<br>`src/verifier/evidence_validator.py` | `tests/test_evidence_verification_phase4.py` (30项) | Done |
| **REQ-VERIF-05** | **六维可信度加权打分与六问差异化理由**：100分制量化打分（来源25/型号25/相关15/信源15/一致15/完整5）；回答六大核心问题；两两相似度>0.85确定性事实重写；十五条事实自检铁律；六大标准板块报告。 | 实施计划第四阶段 | V0.1.7 | 可信度打分、理由生成与报告编排 | `src/verifier/cross_verifier.py`<br>`src/verifier/reason_generator.py`<br>`src/verifier/fact_checker.py`<br>`streamlit_app/ui/components.py` | `tests/test_evidence_verification_phase4.py` (30项) | Done |

---

## 6. 报告生成与本地存储需求 (REQ-REP & REQ-STORE)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-REP-01** | **多格式核验报告导出**：第一版支持导出规范的 Markdown 与 TXT 格式报告，包含商品信息、声明拆解、分级证据、四级结论、置信度、服务模式与免责声明。 | 概述 3.2 / 实施 7 | V0.1 | 报告生成引擎 | `streamlit_app/report.py` | Integration: test_report_export | Done |
| **REQ-REP-02** | **历史记录本地持久化**：分析结果与元数据默认保存在用户电脑本地 SQLite；允许用户单条删除或一键清空全部历史记录。 | 概述 3.1 / 实施 7 | V0.1~V1.0 | 本地存储数据库 | `src/storage/db.py`<br>`src/storage/models.py` | Unit: test_history_crud | Planning |
| **REQ-REP-03** | **文档格式扩展 (Word/PDF)**：预留并实现 Word (.docx) 和 PDF 格式的导出支持。 | 概述 3.2 / 实施 7 | V1.0~V1.5 | 报告扩展包 | `src/reports/docx_exporter.py`<br>`src/reports/pdf_exporter.py` | Integration: test_docx_pdf_export | Planning |

---

## 7. 第五阶段产品整合与终验交付需求 (REQ-FINAL)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-FINAL-01** | **极简六步操作流程**：标准化：1)选择服务模式，2)提交商品资料，3)确认商品身份，4)确认宣传声明，5)搜索与核验证据，6)查看和导出报告；高级设置折叠。 | 终验要求 | V0.1.8 | UI 状态机 | `streamlit_app/app.py` | `tests/test_final_end_to_end_phase5.py::test_01_mock_complete_pipeline_flow` | Done |
| **REQ-FINAL-02** | **三项核心服务彻底解耦**：AI模型服务、网页读取器、网络搜索服务三模块独立展示；未配置搜索严守 0 外部请求与 0 费用防线。 | 终验要求 | V0.1.8 | UI 设置与网关 | `streamlit_app/ui/layout.py`<br>`src/search/no_search_provider.py` | `tests/test_final_end_to_end_phase5.py::test_02_byok_only_user_data_analysis` | Done |
| **REQ-FINAL-03** | **12类标准化友好异常卡片**：统一三段式布局（发生了什么、为什么发生、下一步怎么做）；彻底消灭底层 Python 崩溃红框。 | 终验要求 | V0.1.8 | UI 异常组件 | `streamlit_app/ui/components.py` | `tests/test_final_end_to_end_phase5.py::test_05_link_restricted_text_fallback` | Done |
| **REQ-FINAL-04** | **一键启动与端口顺延**：`启动ClaimCheck Pro.bat` 检查 Python 环境与依赖，端口 8501 占用时自动平移顺延至 8502 端口并弹窗提示。 | 终验要求 | V0.1.8 | 启动守护脚本 | `启动ClaimCheck Pro.bat`<br>`关闭与重新启动说明.txt` | 手动/批处理校验 | Done |
| **REQ-FINAL-05** | **端到端全量测试与12张验收截图**：补充 16 项 Phase 5 E2E 用例，全量 163 项测试 100% 通过；归档 12 张高保真验收截图并完成零泄露扫描。 | 终验要求 | V0.1.8 | 质量保障体系 | `tests/test_final_end_to_end_phase5.py`<br>`screenshots/final_acceptance/` | 163/163 PASS & 0 泄露 | Done |

---

## 8. 多搜索服务 Provider 扩展需求 (REQ-SEARCH)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-SEARCH-01** | **五大搜索 Provider 抽象与工场扩展**：支持 Tavily、Kimi (`/v1/tools/search` 等新接口)、通义千问 (Responses API 与 Chat)、手动证据与未配置模式。 | 多搜索方案 | V0.1.9 | 搜索适配器层 | `src/search/` | `tests/test_multi_search_providers.py` | Done |
| **REQ-SEARCH-02** | **5 维度能力探测矩阵**：支持文本模型、网页搜索、来源URL、正文抓取、Responses API 5 维能力检测，前端展示彩色徽章。 | 多搜索方案 | V0.1.9 | 能力检测模型 | `src/search/base.py`<br>`streamlit_app/ui/layout.py` | `tests/test_multi_search_providers.py` | Done |
| **REQ-SEARCH-03** | **模型与搜索严格解耦警示**：聊天成功不等于搜索可用；当 Key 仅支持普通对话但搜索接口失败时，标记为 `chat_ok_search_fail` 并阻断。 | 多搜索方案 | V0.1.9 | 解耦校验模块 | `src/search/base.py`<br>`streamlit_app/ui/layout.py` | `tests/test_multi_search_providers.py` | Done |
| **REQ-SEARCH-04** | **来源追溯性保护与一票否决**：无来源 URL 时标记 `traceable=False`，分类器强制一票否决禁止晋升 A/B/C 级，降为 D 级并提示用户。 | 多搜索方案 | V0.1.9 | 证据分类器 | `src/verifier/evidence_classifier.py` | `tests/test_multi_search_providers.py` | Done |
| **REQ-SEARCH-05** | **阶段 3 前置 4 维预算确认卡片**：展示预估请求数、分层词数、抓取上限与费用主体，用户显式点击确认后执行。 | 多搜索方案 | V0.1.9 | 前端交互组件 | `streamlit_app/ui/components.py` | `tests/test_multi_search_providers.py` | Done |

---

## 9. 密钥与隐私安全规范 (REQ-SEC)

| 需求ID | 需求描述 | 来源文档 | 目标版本 | 计划实现模块 | 对应代码文件 | 对应测试 | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-SEC-01** | **API Key全局脱敏与防泄漏**：界面展示仅保留首尾字符掩码；日志、异常堆栈、导出报告、前端源码中绝对不打印或持久化真实Key。 | 概述 5.3 / 实施 3.4, 10 | V0.1~V2.0 | 安全脱敏器 | `src/core/security.py`<br>`src/core/logger.py` | Unit: test_key_masking | Done |
| **REQ-SEC-02** | **凭据生命周期管理**：默认单会话有效，退出即清空；勾选保存时使用本地操作系统凭据或本地密钥加密；不向移动前端传递完整Key。 | 概述 5.3 / 实施 3.1, 10 | V0.1~V1.0 | 凭据管理 | `src/core/security.py` | Unit: test_credential_lifecycle | Planning |
| **REQ-SEC-03** | **平台凭据边界**：绝不收集或存储用户淘宝、拼多多等电商平台的账号与密码；未来若扩展仅支持平台官方OAuth授权流程。 | 概述 九 / 实施 10 | V0.1~V2.0 | 安全边界控制 | `src/core/security.py` | Audit: test_no_platform_pwd_storage | Done |

---

## 8. 八大固定测试用例跟踪 (REQ-TEST)

| 测试编号 | 测试场景描述 | 验收标准与预期结果 | 对应测试用例代码 | 覆盖需求ID | 当前状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **T01** | Mock离线模式运行 | 在断网、无任何API Key的环境下，全流程顺畅运行预置案例（耳机/充电宝等），页面与报告明确标出“演示数据”。 | `tests/test_fixed_t01_to_t08.py::test_t01_mock_offline_complete_run` | REQ-SRV-01 | Done (100%) |
| **T02** | 用户API有效与无效配置测试 | 输入正确和错误的Base URL / Key / Model，系统能精准识别有效/无效状态，输出耗时或清晰的失败原因说明。 | `tests/test_fixed_t01_to_t08.py::test_t02_user_api_configurations` | REQ-SRV-02, REQ-SRV-04 | Done (100%) |
| **T03** | 本地模型连接与兼容性 | 配置本地 Ollama/vLLM (localhost/局域网) 地址，成功完成连通性检测并执行最小文本推理任务。 | `tests/test_fixed_t01_to_t08.py::test_t03_local_model_endpoint_address` | REQ-SRV-03 | Done (100%) |
| **T04** | 公开商品链接提取与拆解 | 针对公开静态商品页面（如测试用HTML夹具），解析JSON-LD或DOM，成功抽取品牌型号与宣传要点。 | `tests/test_fixed_t01_to_t08.py::test_t04_public_link_and_claim_decomposition` | REQ-INP-01, REQ-CLAIM-01 | Done (100%) |
| **T05** | 截图存在多个相似型号候选确认 | 传入包含多型号信息的测试截图或文本，系统给出不超过3个候选型号，交互等待用户确认后继续。 | `tests/test_fixed_t01_to_t08.py::test_t05_screenshot_candidate_confirmation` | REQ-INP-04, REQ-IDENT-02 | Done (100%) |
| **T06** | 官方证据支持与部分支持判定 | 分别注入符合“同型号A级证据一致”和“核心成立但省略限定条件”的测试用例，正确判定为“有证据支持”和“部分支持”。 | `tests/test_fixed_t01_to_t08.py::test_t06_supported_and_partially_supported` | REQ-VERIF-01 | Done (100%) |
| **T07** | 官方资料冲突与证据不足判定 | 分别注入“同型号高可信证据矛盾”和“无法检索到有效同型号资料”的用例，正确判定为“存在冲突”和“证据不足”，严禁误判为虚假宣传。 | `tests/test_fixed_t01_to_t08.py::test_t07_conflict_and_insufficient_evidence` | REQ-VERIF-01 | Done (100%) |
| **T08** | 遇到登录或验证码页面降级处理 | 针对返回302重定向登录、403反爬阻查、滑块验证码的模拟URL，自动终止爬取并友好提示切换至文本或截图模式。 | `tests/test_fixed_t01_to_t08.py::test_t08_login_captcha_restricted_graceful_fallback` | REQ-INP-02 | Done (100%) |

---

## 9. 跨阶段演进跟踪 (REQ-ROADMAP)

- [x] **Phase 1 (V0.1)**: Streamlit课程原型、Mock体系、BYOK网关、三入口、8大测试全绿、最终验收通过。
- [ ] **Phase 2 (V1.0)**: 拆分 FastAPI 统一后端，提供标准化 REST API，基于本地 SQLite 存储；构建 Flutter Web 响应式网页版。
- [ ] **Phase 3 (V1.5)**: 构建 Flutter Android APP，实现局域网配对（配对码/二维码）、相机拍照与系统分享监听。
- [ ] **Phase 4 (V2.0)**: 官方平台扩展（开放平台资质申请、官方OAuth授权接入）。
