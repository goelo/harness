# Agent Harness

本项目使用 harness 支持流程化需求开发。协作者使用自然语言表达任务，模型通过内部脚本维护状态和证据文件。

## 自然语言入口

| 表达 | 处理方式 |
| --- | --- |
| 按 `design.md` 开发 | 先进入 `requirement-confirmation`，确认后再进入 `requirement-development` |
| 继续需求开发 | 读取当前任务并推进下一阶段 |
| 查看当前需求开发状态 | 读取 `task.json` 的 `status` 和 `phase` |
| 归档当前任务 | 在 `phase=done` 后移动到 `docs/tasks/archive/` |

## 目录约定

任务包保存在 `docs/tasks/<task>/`。团队工程规范保存在 `docs/standards/`。`docs/index.md` 记录这些目录用途。

## 阶段顺序

`task.json.status` 表示任务大状态，`task.json.phase` 表示细阶段。阶段顺序固定为：

```text
clarify -> doc-plan -> red -> green -> review -> validate -> done -> archived
```

阶段推进只能通过 `python3 .harness/scripts/task.py advance <phase>` 完成。

## 需求确认

需求开发前必须先完成 `requirement-confirmation`。即使需求文档完整，也要复述开发意图、验收标准和边界条件，并等待协作者确认。

`clarification.jsonl` 是需求确认门禁依据，`clarification.md` 是阅读快照。

需求确认中可以记录业务契约。业务契约用于保存业务场景、输入条件、预期行为、可观测信息和测试要求，使业务细节能够进入后续计划、测试和审查。

## 业务契约

业务契约在各阶段的使用方式如下：

| 阶段 | 契约要求 |
| --- | --- |
| `clarify` | `clarification.jsonl` 可记录 `businessContracts` |
| `doc-plan` | `implementation-plan.md` 必须包含 `业务契约覆盖` |
| `red` | `test-result.red.json` 通过 `contractCoverage` 记录测试映射 |
| `green` | `test-result.green.json` 继续记录同一批契约的实现验证 |
| `review` | `review-result.json` 通过 `businessContractCoverage` 记录审查结果 |

## 角色职责

| 阶段 | 角色 | 主要产物 |
| --- | --- | --- |
| `doc-plan` | `architect` | `implementation-plan.md`、`scope.json` |
| `red` | `tester` | `test-result.red.json` |
| `green` | `developer` | `test-result.green.json` |
| `review` | `architect` | `review-result.json` |
| `validate` | `tester` | `verify-result.json` |

hooks 会根据 `phase` 限制角色调用，并注入 `docs/standards/index.md`、`clarification.md`、`implementation-plan.md` 和角色专属 `context.<role>.jsonl`。

## 受控文件

以下文件只能由 harness 内部工具生成或更新：`task.json`、`clarification.jsonl`、`clarification.md`、`test-result.red.json`、`test-result.green.json`、`review-result.json`、`verify-result.json`。

主会话负责最终验证和 git 提交，子代理负责阶段内专业任务。
