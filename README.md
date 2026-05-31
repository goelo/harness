# Agent Harness

Agent Harness 是一套面向 Claude Code 和 Codex 的工程开发辅助框架，用阶段状态、证据文件和角色职责约束 AI 完成需求开发。

它的目标是减少模型差异带来的执行偏差。团队成员用自然语言提出需求，AI 通过 harness 内部脚本维护任务状态、需求确认记录、实现计划、测试证据、审查证据和最终验证结果。

## 安装

默认安装到当前项目：

```bash
curl -fsSL https://git.xiaojukeji.com/morganli/harness/raw/master/install-internal.sh | bash
```

指定目标项目：

```bash
HARNESS_TARGET=/path/to/project \
    curl -fsSL https://git.xiaojukeji.com/morganli/harness/raw/master/install-internal.sh | bash
```

跳过 RTK 和 Caveman 自动安装：

```bash
curl -fsSL https://git.xiaojukeji.com/morganli/harness/raw/master/install-internal.sh \
    | bash -s -- --no-rtk --no-caveman
```

## 安装产物

| 位置 | 内容 |
| --- | --- |
| `.harness/workflow.md` | 阶段提示文本 |
| `.harness/verify.json` | lint、type、test、coverage、scope 检查配置 |
| `.harness/scripts/task.py` | 任务状态和阶段推进工具 |
| `.harness/scripts/verify.py` | 测试证据和最终验证工具 |
| `.harness/scripts/context.py` | 角色上下文读取工具 |
| `.harness/runtime/sessions/` | 本机会话指针，已加入 `.gitignore` |
| `docs/tasks/` | 需求开发任务包 |
| `docs/standards/` | 团队长期工程规范 |
| `docs/index.md` | 项目文档索引 |
| `.claude/hooks/harness-*.py` | Claude Code hooks |
| `.codex/hooks/harness-*.py` | Codex hooks |
| `.claude/agents/{architect,developer,tester}.md` | 三个阶段角色定义 |
| `.claude/skills/requirement-confirmation/SKILL.md` | 需求确认 skill |
| `.claude/skills/requirement-development/SKILL.md` | 需求开发 skill |
| `.claude/skills/grill-me/SKILL.md` | 旧名称兼容入口，转入需求确认 |
| `.claude/skills/harness-implement/SKILL.md` | 旧名称兼容入口，转入需求开发 |
| `CLAUDE.md`、`AGENTS.md` | 给模型读取的项目协作规则 |

## 使用方式

团队成员日常使用自然语言和 AI 对话：

| 表达 | AI 应当执行的处理 |
| --- | --- |
| 按 `design.md` 开发 | 进入需求开发 |
| 继续需求开发 | 读取当前任务，推进下一阶段 |
| 查看当前需求开发状态 | 展示当前 `status`、`phase` 和缺失证据 |
| 归档当前任务 | 在验证完成后归档任务包 |

命令行工具主要供 AI、hooks 和测试使用。团队成员日常开发中通常无需手工执行这些命令。

## 需求确认

每次需求开发前必须先进入 `requirement-confirmation`。即使 `design.md`、`spec.md` 或 `requirements.md` 已经完整，也要先复述开发意图、验收标准和边界条件，并等待协作者确认。

需求来源优先级：

| 优先级 | 来源 |
| --- | --- |
| 1 | 协作者显式指定的文件 |
| 2 | 项目根目录 `design.md` |
| 3 | 项目根目录 `spec.md` |
| 4 | 项目根目录 `requirements.md` |
| 5 | `inline-request` |

确认结果写入 `docs/tasks/<task>/clarification.jsonl`。`clarification.md` 由工具生成，只作为阅读快照。阶段门禁以 `clarification.jsonl` 为准。

## 阶段状态

`task.json.status` 表示任务大状态，`task.json.phase` 表示细阶段。阶段顺序固定：

```text
clarify -> doc-plan -> red -> green -> review -> validate -> done -> archived
```

| 阶段 | 角色 | 必要产物 |
| --- | --- | --- |
| `clarify` | 主会话 | `clarification.jsonl`、`clarification.md` |
| `doc-plan` | `architect` | `implementation-plan.md`、`scope.json`、三份 `context.<role>.jsonl` |
| `red` | `tester` | `test-result.red.json` |
| `green` | `developer` | `test-result.green.json` |
| `review` | `architect` | `review-result.json` |
| `validate` | `tester` | `verify-result.json` |
| `done` | 主会话 | 允许归档 |

阶段推进只能通过 `task.py advance <phase>` 完成。受控文件只能由 harness 工具生成或更新。

## 实现计划

`implementation-plan.md` 只保存实现计划，固定章节如下：

```markdown
# 实现计划

## 开发意图摘要
## 影响范围
## 技术方案
## 可测试契约
## Slice 顺序
## 验证方式
## 已知限制
```

需求原文、长背景和讨论记录保存在需求来源文件与 `clarification.jsonl` 中。

## 三个角色

| 角色 | 阶段 | 职责 |
| --- | --- | --- |
| `architect` | `doc-plan`、`review` | 编写实现计划、维护 `scope.json`、检查实现符合性 |
| `tester` | `red`、`validate` | 编写失败测试、补充边界测试、生成测试证据 |
| `developer` | `green` | 根据 RED 测试完成最小实现 |

默认执行模式是 `agent-team`。如果当前 AI 客户端没有子代理能力，可以降级为 `single-session`，并在 `task.json.executionModeFallbackReason` 记录原因。

## 验证

`.harness/verify.json` 默认要求 `test` 和 `scope`：

```json
{
  "required": ["test", "scope"],
  "commands": {
    "lint": "",
    "type": "",
    "test": "",
    "coverage": ""
  },
  "scope": {
    "denied": [".harness/runtime/**", "docs/standards/**"]
  }
}
```

团队可以按项目情况开启 `lint`、`type`、`coverage`。最终阶段通过 `verify.py all` 生成 `verify-result.json`。

## 本仓测试

```bash
python3 -m unittest discover tests
```

当前测试覆盖安装产物、hooks、任务状态机、验证工具和端到端阶段推进。
