FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --requirement requirements.lock

COPY . .

EXPOSE 8501
CMD ["python", "app.py"]
