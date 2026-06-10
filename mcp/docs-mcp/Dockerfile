FROM python:3.11-slim

WORKDIR /app

# pdfplumber needs pdfminer; libgomp1 for any numpy dependency inside pdfplumber
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8096

CMD ["python", "server.py"]
