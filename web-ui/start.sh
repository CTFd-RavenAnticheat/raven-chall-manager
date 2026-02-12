#!/bin/bash

# Chall-Manager Web UI Startup Script

set -e

echo "🚩 Chall-Manager Web UI"
echo "========================"

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Please run this script from the web-ui directory."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Check if chall-manager SDK is installed
if ! python -c "import chall_manager" 2>/dev/null; then
    echo "⚠️  Warning: chall-manager SDK not found. Installing from ../sdk/python/"
    pip install -q -e ../sdk/python
fi

# Set default environment variables if not set
export REGISTRY_URL="${REGISTRY_URL:-localhost:5000}"
export SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-in-production}"

echo ""
echo "🌐 Configuration:"
echo "  Registry URL: $REGISTRY_URL"
echo ""
echo "🚀 Starting Flask development server..."
echo "  URL: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run Flask app
python app.py