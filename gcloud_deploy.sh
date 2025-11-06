gcloud container images delete gcr.io/despia-cloud/despia-cloud-builder:v1 --force-delete-tags --quiet
gcloud builds submit --tag gcr.io/despia-cloud/despia-cloud-builder:v1
gcloud run deploy despia-cloud-builder --image gcr.io/despia-cloud/despia-cloud-builder:v1 --platform managed --region us-central1 --allow-unauthenticated --memory 16Gi --cpu 4 --set-env-vars GCS_BUCKET=despia-cloud-builder, GOOGLE_NODEJS_VERSION=16.x.x

gcloud container images list-tags gcr.io/despia-cloud/despia-cloud-builder --format="get(digest,tags,timestamp)"