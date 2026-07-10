#!/bin/bash
echo "Setting up EVA Monetizing Agent..."
pip install -r requirements.txt -q
echo "Starting Monetizing Agent on port 8772..."
python main.py
