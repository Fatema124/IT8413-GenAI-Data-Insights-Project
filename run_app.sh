#!/usr/bin/env bash
# ===========================================================================
#  PriceLens BH - one-command start (macOS / Linux)
#  In Terminal, inside the project folder:   bash run_app.sh
#  First run: about 2-3 minutes (installs packages). Ctrl + C stops the app.
# ===========================================================================
set -e
cd "$(dirname "$0")"
APP="src/dashboard/page.py"

echo; echo " === PriceLens BH ==="; echo

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo " Python is not installed. Install it from https://www.python.org/downloads/ and run again."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo " [1/4] Creating the Python environment (first run only)..."
  "$PY" -m venv .venv
else
  echo " [1/4] Python environment found."
fi
VPY=".venv/bin/python"

echo " [2/4] Checking packages (the first run takes a few minutes)..."
"$VPY" -m pip install --disable-pip-version-check -q -r requirements.txt

echo " [3/4] Checking the data files..."
"$VPY" -m scripts.download_sources || echo "       The app also runs without Dataset 3; only the weights are then missing."
mkdir -p data/processed
if ! "$VPY" -m src.pipeline.run > data/processed/pipeline_log.txt 2>&1; then
  cat data/processed/pipeline_log.txt
  echo " Something went wrong. Send a screenshot to the group."
  exit 1
fi
echo "       Data prepared - details in data/processed/quality_report.md"

mkdir -p "$HOME/.streamlit"
[ -f "$HOME/.streamlit/credentials.toml" ] || printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"

echo " [4/4] Opening PriceLens BH in your browser. Ctrl + C stops it."; echo
exec "$VPY" -m streamlit run "$APP"
