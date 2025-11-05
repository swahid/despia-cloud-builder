import express from "express";
import fetch from "node-fetch";
import fs from "fs";
import path from "path";
import { execSync } from "child_process";
import AdmZip from "adm-zip";
import { Storage } from "@google-cloud/storage";
import { nanoid } from "nanoid";
import simpleGit from "simple-git";

const app = express();
app.use(express.json());

const storage = new Storage();
const bucketName = process.env.GCS_BUCKET || "despia-cloud-builder";

app.post("/build", async (req, res) => {
  try {
    const { source_url, branch = "main", client_id } = req.body;
    if (!source_url || !client_id) {
      return res.status(400).json({ error: "source_url and client_id are required" });
    }

    const jobId = nanoid(6);
    const workspace = `/tmp/build-${jobId}`;
    fs.mkdirSync(workspace);

    console.log(`🧩 Starting build job ${jobId}`);

    // --- 1️⃣ Clone or Download Source ---
    if (source_url.endsWith(".git")) {
      console.log("📦 Cloning GitHub repo...");
      await simpleGit().clone(source_url, workspace, ["--branch", branch, "--depth", "1"]);
    } else if (source_url.endsWith(".zip")) {
      console.log("📦 Downloading ZIP file...");
      const zipPath = path.join(workspace, "source.zip");
      const resp = await fetch(source_url);
      const buffer = Buffer.from(await resp.arrayBuffer());
      fs.writeFileSync(zipPath, buffer);

      const zip = new AdmZip(zipPath);
      zip.extractAllTo(workspace, true);
    } else {
      return res.status(400).json({ error: "Unsupported source type. Must be .git or .zip" });
    }

    // Detect root folder
    const entries = fs.readdirSync(workspace);
    const projectDir =
      entries.length === 1 && fs.statSync(path.join(workspace, entries[0])).isDirectory()
        ? path.join(workspace, entries[0])
        : workspace;

    // --- 2️⃣ Detect Package Manager ---
    const pm = fs.existsSync(path.join(projectDir, "yarn.lock"))
      ? "yarn"
      : fs.existsSync(path.join(projectDir, "pnpm-lock.yaml"))
      ? "pnpm"
      : "npm";

    // --- 3️⃣ Detect Framework ---
    const pkg = JSON.parse(fs.readFileSync(path.join(projectDir, "package.json"), "utf8"));
    let buildCmd = "npm run build";
    let outDir = "dist";

    if (pkg.dependencies?.next) {
      buildCmd = `${pm} run build && ${pm} run export || true`;
      outDir = fs.existsSync(path.join(projectDir, "out")) ? "out" : ".next";
    } else if (pkg.dependencies?.vue) {
      buildCmd = `${pm} run build`;
      outDir = "dist";
    } else if (pkg.dependencies?.react) {
      buildCmd = `${pm} run build`;
      outDir = "build";
    }

    console.log(`📦 Using ${pm} | Build command: ${buildCmd}`);

    // --- 4️⃣ Install & Build ---
    execSync(`${pm} install`, { cwd: projectDir, stdio: "inherit" });
    execSync(buildCmd, { cwd: projectDir, stdio: "inherit" });

    // --- 5️⃣ Zip Output ---
    const outputPath = path.join(projectDir, outDir);
    const zipName = `despia_builder_${client_id}.zip`;
    const zipFullPath = path.join(workspace, zipName);

    console.log(`📁 Zipping ${outputPath} -> ${zipName}`);
    const zip = new AdmZip();
    zip.addLocalFolder(outputPath);
    zip.writeZip(zipFullPath);

    // --- 6️⃣ Upload to GCS ---
    const blob = storage.bucket(bucketName).file(`output/${zipName}`);
    await blob.save(fs.readFileSync(zipFullPath));

    // --- 7️⃣ Generate Signed URL (valid for 24h) ---
    const [signedUrl] = await blob.getSignedUrl({
      action: "read",
      expires: Date.now() + 24 * 60 * 60 * 1000,
    });

    res.json({
      message: "Build completed successfully",
      artifact: zipName,
      output_url: signedUrl,
    });
  } catch (err) {
    console.error("❌ Build failed:", err);
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`🚀 Server running on port ${PORT}`));
