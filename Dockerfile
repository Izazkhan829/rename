# Lightweight image for running the Telegram rename bot
FROM python:3.11-slim

# Create a non-root user
RUN useradd -m botuser

WORKDIR /home/botuser/app

# Install build dependencies (needed for some wheels)
RUN apt-get update && apt-get install -y \
    gcc \
    libssl-dev \
    libffi-dev \
  --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copy only requirements first so Docker can cache pip install layer
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure files are owned by non-root user
RUN chown -R botuser:botuser /home/botuser/app

USER botuser

ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

CMD ["python", "main.py"]
