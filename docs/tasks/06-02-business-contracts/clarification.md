---
confirmation_source: live
confirmed: true
confirmed_by: collaborator
open_questions: []
source_doc: inline-request
source_doc_hash: sha256:192dc47569825d7fd8b2f52422236cf694008e7a5d3bc68533b21ad81a3aceda
---

# 需求确认

## 开发意图

增强 Harness 的通用需求开发能力：在需求确认、实现计划、测试证据、开发证据和审查证据中加入业务契约结构，使日常业务需求能够明确业务场景、输入输出、状态变化、异常处理、业务规则、可观测信息和权限边界，并让测试、实现、审查、验证围绕这些契约执行。

## 验收标准

1. clarification 记录支持业务契约字段，并在 clarification.md 中渲染业务契约内容。
2. implementation-plan.md 固定章节增加业务契约覆盖内容，阶段推进会校验该章节存在且非空。
3. verify.py red 和 verify.py green 支持记录 contractCoverage 和 uncoveredContracts，用于保存测试与业务契约的映射关系。
4. review-result.json 支持记录业务契约审查结果，进入 validate 前必须通过业务契约审查。
5. init-harness.py 安装模板、角色提示词和 README 同步说明业务契约机制。
6. 相关单元测试覆盖新增 CLI 参数、计划章节校验、review 门禁和安装模板内容，测试全部通过。

## 边界条件

1. 本次修改 Harness 框架、安装模板、角色提示词、README 和测试。
2. 本次只提供通用业务契约结构与校验能力，具体推荐引擎、订单、支付等领域规则由业务项目任务自行填写。
3. 本次不引入外部服务、不改变已有任务阶段顺序、不删除当前未提交变更。
