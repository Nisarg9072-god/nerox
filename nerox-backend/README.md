# 🚀 Nerox Backend — README

## Overview

Production-ready **FastAPI** backend for the Nerox SaaS platform with JWT authentication, bcrypt password hashing, and MongoDB persistence.

---

## 🗂️ Project Structure

```
nerox-backend/
├── app/
│   ├── main.py                  # FastAPI app factory, CORS, lifecycle hooks
│   ├── core/
│   │   ├── config.py            # Pydantic Settings, loads .env
│   │   └── security.py          # bcrypt hashing + JWT creation/decoding
│   ├── db/
│   │   └── mongodb.py           # PyMongo client lifecycle management
│   ├── models/
│   │   └── user_model.py        # Internal DB-layer user document model
│   ├── schemas/
│   │   └── user_schema.py       # API request/response Pydantic schemas
│   └── api/
│       └── routes/
│           └── auth.py          # POST /auth/register, POST /auth/login
├── .env                         # Environment variables (never commit this!)
└── requirements.txt
```

---

## ⚙️ Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.10+ |
| MongoDB | 6.0+ (Community or Atlas) |
| pip | latest |

---

## 🛠️ Setup & Run

### 1. Install MongoDB

**Option A — Local install (Windows)**
Download from https://www.mongodb.com/try/download/community and install.
Start the service:
```powershell
net start MongoDB
```

**Option B — MongoDB Atlas (Cloud, free tier)**
1. Create a free cluster at https://cloud.mongodb.com
2. Copy the connection string
3. Paste it as `MONGO_URI` in `.env`

---

### 2. Configure `.env`

Open `nerox-backend/.env` and set your values:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017          # or Atlas URI
DB_NAME=nerox

# JWT
SECRET_KEY=replace-this-with-a-secure-random-32-char-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Generate a strong SECRET_KEY (PowerShell):
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

### 3. Install Python Dependencies

```powershell
cd nerox-backend
pip install -r requirements.txt
```

---

### 4. Run the Server

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:
- **Base URL**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health check**: http://localhost:8000/health

---

## 🔐 API Endpoints

### `POST /auth/register`

Register a new user account.

**Request body:**
```json
{
  "company_name": "Acme Corp",
  "email": "admin@acmecorp.io",
  "password": "Str0ng!Pass"
}
```

**Success response (201):**
```json
{
  "message": "User registered successfully.",
  "user_id": "6641abc123def456789012",
  "email": "admin@acmecorp.io"
}
```

**Password policy:** minimum 8 chars, at least 1 uppercase letter, at least 1 digit.

---

### `POST /auth/login`

Authenticate and receive a JWT access token.

**Request body:**
```json
{
  "email": "admin@acmecorp.io",
  "password": "Str0ng!Pass"
}
```

**Success response (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Use the token in all protected requests:
```
Authorization: Bearer <access_token>
```

---

### `GET /health`

Liveness probe.

**Response (200):**
```json
{
  "status": "ok",
  "service": "nerox-api",
  "version": "1.0.0"
}
```

---

## 🛡️ Security Highlights

| Feature | Implementation |
|---------|---------------|
| Password hashing | bcrypt via passlib (slow hash, industry standard) |
| JWT signing | HS256 via python-jose |
| Token expiry | Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` |
| User enumeration protection | Login returns identical 401 for unknown email and wrong password |
| Secret management | All secrets in `.env`, never hardcoded |
| Duplicate registration | 409 Conflict + MongoDB unique index |
| Inactive account guard | 403 Forbidden before token issuance |

---

## 🗄️ MongoDB

**Database:** `nerox`  
**Collection:** `users`

Document structure:
```json
{
  "_id": ObjectId,
  "company_name": "Acme Corp",
  "email": "admin@acmecorp.io",
  "hashed_password": "$2b$12$...",
  "is_active": true,
  "created_at": "2026-04-21T06:00:00Z",
  "updated_at": "2026-04-21T06:00:00Z"
}
```

**Recommended index** (run once in MongoDB shell):
```javascript
db.users.createIndex({ "email": 1 }, { unique: true })
```

---

## 📦 Tech Stack

| Component | Package | Version |
|-----------|---------|---------|
| Framework | FastAPI | ≥ 0.115 |
| Server | Uvicorn | ≥ 0.29 |
| Database driver | PyMongo | ≥ 4.7 |
| Environment | python-dotenv | ≥ 1.0 |
| Password hashing | passlib[bcrypt] | ≥ 1.7 |
| JWT | python-jose[cryptography] | ≥ 3.3 |
| Validation | pydantic[email] | ≥ 2.10 |
| Settings | pydantic-settings | ≥ 2.3 |
