#!/bin/bash
# start_reterminal.sh - Start both Backend and Frontend on reTerminal (Linux)

echo "==========================================="
echo "   Hydroagrix AI Dosing Unit Startup      "
echo "==========================================="

# Trap SIGINT and SIGTERM to kill both background processes gracefully
trap 'kill 0' SIGINT SIGTERM

echo "[1/2] Starting Backend service..."
cd backend

# Set up and activate a virtual environment to avoid PEP 668 restrictions
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

echo "Installing backend dependencies..."
pip3 install -r requirements_reterminal.txt

# Start backend on port 5000 in background
python3 main.py &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# Go back to root
cd ..

echo "[2/2] Starting Frontend service..."
cd frontend

# Install Node dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

# Build if dist doesn't exist
if [ ! -d "dist" ]; then
    echo "Building production frontend..."
    npm run build
fi

# Run vite preview on port 80 or 5173 to serve the production build
echo "Serving frontend..."
npm run preview -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

echo "==========================================="
echo "All services are running! Press Ctrl+C to stop."
echo "Backend is running on port 5000"
echo "Frontend is running on port 5173"
echo "==========================================="

# Wait for both processes to keep script running
wait
