#!/bin/bash
# ============================================
# 启动 Claw Web Chat (集成 Claude AI)
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# ==== 配置区域 (请修改这里) ====
export ANTHROPIC_API_KEY="sk-ant-your-api-key-here"
# ===============================

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

echo "========================================"
echo "  Claw Web Chat 启动中..."
echo "========================================"
echo ""
echo "请在浏览器打开: http://127.0.0.1:8080"
echo ""
echo "模型: claude-sonnet-4-20250514"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python -m src.main web-ui --host 127.0.0.1 --port 8080