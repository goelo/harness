# 实现计划

## 开发意图摘要

增强 Harness 的通用需求开发能力，在需求确认、实现计划、测试证据、开发证据和审查证据中加入业务契约结构。业务契约用于记录业务场景、输入条件、预期行为、可观测信息和测试要求，使日常业务需求中的细节能够进入后续测试、实现、审查和验证。

## 影响范围

修改 `harness_scripts/task.py`、`harness_scripts/verify.py`、`init-harness.py`、`README.md` 和对应测试文件。安装到目标项目后的 `.harness/scripts/task.py`、`.harness/scripts/verify.py`、`.claude/skills/requirement-confirmation/SKILL.md`、`.claude/skills/requirement-development/SKILL.md`、`.claude/agents/*.md`、`AGENTS.md` 和 `CLAUDE.md` 都需要体现业务契约要求。

## 技术方案

`task.py clarify confirm` 增加 `--business-contract` 参数，参数值使用 JSON object 表示一条业务契约。`clarification.jsonl` 保存 `businessContracts`，`clarification.md` 渲染业务契约表格，并在 front matter 中记录业务契约数量。

`implementation-plan.md` 固定章节增加 `业务契约覆盖`，`task.py advance red` 会校验该章节存在且非空。

`verify.py red` 和 `verify.py green` 增加 `--contract-coverage` 与 `--uncovered-contract` 参数，分别写入 `contractCoverage` 和 `uncoveredContracts`。

`task.py review record` 增加业务契约审查字段，`task.py advance validate` 在业务契约审查失败或存在缺失契约时拒绝推进。

## 可测试契约

1. `task.py clarify confirm --business-contract <json>` 成功后，`clarification.jsonl` 包含 `businessContracts`，`clarification.md` 包含业务契约表格和契约数量。
2. 缺少 `业务契约覆盖` 章节的 `implementation-plan.md` 无法推进到 `red`。
3. `verify.py red` 与 `verify.py green` 能保存 `contractCoverage` 和 `uncoveredContracts`。
4. `task.py review record` 默认记录业务契约审查通过，显式失败时 `advance validate` 会拒绝推进。
5. `init-harness.py` 安装出的技能、角色和说明文件包含业务契约要求。

## 业务契约覆盖

| 契约编号 | 代码位置 | 测试位置 | 审查要点 |
| --- | --- | --- | --- |
| BC-001 | `harness_scripts/task.py` | `tests/test_task_cli.py` | 需求确认能保存并渲染业务契约 |
| BC-002 | `harness_scripts/task.py` | `tests/test_task_cli.py` | 实现计划必须包含业务契约覆盖章节 |
| BC-003 | `harness_scripts/verify.py` | `tests/test_verify.py` | RED 和 GREEN 证据能保存契约测试映射 |
| BC-004 | `harness_scripts/task.py` | `tests/test_task_cli.py` | review 结果能阻止缺少业务契约覆盖的任务进入 validate |
| BC-005 | `init-harness.py`、`README.md` | `tests/test_init_harness.py` | 安装模板和说明文件包含业务契约要求 |

## Slice 顺序

1. 增加业务契约相关失败测试。
2. 修改 `task.py`，支持业务契约记录、计划章节校验和 review 门禁。
3. 修改 `verify.py`，支持契约覆盖证据字段。
4. 修改安装模板和 README，使新安装项目也携带业务契约要求。
5. 运行目标测试和全量测试。

## 验证方式

运行以下命令：

```bash
python3 -m unittest tests.test_task_cli tests.test_verify tests.test_init_harness
python3 -m unittest discover tests
```

## 已知限制

业务契约的具体内容由每个任务提供。Harness 只校验业务契约的通用结构、测试映射和审查状态，无法自动判断某个领域规则本身是否完整。
