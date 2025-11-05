# Base image
FROM python:3.11-slim

WORKDIR /app

ENV LOCAL=true
ENV PORT=8080
ENV HOST=0.0.0.0
ENV GIT_PYTHON_REFRESH=quiet

# ---------------------------
# Install system dependencies (without default nodejs)
# ---------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl wget unzip zip build-essential python3-pip \
        libpng-dev pkg-config libjpeg-dev libfreetype6-dev \
        openjdk-21-jdk ca-certificates gnupg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------
# Install Node.js 20 LTS + npm
# ---------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm yarn

# ---------------------------
# Install React Native CLI globally
# ---------------------------
RUN npm install -g react-native-cli

# ---------------------------
# Python dependencies
# ---------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------
# Copy app code
# ---------------------------
COPY . .

# Expose port
EXPOSE 8080

# Start FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "75"]
