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

The API uses PostgreSQL for all persistent data. Copy `backend/.env.example` to `backend/.env` and paste your Neon connection string after `DATABASE_URL=`. Every admin add, edit, and delete action is committed directly to this database, and the public pages read from the same database.

```powershell
Copy-Item backend/.env.example backend/.env
# Open backend/.env and replace the example value with your Neon connection string.
```

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
