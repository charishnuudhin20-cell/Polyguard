#!/bin/bash
cd "$(dirname "$0")"
echo ""
echo " =============================================="
echo "   PolyGuard - starting up"
echo "   Keep this window open while you use it."
echo " =============================================="
echo ""
if ! command -v python3 >/dev/null 2>&1; then
  echo " Python was not found. Install it from python.org, then double-click this file again."
  read -p " Press Enter to close."
  exit 1
fi
echo " Step 1 of 2: checking the add-ons PolyGuard needs..."
echo " (the first time this takes 2-5 minutes)"
python3 -m pip install --disable-pip-version-check --only-binary=:all: -q -r requirements.txt \
  || python3 -m pip install --disable-pip-version-check --only-binary=:all: -q --user -r requirements.txt \
  || { echo " Something went wrong installing add-ons. Check your internet and try again."; read -p " Press Enter to close."; exit 1; }
echo " Step 2 of 2: opening PolyGuard in your browser..."
(sleep 8; open http://localhost:8501) &
python3 -m streamlit run app.py
