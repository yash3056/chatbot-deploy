FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Sandbox working directory for executed code
RUN mkdir -p /app/sandbox_data

EXPOSE 8098

CMD ["python", "server.py"]
