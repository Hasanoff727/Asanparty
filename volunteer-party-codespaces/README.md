# Volunteer Party 2025 — Codespaces starter

A reconstructed, deployable starter based on the Volunteer Party 2025 code and API snippets shared in the ChatGPT conversation. The supplied snippets did not include the complete original repository, so this package recreates the main public registration flow and admin workflows rather than claiming to be a byte-for-byte export of the Emergent project.

## Included

- Public event landing page, event details and schedule
- Participant registration with consent and optional YouTube song suggestion
- Public aggregate registration count
- Admin login using an HTTP-only cookie
- Admin registration list, status changes, deletion and CSV export
- Admin-only song request list (not displayed on the public site)
- Admin event details editor
- Admin image upload/delete API endpoints
- SQLite database, so a MongoDB service is not required for this Codespaces starter

## Run in GitHub Codespaces

1. Create a GitHub repository and upload this folder's contents.
2. Open the repository in Codespaces.
3. In the terminal:

   ```bash
   cp backend/.env.example backend/.env
   ```

4. Edit `backend/.env` and set a unique `ADMIN_PASSWORD` and `ADMIN_EMAIL`.
5. Start the backend in terminal 1:

   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

6. Start the frontend in terminal 2:

   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0
   ```

7. Open forwarded port **5173** for the website. The backend API is on port **8000**.

The frontend defaults to `http://localhost:8000/api`. If your environment requires another backend URL, create `frontend/.env` with `VITE_API_URL=https://YOUR-BACKEND-URL/api` and restart Vite.

## Run with Docker Compose

```bash
cp backend/.env.example backend/.env
# edit backend/.env and set credentials
docker compose up --build
```

## Deploy

The frontend and backend are separate services. Deploy `backend/` as a Python web service and `frontend/` as a static/Vite web service (build command `npm run build`, output directory `dist`). Set `VITE_API_URL` to the public backend URL ending in `/api`. Set backend `CORS_ORIGINS` to the exact frontend origin, comma-separated if needed, and set `COOKIE_SECURE=true` under HTTPS. Use persistent storage for `DATABASE_PATH` and `backend/uploads` on the hosting provider; ephemeral filesystems will lose the SQLite database and uploaded images on redeploy.

## Important security notes

- Never commit `.env` files, database files, uploaded private data, or credentials.
- Replace the default admin email/password before deployment. The default values in `.env.example` are placeholders only.
- Set a strong unique `ADMIN_PASSWORD`, `COOKIE_SECURE=true`, and exact `CORS_ORIGINS` in production.
- This starter does not send email notifications. The prior Emergent email integration returned payment/recipient errors in the shared logs, so email has been left out rather than pretending it works.

## API

- `GET /api/health`
- `GET /api/event`
- `GET /api/gallery`
- `GET /api/registrations/public/summary`
- `POST /api/registrations`
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- Admin: `GET /api/registrations`, `GET /api/registrations/songs`, `GET /api/registrations/stats`
- Admin: `PATCH /api/registrations/{id}`, `DELETE /api/registrations/{id}`, `GET /api/registrations/export.csv`
- Admin: `PUT /api/event`, schedule CRUD under `/api/event/schedule`
- Admin: `POST /api/gallery`, `DELETE /api/gallery/{id}`

API docs are available at `/docs` while the backend is running.

## Source fidelity note

The original snippets supplied in the conversation are retained under `original-snippets/` for reference. The complete original Emergent source tree was not supplied, so the frontend in this archive is a clean functional reconstruction and will not be pixel-identical to the Emergent preview. The earlier pasted `.env` secrets and demo credentials have intentionally not been copied into this repository.
