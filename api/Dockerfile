FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --production
COPY . .
# gcloud SDK is required for this simple starter to call gcloud builds.
# For production, prefer calling Cloud Build REST API with OAuth tokens instead of embedding gcloud.
RUN apt-get update && apt-get install -y curl gnupg && rm -rf /var/lib/apt/lists/*
# install gcloud cli (minimal)
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
 && apt-get update && apt-get install -y google-cloud-sdk
CMD ["node","index.js"]
