#!/bin/bash
cd "$(dirname "$0")"
git add .
git commit -m "work in progress — $(date '+%Y-%m-%d %H:%M')"
git push
echo "Saved and pushed."
