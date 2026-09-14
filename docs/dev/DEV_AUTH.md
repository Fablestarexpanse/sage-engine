<!-- DEV-AUTH:FILE — describes development-only code; `python scripts/release_check.py --strip` deletes this file. -->
# Development-only passwordless logins

Skip passwords while testing locally, then remove every trace before a release.

## Turning it on

In `config/server.toml` (never on a shared or networked host):

```toml
dev_mode = true
dev_login = true
```

Restart the server. It logs a `DEV AUTH ENABLED` banner. Without both flags the routes below are
not mounted at all (404).

| Client | What you get |
|---|---|
| Player client sign-in page | **Play**: a named test character on the `dev-login` account (created if missing), straight into the world. **Choose or create a character instead**: the `dev-login` account at the character chooser, to test character creation. |
| Admin console sign-in page | **Dev login as head admin**: a staff token for `dev-staff`, a head admin with no usable password. |

| Route | Body | Returns |
|---|---|---|
| `GET /play/dev/status` | none | `{"enabled": bool}` for this client |
| `POST /play/dev/login` | `{"character": "Qa Tester"}` or `{"character": ""}` | the login payload plus `play_token`, and `character_id` when a name was given |
| `GET /admin/dev/status` | none | `{"enabled": bool}` for this client |
| `POST /admin/dev/login` | none | `{access_token, token_type, staff}`, the same shape as `/admin/auth/login` |

## What it refuses

- Connections whose address is not loopback (`127.0.0.1`, `::1`).
- Loopback connections from a proxy that relays for anyone else: every address in
  `X-Forwarded-For`, `X-Real-IP` and `Forwarded: for=` must be loopback too, and a `Forwarded`
  header that names no address is refused. The player client and admin console dev servers proxy
  to Nexus with `xfwd: true` (their `vite.config.js`), so a browser on this machine passes and a
  browser elsewhere on the network (Vite started with `--host`) does not. A reverse proxy in front
  of Nexus must forward client addresses the same way.
- Player dev login as a character owned by any other account, agent names, and reserved names.
- Admin dev login when `dev-staff` has been deactivated.

## Where the code is

Everything is marked so it can be removed mechanically:

- Whole files carry `DEV-AUTH:FILE` in their first lines: `engine/src/sage/admin/routes/dev_auth.py`,
  `engine/tests/test_dev_auth.py`, this document.
- Blocks sit between `DEV-AUTH:BEGIN` and `DEV-AUTH:END` comment lines: the router mount in
  `admin/nexus.py`, the public-path entry in `admin/admin_security.py`, the `dev_login` config
  field, `config/server.example.toml`, the player client (`App.jsx`, `playApi.js`), the admin
  console `LoginScreen`, and the dev-login sections of `README.md` and `CLAUDE.md`.

When you add dev-only auth code, put it inside markers too, or the release check will flag it.

## Before a release

On the release branch (or a worktree), not on `main`:

```bash
python scripts/release_check.py            # lists every marked file and block; exit 1 while any remain
python scripts/release_check.py --strip    # deletes them, then re-checks
python -m pytest
(cd engine/clients/player-ui && npm run build)
(cd engine/clients/admin-ui && npm run build)
```

`--strip` refuses to change anything when a marker is unbalanced. After stripping it scans engine
code, the clients, `config/`, `README.md` and `CLAUDE.md` for leftover dev-login references (for
example a route name outside the markers) and fails if it finds one. Fix those by hand.

The live world smoke tests register real accounts and create characters through the normal
routes, so they do not depend on dev login.

Existing deployments: after upgrading to a stripped release, `dev_login` in an old `server.toml` is
ignored, and the `dev-login` account and `dev-staff` staff row remain in the database. Deactivate
`dev-staff` from **Team & access**, or delete both rows, if a database ever ran with dev auth on.
