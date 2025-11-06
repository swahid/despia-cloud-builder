import os
import shutil
import zipfile
import tempfile
import asyncio
import json
import logging
from typing import Optional
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import aiohttp
from git import Repo
import subprocess

# -------------------------
# Logging
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("despia-builder")

# -------------------------
# FastAPI app
# -------------------------
app = FastAPI()
LOCAL = os.environ.get("LOCAL", "true").lower() == "true"
GCS_BUCKET = os.environ.get("GCS_BUCKET", "despia-cloud-builder")

if not LOCAL:
    from google.cloud import storage
    storage_client = storage.Client()
else:
    storage_client = None

# -------------------------
# Models
# -------------------------
class BuildRequest(BaseModel):
    source_url: str
    client_id: str
    callback_url: str

class BuildResponse(BaseModel):
    message: str
    client_id: str
    status: str
    artifact: Optional[str] = None
    output_url: Optional[str] = None
    error: Optional[str] = None

# -------------------------
# Callback sender
# -------------------------
async def send_callback(callback_url: str, data: BuildResponse):
    """Sends the build status back to the client using the provided callback URL."""
    try:
        async with aiohttp.ClientSession() as session:
            # Exclude_none ensures we don't send null fields like 'artifact' if the build fails
            async with session.post(callback_url, json=data.dict(exclude_none=True)) as resp:
                logger.info(f"Callback sent to {callback_url} with status {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send callback: {str(e)}")

# -------------------------
# Clone or download repo
# -------------------------
async def clone_or_download(source_url: str, workspace: str):
    """Clones a Git repository or downloads and extracts a zip archive."""
    loop = asyncio.get_event_loop()
    if source_url.endswith(".git"):
        logger.info(f"Cloning git repo: {source_url}")
        # Use run_in_executor for blocking operations like git clone
        await loop.run_in_executor(None, lambda: Repo.clone_from(source_url, workspace, depth=1))
    elif source_url.endswith(".zip"):
        logger.info(f"Downloading zip archive: {source_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download zip: {resp.status}")
                content = await resp.read()
                zip_path = os.path.join(workspace, "source.zip")
                
                # Define blocking IO operations
                def save_and_extract():
                    with open(zip_path, "wb") as f:
                        f.write(content)
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        # Extract all contents into the workspace
                        zip_ref.extractall(workspace)
                    os.remove(zip_path)
                    
                await loop.run_in_executor(None, save_and_extract)
                logger.info("Zip extracted successfully.")
    else:
        raise Exception("Unsupported source type. Must be .git or .zip")

# -------------------------
# Build Task
# -------------------------
async def build_project_task(source_url: str, client_id: str, callback_url: str):
    """Main function to perform the cloning, building, and deployment/callback."""
    # Create a clean, temporary directory for the build
    workspace = tempfile.mkdtemp(prefix="build-")
    response = BuildResponse(message="Build started", client_id=client_id, status="processing")

    try:
        logger.info(f"Building project for client_id={client_id}. Workspace: {workspace}")
        await clone_or_download(source_url, workspace)

        # Determine project directory (handles cases where a zip/git repo has a single root folder)
        entries = [e for e in os.listdir(workspace) if not e.endswith(".zip")]
        project_dir = os.path.join(workspace, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(workspace, entries[0])) else workspace
        logger.info(f"Detected project directory: {project_dir}")

        # Detect package manager
        pm = "npm"
        if os.path.exists(os.path.join(project_dir, "yarn.lock")):
            pm = "yarn"
        elif os.path.exists(os.path.join(project_dir, "pnpm-lock.yaml")):
            pm = "pnpm"

        # Detect framework & output folder
        build_cmd = f"{pm} install && {pm} run build"
        out_dir = os.path.join(project_dir, "dist")
        pkg_json_path = os.path.join(project_dir, "package.json")
        
        if os.path.exists(pkg_json_path):
            with open(pkg_json_path) as f:
                pkg = json.load(f)
            deps = pkg.get("dependencies", {})
            
            # Heuristic for Next.js
            if "next" in deps:
                # Next.js static export: install, build, and export
                build_cmd = f"{pm} install && {pm} run build && {pm} run export || true"
                out_dir_candidate = os.path.join(project_dir, "out")
                # Prefer 'out' for static export, fallback to '.next'
                out_dir = out_dir_candidate if os.path.exists(out_dir_candidate) else os.path.join(project_dir, ".next")
            # Heuristic for Vue/React/Other
            elif "vue" in deps:
                out_dir = os.path.join(project_dir, "dist")
            elif "react" in deps:
                out_dir = os.path.join(project_dir, "build")
            else:
                # Fallback: check for common output folders
                for candidate in ["dist", "build", "out"]:
                    candidate_path = os.path.join(project_dir, candidate)
                    if os.path.exists(candidate_path):
                        out_dir = candidate_path
                        break

        # --- Execution of Build Command ---
        logger.info(f"Running build command ({pm}): {build_cmd}")
        
        # Execute the build process and capture output for error reporting
        # This is the key change for better diagnostics
        result = subprocess.run(
            build_cmd, 
            shell=True, 
            cwd=project_dir, 
            check=True, # Raises CalledProcessError on non-zero exit code
            capture_output=True, # Captures stdout and stderr
            text=True # Decodes stdout/stderr as text
        )
        
        logger.info(f"Build STDOUT:\n{result.stdout[:500]}...") # Log first 500 chars
        logger.info(f"Build STDERR:\n{result.stderr[:500]}...")

        # If we reach here, the build succeeded
        
        if not os.path.exists(out_dir) or not os.listdir(out_dir):
            raise Exception(f"Build succeeded but output directory {out_dir} is empty or missing.")

        # Zip output
        zip_name = f"despia_builder_{client_id}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_name)
        logger.info(f"Zipping build output from {out_dir} to {zip_path}")
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(out_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Create an arcname that is relative to the output directory
                    arcname = os.path.relpath(file_path, out_dir)
                    zipf.write(file_path, arcname)

        # Upload to GCS if not local
        url = None
        if not LOCAL and storage_client:
            bucket = storage_client.bucket(GCS_BUCKET)
            blob = bucket.blob(f"output/{zip_name}")
            blob.upload_from_filename(zip_path)
            blob.make_public()
            url = blob.public_url

        response = BuildResponse(
            message="Build completed successfully",
            client_id=client_id,
            status="completed",
            artifact=zip_name,
            output_url=url,
        )
        logger.info(f"Build completed for client_id={client_id}. Output URL: {url}")

    except subprocess.CalledProcessError as e:
        # Catch explicit failure from the subprocess execution
        error_details = f"Build command failed with return code {e.returncode}.\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"
        logger.error(error_details)
        response = BuildResponse(
            message="Build failed due to non-zero exit code in build script.",
            client_id=client_id,
            status="failed",
            error=error_details, # Send detailed error back to client
        )
    except Exception as e:
        logger.error(f"Build failed for {client_id}: {str(e)}", exc_info=True)
        response = BuildResponse(
            message="Build failed due to unexpected error.",
            client_id=client_id,
            status="failed",
            error=str(e),
        )
    finally:
        # Cleanup the temporary workspace and zip file
        shutil.rmtree(workspace, ignore_errors=True)
        if 'zip_path' in locals() and os.path.exists(zip_path):
            os.remove(zip_path)
            
        await send_callback(callback_url, response)

# -------------------------
# Endpoints
# -------------------------
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/build", response_model=BuildResponse)
async def build_endpoint(req: BuildRequest, background_tasks: BackgroundTasks):
    logger.info(f"Received build request: {req.source_url}")
    # Run the build task in a background thread to prevent blocking the HTTP worker
    background_tasks.add_task(build_project_task, req.source_url, req.client_id, req.callback_url)
    return BuildResponse(message="Build request accepted and queued", client_id=req.client_id, status="accepted")