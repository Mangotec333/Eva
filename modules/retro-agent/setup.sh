#!/bin/bash
echo "Setting up EVA Retro-Agent..."
pip install -r requirements.txt -q
echo "Starting Retro-Agent on port 8795..."
python main.py
