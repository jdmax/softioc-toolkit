#!/bin/bash
# Start the EPICS Archive Viewer web application

source ../venv/bin/activate

echo "Starting EPICS Archive Viewer..."
echo "The viewer will be available at http://localhost:8501"
echo "Press Ctrl+C to stop"

streamlit run archive_viewer.py \
    --server.port 8501 \
    --server.address localhost \
    --server.headless true \
    --browser.gatherUsageStats false \
    --theme.primaryColor "#1f77b4" \
    --theme.backgroundColor "#ffffff" \
    --theme.secondaryBackgroundColor "#f0f2f6" \
    --theme.textColor "#262730"