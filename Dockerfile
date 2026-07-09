FROM python:3.12-slim

# uv för snabb, reproducerbar install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "docker>=7.1" \
    "jinja2>=3.1" "python-dotenv>=1.0"

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
