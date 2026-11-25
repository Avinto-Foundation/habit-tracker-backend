# Backend image: the Django API.
# Built and started by docker-compose.yml (`docker compose up --build`).
FROM python:3.13-slim

# Print logs straight away and don't write .pyc files into the image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install packages first, in their own layer: rebuilding after a code change is
# then quick, because this step is only repeated when requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Then the code (.dockerignore keeps out venv/, .env, .git ...).
COPY . .

EXPOSE 8000

# Apply database migrations, then start the development server on all network
# interfaces (0.0.0.0), so it can be reached from outside the container.
# (For deployment this will change to a production server such as gunicorn.)
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
