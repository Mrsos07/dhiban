# Dockerfile for Dhiban - Django Application
# Optimized for Render deployment
# Build: 2026-03-27-v2

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput --clear

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Start script: handle migrations safely then run gunicorn
# 1) Fake all initial migrations (tables already exist in prod DB)
# 2) Run all remaining migrations normally (e.g. new columns)
CMD sh -c "\
  python manage.py migrate accounts     0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate ai_agent     0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate conversations 0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate service_requests 0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate suppliers    0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate users        0001_initial --fake --noinput 2>/dev/null; \
  python manage.py migrate --noinput && \
  gunicorn dhiban_project.wsgi:application --bind 0.0.0.0:\$PORT --workers 2 --threads 4 --timeout 120"
