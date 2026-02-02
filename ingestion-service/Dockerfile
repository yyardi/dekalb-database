FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better Docker caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the service
CMD ["python", "main.py"]
