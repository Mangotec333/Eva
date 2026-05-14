#!/bin/bash
echo "=== Claude Desktop App Data Finder ==="
echo ""
echo "--- Application Support ---"
ls ~/Library/Application\ Support/Claude/ 2>/dev/null || echo "Not found"
echo ""
echo "--- Log files ---"
find ~/Library/Application\ Support/Claude/ -name "*.log" 2>/dev/null | head -20
echo ""
echo "--- JSON files (settings, conversations) ---"
find ~/Library/Application\ Support/Claude/ -name "*.json" 2>/dev/null | head -30
echo ""
echo "--- SQLite databases ---"
find ~/Library/Application\ Support/Claude/ -name "*.db" -o -name "*.sqlite" 2>/dev/null | head -10
echo ""
echo "--- Conversations directory ---"
ls ~/Library/Application\ Support/Claude/conversations/ 2>/dev/null || echo "No conversations folder found"
echo ""
echo "--- Storage directory ---"
ls ~/Library/Application\ Support/Claude/storage/ 2>/dev/null || echo "No storage folder found"
echo ""
echo "--- Cache ---"
ls ~/Library/Caches/Claude/ 2>/dev/null || echo "No cache found"
echo ""
echo "--- Logs directory ---"
ls ~/Library/Logs/Claude/ 2>/dev/null || echo "No logs folder found"
echo ""
echo "=== Run this to get all file sizes ==="
du -sh ~/Library/Application\ Support/Claude/ 2>/dev/null
