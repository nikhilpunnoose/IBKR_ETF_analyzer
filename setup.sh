#!/bin/bash
# Setup script for portfolio_analyzer
# Re-run this after a WSL restart if /tmp/pa_venv is gone

set -e

VENV_DIR="/tmp/pa_venv"

if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at $VENV_DIR"
else
    echo "Creating virtual environment at $VENV_DIR..."
    python3 -m venv --without-pip "$VENV_DIR"
    . "$VENV_DIR/bin/activate"
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3
    pip install ibflex yfinance rich pandas pyyaml python-dotenv pytest
    echo "Done."
fi

echo ""
echo "To activate and run:"
echo "  . $VENV_DIR/bin/activate && PYTHONPATH=. python3 -m portfolio_analyzer"
