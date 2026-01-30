#!/bin/bash

cd /workspaces/Context-IQ/actions-runner

echo "Stopping old processes..." >> runner.log
pkill -f run.sh || true

echo "Starting new Runner at $(date)..." >> runner.log
nohup ./run.sh >> runner.log 2>&1 &

echo "Runner started successfully." >> runner.log