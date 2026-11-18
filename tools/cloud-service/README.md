# MuTracer cloud service

This is the independent POC render stack. It does not use Supabase and does not
reuse the legacy stage services.

**This service is preview-only.** Final renders use the Blender dual track in
`tools/dual-track/`; do not treat the `8787` worker as the final image engine.

## Components

- `api.py`: HTTP API that accepts scene JSON plus base64 assets.
- `worker.py`: GPU worker that claims jobs from SQLite and runs `mutracer-render`.
- `systemd/`: service units for the API and worker.

## API

- `GET /healthz`
- `POST /v1/jobs`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs/{id}/render.png`

Authentication uses `Authorization: Bearer <MUTRACER_API_TOKEN>` when that token
is configured.

## Deployment

```bash
REMOTE_HOST=ubuntu@43.192.32.90 tools/cloud-service/deploy.sh
```
