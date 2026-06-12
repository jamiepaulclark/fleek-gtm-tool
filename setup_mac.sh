#!/bin/bash
echo ""
echo "🧥 Fleek GTM Tool — Mac Setup"
echo "=============================="
echo ""

# Check Python
if command -v python3 &>/dev/null; then
    echo "✅ Python found: $(python3 --version)"
else
    echo "❌ Python not found. Please install from https://python.org"
    exit 1
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install pandas openpyxl python-dateutil requests streamlit --quiet
echo "✅ Dependencies installed"

echo ""
echo "✅ Setup complete! Now run:"
echo ""
echo "   python3 run_pipeline.py --no-ai"
echo ""
