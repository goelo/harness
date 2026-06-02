---
name: requirement-development
description: |
  需求开发 skill。仅在需求确认完成后使用，用于依据有效 clarification.jsonl 在 harness 项目中推进后续阶段。
  触发语包括 "继续需求开发"、"查看当前需求开发状态"、"归档当前任务"。
---

# 需求开发

<!-- harness-managed-skill -->

该 skill 负责组织 harness 需求开发流程。协作者通过自然语言表达任务，模型使用 `.harness/scripts/task.py`、`.harness/scripts/verify.py` 和项目 hooks 维护阶段状态与证据文件。

## 前置要求

进入开发前必须先使用 `requirement-confirmation`。如果当前任务尚未生成有效 `clarification.jsonl` 确认记录，必须停止需求开发流程，改用 `requirement-confirmation`。

即使需求文档完整，也至少复述开发意图，确认验收标准和范围边界。

未完成需求确认时，不得创建 task、不得进行模块规划、不得编写 `implementation-plan.md`，也不得调度 `architect`、`developer` 或 `tester`。

## 阶段顺序

| 阶段 | 责任角色 | 必要证据 |
| --- | --- | --- |
| `clarify` | 主会话 | `clarification.jsonl`、`clarification.md` |
| `doc-plan` | `architect` | `implementation-plan.md`、`scope.json`、三份 `context.<role>.jsonl` |
| `red` | `tester` | `test-result.red.json` |
| `green` | `developer` | `test-result.green.json` |
| `review` | `architect` | `review-result.json` |
| `validate` | `tester` | `verify-result.json` |
| `done` | 主会话 | 任务可以归档 |

阶段推进只能通过 `task.py advance <phase>` 完成。`task.json`、`clarification.jsonl`、`clarification.md`、`test-result.red.json`、`test-result.green.json`、`review-result.json` 和 `verify-result.json` 属于受控文件，由 harness 工具生成。

## 计划文件

`implementation-plan.md` 只保存实现计划，固定包含以下章节：

```markdown
# 实现计划

## 开发意图摘要
## 影响范围
## 技术方案
## 可测试契约
## 业务契约覆盖
## Slice 顺序
## 验证方式
## 已知限制
```

## 执行规则

固定使用 `agent-team` 执行模式。每个阶段必须调用对应子代理，角色会通过 hook 注入 `docs/standards/index.md`、`clarification.md`、`implementation-plan.md` 和角色自己的 `context.<role>.jsonl`。

阶段与必选子代理的对应关系固定为：`doc-plan` 和 `review` 使用 `architect`，`red` 和 `validate` 使用 `tester`，`green` 使用 `developer`。主会话负责阶段协调、验证和提交，不负责代替子代理编写阶段产物或业务代码。

业务契约必须贯穿后续阶段：`red` 和 `green` 证据通过 `contractCoverage` 和 `uncoveredContracts` 记录测试映射；`review-result.json` 通过 `businessContractCoverage` 记录审查结果；进入 `validate` 前业务契约审查必须通过。

每个阶段完成后必须写入对应证据文件，再通过 `task.py advance` 进入下一阶段。最终使用 `verify.py all` 生成 `verify-result.json`，通过后才能进入 `done`。
