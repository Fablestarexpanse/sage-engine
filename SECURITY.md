# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
| < 0.2   | No        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Email **fablestarexpanse@gmail.com** with:

1. A description of the vulnerability and its potential impact
2. Steps to reproduce or a proof-of-concept
3. Any suggested mitigations you have in mind

You will receive an acknowledgement within **48 hours** and a resolution update within **7 days**.

## Production Hardening Checklist

Before deploying Fablestar to a network-accessible environment:

- [ ] Copy `config/database.example.toml` → `config/database.toml` and set a strong, unique password
- [ ] Copy `config/server.example.toml` → `config/server.toml` with `dev_mode = false` and `admin_auth_required = true`
- [ ] Set `SAGE_ADMIN_JWT_SECRET` to a cryptographically random 32-byte hex string:
  ```
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] Set `cors_origins` in `server.toml` to the exact URL(s) your admin and player UIs are served from
- [ ] Use TLS (HTTPS/WSS) via a reverse proxy (Nginx, Caddy) in front of Uvicorn
- [ ] Set `POSTGRES_PASSWORD` in `.env` (docker compose no longer ships a default) and use the same value in `config/database.toml`
- [ ] Rotate the PostgreSQL password if your database was created from a docker-compose.yml that still had the old built-in default (it remains in git history)
- [ ] Rotate all credentials if this repo was ever cloned with the default `config/database.toml`
