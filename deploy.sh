#!/bin/bash
echo "Deploying bot to GitHub..."
cd "$(dirname "$0")"
source .venv/bin/activate
git add .
git commit -m "Auto-deploy: $(date '+%Y-%m-%d %H:%M:%S')"
git push origin main
echo "✅ Bot updated. Render will auto-deploy the latest commit."