#!/bin/bash
# 🧪 Nami Kaspa Bot 測試執行器
# by Nami 🌊

set -e

echo "═══════════════════════════════════════════════════════════════════"
echo "🧪 Nami Kaspa Bot v0.5 測試套件"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

cd "$(dirname "$0")"

# 檢查 pytest
if ! command -v pytest &> /dev/null; then
    echo "⚠️ 安裝 pytest..."
    pip install pytest pytest-asyncio -q
fi

echo "📋 測試範圍："
echo "   - 英雄屬性生成"
echo "   - ATB 戰鬥系統"
echo "   - 哥布林系統"
echo "   - 獎勵分配"
echo "   - 整合流程"
echo ""

# 執行測試
echo "🚀 開始測試..."
echo ""

pytest tests/ \
    -v \
    --tb=short \
    --color=yes \
    -x \
    2>&1 | tee /tmp/nami_test_results.log

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "═══════════════════════════════════════════════════════════════════"

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ 所有測試通過！"
else
    echo "❌ 測試失敗 (exit code: $EXIT_CODE)"
    echo "   查看詳情: /tmp/nami_test_results.log"
fi

echo "═══════════════════════════════════════════════════════════════════"

exit $EXIT_CODE
