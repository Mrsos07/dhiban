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
CMD sh -c "\
  python manage.py migrate --fake-initial --noinput && \
  gunicorn dhiban_project.wsgi:application --bind 0.0.0.0:\$PORT --workers 2 --threads 4 --timeout 120"
