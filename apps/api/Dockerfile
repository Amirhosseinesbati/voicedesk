FROM python:3.12.13-slim-bookworm
WORKDIR /app/apps/api
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN python -m pip install --no-cache-dir uv==0.12.19
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api ./
COPY scripts /app/scripts
COPY fixtures /app/fixtures
RUN uv sync --frozen --no-dev
ENV PATH="/app/apps/api/.venv/bin:$PATH" PYTHONPATH=/app/apps/api/src
EXPOSE 8000
CMD ["sh", "start.sh"]
