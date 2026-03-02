#!/usr/bin/env bash
# 🌊 Whisper Covenant — One-Click Installer
# curl -sL https://raw.githubusercontent.com/ryansoq/Nami_backpack/main/projects/whisper-covenant/install.sh | bash
set -euo pipefail

# ─── Colors & Helpers ─────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'
ok()   { echo -e "  ${GREEN}✅ $1${NC}"; }
fail() { echo -e "  ${RED}❌ $1${NC}"; exit 1; }
warn() { echo -e "  ${YELLOW}⚠️  $1${NC}"; }
info() { echo -e "  ${CYAN}$1${NC}"; }
step() { echo -e "\n${BOLD}[$1] $2${NC}"; }

WHISPER_DIR="$HOME/kaspa-whisper"
WALLET_DIR="$HOME/.kaspa-whisper"
WALLET_FILE="$WALLET_DIR/wallet.json"
REPO_URL="https://github.com/ryansoq/Nami_backpack.git"
FAUCET_URL="https://office.openclaw-alpha.com/faucet"

echo ""
echo -e "${BOLD}🌊 Whisper Covenant 安裝程式${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── [1/6] Check Environment ─────────────────────────────────────
step "1/6" "🔍 檢查環境..."

# Python3
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    ok "Python $PY_VER"
else
    fail "找不到 Python3！請先安裝：\n    Ubuntu/Debian: sudo apt install python3 python3-pip\n    macOS: brew install python3"
fi

# pip
if python3 -m pip --version &>/dev/null; then
    ok "pip 已安裝"
else
    warn "pip 未安裝，嘗試安裝..."
    if [[ "$(uname)" == "Darwin" ]]; then
        python3 -m ensurepip --default-pip 2>/dev/null || fail "無法安裝 pip，請手動執行: python3 -m ensurepip"
    else
        sudo apt-get install -y python3-pip 2>/dev/null || python3 -m ensurepip --default-pip 2>/dev/null || fail "無法安裝 pip，請手動執行: sudo apt install python3-pip"
    fi
    ok "pip 安裝完成"
fi

# curl or wget
if command -v curl &>/dev/null; then
    FETCH="curl"
elif command -v wget &>/dev/null; then
    FETCH="wget"
else
    fail "需要 curl 或 wget！請先安裝。"
fi

# git
if ! command -v git &>/dev/null; then
    fail "找不到 git！請先安裝：\n    Ubuntu/Debian: sudo apt install git\n    macOS: xcode-select --install"
fi
ok "git 已安裝"

# ─── [2/6] Install Dependencies ──────────────────────────────────
step "2/6" "📦 安裝依賴..."

python3 -m pip install --quiet --upgrade kaspa eciespy 2>/dev/null || \
python3 -m pip install --quiet --upgrade --break-system-packages kaspa eciespy 2>/dev/null || \
fail "安裝 Python 套件失敗！請檢查網路連線，或手動執行:\n    pip install kaspa eciespy"

ok "kaspa SDK 安裝完成"
ok "eciespy 安裝完成"

# ─── [3/6] Clone Whisper Covenant ─────────────────────────────────
step "3/6" "📥 下載 Whisper Covenant..."

if [ -d "$WHISPER_DIR" ]; then
    warn "~/kaspa-whisper/ 已存在"
    echo -ne "  要更新到最新版嗎？(y/N) "
    # If piped (curl | bash), default to yes
    if [ -t 0 ]; then
        read -r REPLY
    else
        REPLY="y"
        echo "y (自動)"
    fi
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        cd "$WHISPER_DIR"
        git pull --quiet 2>/dev/null && ok "已更新到最新版" || warn "更新失敗，使用現有版本"
        cd - >/dev/null
    else
        ok "保留現有版本"
    fi
else
    # Sparse checkout only the whisper-covenant project
    git clone --quiet --depth 1 --filter=blob:none --sparse "$REPO_URL" "$WHISPER_DIR" 2>/dev/null || \
        fail "下載失敗！請檢查網路連線。"
    cd "$WHISPER_DIR"
    git sparse-checkout set projects/whisper-covenant 2>/dev/null
    # Move files up for convenience
    if [ -d "projects/whisper-covenant" ]; then
        cp -r projects/whisper-covenant/* . 2>/dev/null || true
        cp -r projects/whisper-covenant/.* . 2>/dev/null || true
    fi
    cd - >/dev/null
    ok "已下載到 ~/kaspa-whisper/"
fi

# ─── [4/6] Create Wallet ─────────────────────────────────────────
step "4/6" "🔑 建立錢包..."

mkdir -p "$WALLET_DIR"

if [ -f "$WALLET_FILE" ]; then
    # Wallet exists — don't overwrite!
    EXISTING_ADDR=$(python3 -c "import json; print(json.load(open('$WALLET_FILE'))['address'])" 2>/dev/null || echo "unknown")
    warn "錢包已存在，不會覆蓋！"
    info "📍 你的地址：$EXISTING_ADDR"
else
    # Generate new wallet
    python3 -c "
import json, datetime
from kaspa import PrivateKey

pk = PrivateKey.random()
address = pk.to_address('testnet').to_string()
wallet = {
    'network': 'testnet-12',
    'address': address,
    'private_key': pk.to_hex(),
    'public_key': pk.to_public_key().to_hex(),
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'purpose': 'whisper-covenant'
}
with open('$WALLET_FILE', 'w') as f:
    json.dump(wallet, f, indent=2)
print(address)
" > /tmp/.whisper_addr 2>&1 || fail "錢包建立失敗！kaspa SDK 可能未正確安裝。"

    WALLET_ADDR=$(cat /tmp/.whisper_addr)
    rm -f /tmp/.whisper_addr
    chmod 600 "$WALLET_FILE"

    ok "錢包已建立！"
    info "📍 你的地址：$WALLET_ADDR"
    info "🔐 私鑰已安全保存到 ~/.kaspa-whisper/wallet.json"
    echo ""
    warn "重要！請備份你的私鑰："
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  1. 把 ~/.kaspa-whisper/wallet.json 複製到安全的地方"
    echo "  2. 可以用 USB 隨身碟備份"
    echo "  3. 絕對不要分享給任何人！"
    echo "  ━━━━━━━━━━━━━━━━━━━━━━━━"
fi

# Read address for later use
WALLET_ADDR=$(python3 -c "import json; print(json.load(open('$WALLET_FILE'))['address'])" 2>/dev/null || echo "")

# ─── [5/6] Request tKAS from Faucet ──────────────────────────────
step "5/6" "💧 領取 tKAS..."

if [ -z "$WALLET_ADDR" ]; then
    warn "無法讀取錢包地址，跳過領取 tKAS"
else
    FAUCET_RESP=""
    if [ "$FETCH" = "curl" ]; then
        FAUCET_RESP=$(curl -s -X POST "$FAUCET_URL" \
            -H "Content-Type: application/json" \
            -d "{\"address\": \"$WALLET_ADDR\"}" 2>/dev/null || echo "")
    else
        FAUCET_RESP=$(wget -qO- --post-data="{\"address\": \"$WALLET_ADDR\"}" \
            --header="Content-Type: application/json" "$FAUCET_URL" 2>/dev/null || echo "")
    fi

    if echo "$FAUCET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('success') or d.get('tx_id') or 'already' in str(d).lower()" 2>/dev/null; then
        AMOUNT=$(echo "$FAUCET_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('amount','5'))" 2>/dev/null || echo "5")
        ok "已領取 ${AMOUNT} tKAS！"
    elif echo "$FAUCET_RESP" | grep -qi "already\|cooldown\|limit\|recent"; then
        warn "已經領取過了，請稍後再試"
    else
        warn "領取失敗（可能是網路問題），你可以稍後手動領取："
        info "💧 $FAUCET_URL"
    fi
fi

# ─── [6/6] Done! ─────────────────────────────────────────────────
step "6/6" "🎉 安裝完成！"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "📍 你的地址：$WALLET_ADDR"
info "🔐 私鑰位置：~/.kaspa-whisper/wallet.json"
echo ""
info "📨 發送加密訊息："
echo "  python3 ~/kaspa-whisper/encode.py --to <對方地址> --message \"你的訊息\" --remote"
echo ""
info "📬 讀取加密訊息："
echo "  python3 ~/kaspa-whisper/decode.py --tx <交易ID> --remote"
echo ""
info "💧 需要更多 tKAS？"
echo "  $FAUCET_URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
