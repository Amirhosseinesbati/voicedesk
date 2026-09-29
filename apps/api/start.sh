#!/bin/sh
set -eu
alembic upgrade head
python -m voicedesk.seed
exec uvicorn voicedesk.main:app --host 0.0.0.0 --port 8000
