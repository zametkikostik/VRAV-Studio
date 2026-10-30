# Ports & Contracts

## AIProvider
chat / stream_chat · capabilities: streaming, tools, structured_output, vision

## PaymentProvider
create_checkout · handle_webhook · refund · Money as Decimal

## StorageProvider
put · get · delete · signed_url

## LicenseVerifier
verify(license_key, installation_id, machine_fingerprint) → LicenseStatus

Implemented in `packages/ai-gateway` and `apps/api/app/services/`.
