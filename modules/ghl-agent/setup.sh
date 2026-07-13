#!/bin/bash
echo "Setting up EVA GHL Agent..."
pip install -r requirements.txt -q
echo "Initializing local ledger (idempotent)..."
python3 -c "import memory; memory.init_db(); print('ghl_agent.db ready')"
echo "Starting GHL Agent on port 8782..."
python3 main.py
