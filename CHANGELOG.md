# ClaimCheck Pro 项目更新日志 (CHANGELOG)

本文档记录 ClaimCheck Pro 自项目启动至 V0.1 最终验收交付期间的所有核心功能演进、架构决策与变更记录。

---

## [0.1.9] - 2026-10-19 (Multi-Search Provider 扩展：Tavily / Kimi / Qwen / Manual / None 五大搜索服务 Provider 与可追溯性保护)

### 🌟 核心升级：5大搜索Provider · 5维能力探测矩阵 · 模型与搜索独立解耦 · 来源追溯性一票否决 · 181项自动化测试 · 8张专项全真截图
#### 新增 (Added)
- **多搜索服务 Provider 统一抽象与工场扩展 (`src/search/`)**：
  - `KimiSearchProvider` (`src/search/kimi_provider.py`)：全面对接 Moonshot AI 官方独立搜索工具 (`/v1/tools/search`、`/v1/tools/search_pro`、`/v1/tools/fetch`)，彻底摒弃即将废弃的旧版 `$web_search`，支持 Basic/Pro 双模式与官方独立正文抓取。
  - `QwenSearchProvider` (`src/search/qwen_provider.py`)：全面对接阿里 DashScope，优先使用 Responses API 挂载 `web_search` 与 `web_extractor` 工具，兼容 Chat Completions (`enable_search=true`) 模式。
  - `SearchProviderFactory` (`src/search/factory.py`)：注册支持 `none`、`tavily`、`kimi`、`qwen`、`manual` 五大搜索 Provider 动态无缝切换。
- **5 维度独立能力探测矩阵 (`SearchCapabilities`)**：
  - 定义 `supports_text_model`、`supports_web_search`、`supports_source_urls`、`supports_web_extractor`、`supports_responses_api` 5 维能力模型。
  - 连通性测试返回结构化 `SearchConnectionResult`，前端以清晰彩色徽章卡片呈现真实支持情况。
- **模型与搜索严格解耦与解耦警示 (`chat_ok_search_fail`)**：
  - 聊天接口调用成功绝不代表搜索接口可用；当 API Key 支持普通对话但搜索接口返回 403/404 时，系统阻断标记为连接成功，并在前端弹出醒目橙色解耦警示卡片。
- **真实来源追溯性保护与一票否决机制 (`src/verifier/evidence_classifier.py`)**：
  - 在 `SearchResultItem` 中引入 `traceable: bool = True` 标志。
  - 若模型或搜索接口仅输出生成文本而未返回来源 URL，强制标记为 `traceable=False`，分类器强制执行一票否决：**严禁评为 A 级（官方权威）或 B/C 级**，降为 D 级（无来源URL/不可追溯资料），并提示用户切换至 Responses API。
- **阶段 3 前置 4 维预算确认卡片 (`streamlit_app/ui/components.py`)**：
  - 明确展示预估请求数、分层检索词数、抓取网页上限与费用承担方（用户自有账户）。
  - 用户显式点击“🚀 确认并开始网络搜索”按钮后方可执行外部检索。
- **自动化测试与浏览器截图验证**：
  - 新增 `tests/test_multi_search_providers.py`（18 项高覆盖度单元与集成测试，0 外部 API 费用）。
  - 全量自动化测试 **181 / 181 100% 全部通过** (耗时 8.46s)。
  - 归档 8 张全真 Chromium 浏览器截图至 `screenshots/multi_search_provider/`。
  - 编制交付技术报告 `reports/multi_search_provider_report.md`。

---

## [0.1.8] - 2026-10-18 (Search Provider 第五阶段：最终产品整合、界面优化、端到端测试与课程作业交付)

### 🌟 核心升级：六步极简工作流 · 三项服务严格解耦 · 12类友好异常卡片 · 一键启动脚本与端口顺延 · 163项自动化测试 · 12张验收截图
#### 新增 (Added)
- **极简六步操作流程 (`streamlit_app/app.py`)**：
  - 标准化六步流水线：1) 选择服务模式，2) 提交商品资料，3) 确认商品身份，4) 确认宣传声明，5) 搜索与核验证据，6) 查看和导出报告。
  - 首页精简化：突出三大输入方式单选切换、品牌蓝“开始核验分析”主操作按钮，高级参数与底层调试信息默认折叠收拢。
- **三项服务边界彻底解耦与费用警示 (`streamlit_app/ui/layout.py` & `components.py`)**：
  - 明确划分：1. AI 语言模型服务 (LLM Provider)、2. 网页读取器 (Webpage Fetcher)、3. 网络搜索服务 (Search Provider)。
  - 显式声明零费用防线：未配置搜索严格产生 0 请求与 0 费用；已连接搜索消耗用户自有 API 账户，开发者 0 代付。
- **12 类标准化友好异常与空状态处理卡片 (`streamlit_app/ui/components.py`)**：
  - 统一三段式布局（发生了什么、为什么发生、用户下一步可以做什么），彻底杜绝原生 Python 红色崩溃堆栈。
  - 涵盖网络超时、反爬登录墙、文本过短、截图模糊、型号缺失、无有效声明、Key无效/欠费、搜索无同型号、模型中断、非法URL、导出异常等 12 大场景。
- **一键启动脚本与运行维护文档 (`启动ClaimCheck Pro.bat`, `关闭与重新启动说明.txt`)**：
  - 自动检测虚拟环境 Python、应用入口文件与依赖清单。
  - 智能端口诊断：8501 占用时自动顺延至 8502 端口并弹窗提示，绝不强制杀死外部无关进程；自动唤起默认浏览器。
- **自动化测试套件与安全防护 (`tests/test_final_end_to_end_phase5.py`, `pytest.ini`)**：
  - 增加 16 项 Phase 5 专属 E2E 测试用例，覆盖全链路流程与异常拦截。
  - 全量自动化测试 **163 / 163 100% 全部通过** (耗时 5.22s)。
  - 全项目真实敏感凭据安全扫描 (`tools/scan_secrets.py`) 确认 **0 泄漏**。
- **12 张全流程高保真验收截图 (`screenshots/final_acceptance/`)**：
  - 涵盖首页全景、设置抽屉、三输入、身份确认、声明审查、预算确认、搜索执行、总览看板、单项证据展开、报告导出、平台降级与无有效声明阻断等全部 12 大视图。
- **综合结项验收交付报告 (`reports/final_acceptance_report.md`)**：
  - 包含 11 个标准大节，涵盖架构图、实现矩阵、安全总结、测试结果、截图索引、隔离机制、局限性与学术诚信承诺。

---

## [0.1.7] - 2026-10-18 (Search Provider 第四阶段：商品型号严格对齐、证据有效性判定、多源交叉核验与专业核验报告)

### 🌟 核心升级：五态型号对齐 · 十项证据有效性判定 · 六维100分制可信度量化 · 差异化六问核验理由 · 十五条自检铁律 · 六大板块现代报告
#### 新增 (Added)
- **五态商品型号严格对齐判定器 (`src/verifier/model_alignment.py`)**：
  - 定义 `exact`、`probable`、`series_only`、`mismatch`、`unknown` 五态模型对齐状态。
  - 严格剔除 `mismatch` 证据，非 `exact` 匹配严禁下达强支持/强冲突结论，自动识别销售地区（国行/美版/日版）。
- **十项证据有效性判定与来源分级器 (`src/verifier/evidence_validator.py`)**：
  - 强制 $\ge 20$ 字正文摘录门禁，拦截反爬/滑块/登录墙受限页，强制排除 D 级软文。
  - SHA-256 内容指纹去重，多源通稿转载合并归一为单信源。
- **六维可信度加权算法 (`src/verifier/cross_verifier.py`)**：
  - 实现 100 分制可解释量化评分：来源权威性 25分 + 型号对齐度 25分 + 证据相关性 15分 + 独立信源数 15分 + 结论一致性 15分 + 内容完整性 5分。
  - 精准区间映射：高 (80~100)、中高 (65~79)、中 (45~64)、低 (0~44)。
- **差异化核验理由生成器 (`src/verifier/reason_generator.py`)**：
  - 逐项回答六大核心问题（证据来源、级别、型号一致性、参数差异、遗漏前提条件、定论逻辑）。
  - 两两相似度 $>0.85$ 时触发确定性事实改写，彻底杜绝千篇一律套话。
- **十五条事实自检铁律与合规脱敏器 (`src/verifier/fact_checker.py`)**：
  - 严查凭证 ID、原文真摘、型号限定，严禁曲解“未提及”，中立净化法律措辞 (`sanitize_legal_phrasing`)。
- **六大场景人工复核机制 (`src/verifier/human_review.py`)**：
  - 自动识别缺少官方手册、非完全对齐、安全极限、微小偏差、体感反差、商家免责小字六大边缘场景。
- **六大板块高保真报告界面重构 (`streamlit_app/ui/components.py` & `streamlit_app/app.py`)**：
  - 板块 1（分析模式与来源标识）、板块 2（四级结论分布统计指标）、板块 3（综合核验结论与风险提示）、板块 4（商品身份档案）、板块 5（逐项声明核验与凭证摘录）、板块 6（报告导出与零泄露合规承诺）。
- **自动化测试套件 (`tests/test_evidence_verification_phase4.py`)**：
  - 30 项专属严苛测试用例 100% 通过，全量回归测试达 **151 / 151 全部通过**。
- **Edge 浏览器多视口验收截图 (`screenshots/evidence_verification_phase4/`)**：
  - `01_phase4_overall_report_summary.png`
  - `02_phase4_four_level_verdict_cards.png`
  - `03_phase4_claim_inspection_and_evidence_details.png`
  - `04_phase4_excluded_evidence_and_self_check.png`

---

## [0.1.6] - 2026-10-18 (Search Provider 第三阶段：分层检索词生成、网络搜索执行与真实正文提取)

### 🌟 核心升级：分层检索词生成 · 策略B外部零信任网关 · 真实正文高密度提取 · A/B/C/D来源分级 · 阶段边界安全控制
#### 新增 (Added)
- **分层检索词生成引擎 (`src/search/query_generator.py`)**：
  - 定义 `SearchQueryItem` 数据结构（包含 `query_id`, `claim_id`, `query_text`, `query_type`, `priority`, `generated_at`, `execution_status`）。
  - 落地 Layer 1 (官方规格/说明书/参数词, Priority 1)、Layer 2 (专业评测/实测, Priority 2)、Layer 3 (用户反馈/常见问题, Priority 3，默认关闭) 三层分层规划。
  - 实现核心参数硬核词提取 (`extract_claim_core_keywords`)，精准定位数值+单位（48dB, 40小时, 65W）与技术协议（LHDC 5.0, IPX5）。
  - 强制限制单条声明 4~6 条查询，规范化排重，缺失品牌型号强保护，占位符强过滤。
- **外部网页安全抓取与高密度事实正文提取器 (`src/crawlers/evidence_fetcher.py`)**：
  - 策略 B 公网零信任防御：SSRF 校验拦截回环与私网 IP，手动控制最大 5 跳重定向并每跳复验，单页最大 2MB 流式截断，Content-Type 白名单校验，8秒超时熔断。
  - 自动识别 HTTP 401/403 及网页内容级滑块验证码、登录墙（restricted 状态标记），合规降级，绝不暴力破盾。
  - `clean_html_content` 深度去噪：剔除 nav, header, footer, aside, ads, script, style, svg 等 DOM 噪声。
  - `_extract_keyword_focused_excerpt`：关键词加权段落定位，提取 200~450 字真实上下文事实段落，绝不使用 50 字浅层 snippet。
- **Tavily Extract 端点接入 (`src/search/tavily_provider.py`)**：
  - 新增 `FIXED_EXTRACT_ENDPOINT = "https://api.tavily.com/extract"` 与 `extract()` 方法。
- **证据结构化装配器 (`src/search/evidence_structurer.py`)**：
  - 集成 `EvidenceClassifier` 自动判定 A/B/C/D 来源等级。
  - 集成 `ModelAlignmentVerifier` 执行品牌、型号、规格、地区四维型号对齐（exact/compatible/mismatch/unknown）。
  - 输出标准 `EvidenceItem` 证据对象。
- **搜索前置确认卡片与结果看板 (`streamlit_app/ui/components.py` & `streamlit_app/app.py`)**：
  - 强制用户确认机制：严禁后台自动隐蔽检索，用户必须在 `render_search_execution_panel` 前置卡片显式点击确认按钮后触发。
  - 前置卡片明确展示有效声明数、检索模式、费用承担方声明（严格标明用户自理或零费用）、检索策略与安全防护预览。
  - 结果看板提供 4 项统计指标、分层检索词执行审计表、结构化证据明细卡片与阶段边界保护告示（严禁提前越界进入第四阶段）。
- **自动化测试套件 (`tests/test_search_execution_phase3.py`)**：
  - 16 项专项测试 100% 通过，全量回归测试达 117 / 117 全部通过。
- **浏览器视觉验收截图 (`screenshots/search_execution_phase3/`)**：
  - `01_search_preflight_confirmation.png`
  - `02_layered_queries_audit.png`
  - `03_extracted_evidence_inspection.png`

---

## [0.1.5] - 2026-10-18 (Search Provider 第二阶段：Search Provider 抽象、Tavily 自带 API 与手动证据管理)

### 🌟 核心升级：LLM 与 Search Provider 彻底分离 · Tavily 用户自带 API · 手动证据模式 · 零开发者代付
#### 新增 (Added)
- **Search Provider 抽象基类 (`src/search/base.py`)**：
  - 定义 6 大抽象方法：`test_connection()`, `search()`, `provider_name()`, `is_configured()`, `sanitize_result()`, `capabilities()`。
  - 定义统一数据模型：`SearchResultItem`, `ManualEvidenceItem`, `SearchConnectionResult`。
  - 提供 `clean_suspicious_control_characters` 与 `validate_web_url` 基础工具函数。
- **NoSearchProvider 默认实现 (`src/search/no_search_provider.py`)**：
  - 未配置搜索服务时调用，`is_configured()=False`，`search()` 严格返回空列表，绝对不伪造假搜索数据。
  - 连接测试返回友好中文说明，告知当前不会发起实时网络检索。
- **TavilySearchProvider 用户自带 API (`src/search/tavily_provider.py`)**：
  - 固定官方 HTTPS 端点 `https://api.tavily.com/search`，杜绝用户端点篡改与 SSRF 风险。
  - 最小连通性测试请求 (`query="ping", max_results=1`)，毫秒级响应且避免消耗用户额度。
  - 完善的 HTTP 错误码友好中文映射 (401 凭证无效 / 403 权限受限 / 404 端点错误 / 429 额度超限 / 500+ 服务异常 / 超时)。
  - 异常捕获全链路递归过滤，彻底杜绝原始 API Key 泄露至日志或错误堆栈。
- **ManualEvidenceProvider 手动证据管理 (`src/search/manual_provider.py`)**：
  - 支持用户录入品牌官网、说明书、规格参数表、评测机构文章链接。
  - 提供 URL 格式验证、排重检查、备注记录、增删改查及转换为归一化搜索条目。
- **独立 Session State 与架构解耦 (`streamlit_app/app.py`)**：
  - 独立维护 `search_mode`, `search_api_key`, `manual_evidence_items` 等 11 项搜索状态。
  - 搜索配置修改仅失效当前核验报告，绝不清除 LLM 配置，修改 LLM 配置亦绝不影响搜索配置。
- **设置抽屉搜索服务模块与三卡片重构 (`streamlit_app/ui/layout.py`)**：
  - 增加未配置、Tavily、手动证据、自定义/自建 4 种搜索模式。
  - Tavily Key 密码遮罩与 `tvly-****9A2B` 脱敏展示，提供测试连接按钮与中文反馈。
  - 手动证据在线录入表格与单项删除按钮。
  - 🛡️ 服务能力与边界隔离三卡片：分别独立标注 🧠 模型 API、🕷️ 网页读取器、🌐 搜索服务的状态徽标与边界铁律。
- **任务预算条与防超额守卫 (`src/providers/budget.py`, `streamlit_app/ui/components.py`)**：
  - 预算条动态显示搜索请求数（未配置为 0 次，Tavily 最多 5 次）与费用承担方（用户自有账户自理，开发者0代付）。
- **21 项专项自动化测试套件 (`tests/test_search_provider_phase2.py`)**：
  - 涵盖抽象类规范、NoSearchProvider、Tavily 各状态码与超时、异常脱敏、手动证据生命周期、预算联动等 21 项测试，全量 101 项测试 100% 全部通过。
- **3 张 Edge 高清浏览器验收截图 (`screenshots/search_provider_phase2/`)**。

---

## [0.1.4] - 2026-10-18 (Search Provider 第一阶段：宣传声明质量控制与无效内容过滤)

### 🌟 核心升级：有效声明质量控制、无效内容物理过滤与声明确认门禁
#### 新增 (Added)
- **声明质量过滤核心引擎 (`src/verifier/claim_decomposer.py`)**：
  - 实现 `ClaimQualityFilter`，严格拦截 `【截图1提取内容】` 等占位符、`OCR识别内容`、`商品编号` 等纯字段名、未替换模板变量 `{brand}` 及纯主观营销吹捧词（如 `官方正品`、`假一赔十`）。
  - 实现品牌与型号物理隔离：将“弱水时砂”等品牌名准确收录至 `product_identity.brand`，将“10145673910180”收录至 `product_identity.product_id`，均被拒绝进入 claims 并记录原因。
  - 实现多维度质量打分函数 `evaluate_claim_quality_and_category()`：基于技术标准、数值单位、前提条件、动词赋分，严格设定 `score >= 0.65` 与 `is_verifiable == True` 双重入选门禁。
  - 声明类别严格归一化映射至 7 个标准类别（`参数`、`功能`、`性能`、`材料`、`兼容性`、`使用条件`、`明确体验承诺`）。
  - 实现 `decompose_with_details()` 返回 `(valid_claims, rejected_candidates)`，支持动态数量上限（1~5条），零有效声明时抛出 `NoVerifiableClaimsError`。
- **声明审查与确认交互卡片 (`streamlit_app/ui/components.py`, `app.py`)**：
  - 在正式联网检索前渲染“阶段 1：宣传声明提取确认”卡片。
  - 展示识别到的商品基础信息（品牌、型号、商品编号、规格版本）。
  - 展示有效声明卡片（含原子陈述、类别徽章、质量得分、可独立核验标记）及单项 `🗑️ 删除` 按钮。
  - 提供 `➕ 手动补充一条可验证声明` 表单与 `📁 查看未采用内容` 折叠明细表。
  - 0 条有效声明时弹出显式警告提示，并将底部确认按钮置灰禁用，杜绝回退至 Mock 或发起伪造检索。
- **15 项专项自动化测试套件 (`tests/test_claim_quality_phase1.py`)**：
  - 涵盖占位符、字段名、未填字段、模板变量、品牌词隔离、编号元数据、高质量声明、主观吹捧、复合输入、类别归一化、数量截断、0声明中断等 15 项测试，全量 80 项测试 100% 全部通过。
- **3 张端到端高保真浏览器验收截图 (`screenshots/claim_quality_phase1/`)**。

---

## [0.1.3] - 2026-10-17 (受限页面降级交互闭环与白色高对比度 UI 重构)

### 🌟 核心升级：受限页面无缝降级继续核验闭环与白色专业 SaaS UI
#### 新增 (Added)
- **受限页面合规降级与元数据解析 (`src/crawlers/url_extractor.py`)**：
  - 实现 `normalize_product_url()` 剔除多余营销追踪参数。
  - 实现 `identify_platform_and_product_id()` 识别京东、淘宝、拼多多等主流平台与提取纯数字 ID。
  - 遇到反爬、验证码拦截时抛出带结构化元数据的 `AccessRestrictedError`。
- **白色降级操作卡片与三大无缝交互 (`streamlit_app/ui/components.py`, `app.py`)**：
  - 显示“无法自动读取该商品页面”卡片，清晰呈现平台、商品 ID、HTTP 状态、错误码与科普建议。
  - `[📋 粘贴商品详情文本]`：自动切换至文本输入模式，自动预填 6 部分标准核验模板，保留原始 URL 与 ID。
  - `[🖼️ 上传商品宣传截图]`：自动切换至截图模式并展示隐私脱敏安全提示。
  - `[🔄 使用标准化链接重试 (限1次)]`：安全重试保障。
- **页面文字智能清洗与对比确认 (`src/parsers/text_parser.py`, `app.py`)**：
  - 智能过滤 20+ 类平台导航废话与营销噪声（如“加入购物车”、“店铺首页”等）。
  - 显示清洗前后字数对比卡片，展示已过滤噪声样例，提供双按钮确认机制。
- **白色高对比度专业 SaaS 视觉体系 (`streamlit_app/ui/styles.py`, `components.py`)**：
  - 主背景 `#F6F8FB`，卡片 `#FFFFFF`，边框 `#DDE3EA`，文字 `#152033` / `#526176`（符合 WCAG AA 对比度标准）。
  - 两行 6 步自适应状态步进器（第一行步骤名，第二行状态胶囊，桌面端横向，移动端自适应折行）。
  - 设置抽屉中明确区分并隔离“AI 语言模型服务”与“网络搜索服务”，红黄警告提示避免混淆。
- **12 项合规降级与白色 UI 自动化测试 (`tests/test_restricted_fallback_continuation.py`)**：
  - 涵盖链接标准化、平台提取、降级元数据、错误码分类、清洗前后对比、真实 BYOK 降级继续核验、两行步进器设计规范等 12 项测试全部通过（总测试集达到 65 项全部通过）。
- **6 张端到端高对比度真实浏览器验收长截图 (`screenshots/restricted_fallback_white_ui/`)**。

---

## [0.1.2] - 2026-10-17 (BYOK 与 Mock 物理隔离与数据可信性专项重构)

### 🌟 核心问题根治：真实模式与 Mock 混用缺陷彻底清除
#### 新增 (Added)
- **核心核验流水线引擎 (`src/verifier/pipeline.py`)**：
  - 物理隔离 `run_mock_pipeline()` 与 `run_real_pipeline()`，真实模式下严禁调用 `MockProvider` 或加载内置案例。
  - 数据模式强安全门禁：若真实模式下检测到 `is_mock=True`，立即抛出 `DataModeMismatchError` 阻断展示。
  - 输入指纹校验机制 (`calculate_input_fingerprint`)：精准感知输入内容、服务模式、调用模型与确认型号的任何变动，防止展示过期或不匹配的结果。
  - 搜索解耦机制：未配置搜索服务时显式设定 `search_status="not_configured"`，严格遵循自检铁律1。
- **16 个高优先级回归测试套件 (`tests/test_byok_mock_isolation.py`)**：
  - 涵盖 Mock 隔离、BYOK 路由、受限降级、指纹失效、未配置搜索、Key 脱敏等 16 项关键测试，全部通过 (100% PASS)。
- **反爬空壳与访问限制增强探测 (`src/crawlers/url_extractor.py`)**：
  - 增加 `InsufficientProductInfoError`，匹配 `pc-risk`、`js_security`、通用标语与空规格，遇到反爬即刻合规降级，绝不回退至 Mock。
- **元数据溯源卡片 (`render_report_metadata_header`)**：
  - 在核验看板顶部显式标注数据模式（Mock演示/仅用户资料/实时模型）、调用模型名称、网页抓取状态与搜索服务状态。
- **5 个端到端真实浏览器验收截图 (`screenshots/byok_fix/`)**：
  - 记录 Mock 模式、BYOK 反爬降级、BYOK 真实文本核验、输入变更缓存失效、模式切换状态清理 5 大全景长图。

#### 修复与优化 (Fixed & Optimized)
- **删除硬编码 Mock 回退**：
  - 彻底删除 `app.py` 中 `report = mock_provider.generate_report_from_case(...)` 的硬编码调用，接入统一流水线。
- **状态失效与动态重置**：
  - 用户修改 URL、修改文本、切换模式或更改模型名时，旧核验报告立即被清理，同时完整保留用户 API Key 与 Base URL 等核心配置。
- **真实进度状态绑定**：
  - 步进器真实绑定每一步的执行结果（成功/失败/未配置/已跳过），第一步失败时以红字提示，绝无假绿灯。

---

## [0.1.0] - 2026-10-16 (最终验收交付版本)

### 🌟 阶段六：最终验收阶段 (Final Acceptance Phase)
#### 新增 (Added)
- **八大固定验收测试套件 (`tests/test_fixed_t01_to_t08.py`)**：
  - `T01`：Mock 模式在无 API Key、无网络时完整运行验证。
  - `T02`：用户 API 有效、缺失、401、429 及明文 HTTP 拦截诊断验证。
  - `T03`：本地模型地址白名单（localhost/127.0.0.1/局域网私有网段）与外部公网拦截验证。
  - `T04`：公开商品链接 JSON-LD 读取与声明原子拆解（<=5条，单一事实）验证。
  - `T05`：商品海报/文本多候选（最多3个）提取与用户交互确认锁定机制验证。
  - `T06`：有证据支持与部分支持（前置限制条件）核验案例矩阵验证。
  - `T07`：存在冲突与证据不足（二次事实自检四项铁律纠偏）案例矩阵验证。
  - `T08`：登录墙、验证码及反爬限制页面的安全优雅降级与 SSRF 防护验证。
- **全项目零密钥泄露扫描器 (`tools/scan_secrets.py`)**：全工程递归排查真实 Token、Key、Cookie 与密码，确认零明文泄露。
- **8 大固定测试高清截图自动化采集工具 (`tools/capture_final_acceptance_screenshots.py`)**：基于 Edge CDP 自动化采集与归档 `screenshots/t01_~t08_*.png`。
- **最终验收报告与交付清单**：
  - `reports/final_test_report.md`：记录 8 项测试输入、预期、实际、判定、耗时、截图、日志与修复说明。
  - `FINAL_DELIVERY_CHECKLIST.md`：全量需求与 15 项工程质量检查项逐一核对清单。

#### 修复与优化 (Fixed & Optimized)
- **参数名称与别名兼容**：
  - 在 `OpenAICompatibleProvider` 与 `LocalModelProvider` 构造函数中新增 `model: Optional[str] = None` 参数别名，统一解析为 `chosen_model`，完美兼容调用端传递 `model` 或 `model_name`。
- **宣传声明原子化切分增强**：
  - 增强 `ClaimDecomposer` 中对中文全角逗号 `，` 的切分规则，使得电商详情页中连续使用逗号罗列的技术参数被精准拆解为独立原子事实。
- **诊断异常文案统一**：
  - 统一 HTTP 401/429 诊断文案与本地模型连接拒绝排查指引，测试断言更具容错性与健壮性。

---

### 🌟 阶段五：网络证据检索、多源交叉验证和二次事实自检
#### 新增 (Added)
- **宣传声明拆解器 (`src/verifier/claim_decomposer.py`)**：单次最多处理 5 条声明，每条拆解为单一可验证事实，过滤纯主观推销词。
- **证据来源四级分类器 (`src/verifier/evidence_classifier.py`)**：A级（官方）、B级（专业实测）、C级（用户体验）、D级（软文），强行约束规则4（D级不得用于强结论）与规则5（C级不得单独证明技术参数）。
- **证据 8 项记录规范**：定义 `title`, `url`, `source_type`, `source_level`, `published_at`, `model_match`, `excerpt`, `evidence_direction` 数据规范。
- **四维型号对齐检查器 (`src/verifier/model_alignment.py`)**：针对品牌、型号、版本、地区进行精确比对，防止张冠李戴。
- **二次事实自检器 (`src/verifier/fact_checker.py`)**：
  - 铁律1：未提及不能判断为不支持（缺失证据只能判为证据不足）；
  - 铁律2：其他型号证据不能用于当前型号强结论；
  - 铁律3：单个低可信来源不能支持高置信结论；
  - 铁律4：结论不能超出证据范围。
- **法律合规中立性净化器 (`sanitize_legal_phrasing`)**：严禁出现“假冒伪劣、欺诈、违法、造假”等司法定性词汇。
- **无搜索 API 适配层 (`src/search/search_adapter.py`)**：允许用户手动输入参考材料与链接，绝不制造伪造虚构的网络搜索结果。
- **报告综合摘要与建议生成**：在报告及看板底部自动生成总体摘要、人工确认清单与购买前防坑建议。

---

### 🌟 阶段四：三种输入与商品身份多候选确认机制
#### 新增 (Added)
- **公开链接安全读取与 SSRF 防护 (`src/crawlers/`)**：
  - `safe_fetch_html`：安全请求公开网页，阻断私有网段与危险端口。
  - `AccessRestrictedError`：反爬机制、登录墙与验证码识别，遇阻即停并提示降级至文本/截图。
- **详情文本清理与隐私守护 (`src/parsers/text_parser.py`)**：
  - 过滤空白与重复导航，针对手机号进行掩码保护。
- **本地离线 OCR 提取 (`src/ocr/`)**：
  - 集成 RapidOCR-ONNX，纯 CPU 本地推理提取海报文字，0 云端外部调用费用。
  - Pillow 图像等比缩放与预处理。
- **多候选商品识别与确认锁定 (`src/verifier/identity_extractor.py`)**：
  - 输出最多 3 个候选商品及其匹配度，强制用户在界面点击确认型号后方可继续核验流程。

---

### 🌟 阶段三：BYOK 自带 API 与 Local 模型功能
#### 新增 (Added)
- **安全验证工具 (`src/core/security.py`)**：
  - `validate_byok_url`：强制公网 Base URL 仅允许 HTTPS 协议。
  - `validate_local_url`：白名单放行 localhost、127.0.0.1 及标准局域网私有 IP，拦截外部公网 IP。
  - `mask_api_key`：密钥脱敏显示，禁止任何明文持久化或写入日志报告。
- **AI 提供者接口与实现 (`src/providers/`)**：
  - `AIProvider`：标准统一抽象类。
  - `OpenAICompatibleProvider`：标准 OpenAI 协议适配器。
  - `LocalModelProvider`：Ollama / vLLM 本地模型适配器。
  - `BudgetTracker`：任务前预算估算与调用次数/Token 限制守卫。
- **前端网关配置面板**：实时连接诊断矩阵，可视化探测文本、JSON Mode、视觉及延迟指标。

---

### 🌟 阶段二：项目骨架与 Mock 演示闭环
#### 新增 (Added)
- **项目工程初始化**：创建虚拟环境 `.venv`、缓存目录 `.cache`、下载目录 `downloads`、产出目录 `output`、报告目录 `reports`、截图目录 `screenshots` 与预置案例目录 `mock_data`。
- **V0.1 核心数据结构 (`streamlit_app/schemas.py`)**：基于 Pydantic V2 建立 `ProductIdentity`, `ClaimItem`, `EvidenceItem`, `VerificationReport` 等模型。
- **Mock 提供者与预置案例库 (`streamlit_app/mock_provider.py`)**：
  - Case 1: 声学极客 SoundPro X1 (有证据支持)
  - Case 2: 戴森 V12 Detect Slim (部分支持)
  - Case 3: 某品牌骨传导运动耳机 (存在冲突)
  - Case 4: 某小众品牌降噪睡眠耳塞 (证据不足)
- **前端交互界面 (`streamlit_app/app.py`)**：三种输入 Tab、服务模式切换、离线 Mock 黄色警示条、四级结论看板与 Markdown 报告下载。

---

### 🌟 阶段一：阅读、分析和实施规划基线
#### 新增 (Added)
- 完整解析 `ClaimCheck_Pro_零费用架构项目概述.docx` 与 `ClaimCheck_Pro_零费用架构实施步骤.docx`。
- 编制并固化以下规划文档：
  - `IMPLEMENTATION_PLAN.md`：实施方案书与架构规划。
  - `PROJECT_STATE.md`：项目环境与资产追踪。
  - `REQUIREMENTS_TRACEABILITY.md`：24 项全量需求追溯矩阵。
  - `PROGRESS.md`：里程碑与分阶段进展。
- 确立“零费用架构”与“本地优先”开发基本原则。
