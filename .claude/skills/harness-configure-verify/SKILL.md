---
name: harness-configure-verify
description: 当 harness 项目需要配置 .harness/verify.json，或者需要设置提交前 lint、类型检查、测试和覆盖率检查时使用。
---

# Harness Configure Verify

<!-- harness-managed-skill -->

为当前项目配置 `.harness/verify.json`。目标是让
`python3 .harness/scripts/verify.py all` 在每个 harness slice 提交前真正执行
lint、类型检查、测试、覆盖率和文件变更范围检查。

该 skill 同时供 Claude Code 和 Codex agents 使用。

## 必须执行的流程

1. 读取当前 `.harness/verify.json`。
2. 检查项目入口文件：`Makefile`、`go.mod`、`package.json`、
   `pyproject.toml`、`Cargo.toml`、`README.md` 和 `scripts/`。
3. 识别不会修改文件的检查命令：
   - `commands.lint`
   - `commands.type`
   - `commands.test`
   - `commands.coverage`
4. 先给出推荐 JSON patch，等待确认后再写入文件。
5. 确认后更新 `.harness/verify.json`。
6. 条件允许时运行重点验证命令，然后报告结果。

## 命令规则

1. 优先选择只检查的命令，避免会重写文件的命令。
2. 避免使用带 `-w`、`--write` 或同类修改参数的 formatter 脚本。
3. 覆盖率阈值由项目自己的 coverage 命令负责，harness 只检查命令退出码。
4. 如果无法从项目文件推断命令，说明不确定的字段，并给出最保守的占位命令。

## 常见示例

Go 项目常用：

```json
{
  "commands": {
    "lint": "test -z \"$(gofmt -l .)\" && go vet ./...",
    "type": "go test -run '^$' ./...",
    "test": "go test ./...",
    "coverage": "go test ./... -coverprofile=.harness/runtime/coverage.out"
  },
  "scope": {
    "denied": [".harness/runtime/**", "output/**", "log/**"]
  }
}
```

Node 项目常用 package scripts：

```json
{
  "commands": {
    "lint": "npm run lint",
    "type": "npm run typecheck",
    "test": "npm test",
    "coverage": "npm run coverage"
  },
  "scope": {
    "denied": [".harness/runtime/**", "dist/**", "coverage/**"]
  }
}
```
