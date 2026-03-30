#!/bin/bash
# EMA530 Dashboard - Start Script
# Generates data and starts HTTP server on port 18806

cd "$(dirname "$0")"

echo "📊 EMA530 量化儀表板"
echo "===================="

# Generate data
echo ""
echo "🔄 Generating data..."
python3 generate_data.py
if [ $? -ne 0 ]; then
    echo "❌ Data generation failed!"
    exit 1
fi
echo ""

# Kill existing server on port 18806
kill $(lsof -t -i :18806) 2>/dev/null

# Start HTTP server
echo "🌐 Starting server on http://localhost:18806"
echo "   Press Ctrl+C to stop"
echo ""
python3 -m http.server 18806
