# Agent Harness

一份轻量的 Claude Code 工程化脚手架,让团队协同 AI 写代码这件事可重复、可审计、可共享。

不是 IDE,不是 Cursor 替代,不是 Claude 的 fork。
就是一个 Python 脚本 + 一组 markdown 模板。

---

## 项目目标

我们用 AI 写代码,反复遇到几个问题:

1. **一句话需求,AI 起手就 200 行,还都是猜的。** 它不是写多了,是你给的需求太宽,它在 N 种合理实现里挑了"最完整的一种"。
2. **每次新会话都要重新介绍项目背景。** "我们用 Gin、四层架构、错误码从 errx 出..." 这话一周得讲五六次。
3. **跟 AI 协作 2 小时,自己什么都没干,全程在监工。** AI 反馈太快,你的注意力被它的快反馈拽住了。
4. **AI 用同样自信的语气讲对的和编造的。** 它说"我已经实现了 X",但 X 可能根本没跑过。

Harness 不能根治这些问题,但能把发生频率明显降下来。
更重要的是,它会逼你建立几个新习惯:
**先把需求写清楚再让 AI 动手 / 让上下文从文件里来而不是从你嘴里说 / 把"实时纠错"压成 3 次批量决策**。

---

## 安装

### 一行命令(默认安装到当前目录)

```bash
curl -fsSL https://git.xiaojukeji.com/comercial/harness/raw/master/install-internal.sh | bash
```

### 跳过 RTK / Caveman 自动安装

```bash
curl -fsSL https://git.xiaojukeji.com/comercial/harness/raw/master/install-internal.sh \
    | bash -s -- --no-rtk --no-caveman
```

### 装到指定项目

```bash
HARNESS_TARGET=/path/to/your/project \
    curl -fsSL https://git.xiaojukeji.com/comercial/harness/raw/master/install-internal.sh | bash
```

### 环境变量

| 变量 | 默认 | 说明 |
|------|-----|------|
| `HARNESS_REPO` | `https://git.xiaojukeji.com/comercial/harness.git` | 自定义 fork 时改这里 |
| `HARNESS_BRANCH` | `master` | 装其他分支时改 |
| `HARNESS_TARGET` | `$PWD` | 目标项目根目录 |

### 系统要求

- `python3 ≥ 3.10`
- `git`
- `curl`(用 install 脚本时)

---

## 装上之后会有什么

| 路径 | 内容 | 是否进 git |
|------|-----|----------|
| `.harness/workflow.md` | 工序卡(per-turn breadcrumb 来源) | ✓ |
| `.harness/spec/` | 团队规范(代码风格 / 测试约定 / 错误处理) | ✓(你自己写) |
| `.harness/scripts/task.py` | 任务管理 CLI | ✓ |
| `.harness/scripts/team_cleanup.py` | 兜底清进程 | ✓ |
| `.harness/tasks/` | 任务目录(每个 feature 一个子目录) | ✓(除 runtime) |
| `.harness/runtime/sessions/` | 会话状态(session id ↔ 任务) | ✗(.gitignore) |
| `.claude/hooks/harness-*.py` | 3 个 hook(SessionStart / UserPromptSubmit / PreToolUse) | ✓ |
| `.claude/agents/{architect,developer,tester}.md` | 3 个角色定义 | ✓ |
| `.claude/skills/harness-implement/SKILL.md` | 触发 skill("按 design.md 开发") | ✓ |
| `.claude/skills/grill-me/SKILL.md` | 追问 skill(把模糊需求问到清晰) | ✓ |
| `.claude/settings.json` | hook 注册 + 权限(增量合并) | ✓ |
| `CLAUDE.md` | 项目静态约束(增量追加) | ✓ |
| `.gitignore` | 增量追加 harness / Python / OS 默认 | ✓ |

跨项目共享:
- **RTK**(token 优化)— 全局装,一次到位
- **Caveman**(紧凑输出模式)— 同上

---

## 怎么用

### 1. 在项目根放 design.md

design.md 就是你的产品需求文档(也叫 spec.md / requirements.md,harness 都认)。
**这份文档是用户输入,不是 AI 输出。** 写得越细,AI 实现得越准。

如果你写不细,跟 Claude 说"用 grill-me 帮我把 design.md 问清楚"——它会一直追问到所有歧义都消除。

### 2. 跟 Claude 说一句话触发 harness 流程

可识别的触发词:
- "按 design.md 开发"
- "implement design.md"
- "用 harness 实现这份设计"
- "follow the harness flow"

skill 会自动加载,接管整套 TDD + Teams 流程。

### 3. 在 3 个 checkpoint 出场

| # | 时机 | 你做什么 |
|---|-----|---------|
| 1 | design.md 确认完后 | 这份 spec 准不准?要补什么? |
| 2 | architect 切完 slice 后 | 5 个 slice 顺序你 OK 吗?哪几个砍掉? |
| 3 | 每个 slice 完成后 | 测试全过吗?代码量合理吗?commit? |

其他时间 AI 自己跑,你做你自己的事。

---

## 三个角色

```
                ┌──────────┐   ┌───────────┐   ┌──────────┐
   design.md   │ 架构师    │   │ 测试员     │   │ 开发者    │
  ────────────▶│ 切模块    │──▶│ 写失败测试 │──▶│ 让测试   │
               │ 出 info.md│   │ (RED)     │   │ 通过(GREEN)│
               └──────────┘   └───────────┘   └──────────┘
                                  ▲
                                  └─── 测试员(再跑一次 + 边界 = VALIDATE)
```

| 角色 | 干什么 | 不干什么 |
|------|------|---------|
| `architect` | 把 design.md 翻译成 info.md(模块 / 接口契约 / slice 顺序 / 风险) | 不写需求,不写产品代码 |
| `tester` | RED 模式写失败测试;VALIDATE 模式跑测试 + 找 edge case | 不写产品代码 |
| `developer` | 让现有失败测试通过的最少代码 | 不写多余功能,不改测试 |

只有主会话能 `git commit`。Sub-agent 不碰 git。

---

## 完整工序(13 步)

```
1.  确认项目根有 design.md
2.  task.py create
3.  ★ checkpoint 1: 跟用户确认 design.md
4.  curate 3 个 manifest (context.{architect,developer,tester}.jsonl)
5.  dispatch architect → 出 info.md
6.  验证 info.md 包含可测契约
7.  ★ checkpoint 2: 跟用户确认 slice 计划
8.  task.py start (Phase 1.3 gate 检查 manifest)
9.  TeamCreate + 派 3 个持久 teammate
10. 每个 slice: tester(RED) → developer → architect(REVIEW) → tester(VALIDATE)
                ★ checkpoint 3: 用户 review
11. 主会话 commit
12. 重复 10-11 直到所有 slice 完成
13. TeamDelete + team_cleanup.py + task.py archive
```

---

## 项目结构(模板源,即本仓)

```
harness/
├── init-harness.py          # 入口脚本(模板分发器)
├── install-internal.sh      # curl 一行装的入口
├── harness_hooks/           # 3 个 Claude Code hook 脚本
│   ├── harness-session-start.py
│   ├── harness-workflow-state.py
│   └── harness-inject-context.py
├── harness_scripts/         # 装到目标项目 .harness/scripts/ 的脚本
│   ├── task.py
│   └── team_cleanup.py
├── tests/                   # 55 个单元 + 集成测试
├── HARNESS_BUG_LOG.md       # 4 轮验证 + 改动反思日志
└── README.md                # 你正在读的这份
```

**注意**:harness 是**模板分发器**,本仓是模板源。装到你项目里的产物路径不一样——
你项目里是 `.harness/` + `.claude/`,而不是这里看到的 `harness_*` 目录。

---

## 测试

```bash
cd /path/to/this/repo
python3 -m unittest discover tests
```

55 个测试,涵盖:
- init-harness.py 装产物的正确性 + 幂等性
- 3 个 hook 在不同场景下的注入行为
- task.py CLI 的状态机
- Phase 1.3 gate 拦截 seed-only manifest
- team_cleanup.py 真能 kill 僵尸进程
- 端到端:init → create → curate → start → dispatch → archive

---

## 进一步阅读

| 读什么 | 给谁 |
|------|------|
| [HARNESS_BUG_LOG.md](./HARNESS_BUG_LOG.md) | 4 轮 dogfood 验证的 bug log + 设计反思,理解"为什么这么做" |
| `.harness/workflow.md`(装上后) | per-turn breadcrumb 来源,理解 hook 行为 |

---

## 设计原则(一句话各)

- **PRD 是输入,不是输出。** AI 不替你想需求,只翻译 + 实现。
- **上下文从文件来,不从嘴里说。** 写一次到 spec,长期复用。
- **3 个 checkpoint 替代实时纠错。** 让你做决策,AI 做劳动。
- **失败测试是裁判,AI 自吹没用。** commit 前必看真实测试输出。
- **harness 管 orchestration,其他 skill 管 technique。** 与 superpowers 等 skill 共生,不互斥。

---

## 反馈与贡献

内部仓:`git@git.xiaojukeji.com:comercial/harness.git`

发现问题或想加 feature,可以直接在仓里开 issue / MR;或者把使用过程中踩到的坑写到 `HARNESS_BUG_LOG.md`,提 PR 一起讨论。
