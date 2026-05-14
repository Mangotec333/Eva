#!/bin/bash
# setup.sh — EVA Logger setup script
# Run once to install dependencies and create data directories.

set -e

echo ""
echo "════════════════════════════════════════════════════"
echo "  EVA Logger — Setup"
echo "════════════════════════════════════════════════════"

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.9+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python version: $PYTHON_VERSION"

# Install Python dependencies
echo ""
echo "  Installing Python dependencies..."
pip install -r requirements.txt

# macOS: check for osascript (built-in, always available)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  Platform: macOS — window tracking via osascript ✓"
fi

# Linux: check for xdotool
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v xdotool &>/dev/null; then
        echo "  Platform: Linux — xdotool found ✓"
    else
        echo "  Platform: Linux — xdotool not found."
        echo "  Install with: sudo apt install xdotool   (Debian/Ubuntu)"
        echo "                sudo dnf install xdotool   (Fedora)"
        echo "  Logger will run without window tracking until installed."
    fi
fi

# Windows (Git Bash / WSL)
if [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "cygwin"* ]]; then
    echo "  Platform: Windows"
    echo "  For best tracking, install pywin32: pip install pywin32"
fi

# Create data directories
echo ""
echo "  Creating data directories..."
mkdir -p ~/eva-data/activity
mkdir -p ~/eva-data/summaries
echo "  ~/eva-data/activity    ✓"
echo "  ~/eva-data/summaries   ✓"

# ─── Screenpipe (optional but recommended) ──────────────────────────────────
echo ""
echo "  Checking for Screenpipe (recommended — screen + audio memory)..."
if command -v screenpipe &>/dev/null; then
    echo "  Screenpipe found ✓ — start it with: screenpipe"
else
    echo "  Screenpipe not installed (optional but strongly recommended)."
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  Install on macOS:"
        echo "    brew install screenpipe"
        echo "  OR download from: https://github.com/screenpipe/screenpipe/releases"
    else
        echo "  Download from: https://github.com/screenpipe/screenpipe/releases"
    fi
    echo ""
    echo "  Why Screenpipe?"
    echo "    → EVA sees everything you see (OCR on every screen frame)"
    echo "    → EVA hears everything you say (local Whisper transcription)"
    echo "    → 100% local — zero cloud cost — open source MIT"
    echo "    → Replaces Recall.ai at \$0/month"
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "  EVA Logger ready!"
echo ""
echo "  Quick start:"
echo "    python eva_logger.py --test           # Test for 60 seconds"
echo "    python eva_logger.py                  # Run as daemon"
echo "    python eva_context_api.py             # Start API server (port 8765)"
echo "    python eva_summarize.py               # Generate today's summary"
echo "    python eva_screenpipe_bridge.py       # Test Screenpipe connection"
echo ""
echo "  Unified context (all sources merged):"
echo "    curl localhost:8765/context/unified"
echo ""
echo "  Screen memory search (once Screenpipe is running):"
echo "    curl 'localhost:8765/screenpipe/search?q=RCFE&content_type=all'"
echo "════════════════════════════════════════════════════"
echo ""
