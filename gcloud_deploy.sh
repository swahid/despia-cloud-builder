gcloud builds submit --tag gcr.io/despia-cloud/despia-cloud-builder:latest
gcloud run deploy despia-cloud-builder --image gcr.io/despia-cloud/despia-cloud-builder:latest --platform managed --region us-central1 --allow-unauthenticated --memory 16Gi --cpu 4 --set-env-vars GCS_BUCKET=despia-cloud-artifacts
