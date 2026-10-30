# Desktop code signing

## Windows
1. Obtain Authenticode cert (`.pfx`)
2. Export for CI as base64:
   ```bash
   base64 -w0 cert.pfx > cert.b64
   ```
3. CI env:
   - `CSC_LINK` = path or base64 of pfx
   - `CSC_KEY_PASSWORD` = pfx password
4. Build: `cd apps/desktop && npm run pack:win`

## macOS
1. Developer ID Application certificate in keychain
2. Env for notarization:
   - `APPLE_ID`
   - `APPLE_APP_SPECIFIC_PASSWORD`
   - `APPLE_TEAM_ID`
3. `npm run pack` on macOS runner
4. `afterSign` runs `scripts/notarize.js`

## Linux
AppImage/deb typically not code-signed the same way; publish checksums:
```bash
sha256sum dist/*.AppImage dist/*.deb > dist/SHA256SUMS
gpg --detach-sign dist/SHA256SUMS
```
