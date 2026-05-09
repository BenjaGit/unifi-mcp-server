# Varlock + 1Password Env Workflow

This repo uses `.env.schema` as an AI-safe migration scaffold for the currently inventoried environment variables. Secret values resolve through 1Password using the pinned `@varlock/1password-plugin@1.1.0` plugin.

## Prerequisites

- Install `varlock`.
- Install the 1Password CLI (`op`).
- Enable the 1Password desktop app CLI integration for local desktop-app auth, or provide `OP_TOKEN` for service-account auth.

## Local Use

1. Replace every placeholder with a quoted Varlock 1Password call like `op("op://<vault>/<existing-...>/<field>")`.
2. Run commands through varlock, for example:

```bash
varlock run -- <repo command>
```

3. Keep real `.env` files untracked. Do not paste secret values into tracked files.

## Current Status

The current `.env.schema` has confirmed 1Password references and no local `.env` file is required for runtime use.

## Mapping Status

| Env key | Secret? | 1Password reference | Notes |
| --- | --- | --- | --- |
| `UNIFI_API_TYPE` | no | `op://Private/Coldberg UniFi DreamMachine Pro Max/UNIFI_API_TYPE` | Confirmed 1Password reference. Must resolve to `local`. |
| `UNIFI_LOCAL_API_KEY` | yes | `op://Private/Coldberg UniFi DreamMachine Pro Max/credential` | Confirmed 1Password reference. |
| `UNIFI_REMOTE_API_KEY` | yes | `op://Private/Coldberg UniFi Site Manager API/credential` | Confirmed 1Password reference. |
| `UNIFI_LOCAL_HOST` | no | `op://Private/Coldberg UniFi DreamMachine Pro Max/UNIFI_LOCAL_HOST` | Confirmed 1Password reference. |
