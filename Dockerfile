# Base Python image
FROM python:3.11-slim

WORKDIR /app

# Environment variables
ENV LOCAL=false
ENV PORT=8080
ENV HOST=0.0.0.0
ENV GIT_PYTHON_REFRESH=quiet
# Set Node.js LTS version to use the latest Active LTS
ARG NODE_LTS_VERSION=24.x

# ---------------------------
# Install system dependencies and Node.js 24 LTS
# ---------------------------
RUN apt-get update && \
    # Install common build tools and dependencies
    apt-get install -y --no-install-recommends \
        git curl wget unzip zip build-essential ca-certificates && \
    # Install the latest Node.js LTS (24.x) from NodeSource
    curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    # Clean up APT cache
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------------------------
# Configure npm and Install global JS dependencies
# ---------------------------
# Set the registry to the specified HTTP endpoint to potentially bypass proxy or SSL issues (as requested)
# Note: Using HTTPS is generally recommended for security.
RUN npm config set registry http://registry.npmjs.org/ && \
    # Upgrade npm to ensure the latest version bundled with Node 24 is used
    npm install -g npm@latest

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