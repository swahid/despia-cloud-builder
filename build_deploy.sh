# Build image locally
docker build -t gcr.io/despia-cloud/despia-cloud-builder ./api

# Push image to GCP
docker push gcr.io/despia-cloud/despia-cloud-builder

# Deploy Cloud Run service
gcloud run deploy despia-cloud-builder \
  --image gcr.io/despia-cloud/despia-cloud-builder \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCS_BUCKET=despia-cloud-builder
