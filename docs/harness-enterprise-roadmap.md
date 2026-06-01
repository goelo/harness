# Harness 企业级产品规划

## 背景

Harness 当前已经具备阶段状态、证据文件、角色职责、测试验证和安装能力，适合继续升级为团队级 AI 研发过程管理工具。

企业推广场景下，单个研发人员的效率提升只是起点。更重要的是让团队看到需求状态、质量证据、工程规范、历史记录和组织资产，让 AI 参与研发的过程可以被理解、被检查、被复用。

Harness 的长期定位可以表述为：

> Harness 让 AI 研发从一次性对话，变成有阶段、有证据、有检查、有团队视图的工程过程。

## 产品叙事

Harness 需要讲清楚三层价值。

| 层级 | 面向对象 | 核心价值 |
| --- | --- | --- |
| 个人效率层 | 一线研发 | 减少重复解释上下文，让 AI 按固定流程推进需求 |
| 团队协作层 | Tech Lead、测试、架构负责人 | 用统一阶段、统一产物、统一检查方式管理 AI 参与研发 |
| 企业治理层 | 平台团队、工程效能团队 | 形成可审计、可统计、可推广的 AI 研发基础设施 |

推荐的产品故事：

> AI 写代码只是起点，企业真正需要的是可管理的 AI 研发过程。Harness 提供阶段、角色、证据和质量检查，让团队既能享受 AI 的开发效率，也能保留工程管理所需的秩序。

## 设计原则

| 原则 | 说明 |
| --- | --- |
| CLI 负责可靠执行 | 所有状态变更、证据生成和验证检查都由脚本完成，减少模型自由发挥带来的偏差 |
| Skill 负责降低使用门槛 | 团队成员通过自然语言进入需求确认、需求开发和状态查看 |
| Dashboard 负责展示价值 | 团队负责人可以看到多个需求的阶段、证据、失败原因和质量摘要 |
| 项目知识优先 | 在开发前生成项目画像、接口索引和工程规范，让 AI 有稳定上下文 |
| 证据优先 | 每个阶段都留下可检查的文件，便于评审、排障和复盘 |
| 轻内核，重周边 | 保留 Harness 当前轻量状态机，逐步补充可视化、诊断、统计和模板能力 |

## 能力地图

```text
Harness
├── 安装与诊断
│   ├── install-state.json
│   ├── 版本检查
│   ├── hook 配置检查
│   └── 安装修复建议
├── 需求研发流程
│   ├── clarify
│   ├── doc-plan
│   ├── red
│   ├── green
│   ├── review
│   ├── validate
│   └── done
├── 项目知识
│   ├── docs/standards/project-guide.md
│   ├── docs/standards/api/url-index.md
│   ├── docs/standards/api/detail.md
│   └── .harness/project-profile.json
├── 质量证据
│   ├── clarification.jsonl
│   ├── implementation-plan.md
│   ├── scope.json
│   ├── test-result.red.json
│   ├── test-result.green.json
│   ├── review-result.json
│   └── verify-result.json
└── 团队视图
    ├── 任务列表
    ├── 阶段状态
    ├── 缺失证据
    ├── 失败原因
    ├── 验证摘要
    └── 质量趋势
```

## 阶段安排

| 阶段 | 目标 | 关键能力 | 推广价值 |
| --- | --- | --- | --- |
| 第一阶段：好用 | 单项目内使用顺畅 | 状态增强、缺失证据提示、安装状态记录 | 让一线研发愿意持续使用 |
| 第二阶段：好管 | 团队能管理多个需求 | 任务列表、阶段统计、失败原因汇总、质量检查摘要 | 让负责人能看到团队使用情况 |
| 第三阶段：好接入 | 新团队低成本接入 | 初始化向导、项目画像生成、推荐验证配置、安装诊断 | 降低推广和培训成本 |
| 第四阶段：好治理 | 企业级审计和资产复用 | 评审文档生成、规范资产库、质量趋势、组织级模板 | 支撑跨团队推广和统一治理 |

## 功能规划

### P0：状态可见

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| 增强 `task.py current` | 输出当前任务、阶段、执行模式、缺失证据、最近失败原因和下一步建议 | 控制台文本 |
| 增加 `task.py current --json` | 为 Dashboard 和自动化脚本提供结构化状态 | JSON |
| 增加 `task.py list` | 列出 `docs/tasks/` 下全部任务，显示状态、阶段、更新时间 | 控制台表格 |
| 增加 `task.py list --json` | 为多任务视图提供基础数据 | JSON |

### P0：安装可信

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| `.harness/install-state.json` | 记录 Harness 版本、安装时间、安装来源、写入文件、启用能力 | JSON |
| 安装诊断命令 | 检查 `.harness/scripts`、hooks、skills、agents、`verify.json` 是否完整 | 控制台报告 |
| 升级保护 | 安装时保留本地配置和运行时状态，避免覆盖团队自定义内容 | 安装日志 |
| 安装进度事件 | 安装器输出 CLI 进度条，并写入 `.harness/runtime/install-progress.json` | 进度 JSON |
| 项目扫描 Skill | 默认安装 `project-doc-scanner`，引导用户在 AI 会话中扫描当前项目 | Skill |

### P1：项目画像

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| 项目开发指南生成 | 扫描代码、README、架构文档，生成项目分层、命名、错误处理、日志、测试规则 | `docs/standards/project-guide.md` |
| 接口索引生成 | 扫描路由、controller、handler、proto，生成接口清单 | `docs/standards/api/url-index.md` |
| 接口详情生成 | 提取出入参、认证、状态码、示例和敏感字段 | `docs/standards/api/detail.md` |
| 项目画像生成 | 结构化保存技术栈、入口文件、关键目录、接口统计、验证命令和审阅状态 | `.harness/project-profile.json` |
| 验证命令识别 | 根据项目技术栈推荐 `lint`、`type`、`test`、`coverage` 命令 | `.harness/verify.json` 建议项 |

## 项目文档初始化能力

项目文档初始化是项目级前置能力，不并入单次需求开发阶段。安装命令只负责检查当前项目是否已有项目知识文档，并提示用户在 Codex 或 Claude Code 中执行项目扫描。真正的代码扫描、模板选择、子代理调度、文档生成和审阅状态写入由默认安装的 `project-doc-scanner` Skill 完成。

### 默认 Skill 入口

`project-doc-scanner` 是项目知识初始化的默认入口，随 Harness 安装进入目标项目。

| 项目 | 设计 |
| --- | --- |
| Skill 名称 | `project-doc-scanner` |
| 安装位置 | `.claude/skills/project-doc-scanner/SKILL.md`，后续补齐 Codex 侧等效入口 |
| 触发语 | 扫描当前项目、初始化项目文档、生成项目开发文档、生成接口文档、刷新项目知识文档 |
| 配套脚本 | `.harness/scripts/project.py`，负责配置、状态、哈希、审阅记录和索引更新 |

Skill 固定采用“先检测，再确认，再扫描”的交互流程：

| 步骤 | 行为 |
| --- | --- |
| 检测项目状态 | 检查 `.harness/`、`.harness/project-docs.json`、`.harness/project-profile.json` 和 `docs/standards/` 下的项目知识文档 |
| 判断扫描类型 | 文档缺失时首次扫描，文档存在时增量扫描，`stale` 或 `needs_update` 时刷新扫描 |
| 确认模板来源 | 已有 `.harness/project-docs.json` 时展示配置摘要；无配置时询问使用内置模板还是自定义模板 |
| 确认写入范围 | 展示将写入、覆盖、生成候选稿、保存缓存和审阅记录的文件 |
| 开始扫描 | 调度架构、接口、质量、规范子代理，汇总结果并生成文档 |

### 产物结构

| 产物 | 路径 | 生命周期 | 是否纳入版本管理 |
| --- | --- | --- | --- |
| 项目开发指南 | `docs/standards/project-guide.md` | 长期保留 | 是 |
| 接口索引 | `docs/standards/api/url-index.md` | 长期保留 | 是 |
| 接口详情 | `docs/standards/api/detail.md` | 长期保留 | 是 |
| 项目画像 | `.harness/project-profile.json` | 长期保留 | 是 |
| 项目文档配置 | `.harness/project-docs.json` | 长期保留 | 是 |
| 子代理扫描缓存 | `.harness/analysis/latest/*.json` | 可再生成 | 默认否 |
| 项目级审阅记录 | `.harness/project-docs/reviews/*.json` | 长期保留 | 是 |
| 扫描摘要 | `.harness/project-docs/reviews/<timestamp>-scan-summary.md` | 长期保留 | 是 |
| 待审阅清单 | `docs/standards/project-docs-review.md` | 长期保留 | 是 |
| 候选更新稿 | `.harness/project-docs/proposals/*.proposed.md` | 临时到半长期 | 默认否 |
| 覆盖前备份 | `.harness/project-docs/backups/<timestamp>/` | 长期保留 | 是 |

`docs/tasks/` 继续只保存单次需求开发任务包。初始化文档属于长期项目知识，统一放在 `docs/standards/` 下，便于后续 `architect`、`developer`、`tester` 阶段读取。

### 文档证据结构

初始化文档的关键判断必须采用“判断 + 证据 + 置信度 + 待确认项”的结构，避免 AI 将推测内容写成项目事实。

| 字段 | 含义 |
| --- | --- |
| 判断 | AI 对项目架构、接口、测试方式、工程规范的理解 |
| 证据 | 对应的文件路径、行号、函数名、配置项或命令输出摘要 |
| 置信度 | `high`、`medium`、`low` |
| 待确认项 | 代码证据不足，需要负责人确认的内容 |

### 子代理扫描机制

初始化过程由 `project-doc-scanner` Skill 的主会话调度子代理扫描，主会话只负责汇总结果和生成最终文档，避免大范围源码内容污染主会话窗口。

| 子代理 | 扫描内容 | 输出 |
| --- | --- | --- |
| 架构扫描子代理 | 入口文件、目录结构、模块分层、依赖方向、架构规则 | `.harness/analysis/latest/architecture-scan.json` |
| 接口扫描子代理 | 路由、controller、handler、proto、OpenAPI 文件、接口出入参 | `.harness/analysis/latest/api-scan.json` |
| 质量扫描子代理 | 测试框架、lint、type、coverage、CI 配置 | `.harness/analysis/latest/quality-scan.json` |
| 规范扫描子代理 | README、CONTRIBUTING、docs、已有团队规范 | `.harness/analysis/latest/standards-scan.json` |

子代理输出结构化事实，主会话只基于这些事实生成最终文档。中间结果保存路径、行号和短摘要，不保存大段源码。

子代理扫描结果默认只保留 `.harness/analysis/latest/*.json`。如果 `.harness/project-docs.json` 中配置 `keepHistory=true`，则同时写入 `.harness/analysis/history/<timestamp>/*.json`。

### 扫描成本控制

扫描分为三层执行。

| 层级 | 行为 | 输出 |
| --- | --- | --- |
| 索引优先 | 读取文件树、依赖清单、配置文件、路由注册入口 | 候选模块、候选接口、候选测试命令 |
| 抽样验证 | 每类目录抽取代表文件，验证架构和规范判断 | 带证据的 findings |
| 按需深入 | 对低置信度、冲突项、关键接口读取更多文件 | 待确认项和补充证据 |

预算配置由 `.harness/project-docs.json` 控制，例如 `maxFiles`、`maxFindings`、`maxEvidencePerFinding`、`maxEndpoints`。

### 局部扫描

`project-doc-scanner` 支持局部扫描，避免接口文档、小范围规范变化时重复扫描整个项目。

| 意图 | 扫描范围 | 影响文件 |
| --- | --- | --- |
| 只更新接口文档 | `api` scanner | `docs/standards/api/url-index.md`、`docs/standards/api/detail.md` |
| 只刷新项目开发指南 | `architecture`、`quality`、`standards` scanner | `docs/standards/project-guide.md` |
| 重新识别测试命令 | `quality` scanner | `.harness/project-profile.json`、`docs/standards/project-guide.md` 中的验证章节 |
| 完整扫描当前项目 | 全部 scanner | 全部项目知识文档 |

底层脚本预留参数：

```bash
python3 .harness/scripts/project.py docs refresh --only api
python3 .harness/scripts/project.py docs refresh --only project-guide
python3 .harness/scripts/project.py docs refresh --only quality
python3 .harness/scripts/project.py docs refresh --all
```

### 配置方式

配置采用“内置 preset + 项目覆盖配置”。Harness 内置常见技术栈 preset，项目中只保存 `.harness/project-docs.json` 覆盖项。

```json
{
  "version": 1,
  "preset": "go-service",
  "documents": {
    "projectGuide": {
      "enabled": true,
      "output": "docs/standards/project-guide.md",
      "template": "default"
    },
    "apiUrlIndex": {
      "enabled": true,
      "output": "docs/standards/api/url-index.md",
      "template": "default"
    },
    "apiDetail": {
      "enabled": true,
      "output": "docs/standards/api/detail.md",
      "template": "default"
    }
  },
  "review": {
    "initialStatus": "draft",
    "requiredBeforeUseAsStandard": true,
    "contextInjection": {
      "approved": "standard",
      "draft": "reference",
      "needs_update": "limited",
      "stale": "disabled"
    }
  },
  "analysis": {
    "cacheDir": ".harness/analysis/latest",
    "keepHistory": false,
    "historyDir": ".harness/analysis/history"
  }
}
```

建议内置 preset 包括 `default`、`go-service`、`java-spring`、`node-service`、`python-service`。

### 审阅状态

负责人审阅结果进入 `.harness/project-profile.json`，后续需求开发根据文档状态决定注入强度。

| 状态 | 含义 | 后续 AI 使用规则 |
| --- | --- | --- |
| `draft` | AI 刚生成，负责人尚未审阅 | 可作为参考，关键判断必须重新核对证据 |
| `approved` | 负责人已经审阅通过 | 可作为项目长期规范注入 |
| `needs_update` | 负责人发现内容不准确 | 只注入摘要和待确认项 |
| `stale` | 代码变化较大，文档可能过期 | 默认不注入正文，只提示需要刷新 |

支持逐文档批准和一键全部批准。

```bash
python3 .harness/scripts/project.py docs approve project-guide
python3 .harness/scripts/project.py docs approve api-url-index
python3 .harness/scripts/project.py docs approve api-detail
python3 .harness/scripts/project.py docs approve --all
```

首版只同步文档状态、内容哈希、路径和更新时间。后续在模板稳定后，再支持从 Markdown 反写结构化字段。

`approved` 文档默认不允许直接覆盖。扫描发现需要更新已批准文档时，先生成候选稿：

```text
.harness/project-docs/proposals/
├── project-guide.proposed.md
├── api-url-index.proposed.md
└── api-detail.proposed.md
```

只有用户明确同意覆盖后，才允许把候选稿写回正式文档。覆盖前必须自动备份旧版本：

```text
.harness/project-docs/backups/
└── 2026-06-01T10-00-00/
    ├── project-guide.md
    ├── api-url-index.md
    ├── api-detail.md
    └── backup-manifest.json
```

### 生成模式

| 模式 | 使用场景 | 行为 |
| --- | --- | --- |
| 全量生成 | 新项目首次接入 Harness | 扫描代码，生成全部项目知识文档和项目画像 |
| 增量刷新 | 代码结构、接口、测试命令发生变化 | 只刷新受影响部分，并保留负责人已批准内容 |
| 强制重建 | 文档明显过期或项目结构大改 | 重新生成全部文档，旧文档覆盖前备份 |

建议命令：

```bash
python3 .harness/scripts/project.py docs init
python3 .harness/scripts/project.py docs refresh
python3 .harness/scripts/project.py docs rebuild
python3 .harness/scripts/project.py docs status
```

### 安装前置提示

安装流程增加项目文档检查。安装完成 `.harness/`、hooks、skills、agents、`docs/tasks/`、`docs/standards/` 和 `project-doc-scanner` Skill 后，检查项目知识文档是否存在，并提示用户在 AI 会话中执行项目扫描。

| 场景 | 行为 |
| --- | --- |
| 交互式安装 | 检测缺失后提示用户在 Codex 或 Claude Code 中输入“扫描当前项目” |
| 非交互安装 | 不询问，只记录项目文档待初始化状态 |
| `--init-project-docs` | 不做深度扫描，只生成配置骨架并提示进入 AI 会话扫描 |
| `--no-init-project-docs` | 跳过项目文档提示，并记录原因 |

安装命令不直接依赖 AI 子代理，因此安装成功和项目文档扫描成功天然分离。项目文档扫描失败时，由 `project-doc-scanner` Skill 和 `.harness/scripts/project.py` 写入 `.harness/project-profile.json` 与审阅记录。

安装完成提示示例：

```text
Harness 安装完成。

当前项目尚未生成 AI 自动化开发文档。
建议在 Codex 或 Claude Code 中输入：

扫描当前项目

该操作会触发 project-doc-scanner Skill，生成 docs/standards/ 下的项目知识文档。
```

### 安装进度

首版暂缓 HTML 安装页面，先提供 CLI 进度条和 `.harness/runtime/install-progress.json`。进度只覆盖安装本体、配置写入和项目文档状态检查，不覆盖 AI 会话中的深度扫描。后续再基于同一份进度事件接入本地页面或企业平台页面。

| 阶段 | 参考进度 | 文案 |
| --- | ---: | --- |
| `prepare` | 5% | 正在准备安装环境 |
| `install_files` | 15% | 正在写入 Harness 文件 |
| `configure_hooks` | 25% | 正在配置 Claude Code 和 Codex hooks |
| `install_skills` | 35% | 正在安装 Harness Skills |
| `docs_preflight` | 55% | 正在检查项目文档状态 |
| `write_project_docs_config` | 70% | 正在写入项目文档配置骨架 |
| `write_install_state` | 90% | 正在写入安装状态 |
| `done` | 100% | 安装完成 |

### 扫描摘要与审阅入口

`project-doc-scanner` 每次扫描完成后生成面向负责人的扫描摘要：

```text
.harness/project-docs/reviews/<timestamp>-scan-summary.md
```

摘要包含本次扫描类型、使用模板、子代理结果、生成文件、候选稿、待确认项和建议审阅顺序。

同时生成集中待审阅清单：

```text
docs/standards/project-docs-review.md
```

建议审阅顺序：

| 顺序 | 文档 | 审阅重点 |
| ---: | --- | --- |
| 1 | `docs/standards/project-docs-review.md` | 待确认项和高优先级问题 |
| 2 | `docs/standards/project-guide.md` | 架构、目录职责、开发规范、验证命令 |
| 3 | `docs/standards/api/url-index.md` | 接口是否遗漏、分组是否合理 |
| 4 | `docs/standards/api/detail.md` | 关键接口的出入参、认证、状态码 |
| 5 | `.harness/project-profile.json` | 自动化配置和排障信息 |

### P1：评审材料

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| 技术评审文档生成 | 汇总 `implementation-plan.md`、`scope.json`、测试证据和验证结果 | `review-spec.md` |
| Mermaid 图生成 | 根据设计和任务拆分生成模块关系、调用流程和状态变化图 | Markdown 图表 |
| Cooper 输出预留 | 先生成本地文档，后续接入 Cooper 平台 | 本地文件或 Cooper 文档 |

### P1：质量增强

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| phase 级检查脚本 | 在 `verify.json` 中允许配置阶段级检查命令 | `verify-result.json` |
| 缺失证据检查 | 在阶段推进前列出缺少的必要文件 | 控制台报告 |
| 变更范围检查增强 | 基于 `scope.json` 输出允许、禁止、未声明变更清单 | `verify-result.json` |

### P2：团队看板

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| 本地 Web 看板 | 展示任务列表、阶段状态、证据状态和验证结果 | Dashboard |
| 多项目状态输入 | 读取多个项目的 `.harness` 状态，形成团队视图 | JSON 聚合结果 |
| 阶段耗时统计 | 统计每个任务在各阶段的停留时间 | 指标表 |
| 失败原因统计 | 汇总阶段推进失败和验证失败原因 | 指标表 |

### P2：组织模板

| 功能 | 说明 | 产物 |
| --- | --- | --- |
| 技术栈模板 | 为 Go、Java、Node、Python 等项目提供默认验证配置 | 模板目录 |
| 团队规范模板 | 为不同团队提供默认 `docs/standards/` 内容 | 模板目录 |
| 模板选择命令 | 初始化时选择团队或技术栈模板 | 安装参数 |
| 模板版本记录 | 记录当前项目使用的模板名称和版本 | `install-state.json` |

## 近期版本建议

| 版本 | 主题 | 交付内容 |
| --- | --- | --- |
| `v0.4` | 状态可见 | 增强 `task.py current`，增加 JSON 输出，补齐缺失证据提示 |
| `v0.5` | 安装可信 | 增加 `install-state.json`、安装诊断、版本展示 |
| `v0.6` | 项目文档扫描 Skill | 默认安装 `project-doc-scanner`，生成项目开发指南、接口文档、项目画像和审阅状态 |
| `v0.7` | 评审材料 | 增加 `review-spec.md` 生成器 |
| `v0.8` | 团队看板 | 基于 JSON 状态输出做本地 Web 页面 |
| `v1.0` | 企业试点 | 模板配置、团队规范、统计报表、接入文档统一成正式版本 |

## 与 Trek 的取舍

| Trek 能力 | Harness 处理方式 |
| --- | --- |
| YAML preset 节点编排 | 暂时保持 Harness 固定阶段，后续只开放验证配置和模板配置 |
| `check_script` 节点校验 | 吸收为 phase 级检查脚本，避免引入过细节点系统 |
| `status` 和 `dashboard` | 优先借鉴，作为 Harness 企业级展示能力基础 |
| `/init-dev-guide` 和 `/init-dev-url` | 优先借鉴，作为项目画像能力基础 |
| `review-spec-generator` | 优先借鉴，作为技术评审材料生成能力 |
| rollback 和复杂 session 治理 | 后续再评估，当前阶段优先保证主流程简单可靠 |

## 推广材料方向

| 材料 | 用途 |
| --- | --- |
| 一页产品介绍 | 用于解释 Harness 解决什么问题 |
| 五分钟演示脚本 | 用一个需求展示从确认到验证的全过程 |
| 团队接入手册 | 用于说明安装、配置和日常使用方式 |
| 负责人视角看板截图 | 用于展示团队管理价值 |
| 典型案例复盘 | 用真实需求说明 Harness 如何减少返工、保留证据和提升质量 |

## 第一批任务拆分

| 编号 | 任务 | 验收标准 |
| --- | --- | --- |
| `EP-001` | 增强当前任务状态输出 | `task.py current` 能显示缺失证据和下一步建议 |
| `EP-002` | 增加任务列表 JSON 输出 | `task.py list --json` 能返回全部任务状态 |
| `EP-003` | 增加安装状态记录 | 安装后生成 `.harness/install-state.json` |
| `EP-004` | 增加安装诊断命令 | 能检查脚本、hooks、skills、agents 是否齐全 |
| `EP-005` | 增加安装进度事件 | CLI 显示进度条，并写入 `.harness/runtime/install-progress.json` |
| `EP-006` | 默认安装项目文档扫描 Skill | 安装后存在 `.claude/skills/project-doc-scanner/SKILL.md` |
| `EP-007` | 增加项目文档配置 | Skill 能生成或读取 `.harness/project-docs.json` |
| `EP-008` | 实现项目文档扫描流程 | Skill 能先检测项目状态、确认模板来源和写入范围，再调度子代理扫描 |
| `EP-009` | 生成项目开发指南 | 能基于当前项目生成 `docs/standards/project-guide.md` |
| `EP-010` | 生成接口文档 | 能生成 `docs/standards/api/url-index.md` 和 `docs/standards/api/detail.md` |
| `EP-011` | 增加项目文档审阅状态 | 能记录 `draft`、`approved`、`needs_update`、`stale` |
| `EP-012` | 增加审阅保护能力 | `approved` 文档默认生成候选稿，用户同意覆盖后自动备份旧版本 |
| `EP-013` | 生成扫描摘要和待审阅清单 | 能生成 `.harness/project-docs/reviews/<timestamp>-scan-summary.md` 和 `docs/standards/project-docs-review.md` |
| `EP-014` | 生成技术评审文档 | 能基于任务产物生成 `review-spec.md` |

### 项目文档扫描 Skill 首版任务

首版先支持 Claude Code，目标是让 `project-doc-scanner` 能随 Harness 安装进入项目，并完成项目文档扫描的基础状态管理、索引更新和文档骨架生成。

| 顺序 | 任务 | 交付内容 | 验收标准 |
| ---: | --- | --- | --- |
| 1 | 安装 `project-doc-scanner` Skill | 在安装器中写入 `.claude/skills/project-doc-scanner/SKILL.md` | `init-harness.py` 安装后目标项目存在该 Skill 文件 |
| 2 | 新增 `project.py` 脚本 | 写入 `.harness/scripts/project.py`，提供项目文档状态管理入口 | 支持 `python3 .harness/scripts/project.py docs status` 和 `docs init-config` |
| 3 | 管理项目文档配置 | 读写 `.harness/project-docs.json` | 缺失配置时能生成默认配置，已有配置时能读取并展示摘要 |
| 4 | 管理项目画像状态 | 读写 `.harness/project-profile.json` | 能记录文档位置、审阅状态、内容哈希、生成时间和扫描摘要位置 |
| 5 | 更新文档索引 | 使用受控区块更新 `docs/index.md` 和 `docs/standards/index.md` | 区块外原有内容保持不变，区块重复执行时只替换 Harness 管理区块 |
| 6 | 固化 Skill 交互流程 | 在 `SKILL.md` 中定义“先检测，再确认，再扫描” | 已有文档时提示增量扫描，缺少文档时提示首次扫描，缺少配置时询问模板来源 |
| 7 | 生成首版文档骨架 | 生成 `project-guide.md`、`api/url-index.md`、`api/detail.md`、`project-docs-review.md` | 文档包含判断、证据、置信度、待确认项结构 |
| 8 | 支持审阅状态管理 | 支持 `draft`、`approved`、`needs_update`、`stale` | `docs approve --all` 能把目标文档状态更新为 `approved` 并记录哈希 |

## 评估指标

| 指标 | 含义 |
| --- | --- |
| 接入项目数 | 已安装 Harness 的项目数量 |
| 活跃任务数 | 一段时间内使用 Harness 推进的需求数量 |
| 项目文档初始化率 | 已生成项目知识包的项目比例 |
| 项目文档审阅通过率 | 进入 `approved` 状态的项目知识文档比例 |
| 阶段完成率 | 任务从 `clarify` 推进到 `done` 的比例 |
| 验证通过率 | `verify.py all` 成功的比例 |
| 证据完整率 | 必要产物齐全的任务比例 |
| 人工评审采用率 | `review-spec.md` 被生成或使用的比例 |

## 总体方向

Harness 企业级升级的重点是增强可见性、可诊断性、可接入性和可展示性。主流程保持简洁，周边能力逐步加厚，让团队能用、负责人能管、平台团队能推广。
