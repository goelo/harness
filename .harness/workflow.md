# Harness 阶段说明

[workflow-phase:no_task]
当前没有激活的需求开发任务。收到需求开发请求时，先进入 `requirement-confirmation`，确认开发意图、验收标准和范围边界。
[/workflow-phase:no_task]

[workflow-phase:clarify]
当前处于需求确认阶段。有效门禁是 `clarification.jsonl` 中最近一条 `event=confirm` 记录，且 `openQuestions=[]`、`confirmed=true`、`confirmedBy=collaborator`。
[/workflow-phase:clarify]

[workflow-phase:doc-plan]
当前处于实现计划阶段。只允许调用 `architect`，生成 `implementation-plan.md`、`scope.json`，并补齐三份 `context.<role>.jsonl` 的真实文件引用。
[/workflow-phase:doc-plan]

[workflow-phase:red]
当前处于 RED 阶段。只允许调用 `tester`，目标是写出预期失败测试，并通过 `verify.py red` 写入 `test-result.red.json`。
[/workflow-phase:red]

[workflow-phase:green]
当前处于 GREEN 阶段。只允许调用 `developer`，目标是让 RED 阶段同一组目标测试通过，并通过 `verify.py green` 写入 `test-result.green.json`。
[/workflow-phase:green]

[workflow-phase:review]
当前处于 REVIEW 阶段。只允许调用 `architect`，检查需求符合性和代码质量，并通过 `task.py review record` 写入 `review-result.json`。
[/workflow-phase:review]

[workflow-phase:validate]
当前处于 VALIDATE 阶段。只允许调用 `tester`，补充验证后由主会话运行 `verify.py all` 写入 `verify-result.json`。
[/workflow-phase:validate]

[workflow-phase:done]
任务已经完成验证，可以归档。
[/workflow-phase:done]

[workflow-phase:archived]
任务已经归档。
[/workflow-phase:archived]
