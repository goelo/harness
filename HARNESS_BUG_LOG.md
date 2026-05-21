# Harness Bug Log

实战验证 round 1 — todolist (Go + Gin + SQLite + React TS) 项目。

格式：`[type] description — status`

类型：
- `bug` — 真正的错误，必须修
- `ux` — 不是 bug 但用户体验差
- `design` — 设计层面的问题或值得讨论的权衡
- `obs` — 观察记录，待评估是否需要改

---

## v1.6 优化（2026-05-21）

不是 round，是依据用户长期使用反馈做的简化重构。

### 改动

- **5 角色 → 3 角色**：research/architect/developer/reviewer/qa → architect/developer/tester
  - architect 吸收 research（自己做调研）和 reviewer（REVIEW + REFACTOR）的职责
  - tester 取代 qa（命名更直接），同样支持 RED + VALIDATE 双模式
- **3 manifest 替代 4 manifest**：context.{architect,developer,tester}.jsonl
- **RTK 自动安装** via curl|sh：默认开，`--no-rtk` 跳过
- **Caveman 自动安装** via curl|bash：默认开，`--no-caveman` 跳过
- **`--check-deps` 干跑模式**：不实际安装/写文件，只报告

### 设计反思

**"减法的勇气"**：v1.0→v1.5 一直在加（角色、step、manifest、cleanup script），v1.6 是第一次主动减。理由是真实使用证明了 5 角色冗余——reviewer 和 architect 的边界模糊，研究阶段和设计阶段在小项目里融合更顺。**当反馈说"重"的时候，不要找借口加新机制覆盖，先看能不能减原有机制。**

**单 agent 多阶段** 是 Teams 持久化的产物：同一个 teammate 在多次 SendMessage 间复用 context，所以 tester 既能 RED 又能 VALIDATE，不浪费 spawn 成本。

55 tests 全过（含 4 个 RTK + 2 个 Caveman 新测试）。

---

## Round 4 — pwstrength v1.5.3 验收（2026-05-20）

✅ **v1.5.3 持久 teammate 设计验证成功**：4 个 teammate 跨 3 slice 复用，零累积。

✅ **共生性验证通过**：带全部用户级 skill / plugin 跑，harness-implement skill 优先级被尊重，没被其他 skill 覆盖。

📊 **数据**：197 行实现 / 1252 行测试 / 150 pass + 2 skip / 6.4:1 测比 / 4 commits / < 10ms 执行

📋 复盘文档：`/Users/didi/go/src/git.xiaojukeji.com/pwstrength/retrospective.md`

### 新发现（按严重度）

- [x] **bug (严重)**: TeamDelete 不杀 teammate 进程 — **已修 v1.5.4**（脚本化）
  - 修复：harness_scripts/team_cleanup.py 用 pgrep + SIGTERM/SIGKILL 兜底；init-harness 部署到 .harness/scripts/team_cleanup.py；SKILL.md step 14 改为先 TeamDelete 再调 cleanup 脚本
  - 测试：spawn 假进程验证真能 kill；4 个测试全过
  - 设计反思：固定确定性流程（杀进程、清配置）应固化为脚本，skill 只调用。这条洞见来自用户："我们是不是通过 scripts 的脚本来保证这种固定化的流程"

- [x] **bug**: 首 commit 把 __pycache__ 暂存 — **已修 v1.5.4**
  - 修复：init-harness.py 加 GITIGNORE_TEMPLATE + create_gitignore()，覆盖 Python/Node/OS/IDE 默认；user 已有 .gitignore 时增量追加
  - 幂等：重跑 init 不会重复追加（用 `# harness defaults` 标记防重）

- [x] **bug (中等)**: TaskCreate 在 TeamCreate 之前创建孤儿任务 — **已修 v1.5.4**
  - 修复：SKILL.md step 10b 加显眼提示"TaskCreate after TeamCreate"

- [x] **bug (中等)**: architect 锚点表 35 vs 45 typo 漏到 GREEN — **已修 v1.5.4**
  - 修复：architect.md 加"anchor 表 expected-value 必须由 formula 驱动"章节，附 bad/good 对照例子
  - 实质：让公式为 ground truth，expected 在 qa-RED 阶段独立计算，避免 architect 手算 typo 传染

- [x] **gap (轻微)**: Manifest write Read-before-Write 工具约束 — **已修 v1.5.4**
  - 修复：SKILL.md step 5 加"用 Edit replace_all 或先 Read 再 Write"工具提示

- [x] **gap (轻微)**: commit 前没显式 invoke verification-before-completion — **已修 v1.5.4**
  - 修复：SKILL.md slice 提交段加"调用 superpowers:verification-before-completion skill 或至少手工跑测试看到 GREEN"

---

## Round 3 — todolist 全栈 v1.5 验收（2026-05-20）

✅ **整体成功**：5 slice TDD 完整跑完，211 tests 全 GREEN，task 正确归档。

| 验收点 | 结果 |
|--------|------|
| Skill 自动加载（"按 design.md 开发"） | ✓ |
| User checkpoint 守护（PRD 确认 / slice 计划 / 每 slice review） | ✓ |
| 5 slice 都走完整 TDD 4 阶段 | ✓ |
| Sub-agent 都传 mode: bypassPermissions | ✓ |
| Sub-agent 不 commit，主会话独占 git | ✓ |
| 每 slice 1 commit + bootstrap + archive = 7 commits | ✓ |
| Backend 四层结构（api/service/repository/model + middleware） | ✓ |
| Frontend 清晰分层（api/hooks/components/types） | ✓ |
| Backend tests pass | ✓ |
| Frontend 96 tests pass | ✓ |
| 任务正确归档（status=archived + summary.md + archive/） | ✓ |
| 团队清理无残留（config.json 不存在 + 无 tmux session） | ✓（但靠 AI 手工清，见下） |
| 设计哲学吻合：harness 管 orchestration，技术细节 AI 自决 | ✓ |

❌ **核心遗留问题**：v1.5.2 shutdown_request 修法实测无效，AI 靠 tmux kill 强杀。需 v1.5.3。

📍 **小问题**：archive 时没 TeamDelete（team 已被 AI 提前清空，但仍是流程缺失）。

📊 **数据**：1 个 architect + 5 slice × 4 = 21 个 sub-agent dispatch。整套耗时约 4 小时（含若干修复迭代）。

---

## Round 1 — todolist 5 角色全栈

### Plan 阶段

- [x] **bug**: workflow.md v1.1 的步骤顺序错（curate 在 architect 之后） — **已修** (2026-05-19)
  - 影响：architect 跑时看不到 spec，设计可能脱离团队规范
  - 修复：移到 architect 之前
  - 双重防御：task.py start 加 gate

- [x] **bug**: AI 容易跳过 Phase 1.3（curate manifest） — **已修**
  - 修复：task.py start 检查 manifest 不能只有 _example 行，否则 exit 1
  - 逃生口：--force

- [ ] **ux**: 默认 manifest 是 `_example` seed row + 用户加的真行，看起来很乱 — pending
  - 目前 jsonl 长这样：
    ```
    {"_example": "Add entries..."}
    {"file": ".harness/spec/index.md", "reason": "..."}
    ```
  - 改进：seed 注释改成 `#` 注释行（jsonl 标准里不支持，但很多工具会忽略），或者干脆不 seed

### Execute 阶段

- [ ] **design**: developer/reviewer/qa 是顺序还是并行？ — pending 讨论
  - 当前 AI 行为：严格顺序 developer → reviewer → qa
  - 数据依赖：reviewer 和 qa 都需要 developer 的输出（diff/code），所以这三个**必须顺序**
  - 但 developer 内部可以并行：backend 和 frontend 是不同语言、不同目录，理论上可同时派两个 developer agent
  - 当前 harness 没引导并行，AI 默认串行（耗时 6m+）
  - 改进方向：CLAUDE.md / workflow.md 加一段"并行机会识别"指引

- [ ] **obs**: developer 一次完成全栈 vs 分块派遣 — pending 评估
  - 当前：一次 dispatch developer 写完后端+前端（14+ tool uses）
  - 之前 PRD 推荐分块（backend chunk → reviewer → qa → commit → frontend chunk → ...）
  - AI 没分块，可能因为 PRD 没强制
  - 改进方向：加 task 切片（subtask）支持？或者 workflow 引导"先后端后前端"？

- [x] **design (重要)**: harness 不是 TDD 的，是 "test-after" — **已修 v1.2** (2026-05-19)
  - 修复内容：
    - 顺序改为 qa(RED) → developer(GREEN) → reviewer(REFACTOR) → qa(VALIDATE)
    - architect 必须产出"可测试契约"（contract test 风格的 info.md）
    - qa 双模式：dispatch context 决定走 RED 还是 VALIDATE
    - 逃生口：trivial 改动可声明跳过 TDD
  - 反思：v1.1 设计时我潜意识用了"传统团队"模型，没对称应用 TDD 哲学到 AI 引导上

### TBD（继续记录中）

- 待 reviewer 跑完看输出
- 待 qa 跑完看输出
- 待 main session commit 行为
- 待 /harness:finish 行为

---

## 设计观察（不一定是 bug，但值得记录）

- [x] **design (重要)**: harness 与其他 skill 的关系没明示 — **已加 coexistence 章节 v1.5.3** (2026-05-20)
  - 用户洞察："如果用户安装了其他的 skill，是否还能严格按照 harness 执行？我觉得是可以共生的"
  - 设计哲学定位：
    - harness 管 **orchestration**（角色、顺序、边界、协议、状态机）
    - 其他 skill 管 **technique**（HOW，比如 TDD 怎么写测试、debug 怎么排查）
    - 他们是互补的，不是互斥的
  - 修复：
    - SKILL_HARNESS_IMPLEMENT 加 "Coexistence with Other Skills" 章节，列出明确分工 + conflict resolution 规则
    - CLAUDE.md HARNESS_SECTION 加同样说明（让每次会话静态加载时都看到）
  - 关键澄清：clean-claude.sh 是验证用的隔离工具，**不代表 harness 排斥其他 skill**。生产使用时其他 skill 应该正常协同

- [x] **bug (严重)**: shutdown_request 修法失败 + fresh-spawn 设计有问题 — **已修 v1.5.3** (2026-05-20，方案 C)
  - Round 3 验收发现：shutdown_request 不会终止 idle teammate；AI 靠 tmux kill 强杀 + 手改 config.json
  - 根本反思：v1.5 fresh-spawn-per-slice 解决的"stale context"问题不存在
    - PRD / info.md / manifests 在 plan 阶段定型，execute 阶段不变
    - 每 slice 真正变化的（git diff、新代码）agent 用 Read 工具自己拿
    - 所以"为防止 stale 而 fresh spawn"是过度担忧
  - 修复 (v1.5.3)：
    - SKILL_HARNESS_IMPLEMENT 改为：execute 开始 spawn 4 个持久 teammate 一次（hook 一次性注入 context），slice N 用 SendMessage(to: "qa-red", ...) 复用
    - 删除失败的 step 11b shutdown_request
    - 收尾用单次 TeamDelete 一并清掉所有 teammate
    - workflow.md in_progress 块同步更新
  - 净收益：4 个 teammate 全程稳定，零累积，零 shutdown 仪式
  - 教训：**"以为存在的问题"和"真正存在的问题"要分清**——v1.5 设计时优先解决了不存在的问题，引入了真存在的问题

- [x] **bug (严重)**: SessionStart hook 没把 session_id 导出到 CLAUDE_ENV_FILE — **已修 v1.5.1** (2026-05-20)
  - 触发：Round 3 试 v1.5 skill，AI 加载 skill 后跑 task.py current → exit 1: "No session identity (set HARNESS_CONTEXT_ID)"
  - 根因：从 Trellis 移植 session-start hook 时漏了 `_persist_context_key_for_bash`。Bash 工具调用看不到 session id，task.py 失败
  - 修复：harness-session-start.py 加 `export_context_id_to_env_file()`，向 CLAUDE_ENV_FILE 追加 `export HARNESS_CONTEXT_ID=...`
  - 验收：v1.5 skill 触发成功（这是 round 3 最大正面发现），但缺这一基础设施所以卡在第一步

- [x] **design (重要)**: 用户启动 prompt 太长（~500 字），不实际 — **已修 v1.5** (2026-05-20)
  - 用户洞察："这个我觉得可以假设应该是用户拿到的一份技术详细设计文档" + "你觉得是否需要把这个做成 skill？"
  - 修复：新增 `.claude/skills/harness-implement/SKILL.md`，AI 看到"按 design.md 开发"等触发词自动加载 skill，按 skill 步骤跑完整 v1.4 流程
  - 用户启动咒语简化：~500 字 → 一句话
  - skill description 严格不复述工作流（按 superpowers:writing-skills 指引），避免 AI 走捷径

- [x] **design (重要)**: AI 写 PRD 错位——PRD 应该是用户输入，不是 AI 输出 — **已修 v1.4** (2026-05-20)
  - 用户洞察："架构师不是写 prd？应该是根据详细设计文档来拆解技术模块？"
  - 根因：v1.3 假设用户提供"brief"，AI 写 PRD。但实际场景中用户经常已有详细设计文档
  - 修复：
    - workflow.md planning 块：如果 project root 有 design.md/spec.md/requirements.md，复制到 task 作为 prd.md，不重写
    - architect agent prompt 改为"技术分解者"，明确"不写需求，只读 PRD/design.md → 输出 info.md (模块切分 + 契约 + slice 顺序 + 风险)"
    - info.md 结构标准化：module breakdown / interface contracts / slice order / risks
  - 设计哲学转变：harness 现在更像"接收用户 spec → AI 实现"，而不是"AI 帮用户想"

- [x] **obs**: bypass permissions 不一定传给 sub-agent — **已加显式 mode 指引** (2026-05-19)
  - 问题：默认 sub-agent 继承父会话的 mode，但跨 Claude Code 版本行为不一致
  - 解决：CLAUDE.md / workflow.md 都明确说 "Agent/SendMessage 调用必须传 mode: bypassPermissions"
  - clean-claude.sh 启动时如果是 bypass 模式，会在 banner 里提示用户

- [x] **obs**: 没用 Claude Code 的 Agent Teams 功能 — **已加 v1.3 Teams 集成** (2026-05-19)
  - 修复内容：
    - workflow.md / CLAUDE.md 改为 Teams 派遣模式
    - 每个 agent prompt 加 "重读 prd.md/info.md" 指令（应对 SendMessage 不触发 hook）
    - Hook 不变：Agent(team_name, name, subagent_type) 仍触发 PreToolUse(Agent)，subagent_type 还是关键字段
  - 设计权衡：
    - Fresh spawn per slice（hook 重新注入）vs persistent teammate（SendMessage 走持久 context）
    - 默认推荐 fresh spawn，但留 persistent 选项给需要的场景
  - 注意点：SendMessage 不走 hook，state 变化要靠 agent 主动 broadcast + 接收方主动重读
