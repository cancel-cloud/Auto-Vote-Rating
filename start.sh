#!/bin/bash

# Startup script for Auto-Vote-Rating Docker container
# Runs both the worker and dashboard in the background

echo "Starting Auto-Vote-Rating..."

# Start the dashboard in the background
echo "Starting dashboard..."
python /app/dashboard/app.py &
DASHBOARD_PID=$!

# Wait a bit for dashboard to initialize
sleep 2

# Start the worker in the foreground (main process)
echo "Starting worker..."
python /app/worker/main.py &
WORKER_PID=$!

# Handle shutdown gracefully
trap 'kill $DASHBOARD_PID $WORKER_PID; exit' SIGTERM SIGINT

# Wait for both processes
wait $WORKER_PID $DASHBOARD_PID
