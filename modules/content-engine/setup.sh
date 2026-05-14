#!/bin/bash
echo "Setting up EVA Content Engine..."
pip install -r requirements.txt -q
echo "Starting Content Engine on port 8767..."
python main.py
