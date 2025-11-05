# Base Python image
FROM python:3.11-slim

WORKDIR /app

# Environment variables
ENV LOCAL=false
ENV PORT=8080
ENV HOST=0.0.0.0
ENV GIT_PYTHON_REFRESH=quiet

# ---------------------------
# Install system dependencies and Node.js 20 LTS
# ---------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git curl wget unzip zip build-essential ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm yarn react-native-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------------------------
# (Optional) Install Google Cloud SDK if you want to deploy/run gcloud commands inside container
# ---------------------------
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" \
    | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - && \
    apt-get update -y && apt-get install -y google-cloud-sdk && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------------------------
# Install Python dependencies
# ---------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------
# Copy app source
# ---------------------------
COPY . .

# Expose port
EXPOSE 8080

# Start FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
