#!/usr/bin/env bash
# install-internal.sh — one-line installer for Agent Harness.
#
# Default usage (install into current directory, via SSH):
#
#   TMP=$(mktemp -d -t harness-install-XXXXXX) && \
#   git clone --depth 1 --branch master git@git.xiaojukeji.com:comercial/harness.git "$TMP/harness" && \
#   bash "$TMP/harness/install-internal.sh"
#
# Pass extra flags to init-harness.py (note the -s -- separator):
#
#   TMP=$(mktemp -d -t harness-install-XXXXXX) && \
#   git clone --depth 1 --branch master git@git.xiaojukeji.com:comercial/harness.git "$TMP/harness" && \
#   bash "$TMP/harness/install-internal.sh" --no-rtk --no-caveman
#
# Override defaults via env vars:
#
#   HARNESS_BRANCH=develop  curl ... | bash
#   HARNESS_TARGET=/path/to/proj  curl ... | bash
#   HARNESS_REPO=git@your.git.host:x/harness.git  bash install-internal.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (env-overridable)
# ---------------------------------------------------------------------------
HARNESS_REPO="${HARNESS_REPO:-git@git.xiaojukeji.com:comercial/harness.git}"
HARNESS_BRANCH="${HARNESS_BRANCH:-master}"
HARNESS_TARGET="${HARNESS_TARGET:-$PWD}"

# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------
say()  { printf '\033[1;34m▶\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------
for cmd in git python3; do
    command -v "$cmd" >/dev/null 2>&1 || die "需要 $cmd,请先安装。"
done

# Python version sanity (init-harness.py uses 3.10+ features like X|None types)
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    die "需要 python3 ≥ 3.10,当前是 $PY_VER"
fi

# Target dir exists & writable
[ -d "$HARNESS_TARGET" ] || die "目标目录不存在: $HARNESS_TARGET"
[ -w "$HARNESS_TARGET" ] || die "目标目录不可写: $HARNESS_TARGET"

# ---------------------------------------------------------------------------
# Shallow clone harness into a tempdir, run init, clean up
# ---------------------------------------------------------------------------
TMP=$(mktemp -d -t harness-install-XXXXXX)
trap 'rm -rf "$TMP"' EXIT

say "下载 harness ($HARNESS_BRANCH 分支)..."
git clone --quiet --depth 1 --branch "$HARNESS_BRANCH" \
    "$HARNESS_REPO" "$TMP/harness" \
    || die "git clone 失败,检查网络 / 仓库地址 / 分支名"
ok "下载完成"

say "在 $HARNESS_TARGET 上安装 harness..."
python3 "$TMP/harness/init-harness.py" --target "$HARNESS_TARGET" "$@"

ok "Harness 安装完成。"
echo "" >&2
echo "    试一次:在你的项目跟 Claude 说「按 design.md 开发」" >&2
echo "" >&2
