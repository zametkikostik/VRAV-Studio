const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("vravDesktop", {
  getAppInfo: () => ipcRenderer.invoke("vrav:get-app-info"),
  getApiBase: () => ipcRenderer.invoke("vrav:get-api-base"),
  getInstallationId: () => ipcRenderer.invoke("vrav:get-installation-id"),
  activateLicense: (licenseKey) => ipcRenderer.invoke("vrav:activate-license", licenseKey),
});
