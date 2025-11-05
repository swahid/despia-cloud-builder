import os
import shutil
import zipfile
import tempfile
import asyncio
import json
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import aiohttp
from git import Repo
import subprocess

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("despia-builder")

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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(callback_url, json=data.dict(exclude_none=True)) as resp:
                logger.info(f"Callback sent to {callback_url} with status {resp.status}")
    except Exception as e:
        logger.error(f"Failed to send callback: {str(e)}")


# -------------------------
# Clone or download repo
# -------------------------
async def clone_or_download(source_url: str, workspace: str):
    loop = asyncio.get_event_loop()

    if source_url.endswith(".git"):
        logger.info(f"Cloning git repo: {source_url}")
        await loop.run_in_executor(None, lambda: Repo.clone_from(source_url, workspace, depth=1))

    elif source_url.endswith(".zip"):
        logger.info(f"Downloading zip archive: {source_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(source_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download zip: {resp.status}")

                content = await resp.read()
                zip_path = os.path.join(workspace, "source.zip")

                def save_and_extract():
                    with open(zip_path, "wb") as f:
                        f.write(content)
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
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
    workspace = tempfile.mkdtemp(prefix="build-")
    response = BuildResponse(message="Build started", client_id=client_id, status="processing")

    try:
        logger.info(f"Building project for client_id={client_id}")
        await clone_or_download(source_url, workspace)

        # Determine actual project directory
        entries = [e for e in os.listdir(workspace) if not e.endswith(".zip")]
        if len(entries) == 1 and os.path.isdir(os.path.join(workspace, entries[0])):
            project_dir = os.path.join(workspace, entries[0])
        else:
            project_dir = workspace

        logger.info(f"Detected project directory: {project_dir}")

        # Detect package manager
        pm = "npm"
        if os.path.exists(os.path.join(project_dir, "yarn.lock")):
            pm = "yarn"
        elif os.path.exists(os.path.join(project_dir, "pnpm-lock.yaml")):
            pm = "pnpm"

        # Detect framework
        build_cmd = f"{pm} install && {pm} run build"
        out_dir = os.path.join(project_dir, "dist")

        pkg_json = os.path.join(project_dir, "package.json")
        if os.path.exists(pkg_json):
            with open(pkg_json) as f:
                pkg = json.load(f)

            if "next" in pkg.get("dependencies", {}):
                build_cmd = f"{pm} install && {pm} run build && {pm} run export || true"
                out_dir = os.path.join(project_dir, "out" if os.path.exists(os.path.join(project_dir, "out")) else ".next")
            elif "vue" in pkg.get("dependencies", {}):
                out_dir = os.path.join(project_dir, "dist")
            elif "react" in pkg.get("dependencies", {}):
                out_dir = os.path.join(project_dir, "build")

        logger.info(f"Running build command: {build_cmd}")
        subprocess.run(build_cmd, shell=True, cwd=project_dir, check=True)

        # Zip output directory
        zip_name = f"despia_builder_{client_id}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_name)
        logger.info(f"Zipping build output from {out_dir}")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(out_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, out_dir)
                    zipf.write(file_path, arcname)

        url = None
        if not LOCAL and storage_client:
            bucket = storage_client.bucket(GCS_BUCKET)
            blob = bucket.blob(f"output/{zip_name}")
            blob.upload_from_filename(zip_path)
            url = blob.generate_signed_url(expiration=86400)

        response = BuildResponse(
            message="Build completed successfully",
            client_id=client_id,
            status="completed",
            artifact=zip_name,
            output_url=url,
        )

    except Exception as e:
        logger.error(f"Build failed for {client_id}: {str(e)}", exc_info=True)
        response = BuildResponse(
            message="Build failed",
            client_id=client_id,
            status="failed",
            error=str(e),
        )

    finally:
        shutil.rmtree(workspace, ignore_errors=True)
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
    background_tasks.add_task(build_project_task, req.source_url, req.client_id, req.callback_url)
    return BuildResponse(message="Build request accepted", client_id=req.client_id, status="accepted")
