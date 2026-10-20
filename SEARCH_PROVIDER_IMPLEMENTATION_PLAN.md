# ClaimCheck Pro 声明质量过滤与独立 Search Provider (Tavily) 实施方案
# (Search Provider & Claim Quality Architecture Implementation Plan)

> **文档状态**：待用户批准确认 (Pending Approval)  
> **规划版本**：V2.0 (针对有效声明清洗、Tavily 搜索服务集成与 20 项专项测试全面修订)  
> **工作区目录**：`D:\ClaimCheck_Pro`  
> **执行纪律**：本方案仅作为设计与实施规划，当前**不安装依赖、不修改核心业务代码**，待用户审查批准后方可按阶段推进。

---

## 目录 (Table of Contents)

1. [背景诊断与核心整改目标](#1-背景诊断与核心整改目标)
2. [修改文件清单与依赖变更分析](#2-修改文件清单与依赖变更分析)
3. [Search Provider 统一抽象接口规范](#3-search-provider-统一抽象接口规范)
4. [Tavily 搜索与正文提取集成方案](#4-tavily-搜索与正文提取集成方案)
5. [用户配置与交互设计 (脱敏与连通性测试)](#5-用户配置与交互设计-脱敏与连通性测试)
6. [零费用本地功能 vs 用户自理费用功能边界](#6-零费用本地功能-vs-用户自理费用功能边界)
7. [第一阶段：有效声明质量过滤与评分架构](#7-第一阶段有效声明质量过滤与评分架构)
8. [分层检索词生成与调用预算控制](#8-分层检索词生成与调用预算控制)
9. [候选页面提取、清洗与严密 SSRF 防护网关](#9-候选页面提取清洗与严密-ssrf-防护网关)
10. [证据四级分级 (A/B/C/D) 与型号版本四维对齐](#10-证据四级分级-abcd-与型号版本四维对齐)
11. [四级核验结论与差异化分析理由 (防 0.85 相似度模板化)](#11-四级核验结论与差异化分析理由-防-085-相似度模板化)
12. [结果看板重构与手动证据模式](#12-结果看板重构与手动证据模式)
13. [系统全流程优雅降级方案 (Graceful Degradation)](#13-系统全流程优雅降级方案-graceful-degradation)
14. [20 项专项自动化测试方案](#14-20-项专项自动化测试方案)
15. [分阶段实施步骤与审批确认点](#15-分阶段实施步骤与审批确认点)

---

## 1. 背景诊断与核心整改目标

### 1.1 现状缺陷诊断
1. **声明提取混入无效噪点**：截图 OCR 与文本解析后，常出现 `【截图1提取内容】`（占位符）、`弱水时砂`（品牌名称）、`商品编号`（字段标签）等非声明内容，导致后续分析失去可验证事实基础。
2. **搜索服务缺位导致千篇一律**：未接入真正的网络搜索服务，所有声明在交叉比对时因没有外部客观凭证，全部返回相同的模板化理由，无法体现不同声明的真实差异。
3. **模型与搜索职责混淆**：模型 API (LLM) 负责推理与语言理解，绝不能等同于搜索能力；必须确立独立的 Search Provider 架构体系。

### 1.2 核心整改目标
- **声明严选**：通过质量评分（`quality_score >= 0.65`）与可验证性（`is_verifiable == True`）双门禁，彻底剔除品牌名、型号、字段名、占位符；
- **独立搜索**：构建 `SearchProvider` 抽象接口，首期支持 `TavilySearchProvider`、`ManualEvidenceProvider` 和 `NoSearchProvider`；
- **深度取证**：拒绝仅凭搜索摘要定性，必须提取候选网页正文并去除导航、广告与页脚，提取相关原文；
- **型号精确对齐**：引入 `exact` / `probable` / `series_only` / `mismatch` / `unknown`，同系列异型号不得用于强支持结论；
- **杜绝模板理由**：严格依据实际证据生成具体分析理由，建立成对文本相似度 > 0.85 熔断重写机制；
- **严守合规底线**：严禁内置开发者共享 Key，所有商业检索费用由用户自带账户承担；未配置搜索时显式标明并安全降级，绝不捏造假证据，绝不回退至 Mock 案例。

---

## 2. 修改文件清单与依赖变更分析

### 2.1 修改与新建文件清单

| 文件路径 | 操作性质 | 核心修改与实现职责 |
| :--- | :---: | :--- |
| `streamlit_app/schemas.py` | 修改 | 扩展 `ClaimItem`（新增 quality_score, is_verifiable, rejection_reason 等字段）；扩展 `EvidenceItem`（新增 16 项对齐与来源字段）；新增 `SearchResultItem`；扩展 `VerificationReport` 头部搜索状态字段 |
| `src/verifier/claim_decomposer.py` | 重构 | 实现 `ClaimQualityFilter`，拦截品牌、型号、字段标签、占位符；落实 7 大限定类别与质量评分算法；动态声明数量控制（1~5条，不足时不强凑；0条时安全中断） |
| `src/search/base.py` | 新建 | 定义统一的 `SearchProvider` 抽象基类，规范 `test_connection`、`search`、`extract`、`provider_name`、`is_configured`、`sanitize_result` 接口 |
| `src/search/tavily_provider.py` | 新建 | 实现 `TavilySearchProvider`，支持搜索接口 (`/search`) 与正文提取接口 (`/extract`)，严格隔离 API Key |
| `src/search/manual_provider.py` | 新建 | 实现 `ManualEvidenceProvider`，处理用户手动录入的官网、手册或评测 URL 的安全抓取与解析 |
| `src/search/no_search_provider.py` | 新建 | 实现 `NoSearchProvider`，代表未配置状态，输出标准化 `not_configured` 状态与友好的降级上下文 |
| `src/search/query_generator.py` | 新建 | 实现针对有效声明的三组分层检索词生成器（官方规格、专业实测、用户体验）与调用预算预估 |
| `src/crawlers/ssrf_filter.py` | 修改 | 严格强化 SSRF 拦截：区分本地模型白名单与外网爬取黑名单；拦截回环、内网、云元数据 (169.254)、非标准协议、重定向检查与大文件保护 |
| `src/crawlers/evidence_fetcher.py` | 新建 | 负责候选 URL 正文提取、去噪（去除页眉页脚导航）、JSON-LD 提取与声明关键词原文片段定位；识别验证码并标记 `restricted` |
| `src/verifier/model_alignment.py` | 修改 | 扩展型号四维匹配逻辑（exact / probable / series_only / mismatch / unknown），生成差异化对齐说明 |
| `src/verifier/cross_verifier.py` | 重构 | 实现新四级结论判定准则；重构个性化分析理由生成引擎；建立理由相似度 > 0.85 熔断重写机制 |
| `src/verifier/pipeline.py` | 重构 | 串联质量过滤、Search Provider 路由调度、候选页读取、四维对齐与跨源核验全流程 |
| `streamlit_app/ui/layout.py` | 修改 | 设置抽屉新增独立的【🌐 网络搜索服务 (Search Provider)】设置面板，支持 Tavily、手动模式与连通性测试 |
| `streamlit_app/ui/components.py` | 修改 | 结果看板重构：顶部单次全局搜索状态提示；单条声明展示 13 项详细指标、可点击外部链接与型号对齐徽章 |
| `streamlit_app/app.py` | 修改 | 增加前置声明质量门禁拦截、搜索与正文提取预算计算面板、会话状态同步与降级渲染 |
| `tests/test_search_and_claim_quality.py` | 新建 | 包含用户指定的 **20 项专项自动化测试用例** |

### 2.2 新增依赖分析与选型建议

在 `requirements.txt` 中：
- **方案 A（推荐，零外部大依赖膨胀）**：直接使用已存在的 `requests>=2.31.0` 封装调用 Tavily REST API（`https://api.tavily.com/search` 和 `https://api.tavily.com/extract`）。  
  *优势*：由于项目中已有 `requests` 与 `urllib`，直接封装 REST 请求可获得对 HTTP 超时、重定向控制、API Key 掩码及 SSRF 前置校验的 100% 精确控制，**无需在 `requirements.txt` 中增加任何第三方包**，杜绝 Windows 平台上的轮子兼容风险。
- **方案 B（备选）**：增加官方 `tavily-python>=0.5.0`。  
  *对比*：官方 SDK 封装了重试与数据模型，但在网络请求透明度、SSRF 深度拦截和自定义 HTTP 代理方面不如自研轻量 REST 适配器直观。
- **规划结论**：首选**方案 A**，基于已有标准库 `requests` 实现 `TavilySearchProvider`，保持 `requirements.txt` 极简清爽；若后续需要扩展高级特性，可无缝切换。

---

## 3. Search Provider 统一抽象接口规范

在 `src/search/base.py` 中建立严格统一的抽象驱动接口：

```python
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class SearchResultItem(BaseModel):
    """标准化搜索结果条目"""
    title: str = Field(..., description="网页标题")
    url: str = Field(..., description="规范化完整 URL")
    snippet: str = Field(default="", description="搜索摘要")
    domain: str = Field(..., description="来源域名")
    published_at: Optional[str] = Field(default=None, description="发布时间")
    provider: str = Field(..., description="搜索提供者标识 (如 tavily / manual)")
    query: str = Field(..., description="命中该结果的检索查询词")

class PageExtractResult(BaseModel):
    """网页正文提取标准化输出"""
    url: str
    title: str
    domain: str
    main_text: str = Field(..., description="净化后的网页正文主体 (过滤导航页脚)")
    relevant_excerpts: List[str] = Field(default_factory=list, description="与声明关键词直接相关的原文片段")
    json_ld_specs: Dict[str, Any] = Field(default_factory=dict, description="结构化参数表或JSON-LD")
    fetch_status: str = Field(default="success", description="抓取状态: success / restricted / failed")
    error_message: Optional[str] = None

class SearchProvider(ABC):
    """Search Provider 统一抽象基类"""

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """测试搜索服务连通性与密钥有效性 (仅执行一次极小开销测试，严禁打印明文Key)"""
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[SearchResultItem]:
        """执行互联网关键词检索，返回标准化候选 URL 列表"""
        pass

    @abstractmethod
    def extract(self, url: str) -> PageExtractResult:
        """读取指定候选 URL 的正文内容，并提取净化文本与参数表"""
        pass

    @abstractmethod
    def provider_name(self) -> str:
        """返回当前 Provider 标识 (tavily / manual / none)"""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """当前是否已配置并具备可用凭据"""
        pass

    @abstractmethod
    def sanitize_result(self, raw_item: Dict[str, Any], query: str) -> SearchResultItem:
        """清洗原始结果，过滤敏感信息并标准化字段"""
        pass
```

---

## 4. Tavily 搜索与正文提取集成方案

### 4.1 端点与调用机制 (`src/search/tavily_provider.py`)
- **Base URL**：`https://api.tavily.com`
- **Search 端点**：`POST https://api.tavily.com/search`
  - 核心参数：
    - `api_key`: 用户配置的密钥；
    - `query`: 分层生成的关键词；
    - `search_depth`: `"basic"`（轻量快速，减少计费点数）或 `"advanced"`；
    - `max_results`: 用户配置的单条声明候选上限（默认 3~5）；
    - `include_domains`: 当开启“优先官方来源”时，智能注入品牌已知一级与二级域名；
    - `exclude_domains`: 自动剔除低质量内容农场与垃圾聚合站。
- **Extract 端点**：`POST https://api.tavily.com/extract`
  - 传入抓取到的前 2~3 个权威候选 URL，调用 Tavily 官方净化引擎提取结构化网页正文，自动剥离无用广告、导航栏与页脚脚本。
  - 若调用失败或超额，自动降级为本地 `evidence_fetcher.py`（经 SSRF 校验后通过 BeautifulSoup 解析本地净化）。

### 4.2 连通性测试机制 (`test_connection`)
用户点击设置界面的 `[测试搜索连接]` 按钮时：
1. 构造一个最简探测请求：`query="ping"`, `max_results=1`, `search_depth="basic"`；
2. 记录请求往返耗时（毫秒）；
3. 校验 HTTP 响应：
   - 若 `200 OK`：标记“搜索可用”，尝试探测单页 extract 连通性；
   - 若 `401 Unauthorized`：明确提示“Tavily API Key 无效或未激活”；
   - 若 `429 Too Many Requests`：明确提示“当前 Key 调用配额已耗尽，请检查账户余额”；
   - 若网络超时：返回具体连接超时描述；
4. **脱敏保护**：返回字典中只包含掩码处理后的 Key（如 `tvly-abc****1234`），严禁抛出明文。

---

## 5. 用户配置与交互设计 (脱敏与连通性测试)

在设置抽屉 (`streamlit_app/ui/layout.py`) 中，将原有的三大服务卡片进一步具象化为独立的交互表单：

```
+----------------------------------------------------------------------------------------------------+
|                                ⚙️ 服务模式与端点设置 (Service Settings)                              |
+----------------------------------------------------------------------------------------------------+
|  [服务 1：🧠 模型 API (LLM)]   [服务 2：🕷️ 网页读取器]    [服务 3：🌐 网络搜索服务 (Search API)]     |
|  - Mock / BYOK / Local        - 内置合规读取器           - 未配置 (默认)                            |
|                                                          - Tavily (推荐)                           |
|                                                          - 手动证据链接                            |
|                                                          - 自定义搜索服务 (后续扩展)                 |
+----------------------------------------------------------------------------------------------------+
|  >>> 用户选择【Tavily】时展开的配置项：                                                             |
|  1. Tavily API Key: [ tvly-******************************** ] (密码框掩码)                          |
|  2. 每条声明最大搜索结果数: [ 3 ] 条 (滑动条: 1~5)                                                  |
|  3. 每条声明最大正文提取数: [ 2 ] 篇 (滑动条: 1~3)                                                  |
|  4. 检索语言偏好: (o) zh-CN (中文优先)   ( ) en-US (英文优先)                                       |
|  5. 搜索超时时间: [ 10 ] 秒                                                                        |
|  6. [x] 是否优先官方来源 (自动强化官网、技术白皮书与支持页权重)                                      |
|  7. [ ] 是否搜索用户评论 (默认关闭，避免社交噪声干扰硬核参数)                                       |
|                                                                                                    |
|  [ 🔌 测试搜索连接 ]                                                                               |
|  --> 点击后执行最小探测，展示绿色成功卡片：                                                        |
|      ✅ Tavily 搜索服务连接正常！耗时: 342 ms ｜ 搜索能力: 正常 ｜ 正文提取: 正常 ｜ Key: tvly-***1234 |
+----------------------------------------------------------------------------------------------------+
```

---

## 6. 零费用本地功能 vs 用户自理费用功能边界

```
+---------------------------------------------------------------------------------------------------+
|                                 ClaimCheck Pro 费用与成本边界公约                                  |
+---------------------------------------------------------------------------------------------------+
|  [完全本地免费 · 开发者与用户均 0 费用支出]                                                       |
|  1. 声明质量评分与垃圾占位符过滤 (纯本地规则引擎)                                                 |
|  2. 候选页面提取、JSON-LD 与规格表解析 (纯本地解析)                                               |
|  3. SSRF 网络安全拦截与内容类型校验 (纯本地安全网关)                                              |
|  4. 型号四维对齐检查 (exact / probable / series_only / mismatch) (纯本地对齐)                     |
|  5. 证据四级分级器 (A/B/C/D) 与二次事实自检四项铁律 (纯本地决策)                                  |
|  6. 理由重复度与套话检测 (>0.85 拦截) (纯本地算法)                                                |
|  7. 用户手动参考链接读取与核验 (直接单页访问，0 搜索账单)                                         |
|  8. 本地离线 OCR (RapidOCR CPU 推理) 与 Mock 演示模式全闭环                                       |
+---------------------------------------------------------------------------------------------------+
|  [用户自带账户自理费用 · 开发者绝对 0 垫付 · 绝无隐藏成本]                                        |
|  1. 用户配置的 Tavily API Key (消耗用户自己的月度免费额度或商业账单)                              |
|  2. 用户配置的 OpenAI / 兼容模型 API Key (由用户第三方模型服务商扣费)                             |
|  * 强约束防护：系统在启动搜索前强制显示预计搜索次数与提取页数，单次任务硬上限 10 次，严防意外扣费。|
+---------------------------------------------------------------------------------------------------+
```

---

## 7. 第一阶段：有效声明质量过滤与评分架构

### 7.1 核心过滤规则与拦截清单
在 `src/verifier/claim_decomposer.py` 中重构 `ClaimQualityFilter`，在任何模型核验与网络搜索前执行第一道质检硬门禁：

1. **绝对黑名单强力过滤 (Hard Blacklist)**：
   - 截断占位符：`【截图1提取内容】`, `截图2提取内容`, `OCR提取内容`, `OCR结果`, `未知内容`, `暂无`, `空文本`；
   - 字段标签与标题：`商品编号`, `商品名称`, `品牌`, `型号`, `规格`, `参数`, `详情页`, `主图`, `店铺`, `包装清单`, `好评率`；
   - 模板变量：`{brand}`, `{model}`, `<param>`, `例如：...`, `请补充...`；
   - 无字段值的纯字段名（如仅输入“续航：”或“充电功率”而无具体参数）。
2. **品牌与型号互斥归属 (Brand & Model Routing)**：
   - 拦截纯品牌词（如“弱水时砂”、“声学极客”、“漫步者”等）：
     - 检测候选词是否与当前上下文中的品牌字典或 `product_identity.brand` 一致；
     - 若一致且该行不包含任何动词、量化指标或功能描述，**强制归入 `product_identity.brand`，绝对禁止作为声明进入核验**；
     - 记录剔除原因：`"属于商品品牌标识，已收录于商品身份，不属于宣传声明"`。
3. **7 大严格允许的类别规范 (`category`)**：
   每条进入核验的声明必须归入以下 7 种标准类别之一：
   - `参数`（如：重量 4.5g，驱动单元 12mm，电池容量 500mAh）
   - `功能`（如：支持双设备连接，支持入耳检测，支持无线充电）
   - `性能`（如：主动降噪深度达 45dB，单次续航 8 小时，综合续航 30 小时）
   - `材料`（如：采用航空铝合金腔体，医用级液体硅胶耳塞）
   - `兼容性`（如：兼容 Android 与 iOS，支持 LHDC 5.0，支持蓝牙 5.3）
   - `使用条件`（如：需搭配官方专用 App 开启高解析模式，快充需使用原装线材）
   - `明确体验承诺`（如：IPX5 级级生活防水防汗，通话抗风噪达 6m/s）

### 7.2 声明质量评分体系 (`claim_quality_score`)
每条候选声明计算 0.0 ~ 1.0 的质量评分：
- **基础分**：0.50
- **包含具体数值与物理单位**（dB, W, mAh, Wh, Hz, GHz, GB, mm, g, 小时, min）：`+0.25`
- **包含具体行业技术标准/协议/芯片/认证**（Hi-Res, LDAC, Qi, PD, IPX, 蓝牙5.x）：`+0.20`
- **表达清晰的独立条件句**（“在...条件下达到...”）：`+0.15`
- **包含主观夸张形容词**（遥遥领先, 震撼, 顶级, 绝绝子, 极智）：`-0.25`
- **过短无实义**（长度小于 5 字符且无数字）：`-0.30`

**准入门槛**：
- 必须同时满足：`is_verifiable == True` 且 `claim_quality_score >= 0.65`。
- **动态数量机制**：提取到几条合格就核验几条（例如 2 条有效则只核验 2 条），**“最多 5 条”绝非“必须生成 5 条”**，严禁为了补齐数量而生成垃圾声明。
- **无有效声明中断拦截**：若合格声明数为 0，系统立即终止核验流程并给出明确前台提示：
  > “⚠️ **暂未从当前资料中提取到可验证的宣传声明。**  
  > 请上传包含具体参数、功能或卖点的清晰截图，例如续航时间、降噪等级、防水等级、功率或兼容性说明。”

---

## 8. 分层检索词生成与调用预算控制

### 8.1 三组分层检索词生成规则 (`src/search/query_generator.py`)
输入商品上下文（`brand`, `model`, `variant`, `region`）与单条有效声明：

- **第一组：官方参数与规格（优先度最高，直接寻找官方证据）**
  - `{brand} {model} 官方规格`
  - `{brand} {model} 官方说明书`
  - `{brand} {model} 官方支持`
  - `{brand} {model} {声明核心关键词}`
- **第二组：独立权威评测（寻求第三方实验室实测对比）**
  - `{brand} {model} 专业评测`
  - `{brand} {model} 实测`
  - `{brand} {model} {声明核心关键词} 评测`
- **第三组：用户体验与真实反馈（辅助佐证体验趋势）**
  - `{brand} {model} 用户反馈`
  - `{brand} {model} 常见问题`

每条声明最多生成 4 至 6 个候选查询，按类别挑选 **Top 2 个最具辨识度的 Query** 发送给 Search Provider。

### 8.2 透明预算控制机制 (Preflight Cost Modal)
在开始执行前，界面向用户展示预估面板：
- 有效声明：`N 条`
- 预计搜索请求：`约 N * 2 次`（受单任务上限限制）
- 预计正文提取：`约 N * 2 个页面`
- 预计模型调用：`约 N 次`
- 费用承担方：`用户配置的第三方 API 账户 (由用户自理，支持随时取消)`

---

## 9. 候选页面提取、清洗与严密 SSRF 防护网关

### 9.1 搜索摘要非证据原则
搜索返回的 `snippet` 仅用于候选结果排序与初步过滤。系统严禁仅凭几十个字符的摘要断定宣传真伪，必须通过 `extract` 读取目标页面正文。

### 9.2 候选网页提取与去噪流程 (`src/crawlers/evidence_fetcher.py`)
1. 对目标候选 URL 执行 SSRF 与安全过滤；
2. 拉取 HTML 页面（限制超时 8 秒，限制大小 2MB）；
3. 自动识别页面访问受限（遇到验证码、登录页 302、403、滑块等，直接标记 `fetch_status = "restricted"`，绝不暴力破解）；
4. 解析页面的 `JSON-LD` 结构化对象与 `<table class="specs">` 规格参数表；
5. 去噪过滤：彻底剔除 `<nav>`, `<header>`, `<footer>`, `<aside>`, 广告浮层及底部版权推荐；
6. 基于声明关键词切分并提取 200~400 字的**原文事实片段 (Excerpt)**，保存真实来源链接与域名。

### 9.3 严密的 SSRF 差异化防御网关
由于本地模型（如 Ollama）允许访问 `127.0.0.1:11434`，而**证据爬虫与网络访问绝不允许访问内网**，系统建立严格的差异化安全策略：

```
+----------------------------------------------------------------------------------------------------+
|                                    ClaimCheck Pro SSRF 差异化安全准则                               |
+----------------------------------------------------------------------------------------------------+
| [策略 A：本地模型端点 (Local Provider)]                                                            |
| - 仅限本地回环或指定内网端口 (127.0.0.1, localhost, 192.168.x.x)                                   |
| - 严禁在公网随意暴露未经认证的本地端口                                                              |
+----------------------------------------------------------------------------------------------------+
| [策略 B：外部证据抓取与搜索 (Web Crawler & Search Fetcher)] —— 绝对零信任公网隔离网关              |
| 1. 严格禁止 localhost 与 127.0.0.1 回环访问                                                        |
| 2. 严格阻止私有网络 IP (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)                                  |
| 3. 严格拦截各大云服务商元数据端点 (169.254.169.254, metadata.google.internal 等)                    |
| 4. 严格禁止 file://, ftp://, gopher:// 等非 HTTP(S) 协议                                           |
| 5. 重定向二次防御：禁用自动重定向，跟踪 301/302 并逐级解析目标域名 IP，防止通过公网域名 302 穿透至内网 |
| 6. 响应大小截断：流式读取限制 2MB，超时限制 8 秒，阻断超大文件耗尽内存                             |
| 7. 内容类型检查：仅接收 text/html, application/xhtml+xml，严禁下载可执行程序 (.exe, .sh, .bat)    |
+----------------------------------------------------------------------------------------------------+
```

---

## 10. 证据四级分级 (A/B/C/D) 与型号版本四维对齐

### 10.1 证据来源严格四级体系
- **A 级 (官方基准证据)**：品牌一级官网、品牌认证技术支持站、官方电子说明书、入网质检许可。
- **B 级 (权威独立实测)**：国家级/国际权威检测机构、知名科技媒体具备完整测试流程与实验室仪器的实测。
- **C 级 (社群体验趋势)**：垂直数码论坛、电商带图真实长评、问答社区（**仅用于体验趋势参考，严禁单独证明技术硬参数**）。
- **D 级 (不可作为结论依据)**：营销软文、无出处转载、型号不明内容、聚合站、**仅有搜索摘要且正文无法访问的内容**（**绝对禁止用于强支持结论**）。

### 10.2 型号四维对齐机制 (`model_match`)
每条提取的证据必须与目标商品进行四维核验：
- `brand_match`: 品牌是否一致；
- `model_match`:
  - `exact`：目标型号完全匹配；
  - `probable`：型号名称存在轻微别称但高置信对应；
  - `series_only`：仅属于同系列，非当前具体型号；
  - `mismatch`：型号完全不符；
  - `unknown`：页面未明确记载型号。
- `variant_match`: 规格/颜色/内存版本是否一致；
- `region_match`: 销售地区与网络制式是否一致。

**强结论准入门槛**：
- 只有 `exact` 或高置信 `probable` 证据可用于支持“有证据支持”或“存在冲突”的判定；
- 属于 `series_only` 的同系列不同型号证据，系统强制标记：
  > “⚠️ **型号对齐提示**：该资料来自同系列其他型号（如 Pro 版 vs 标准版），不能直接用于当前商品的定性结论。”

---

## 11. 四级核验结论与差异化分析理由 (防 0.85 相似度模板化)

### 11.1 四级结论严格判定矩阵
- **有证据支持**：至少 1 条同型号 A 级证据明确支持，且无同等级冲突证据；
- **部分支持**：核心事实成立，但在测试条件、范围、版本或第三方实测数据上存在差异；
- **存在冲突**：同型号 A 级证据或高质量 B 级实测与宣传声明直接矛盾；
- **证据不足**：搜索未配置 / 未检索到同型号官方资料 / 候选网页受限 / 只有低可信 C/D 级来源 / 型号匹配失败 / 声明本身不可验证。  
  *铁律*：**绝对不得因“未搜到资料”断定宣传虚假**。

### 11.2 分析理由差异化结构规范
每条声明的分析理由必须通过动态变量组装，涵盖：
1. 当前声明原文核心词；
2. 实际调用的具体检索 Query；
3. 检索到的候选结果数与有效正文提取数；
4. 最高证据等级及代表性来源域名；
5. 关键原文摘录片段；
6. 型号匹配状态与差异化推导结论。

### 11.3 证据不足的 6 种明确细分
当判定为“证据不足”时，严禁输出通用套话，必须输出具体原因：
1. `search_not_configured`：“网络搜索服务未配置，仅依据用户提供的有限文案无法证实该项指标。”
2. `official_not_found`：“已在全网检索（Query: '...'），未收录与当前型号【{model}】直接对应的客观技术记载。”
3. `page_restricted`：“检索到潜在官方页面，但因平台访问保护无法提取正文，在获得直接原文前不妄加推测。”
4. `low_credibility_only`：“仅检索到论坛与社交讨论线索，缺乏 A/B 级权威同型号数据支撑技术硬参数。”
5. `model_mismatched`：“检索到的实测数据属于同系列其他产品【{other_model}】，与当前目标型号不一致。”
6. `unverifiable_claim`：“宣传文案属于主观形容词或不可测量的感官体验，缺乏物理对照指标。”

### 11.4 文本相似度重复度熔断保护
在全流程输出前，计算报告中所有声明理由的成对 Jaccard / Levenshtein 相似度：
- 若任意两篇理由的相似度高于 **0.85**，流水线触发差异化修正回路，强制注入各声明特定的参数指标与检索轨迹，确保每条声明的核验理由独一无二。

---

## 12. 结果看板重构与手动证据模式

### 12.1 顶部状态栏清晰区分三大维度
在结果页面看板顶部，以醒目的白色高对比度卡片展示当前的运行环境：
- **AI 模型**：实际 Provider 名称与模型名称（如 `OpenAICompatibleProvider · gpt-4o-mini`）；
- **网络搜索**：实际搜索状态（`Tavily 已连接` ｜ `⚪ 未配置` ｜ `⚠️ 搜索失败` ｜ `📋 手动证据模式`）；
- **数据模式**：当前核验真实性模式（`🌐 实时网络核验` ｜ `📄 仅用户资料分析` ｜ `📋 手动证据核验` ｜ `🟢 Mock 演示数据`）。

**单次全局提示**：
若未配置网络搜索服务，仅在结果页顶部统一显示一次：
> “ℹ️ **本次未执行实时网络搜索**。当前结论严格基于用户提供的商品资料和手动证据，未发起全网外部检索。”  
卡片内部不再冗余复读，使每条声明卡片聚焦于商品事实本身。

### 12.2 单条声明卡片 13 项全景指标
展开每条声明卡片，清晰呈现：
1. 宣传声明（原子提炼与原文摘录）
2. 声明来源（如：`截图1提取内容行2` / `详情文本参数表`）
3. 声明质量评分（如：`可验证性得分 88%`）
4. 核验结论（四级彩色徽章）
5. 置信度（百分比数值）
6. 搜索查询（实际执行的关键词）
7. 候选结果数（搜索引擎返回数量）
8. 有效证据数（成功抓取正文的数量）
9. 最高证据等级（如：`A级 (品牌官方规格)`）
10. 具体分析理由（个性化推导链条）
11. 型号匹配情况（`✅ exact 严格对齐`）
12. 真实可点击来源链接（`[🔗 官方支持文档]`，点击新标签页打开）
13. 人工确认建议（购买前的具体核实小贴士）

### 12.3 手动证据模式 (Manual Evidence Mode)
当用户没有搜索 API 时，允许在高级选项中逐条粘贴：
- 品牌官网链接
- 官方说明书下载页链接
- 权威评测页面链接  
系统执行相同标准的安全检测、正文提取、型号对齐与四级比对；若手动输入的 URL 无法访问，明确提示读取受限，绝不伪造内容。

---

## 13. 系统全流程优雅降级方案 (Graceful Degradation)

```
                                  ClaimCheck Pro 全链路优雅降级决策树
                                                   │
                ┌──────────────────────────────────┴──────────────────────────────────┐
                ▼                                                                     ▼
       [用户配置了 Tavily 搜索]                                              [用户未配置搜索服务]
                │                                                                     │
        执行分层检索与网页读取                                                 标记 search_status = "not_configured"
                │                                                                     │
   ┌────────────┴────────────┐                                                        ▼
   ▼                         ▼                                             只依据用户材料与手动链接核验
[正常返回结果]          [网络异常 / 401 / 429 配额耗尽]                                        │
   │                         │                                                        ▼
   ▼                         ▼                                             输出包含 "本次未执行实时网络搜索"
提取正文并核验          标记 search_status = "failed"                                  声明的个性化核验报告
                        友好呈现异常原因与耗尽诊断，                                  (绝不捏造假证据，绝不回退至Mock)
                        自动降级为“仅依据用户材料核验”，
                        🔒 严格遵守零伪造铁律，绝不回退至 Mock！
```

---

## 14. 20 项专项自动化测试方案

在 `tests/test_search_and_claim_quality.py` 中构建用户要求的 **20 项专项自动化测试套件**：

```python
# 20 项专项自动化测试清单：
def test_01_placeholder_never_becomes_claim():
    """1. 截图占位符（如【截图1提取内容】）绝不被提取为声明"""

def test_02_brand_name_never_becomes_claim():
    """2. 品牌名称（如弱水时砂）进入 product_identity.brand，绝不进入声明"""

def test_03_field_title_never_becomes_claim():
    """3. 商品编号、商品名称、规格参数等字段标签绝不成为声明"""

def test_04_dynamic_claim_count_no_forced_five():
    """4. 不足5条有效声明时按实际数量核验，绝不强行补齐垃圾内容"""

def test_05_stop_search_when_no_valid_claims():
    """5. 没有有效声明时安全停止任务，并给出明确用户补充提示"""

def test_06_search_not_configured_status_correct():
    """6. Search Provider 未配置时状态标明 not_configured，绝不静默伪造"""

def test_07_tavily_config_test_masks_api_key():
    """7. Tavily 配置测试时返回结果与日志对 API Key 严格脱敏"""

def test_08_search_results_retain_real_urls():
    """8. 搜索结果数据结构完整保留真实的来源 URL 与域名"""

def test_09_search_snippets_cannot_be_level_a():
    """9. 搜索摘要不能直接成为 A 级证据，必须深入提取正文"""

def test_10_official_pages_classified_as_level_a():
    """10. 品牌官网、官方手册与质检资料正确标记为 A 级来源"""

def test_11_expert_reviews_classified_as_level_b():
    """11. 具备实验数据与测试流程的权威评测机构正确标记为 B 级"""

def test_12_user_reviews_cannot_support_tech_parameters():
    """12. 用户评论与社交讨论（C/D级）不能单独作为技术硬参数的支撑证据"""

def test_13_other_models_cannot_support_strong_conclusions():
    """13. 同系列其他型号证据明确标记 mismatch/series_only，不可用于强结论"""

def test_14_claim_reasons_distinct_similarity_under_threshold():
    """14. 多条声明的分析理由不得完全相同，文本相似度严格低于 0.85"""

def test_15_search_provider_exception_never_falls_back_to_mock():
    """15. Search Provider 出现 401/429/超时异常时，绝不回退至 SoundPro X1 等 Mock 案例"""

def test_16_restricted_candidate_pages_marked_restricted():
    """16. 候选页面遭遇验证码或反爬拦截时，fetch_status 正确标记为 restricted"""

def test_17_manual_evidence_links_participate_in_verification():
    """17. 用户手动输入的参考证据链接能够正常抓取、对齐并参与四级核验"""

def test_18_report_contains_real_source_hyperlinks():
    """18. 最终生成的报告与卡片中包含真实的外部参考资料超链接"""

def test_19_api_key_never_leaked_in_logs_and_reports():
    """19. API Key 绝不出现在系统日志、前端代码、截图和 Markdown 报告中"""

def test_20_ssrf_addresses_strictly_blocked():
    """20. 证据抓取严格拦截 localhost, 127.0.0.1, 私有网段及 169.254 元数据地址"""
```

---

## 15. 分阶段实施步骤与审批确认点

根据任务约束，本项目按以下五个阶段逐步推进：

- [x] **规划阶段 (Current)**：完成 `SEARCH_PROVIDER_IMPLEMENTATION_PLAN.md` 编制，等待用户审批；
- [ ] **第一阶段：声明质量过滤重构**
  - 实现 `ClaimQualityFilter`，完成占位符、品牌名、字段名拦截；
  - 实现 7 大分类约束与质量评分体系；动态数量控制（1~5条）；无有效声明中断提示；
  - 跑通测试 1~5。
- [ ] **第二阶段：Search Provider 抽象与 Tavily 配置界面**
  - 实现 `SearchProvider` 统一抽象基类；
  - 实现 `TavilySearchProvider`、`ManualEvidenceProvider` 与 `NoSearchProvider`；
  - 在 `streamlit_app/ui/layout.py` 中增加独立搜索配置抽屉与 `[测试搜索连接]` 交互；
  - 跑通测试 6~7。
- [ ] **第三阶段：真实搜索、网页提取与证据结构**
  - 实现分层检索词生成器；
  - 强化 SSRF 防御网关，实现候选网页正文提取与去噪；
  - 扩展全景 `EvidenceItem` 数据模型；
  - 跑通测试 8~10、16、20。
- [ ] **第四阶段：型号四维对齐与差异化核验**
  - 实现型号与版本四维对齐（区分同系列不同型号）；
  - 落实全新四级结论准则；
  - 实现差异化理由生成引擎与相似度 > 0.85 熔断去重；
  - 跑通测试 11~15。
- [ ] **第五阶段：结果页面重构与端到端测试**
  - 结果看板渲染 13 项详细指标与可点击来源超链接；
  - 跑通 20 项全量自动化测试套件；
  - 启动 Streamlit 进行真实浏览器端到端验收与截图归档。

---

> ⚠️ **等待用户指令**：  
> 本实施规划方案已完整生成并保存至 [`D:\ClaimCheck_Pro\SEARCH_PROVIDER_IMPLEMENTATION_PLAN.md`](file:///D:/ClaimCheck_Pro/SEARCH_PROVIDER_IMPLEMENTATION_PLAN.md)。  
> 当前**未安装任何依赖，未修改任何核心代码**。请您审阅并批准本方案，确认后我将正式开始第一阶段（有效声明质量过滤）的实现！
