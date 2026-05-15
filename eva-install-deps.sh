#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  EVA — Install All Python Dependencies
#  Run this once before first launch:
#    bash ~/Eva/eva-install-deps.sh
# ─────────────────────────────────────────────────────────────────

set -e
CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'

echo -e "${CYAN}${BOLD}  EVA — Installing Python Dependencies${RESET}"
echo ""

# Detect python3
PY=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PY" ]; then
  echo -e "${RED}  ✗ python3 not found. Install from https://python.org${RESET}"
  exit 1
fi
echo "  Python: $($PY --version)"

# Detect pip3
PIP=$(which pip3 2>/dev/null || which pip 2>/dev/null)
if [ -z "$PIP" ]; then
  echo -e "${RED}  ✗ pip not found. Run: python3 -m ensurepip --upgrade${RESET}"
  exit 1
fi

install_module() {
  local name="$1"
  local req="$HOME/Eva/modules/$name/requirements.txt"
  if [ -f "$req" ]; then
    echo "  → $name"
    $PIP install -q -r "$req"
    echo -e "  ${GREEN}✓ $name${RESET}"
  else
    echo "  ⚠ No requirements.txt for $name — skipping"
  fi
}

echo ""
echo "  Installing module dependencies…"
echo ""

install_module "logger"
install_module "deal-scout"
install_module "content-engine"
install_module "launcher"
install_module "lovable-bridge"

echo ""
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}${BOLD}  All dependencies installed ✓${RESET}"
echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo "  Now run:  bash ~/Eva/eva-start.sh"
echo ""
