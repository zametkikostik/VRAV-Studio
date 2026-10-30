/**
 * VRAV Desktop — Electron main process.
 */
const { app, BrowserWindow, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const https = require("https");
const http = require("http");

const isDev = !app.isPackaged;
const RENDERER_URL = process.env.VRAV_RENDERER_URL || "http://localhost:3000";
const API_BASE = process.env.VRAV_API_URL || "http://localhost:8000";

function getInstallDataPath() {
  return path.join(app.getPath("userData"), "installation.json");
}

function getOrCreateInstallationId() {
  const p = getInstallDataPath();
  try {
    if (fs.existsSync(p)) {
      const data = JSON.parse(fs.readFileSync(p, "utf8"));
      if (data.installation_id) return data;
    }
  } catch (_) {}
  const installation_id = crypto.randomUUID();
  const machine_fingerprint = crypto
    .createHash("sha256")
    .update([app.getPath("home"), process.platform, process.arch].join("|"))
    .digest("hex")
    .slice(0, 32);
  const data = { installation_id, machine_fingerprint };
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(data, null, 2));
  return data;
}

function httpJson(method, url, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const lib = u.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        hostname: u.hostname,
        port: u.port,
        path: u.pathname + u.search,
        method,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
      },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => {
          try {
            resolve({ status: res.statusCode, body: JSON.parse(data || "{}") });
          } catch (e) {
            resolve({ status: res.statusCode, body: data });
          }
        });
      }
    );
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    title: "VRAV Studio",
  });
  if (isDev) {
    win.loadURL(RENDERER_URL);
  } else {
    win.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("vrav:get-app-info", async () => ({
  version: app.getVersion(),
  platform: process.platform,
  isPackaged: app.isPackaged,
}));

ipcMain.handle("vrav:get-api-base", async () => API_BASE);

ipcMain.handle("vrav:get-installation-id", async () => getOrCreateInstallationId());

ipcMain.handle("vrav:activate-license", async (_evt, licenseKey) => {
  const inst = getOrCreateInstallationId();
  const result = await httpJson("POST", `${API_BASE}/licenses/verify`, {
    license_key: licenseKey,
    installation_id: inst.installation_id,
    machine_fingerprint: inst.machine_fingerprint,
    bind: true,
  });
  if (result.body && result.body.valid) {
    const p = getInstallDataPath();
    const data = { ...inst, license_key: licenseKey, activated_at: new Date().toISOString() };
    fs.writeFileSync(p, JSON.stringify(data, null, 2));
  }
  return result;
});
