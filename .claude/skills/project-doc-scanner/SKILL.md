---
name: project-doc-scanner
description: |
  当协作者要求扫描当前项目、初始化项目文档、生成接口文档、更新 docs/standards 下项目知识文档时使用。
  首版面向 Claude Code 使用。
---

# Project Doc Scanner

<!-- harness-managed-skill -->

该 skill 用于把当前项目扫描结果整理成支持 AI 自动化开发的长期项目文档。文档会放在 `docs/standards/`，负责人可以 review 文档是否准确。

## 核心规则

固定采用“先检测，再确认，再扫描”。

1. 先运行 `python3 .harness/scripts/project.py docs status --json` 检查当前项目文档状态。
2. 如果 `.harness/project-docs.json` 或 `.harness/project-profile.json` 缺失，先询问是否执行初始化。
3. 初始化命令为 `python3 .harness/scripts/project.py docs init-config`。
4. 如果已有 `approved` 文档，覆盖前必须先得到明确确认，并保留备份。
5. 扫描时优先使用 Claude Code 子代理读取不同代码区域，避免主会话窗口被大量代码细节污染。
6. 生成文档时，每个关键判断都要写明“判断、证据、置信度、待确认项”。

## 默认产物

| 文件 | 用途 |
| --- | --- |
| `.harness/project-docs.json` | 项目文档初始化配置 |
| `.harness/project-profile.json` | 文档审阅状态、哈希和负责人确认记录 |
| `docs/standards/project-guide.md` | 项目架构、模块职责、启动方式和开发入口 |
| `docs/standards/api/url-index.md` | 接口地址索引 |
| `docs/standards/api/detail.md` | 接口请求、响应、鉴权、错误码和业务约束 |
| `.harness/analysis/latest/*.json` | 子代理扫描中间结果 |

## 操作顺序

### 1. 检测状态

```bash
python3 .harness/scripts/project.py docs status --json
```

根据输出判断文档是否缺失、草稿、已确认、需要更新或过期。

### 2. 初始化配置

在得到确认后运行：

```bash
python3 .harness/scripts/project.py docs init-config
```

该命令只创建配置、状态文件、`docs/standards/api/` 目录，并维护 `docs/index.md` 和 `docs/standards/index.md` 中的 harness 管理区块。

### 3. 子代理扫描

根据项目类型拆分扫描任务。常见拆分方式：

| 子代理 | 扫描范围 |
| --- | --- |
| 架构扫描 | 入口文件、模块目录、依赖方向、启动方式 |
| 接口扫描 | 路由、控制器、RPC 定义、事件入口 |
| 质量扫描 | 测试命令、构建命令、配置文件、常见变更约束 |

子代理只返回结构化摘要和证据文件位置，主会话负责汇总成文档。

### 4. 文档生成与确认

文档生成后先保持 `draft` 状态。负责人确认准确后运行：

```bash
python3 .harness/scripts/project.py docs approve --all --approved-by "<reviewer>"
```

审批后 `.harness/project-profile.json` 会记录文档哈希。后续文档内容变化会显示为 `stale`。

## 生成要求

1. 接口文档必须覆盖入口地址、代码位置、请求字段、响应字段、鉴权方式、错误情况和待确认项。
2. 项目说明必须覆盖目录结构、核心模块、启动方式、测试方式、常见开发入口和重要约束。
3. 对无法确认的内容，写入待确认项，禁止编造成确定事实。
4. 已确认文档默认不能覆盖。只有在协作者明确同意覆盖后，才生成新版本。
5. 临时扫描结果默认只保留 `.harness/analysis/latest/`，配置 `keepHistory=true` 时再保存历史。
