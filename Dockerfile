FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

# migrate -> seed_if_empty -> collectstatic -> gunicorn.
# seed_if_empty наполняет только ПУСТУЮ базу, поэтому при каждом
# перезапуске и редеплое существующее расписание остаётся на месте.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py seed_if_empty && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]
