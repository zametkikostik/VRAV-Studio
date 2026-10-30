# Secrets management

## SOPS + age (recommended)
```bash
age-keygen -o ~/.config/sops/age/keys.txt
# put public key into .sops.yaml creation_rules.age
cp production.env.example production.env
# edit secrets
sops -e -i production.env   # after filling, or:
sops production.env         # interactive encrypt editor
```

Deploy:
```bash
sops -d infra/secrets/production.env | kubectl create secret generic vrav-secrets -n vrav --from-env-file=/dev/stdin
```

Never commit decrypted `production.env`.
