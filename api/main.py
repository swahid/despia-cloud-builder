import os
import shutil
import zipfile
import tempfile
import asyncio
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import requests
from git import Repo
from google.cloud import storage
import subprocess
import aiohttp

app = FastAPI()

GCS_BUCKET = os.environ.get("GCS_BUCKET", "despia-cloud-builder")
CALLBACK_TIMEOUT = 30  # Timeout for callback requests in seconds

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

class BuildRequest(BaseModel):
    source_url: str
    branch: str = "main"
    client_id: str
    callback_url: str  # URL to notify when build is complete

class BuildResponse(BaseModel):
    message: str
    client_id: str
    status: str
    error: Optional[str] = None
    artifact: Optional[str] = None
    output_url: Optional[str] = None

async def notify_completion(callback_url: str, response: BuildResponse):
    """Notify the callback URL with the build results"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                callback_url, 
                json=response.dict(exclude_none=True),
                timeout=CALLBACK_TIMEOUT
            ) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"Failed to send callback notification: {str(e)}")
        return False

async def process_build(
    source_url: str,
    branch: str,
    client_id: str,
    callback_url: str
) -> None:
    """Background task to process the build request"""
    workspace = None
    
    # Initial response for processing state
    response = BuildResponse(
        message="Processing started",
        client_id=client_id,
        status="processing"
    )
    
    try:
        workspace = tempfile.mkdtemp(prefix="build-")
        
        # Clone or download the source code
        await clone_or_download(source_url, workspace)
        
        if not os.path.exists(workspace):
            raise Exception("Failed to create or access workspace directory")

        # Detect project directory
        entries = os.listdir(workspace)
        project_dir = os.path.join(workspace, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(workspace, entries[0])) else workspace

        # Detect package manager
        pm = "npm"
        if os.path.exists(os.path.join(project_dir, "yarn.lock")):
            pm = "yarn"
        elif os.path.exists(os.path.join(project_dir, "pnpm-lock.yaml")):
            pm = "pnpm"

        # Detect framework & build
        pkg_json = os.path.join(project_dir, "package.json")
        if os.path.exists(pkg_json):
            with open(pkg_json) as f:
                pkg = json.load(f)
                
            if "next" in pkg.get("dependencies", {}):
                build_cmd = f"{pm} install && {pm} run build && {pm} run export || true"
                out_dir = os.path.join(project_dir, "out") if os.path.exists(os.path.join(project_dir, "out")) else os.path.join(project_dir, ".next")
            elif "vue" in pkg.get("dependencies", {}):
                build_cmd = f"{pm} install && {pm} run build"
                out_dir = os.path.join(project_dir, "dist")
            elif "react" in pkg.get("dependencies", {}):
                build_cmd = f"{pm} install && {pm} run build"
                out_dir = os.path.join(project_dir, "build")
            else:
                build_cmd = f"{pm} install && {pm} run build"
                out_dir = os.path.join(project_dir, "dist")
                
            # Run the build command
            subprocess.run(build_cmd, shell=True, cwd=project_dir, check=True)
        else:
            # no package.json → skip build
            out_dir = project_dir

        # Create ZIP archive
        zip_name = f"despia_builder_{client_id}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(out_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, out_dir)
                    zipf.write(file_path, arcname)

        # Upload to GCS
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(f"output/{zip_name}")
        blob.upload_from_filename(zip_path)

        # Generate signed URL
        url = blob.generate_signed_url(expiration=86400)  # 24 hours

        # Prepare success response
        response = BuildResponse(
            message="Build completed successfully",
            client_id=client_id,
            status="completed",
            artifact=zip_name,
            output_url=url
        )

    except Exception as e:
        # Prepare error response
        response = BuildResponse(
            message="Build failed",
            client_id=client_id,
            status="failed",
            error=str(e)
        )
        
    finally:
        # Clean up workspace
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)
        
        # Send callback notification
        await notify_completion(callback_url, response)

@app.post("/build", response_model=BuildResponse)
async def build_project(req: BuildRequest, background_tasks: BackgroundTasks):
    # Start the build process in the background
    background_tasks.add_task(
        process_build,
        source_url=req.source_url,
        branch=req.branch,
        client_id=req.client_id,
        callback_url=req.callback_url
    )
    
    # Immediately return that we've accepted the request
    return BuildResponse(
        message="Build request accepted",
        client_id=req.client_id,
        status="accepted"
    )

async def clone_or_download(source_url: str, workspace: str) -> None:
    """Clone or download the source code"""
    if source_url.endswith(".git"):
        Repo.clone_from(source_url, workspace, depth=1)
    elif source_url.endswith(".zip"):
        r = requests.get(source_url)
        if r.status_code != 200:
            raise Exception("Failed to download ZIP file")
        zip_path = os.path.join(workspace, "source.zip")
        with open(zip_path, "wb") as f:
            f.write(r.content)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(workspace)
    else:
        raise Exception("Unsupported source type")

if __name__ == "__main__":
    import uvicorn
    import sys

    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            log_level="info",
            proxy_headers=True,
            forwarded_allow_ips="*"
        )
    except Exception as e:
        print(f"[Startup Error] {str(e)}", file=sys.stderr)
        sys.exit(1)