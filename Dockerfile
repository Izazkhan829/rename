FROM python:3.11-slim

# Set a non-root user
RUN useradd -m botuser
WORKDIR /home/botuser/app

# Install system deps
RUN apt-get update && apt-get install -y gcc libssl-dev libffi-dev --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

RUN chown -R botuser:botuser /home/botuser/app
USER botuser

ENV PYTHONUNBUFFERED=1
ENV TZ=UTC

CMD ["python", "main.py"]