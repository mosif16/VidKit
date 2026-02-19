#!/bin/bash
# Start VidKit
cd "$(dirname "$0")"
source .venv/bin/activate
echo "🎬 VidKit starting at http://localhost:8899"
echo "   Drop a video to begin editing."
echo ""
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8899 --reload
