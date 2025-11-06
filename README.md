Automated Web App Build and Artifact Generation Workflow

This document serves as the comprehensive guide for the automated Codemagic workflow (ios-app), detailing its inputs, execution steps, status reporting mechanism, and the complete YAML configuration.

1. Inputs (Environment Variables)

This workflow requires the following environment variables to be set before execution:

Variable Name

Description

Example Value

CLIENT_ID

A unique identifier for the client or request. Used for tracking in the callback.

prod-widget-456

CLIENT_ASSEST_URL

The source code repository or download link.

https://github.com/user/repo.git OR https://example.com/assets/code.zip

CALLBACK_URL

The endpoint the workflow calls to report build status.

https://api.yourdomain.com/status/update

2. Workflow Execution Flow

The workflow executes in three main stages, with robust failure handling and reporting at each step.

Step 1: Fetch Source Code (Git or Zip)

The script analyzes the CLIENT_ASSEST_URL to determine the source type:

Git Repository: If the URL ends with .git, it attempts to clone the repository into a local source folder.

Zip Archive: If the URL ends with .zip, it downloads the archive, extracts it, and places the contents into the source folder.

Error Handling: If the URL is invalid or the clone/download/extraction fails, a failed callback is sent immediately, and the build stops.

Step 2: Detect Framework and Build Web Project

The script navigates into the source directory and performs the following actions:

Dependency Install: Runs npm install to set up project dependencies.

Framework Detection: Reads package.json to identify the framework and the corresponding distribution folder:

Next.js: Detects next dependency; expected folder: .next

CRA/React: Detects react and react-scripts; expected folder: build

Vite/React or Vue.js: Detects vite or vue; expected folder: dist

Build Execution: Runs the standard build command: npm run build.

Error Handling: If npm install, npm run build, or the resulting distribution folder check fails, a failed callback is sent immediately, and the build stops.

Step 3: Package Artifact and Send Final Success Callback

Artifact Creation: The detected distribution folder (.next, build, or dist) is zipped into a single file named web-app-dist.zip.

Success Callback: A final success callback is sent to the CALLBACK_URL containing the link to the downloadable artifact.

3. Callback Response Format

The workflow attempts to send a JSON payload to the configured CALLBACK_URL (with exponential backoff retries) upon build completion or immediate failure.

Core curl Request Structure

The shell script constructs and sends the status update using the following curl format:

curl -fs -H "Content-Type: application/json" --data '{...JSON Payload...}' "$CALLBACK_URL"


A. Success Payload (End of Build)

Sent only when the artifact is successfully zipped and published.

Key

Description

Example Value

build_id

The unique Codemagic build ID.

64c1234567890abcdef123456

client_id

The input identifier from the environment variable.

prod-widget-456

output_url

MANDATORY: The public URL where the web-app-dist.zip artifact can be downloaded.

https://app.codemagic.io/app/CM_APP_ID/build/CM_BUILD_ID/artifacts

status

The resulting status.

success

message

A brief, human-readable summary.

Build completed, artifact successfully published.

Example Success Response (JSON Body):

{
  "build_id": "64c1234567890abcdef123456",
  "client_id": "prod-widget-456",
  "output_url": "[https://app.codemagic.io/app/CM_APP_ID/build/64c1234567890abcdef123456/artifacts](https://app.codemagic.io/app/CM_APP_ID/build/64c1234567890abcdef123456/artifacts)",
  "status": "success",
  "message": "Build completed, artifact successfully published."
}


B. Failure Payload (Immediate Exit)

Sent if any script step fails (e.g., failed git clone, failed npm install, build error).

Key

Description

Example Value

build_id

The unique Codemagic build ID.

64c1234567890abcdef123456

client_id

The input identifier from the environment variable.

prod-widget-456

output_url

MANDATORY: Always empty for failure callbacks.

""

status

The resulting status.

failed

message

A detailed description of the error encountered.

npm install failed. Check project dependencies.

Example Failure Response (JSON Body):

{
  "build_id": "64c1234567890abcdef123456",
  "client_id": "prod-widget-456",
  "output_url": "",
  "status": "failed",
  "message": "Failed to clone Git repository from [CLIENT_ASSEST_URL]."
}
