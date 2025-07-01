#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Variables
FRONTEND_DIR="/home/pi/Desktop/flask_frontend/audio-control"
BACKEND_DIR="/home/pi/Desktop/flask_frontend/socketflaskaudio"
FRONTEND_PORT=5173
BACKEND_PORT=5500

# Function to display status
status() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

# Function to display error
error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

# Change to frontend directory and start Vite dev server
status "Starting frontend development server in $FRONTEND_DIR"
cd "$FRONTEND_DIR" || error "Failed to change to frontend directory"
npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > frontend.log 2>&1 &
FRONTEND_PID=$!
sleep 5  # Give it time to start

# Check if frontend started and get actual port
if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    error "Frontend development server failed to start. Check frontend.log"
fi
ACTUAL_FRONTEND_PORT=$(grep -oP 'http://\K[^:]+:\K\d+' frontend.log | head -1)
status "Frontend running on http://0.0.0.0:$ACTUAL_FRONTEND_PORT (actual port from log)"

# Change to backend directory and start Flask app
status "Starting backend in $BACKEND_DIR"
cd "$BACKEND_DIR" || error "Failed to change to backend directory"
python3 socketflaskaudio.py --host 0.0.0.0 --port $BACKEND_PORT > backend.log 2>&1 &
BACKEND_PID=$!
sleep 5  # Give it time to start

# Check if backend started
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    error "Backend failed to start. Check backend.log for details"
fi
status "Backend running on http://0.0.0.0:$BACKEND_PORT"

# Keep script running to monitor processes
wait $FRONTEND_PID $BACKEND_PID
