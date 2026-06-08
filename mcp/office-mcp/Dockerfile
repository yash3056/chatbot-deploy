FROM python:3.11-slim

WORKDIR /app

# Install system deps (git for git_status/git_log tools, curl for debugging)
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8097

CMD ["python", "server.py"]
