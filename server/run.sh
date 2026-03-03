#!/bin/bash
# ClawChat Server - Easy Run Script

# Get the directory of this script and cd into it
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=== ClawChat Server Setup & Run ==="

# 1. Setup virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "➡️ Creating virtual environment..."
    
    # Try to find Python 3.11+
    if [ -x "/usr/local/bin/python3.11" ]; then
        /usr/local/bin/python3.11 -m venv venv
    elif [ -x "/usr/local/opt/python@3.11/bin/python3.11" ]; then
        /usr/local/opt/python@3.11/bin/python3.11 -m venv venv
    elif [ -x "/opt/homebrew/bin/python3.11" ]; then
        /opt/homebrew/bin/python3.11 -m venv venv
    elif command -v python3 &> /dev/null; then
        python3 -m venv venv
    else
        echo "❌ Python 3 is required but not installed."
        exit 1
    fi
fi

# 2. Activate virtual environment
source venv/bin/activate

# 3. Install requirements
echo "➡️ Installing/Updating dependencies..."
pip install -r requirements.txt -q

# 4. Setup environment variables
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "➡️ Creating default .env file..."
        cp .env.example .env
    else
        echo "⚠️ Warning: .env.example not found."
    fi
fi

# 5. Run the server
echo "✅ Starting ClawChat server..."
echo "API Docs available at: http://localhost:8000/docs"
echo "--------------------------------------------------------"
uvicorn main:app --reload --port 8000 --host 0.0.0.0
