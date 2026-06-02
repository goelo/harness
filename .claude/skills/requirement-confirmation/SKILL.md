---
name: requirement-confirmation
description: |
  需求确认 skill。用于在需求开发前逐项确认开发意图、验收标准、边界条件、依赖关系和未决问题。
  初始实现请求也必须先使用本 skill，例如 "按 design.md 开发"、"按照需求开发"、"参考 docs 进行业务逻辑开发"、"进行模块规划"。
  触发语包括 "需求确认"、"确认需求"、"grill me"、"先问清楚需求"、"需求还要再确认"。
---

# 需求确认

<!-- harness-managed-skill -->

该 skill 是 harness 需求开发前置环节。目标是让开发意图、验收标准、边界条件和关键依赖形成可核验记录，避免模型根据模糊描述自行补全。

## 必须遵守

每次只提出一个问题。

每个问题都给出推荐回答，推荐回答应当基于已知需求文档和代码检查结果。

能够通过检查仓库回答的问题，先检查仓库，再继续提问。

即使 `design.md`、`spec.md` 或 `requirements.md` 内容完整，也必须先复述开发意图，并等待协作者确认。

## 完成标准

确认完成后，通过 harness 内部工具写入 `clarification.jsonl`，并生成 `clarification.md` 阅读快照。有效确认记录必须包含：

| 字段 | 要求 |
| --- | --- |
| `developmentIntent` | 开发者理解的开发意图 |
| `acceptanceCriteria` | 可验证的验收标准 |
| `boundaries` | 明确的范围边界 |
| `businessContracts` | 业务契约列表，记录场景、输入、预期行为、可观测信息和测试要求 |
| `openQuestions` | 必须为空数组 |
| `confirmed` | 必须为 `true` |
| `confirmedBy` | 必须为 `collaborator` |
| `sourceDoc` | 需求来源文件或 `inline-request` |
| `sourceDocHash` | 需求来源内容哈希 |

业务契约是通用结构，用于让订单、支付、推荐、运营后台等日常需求都能把业务细节转成可测试、可审查的记录。每条契约至少包含 `id`、`scenario` 和 `expectedBehavior`。

`clarification.jsonl` 是阶段推进门禁依据，`clarification.md` 只作为阅读快照。
