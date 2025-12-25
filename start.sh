#!/bin/bash
set -e

# Startup script for Auto-Vote-Rating Docker container
# Runs both the worker and dashboard in the background

echo "=========================================="
echo "Starting Auto-Vote-Rating..."
echo "=========================================="

# Create data directory if it doesn't exist
mkdir -p /app/data

# Start the dashboard in the background
echo "Starting dashboard on port ${DASHBOARD_PORT:-8080}..."
python /app/dashboard/app.py &
DASHBOARD_PID=$!
echo "Dashboard PID: $DASHBOARD_PID"

# Wait a bit for dashboard to initialize
sleep 3

# Check if dashboard is running
if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
    echo "ERROR: Dashboard failed to start"
    exit 1
fi

echo "Dashboard started successfully"

# Start the worker in the foreground (main process)
echo "Starting voting worker..."
python /app/worker/main.py &
WORKER_PID=$!
echo "Worker PID: $WORKER_PID"

# Wait a bit to ensure worker starts
sleep 2

# Check if worker is running
if ! kill -0 $WORKER_PID 2>/dev/null; then
    echo "ERROR: Worker failed to start"
    kill $DASHBOARD_PID 2>/dev/null || true
    exit 1
fi

echo "=========================================="
echo "Auto-Vote-Rating started successfully!"
echo "Dashboard: http://localhost:${DASHBOARD_PORT:-8080}"
echo "=========================================="

# Handle shutdown gracefully
cleanup() {
    echo "Shutting down..."
    kill $DASHBOARD_PID 2>/dev/null || true
    kill $WORKER_PID 2>/dev/null || true
    wait $DASHBOARD_PID 2>/dev/null || true
    wait $WORKER_PID 2>/dev/null || true
    echo "Shutdown complete"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Wait for both processes
wait $WORKER_PID $DASHBOARD_PID
