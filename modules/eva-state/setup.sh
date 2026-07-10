#!/bin/bash
echo "Setting up EVA State Ledger..."
pip install -r requirements.txt -q
echo "Seeding ledger (idempotent)..."
python seed.py || true
echo "Starting State Ledger on port 8769..."
python main.py
