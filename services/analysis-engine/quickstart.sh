#!/bin/bash
# Quick start script for Customer Feedback Analyzer

set -e

echo "=========================================="
echo "Customer Feedback Analyzer - Quick Start"
echo "=========================================="
echo ""

# Check Python version
echo "1. Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Found Python $python_version"

# Create virtual environment
echo ""
echo "2. Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   ✓ Virtual environment created"
else
    echo "   ✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "3. Activating virtual environment..."
source venv/bin/activate
echo "   ✓ Virtual environment activated"

# Install dependencies
echo ""
echo "4. Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "   ✓ Dependencies installed"

# Download NLTK data
echo ""
echo "5. Downloading NLTK data..."
python -c "import nltk; nltk.download('punkt', quiet=True); nltk.download('stopwords', quiet=True)"
echo "   ✓ NLTK data downloaded"

# Create .env file if it doesn't exist
echo ""
echo "6. Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "   ✓ .env file created from template"
else
    echo "   ✓ .env file already exists"
fi

# Run tests
echo ""
echo "7. Running tests..."
pytest -q
echo "   ✓ Tests passed"

# Run example
echo ""
echo "8. Running example analysis..."
echo ""
python examples/usage_example.py

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  • Activate venv: source venv/bin/activate"
echo "  • Run API: python -m src.api.main"
echo "  • Run tests: pytest"
echo "  • View docs: See USAGE.md and API.md"
echo ""
