# Electron IPC Contract

| Channel | Direction | Payload | Result |
|---------|-----------|---------|--------|
| `vrav:get-app-info` | invoke | — | `{ version, platform, isPackaged }` |
| `vrav:get-api-base` | invoke | — | `string` URL |
| `vrav:get-installation-id` | invoke | — | `{ installation_id, machine_fingerprint }` |
| `vrav:activate-license` | invoke | `licenseKey: string` | `{ status, body: LicenseStatus }` |

Renderer: `window.vravDesktop.*`
