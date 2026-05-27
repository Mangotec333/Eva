#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  EVA Boot — double-click this file to start all EVA services
#  Place on Desktop: ~/Desktop/EVA Boot.command
# ─────────────────────────────────────────────────────────────────

# Make Terminal window visible long enough to see status
clear
echo ""
echo "  ███████╗██╗   ██╗ █████╗ "
echo "  ██╔════╝██║   ██║██╔══██╗"
echo "  █████╗  ██║   ██║███████║"
echo "  ██╔══╝  ╚██╗ ██╔╝██╔══██║"
echo "  ███████╗ ╚████╔╝ ██║  ██║"
echo "  ╚══════╝  ╚═══╝  ╚═╝  ╚═╝"
echo ""
echo "  Starting EVA services..."
echo ""

bash ~/Eva/modules/autostart/eva-boot.sh

echo ""
echo "  Opening Command Center..."
sleep 1
open https://eva.mangotec.ai

echo ""
echo "  Done. This window will close in 5 seconds."
sleep 5
