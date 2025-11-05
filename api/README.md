# Auto-Builder


Starter repo for an automated builder service that accepts a Git URL (or uploaded ZIP), detects framework (React/Next/Vue/Vite), runs build, packages output and uploads to a GCS bucket.


Two operation modes included:


- **cloudbuild/**: YAML + scripts suitable for `gcloud builds submit` testing locally.
- **api/**: An Express API that **submits Cloud Build via REST**