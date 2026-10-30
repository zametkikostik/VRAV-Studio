# Iteration 10 Status — BYOK runtime injection

`POST /ai/chat` resolves provider, looks up BYOK connection, decrypts key, builds one-shot registry.
Priority: BYOK → env keys → error.
