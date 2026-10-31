# Northstar Studio Platform

A local-first software company platform. No runtime external APIs are required.

## Run frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Run backend

```powershell
cd backend
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API uses four separate PostgreSQL databases: `content`, `inquiries`, `applications`, and `certificates`. Create one database for each in your PostgreSQL provider, then set `CONTENT_DATABASE_URL`, `INQUIRIES_DATABASE_URL`, `APPLICATIONS_DATABASE_URL`, and `CERTIFICATES_DATABASE_URL` in the backend deployment environment. Each URL must point to a different database. The API creates the required tables on startup and adds starter website content only when the content database is empty.

```powershell
Copy-Item backend/.env.example backend/.env
# Replace each example URL with that database's connection string.
```

For online deployment, configure the same four variables in the backend host's environment settings. Do not commit real connection strings. The previous single-database `DATABASE_URL` is no longer used; keep its database untouched as a backup until the new deployment has been verified. New databases start with fresh records, except for the website's starter content, default enquiry fields, and demo certificate.

The app does not drop tables or erase records on startup. To do a clean cutover, create the four databases first, set the backend variables, deploy, and check `/api/health` and the admin portal before removing the old database from your provider.

Client inquiries are stored in the admin portal. For local development, the default admin credentials are `admin@gmail.com` / `900AB`. You can override them before starting the backend:

```powershell
$env:ADMIN_EMAIL = "admin@example.com"
$env:ADMIN_PASSWORD = "choose-a-strong-password"
```

The admin portal uses these credentials to show all saved inquiries. Do not use your Gmail account password here; use a separate admin password.

Demo certificate: `NS-2026-041`

## Enquiry service options

After signing into the Admin portal, use the **Manage enquiry options** section to add or delete choices for the client's fixed **What can we help with?** field. The public Contact form loads these choices automatically. The rest of the client enquiry form remains fixed: name, email, service, and project description.

The Contact form also includes a required mobile number with country code. It accepts 7-15 digits and stores the combined value, such as `+919876543210`, in the inquiry record.
