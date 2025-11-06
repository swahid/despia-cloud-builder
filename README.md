Automated Web App Build and Artifact Generation Workflow

This document serves as the comprehensive guide for the automated Codemagic workflow (despia-app-builder), detailing its inputs, execution steps, status reporting mechanism, and the complete YAML configuration.

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



4. Codemagic Configuration (codemagic.yaml)

Below is the complete, up-to-date YAML configuration for the CI/CD workflow, now running on a mac_mini_m2 instance and leveraging latest Node/npm/Yarn versions:

workflows:
  despia-app-builder:
    name: Despia Cloud Web App Builder
    instance_type: mac_mini_m2
    max_build_duration: 30
    labels:
      - ${CLIENT_ID}
    environment:
      vars:
        CLIENT_ID: ${CLIENT_ID}
        CLIENT_ASSEST_URL: $CLIENT_ASSEST_URL
        CALLBACK_URL: $CALLBACK_URL
      # Use the latest Node.js version as requested for the macOS environment
      node: latest 

    scripts:
      - name: Setup Utilities and Callback Functions
        script: |
          #!/bin/bash
          
          # Install jq for robust JSON payload generation using Homebrew (standard on macOS CI runners)
          echo "Installing jq via brew..."
          brew install jq

          # Update npm and install latest yarn globally as requested
          echo "Updating npm and yarn to latest global versions..."
          npm install -g npm@latest
          npm install -g yarn@latest
          
          # Define the artifact URL environment variable for use in callbacks
          # This URL directs to the artifacts page in Codemagic where the zip can be downloaded
          export CM_ARTIFACT_URL="[https://app.codemagic.io/app/$CM_APP_ID/build/$CM_BUILD_ID/artifacts](https://app.codemagic.io/app/$CM_APP_ID/build/$CM_BUILD_ID/artifacts)"
          
          # Define the generic callback function (exported for use in other scripts)
          send_callback() {
            local status=$1
            local message=$2
            local output_url=${3:-} # Defaults to empty string if not provided
            
            echo "Sending $status callback to $CALLBACK_URL with URL: $output_url"
            
            # Use jq to safely construct the JSON payload
            JSON_PAYLOAD=$(jq -n \
              --arg bid "$CM_BUILD_ID" \
              --arg cid "$CLIENT_ID" \
              --arg url "$output_url" \
              --arg stat "$status" \
              --arg msg "$message" \
              '{
                "build_id": $bid,
                "client_id": $cid,
                "output_url": $url,
                "status": $stat,
                "message": $msg
              }')

            # Attempt to send callback with exponential backoff
            MAX_RETRIES=5
            DELAY=2
            for i in $(seq 1 $MAX_RETRIES); do
              echo "Attempt $i: Sending callback."
              # -s for silent, -f for fail on HTTP errors
              curl -fs -H "Content-Type: application/json" --data "$JSON_PAYLOAD" "$CALLBACK_URL" && return 0
              echo "Callback failed. Retrying in $DELAY seconds..."
              sleep $DELAY
              DELAY=$((DELAY * 2))
            done
            echo "ERROR: Failed to send final callback after $MAX_RETRIES attempts."
            return 1
          }
          export -f send_callback

          # Define failure handler (exported for use in other scripts)
          send_failure_callback() {
            send_callback "failed" "$1" ""
            exit 1 # Crucial: Stop the workflow immediately on failure
          }
          export -f send_failure_callback

      - name: 1. Fetch Source Code (Git or Zip)
        script: |
          #!/bin/bash
          
          # Check if the URL contains .git to assume it's a Git repository
          if [[ "$CLIENT_ASSEST_URL" == *".git"* ]]; then
            echo "Source URL detected as Git repository. Cloning..."
            if ! git clone "$CLIENT_ASSEST_URL" source; then
              send_failure_callback "Failed to clone Git repository from $CLIENT_ASSEST_URL."
            fi
            
          # Check if the URL contains .zip to assume it's a compressed file
          elif [[ "$CLIENT_ASSEST_URL" == *".zip"* ]]; then
            echo "Source URL detected as Zip file. Downloading and extracting..."
            
            # Use curl instead of wget for reliable downloading on macOS instances.
            if ! curl -L -o source.zip "$CLIENT_ASSEST_URL"; then
              send_failure_callback "Failed to download zip file from $CLIENT_ASSEST_URL."
            fi
            
            mkdir -p source
            # unzip is typically pre-installed on macOS
            if ! unzip -q source.zip -d source; then
              send_failure_callback "Failed to extract zip file."
            fi

          else
            send_failure_callback "Source URL $CLIENT_ASSEST_URL is neither a Git repository nor a Zip file."
          fi
          
          # Move into the source directory for subsequent steps
          cd source || send_failure_callback "Failed to navigate into source directory."
          
          # Handle common case where zip/clone results in a single sub-directory (flatten structure)
          if [[ $(find . -maxdepth 1 -mindepth 1 -type d | wc -l) -eq 1 ]]; then
              DIR_TO_MOVE=$(find . -maxdepth 1 -mindepth 1 -type d)
              echo "Detected single top-level directory ($DIR_TO_MOVE), flattening structure."
              mv "$DIR_TO_MOVE"/* .
              rmdir "$DIR_TO_MOVE"
          fi
          
          echo "Source code fetched successfully."

      - name: 2. Detect Framework and Build Web Project
        script: |
          #!/bin/bash
          
          if [ ! -f package.json ]; then
            send_failure_callback "Could not find package.json in the source code root. Cannot determine framework."
          fi
          
          echo "Installing Node dependencies..."
          if ! npm install; then
            send_failure_callback "npm install failed. Check project dependencies."
          fi

          PACKAGE_CONTENT=$(cat package.json)
          FRAMEWORK=""
          DIST_FOLDER=""

          # Logic to detect common web frameworks
          if echo "$PACKAGE_CONTENT" | grep -q '"next"'; then
            FRAMEWORK="Next.js"
            DIST_FOLDER=".next"
          elif echo "$PACKAGE_CONTENT" | grep -q '"react"' && echo "$PACKAGE_CONTENT" | grep -q '"react-scripts"'; then
            FRAMEWORK="CRA-React"
            DIST_FOLDER="build"
          elif echo "$PACKAGE_CONTENT" | grep -q '"react"' && echo "$PACKAGE_CONTENT" | grep -q '"vite"'; then
            FRAMEWORK="Vite-React"
            DIST_FOLDER="dist"
          elif echo "$PACKAGE_CONTENT" | grep -q '"vue"'; then
            FRAMEWORK="Vue.js"
            DIST_FOLDER="dist"
          else
            send_failure_callback "Unsupported framework detected. Only Next.js, React, and Vue.js are supported."
          fi

          echo "Detected Framework: $FRAMEWORK. Running build command: npm run build"
          
          # Run the build command
          if ! npm run build; then
            send_failure_callback "Build command failed for $FRAMEWORK project (npm run build)."
          fi
          
          # Check for the distribution folder existence
          if [ ! -d $DIST_FOLDER ]; then
            send_failure_callback "Build succeeded, but the expected distribution folder ($DIST_FOLDER) was not found."
          fi
          
          # Save the detected folder name to a temporary file for the publishing step
          echo $DIST_FOLDER > /tmp/dist_folder_name.txt 
          
          echo "Web project built successfully. Distribution folder: $DIST_FOLDER"


    # Artifacts section: Tells Codemagic what file to upload and make available
    artifacts:
      - web-app-dist.zip
    
    publishing:
      scripts:
        - name: 3. Zip Artifact and Final Success Callback
          script: |
            #!/bin/bash
            
            # Load the detected distribution folder name from /tmp
            DIST_FOLDER=$(cat /tmp/dist_folder_name.txt)
            OUTPUT_ZIP_NAME="web-app-dist.zip"
            
            echo "Zipping the distribution folder ($DIST_FOLDER) into $OUTPUT_ZIP_NAME..."
            
            # Zip the contents of the distribution folder. 
            # We move the zip file one directory up (to the root of the build) 
            # so Codemagic finds it easily based on the 'artifacts' setting.
            if ! zip -r "../$OUTPUT_ZIP_NAME" "$DIST_FOLDER"; then
              echo "ERROR: Failed to zip the distribution folder $DIST_FOLDER."
              exit 1
            fi
            
            echo "Artifact successfully created: $OUTPUT_ZIP_NAME"
            
            # Send the final success callback. This script only runs on successful build.
            send_callback "success" "Build completed, artifact successfully published." "$CM_ARTIFACT_URL"
            
            echo "Final callback finished."
