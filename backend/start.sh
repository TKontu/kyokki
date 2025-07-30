#! /usr/bin/env bash

# Run pre-start script
/app/prestart.sh

# Start Uvicorn server
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
