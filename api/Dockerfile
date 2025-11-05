# Use official Python image
FROM python:3.11-slim

WORKDIR /app

# Install git, curl, npm and clean up apt cache
RUN apt-get update && \
    apt-get install -y git curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm yarn

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Set environment variables
ENV PORT=8080
ENV HOST=0.0.0.0
ENV GIT_PYTHON_REFRESH=quiet

# Start FastAPI with Uvicorn
CMD exec uvicorn main:app --host $HOST --port $PORT --workers 1 --timeout-keep-alive 75
