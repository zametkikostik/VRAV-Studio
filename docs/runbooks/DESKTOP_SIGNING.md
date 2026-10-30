# Desktop code signing

## Windows
1. Authenticode cert (`.pfx`)
2. CI env: `CSC_LINK`, `CSC_KEY_PASSWORD`
3. `cd apps/desktop && npm run pack:win`

## macOS
1. Developer ID Application certificate
2. Env: `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`
3. `npm run pack` — `afterSign` runs `scripts/notarize.js`

## Linux
```bash
sha256sum dist/*.AppImage dist/*.deb > dist/SHA256SUMS
gpg --detach-sign dist/SHA256SUMS
```
