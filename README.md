# 🛡️ Nerox — AI-Powered Digital Asset Protection Platform

> **Protect your images and videos from unauthorized use with AI fingerprinting, invisible watermarking, and real-time piracy detection.**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?style=flat&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?style=flat&logo=typescript)](https://www.typescriptlang.org/)
[![MongoDB](https://img.shields.io/badge/MongoDB-7-47A248?style=flat&logo=mongodb)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat&logo=redis)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat&logo=docker)](https://docs.docker.com/compose/)

---

## 📖 Overview

**Nerox** is a full-stack SaaS platform that helps creators, agencies, and businesses protect their digital assets. It combines deep learning-based visual fingerprinting, invisible DCT watermarking, and automated external crawling to detect and track unauthorized use of images and videos across the internet.

### Key Capabilities

| Feature | Description |
|---------|-------------|
| 🤖 **AI Fingerprinting** | ResNet50-based 2048-d embeddings + FAISS vector similarity search |
| 🔏 **Invisible Watermarking** | DCT frequency-domain watermarks that survive JPEG (Q70+), resizing, and mild edits |
| 🔍 **Ownership Trace** | Map leaked/stolen content back to the original rightful owner |
| 🌐 **Auto-Detection** | Scheduled crawling of YouTube and the web for asset misuse |
| ⚡ **Real-Time Alerts** | WebSocket-powered live notifications for every new detection |
| 📊 **Analytics Dashboard** | Risk scores, detection trends, platform breakdowns, and confidence metrics |
| 🏢 **Multi-Org SaaS** | Organization-based accounts, tiered plans, usage quotas, and Stripe billing |
| 🔐 **Secure Auth** | JWT access tokens, bcrypt password hashing, and password reset flows |

---

## 🏗️ Architecture

```
Nerox/
├── nerox-frontend/        # React 18 + TypeScript + Vite SPA
├── nerox-backend/         # FastAPI v8 Python backend
│   └── app/
│       ├── api/routes/    # REST + WebSocket endpoints
│       ├── core/          # Config, security, middleware, logging
│       ├── db/            # MongoDB (Motor async + PyMongo sync)
│       ├── models/        # DB-layer document models
│       ├── schemas/       # Pydantic request/response schemas
│       ├── services/      # Business logic & AI services
│       └── worker/        # Background task worker process
├── nginx/                 # Reverse proxy config (production)
├── scripts/               # Backup utilities (MongoDB)
└── docker-compose.yml     # Full-stack orchestration
```

### Service Graph

```
┌──────────────┐    HTTP/WS     ┌───────────────┐
│   Browser    │ ─────────────► │  nginx proxy  │
└──────────────┘                └───────┬───────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                  ┌──────────┐   ┌──────────┐   ┌──────────┐
                  │ Frontend │   │ Backend  │   │  Worker  │
                  │  :5173   │   │  :8000   │   │(headless)│
                  └──────────┘   └────┬─────┘   └────┬─────┘
                                      │               │
                               ┌──────┴──────┐ ┌─────┴────┐
                               │   MongoDB   │ │  Redis   │
                               │    :27017   │ │  :6379   │
                               └─────────────┘ └──────────┘
```

---

## 🖥️ Frontend

**Stack:** React 18 · TypeScript · Vite · TailwindCSS v4 · shadcn/ui (Radix UI) · Recharts · React Router v7 · Motion

### Pages & Routes

| Route | Page | Access |
|-------|------|--------|
| `/` | Landing | Public |
| `/features` | Feature showcase | Public |
| `/demo` | Interactive demo | Public |
| `/pricing` | Plans & pricing | Public |
| `/about` | About Nerox | Public |
| `/contact` | Contact form | Public |
| `/login` | Sign in | Public |
| `/register` | Create account | Public |
| `/forgot-password` | Password reset request | Public |
| `/reset-password` | Set new password | Public |
| `/dashboard` | Dashboard home | 🔒 Auth required |
| `/dashboard/upload` | Upload assets | 🔒 Auth required |
| `/dashboard/assets` | Asset library | 🔒 Auth required |
| `/dashboard/detections` | Detection results | 🔒 Auth required |
| `/dashboard/auto-detect` | Auto-detection jobs | 🔒 Auth required |
| `/dashboard/analytics` | Analytics & trends | 🔒 Auth required |
| `/dashboard/alerts` | Real-time alerts | 🔒 Auth required |
| `/dashboard/verification` | Ownership verification | 🔒 Auth required |
| `/dashboard/settings` | Account & org settings | 🔒 Auth required |

---

## ⚙️ Backend

**Stack:** FastAPI v0.115 · Python 3.10+ · Motor (async MongoDB) · PyMongo · Redis + RQ · PyTorch (CPU) · FAISS · OpenCV · Playwright · Stripe

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Register a new user/organization |
| `POST` | `/auth/login` | Authenticate and receive JWT |
| `GET` | `/assets/` | List user assets |
| `POST` | `/assets/upload` | Upload image or video asset |
| `GET` | `/assets/{id}/fingerprint-status` | Poll fingerprint processing status |
| `GET` | `/assets/{id}/watermark-status` | Poll watermark processing status |
| `POST` | `/detect` | Run similarity search against FAISS index |
| `POST` | `/detect/auto/start` | Start auto-detection scan |
| `POST` | `/watermark/verify` | Verify ownership from watermark token |
| `GET` | `/analytics/...` | Detection analytics & trend data |
| `GET` | `/ws/notifications` | WebSocket real-time event stream |
| `GET` | `/billing/...` | Stripe subscription management |
| `GET` | `/health` | Liveness probe with service status |

### AI Services

| Service | File | Description |
|---------|------|-------------|
| Embedding | `embedding_service.py` | ResNet50 → 2048-d feature vector |
| Vector Index | `vector_service.py` | FAISS in-memory index management |
| Fingerprint | `fingerprint_service.py` | End-to-end asset fingerprinting pipeline |
| Image Watermark | `image_watermark.py` | DCT frequency-domain invisible watermarking |
| Video Watermark | `video_watermark.py` | Per-frame video watermarking |
| Watermark Verify | `watermark_verify.py` | Token extraction and ownership tracing |
| Detection | `detection_service.py` | FAISS similarity search + confidence scoring |
| Auto-Detect | `auto_detect_service.py` | Web/YouTube crawling for misuse detection |
| Risk Engine | `risk_engine.py` | Priority and risk score computation |
| Analytics | `analytics_service.py` | Aggregation and trend reporting |
| WebSocket | `ws_manager.py` | Real-time notification broadcasting |
| Scheduler | `scheduler.py` | Periodic auto-detection job scheduling |

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | v2+ |
| (Dev) Python | 3.10+ |
| (Dev) Node.js | 18+ |

### Option A — Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/nerox.git
cd nerox

# 2. Configure environment variables
cp nerox-backend/.env.development nerox-backend/.env
# Edit nerox-backend/.env — fill in SECRET_KEY, STRIPE keys, YouTube API key, etc.

# 3. Start all services
docker compose up --build

# Frontend →  http://localhost:5173
# Backend  →  http://localhost:8000
# API Docs →  http://localhost:8000/docs
```

### Option B — Local Development

#### Backend

```powershell
cd nerox-backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.development .env
# Edit .env with your values

# Run the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# In a separate terminal — run the background worker
python -m app.worker.worker
```

#### Frontend

```bash
cd nerox-frontend

# Install dependencies
npm install

# Start dev server
npm run dev

# Open http://localhost:5173
```

---

## 🔧 Configuration

### Backend Environment Variables (`nerox-backend/.env`)

```env
# ── Application ──────────────────────────────────────────
ENVIRONMENT=development          # development | production
SECRET_KEY=your-32-char-secret   # JWT signing key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALLOWED_HOSTS=localhost,127.0.0.1

# ── Database ──────────────────────────────────────────────
MONGO_URI=mongodb://localhost:27017
DB_NAME=nerox
REDIS_URL=redis://localhost:6379

# ── Storage ───────────────────────────────────────────────
STORAGE_TYPE=local               # local | s3
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
# AWS_S3_BUCKET=...

# ── External Services ─────────────────────────────────────
YOUTUBE_API_KEY=your-youtube-api-key
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# ── CORS ──────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173
```

Generate a strong `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 🗄️ Database Schema (MongoDB)

| Collection | Purpose |
|------------|---------|
| `users` | User accounts (hashed passwords, org membership, roles) |
| `organizations` | Organization records (plan, Stripe IDs, usage) |
| `assets` | Uploaded files (metadata, storage path, status) |
| `fingerprints` | AI embedding records per asset |
| `watermarks` | Watermark tokens and embed status |
| `detections` | Detection match results with risk scores |
| `detection_jobs` | Auto-detection scan job records |
| `alerts` | Real-time alert records |
| `background_jobs` | Background task tracking |
| `usage` | Per-organization quota tracking |
| `api_keys` | Organization API key management |
| `billing_events` | Stripe webhook event log |

---

## 🛡️ Security

| Feature | Implementation |
|---------|---------------|
| Password hashing | bcrypt via passlib (slow hash) |
| JWT signing | HS256 via python-jose |
| Token expiry | Configurable via env var |
| User enumeration protection | Identical 401 for unknown email + wrong password |
| Secret management | All secrets via `.env`, never hardcoded |
| Duplicate accounts | 409 Conflict + MongoDB unique index |
| Inactive account guard | 403 Forbidden before token issuance |
| CORS | Configurable origins; locked down in production |
| Trusted hosts | TrustedHostMiddleware enforced in production |

---

## 🐳 Docker Services

| Service | Image | Port | Role |
|---------|-------|------|------|
| `mongo` | `mongo:7` | 27017 | Primary database |
| `redis` | `redis:7-alpine` | 6379 | Task queue broker |
| `backend` | Custom (Python) | 8000 | FastAPI REST + WebSocket |
| `worker` | Custom (Python) | — | Background task processor |
| `frontend` | Custom (Nginx) | 5173 | React SPA static server |

---

## 💾 Database Backups

Backup scripts are provided in the `scripts/` directory:

```powershell
# Windows (PowerShell)
.\scripts\backup_mongo.ps1
```

```bash
# Linux / macOS
bash scripts/backup_mongo.sh
```

---

## 🧪 Testing

The backend includes a full test suite organized by development phase:

```bash
cd nerox-backend

# Phase 2 — Authentication & user management
python test_phase2.py

# Phase 3 — AI fingerprinting & detection engine
python test_phase3.py

# Phase 4 — Watermarking pipeline
python test_phase4.py

# Phase 5 — Invisible watermarking & ownership trace
python test_phase5.py

# Phase 6 — Real-time intelligence & auto-detection
python test_phase6.py

# Detection accuracy benchmarks
python test_detection_accuracy.py

# File upload integration
python test_upload.py
```

---

## 📡 Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "service": "nerox-api",
  "version": "8.0.0",
  "storage": "local",
  "faiss_vectors": 142,
  "auto_detect": true,
  "websocket": true,
  "services": {
    "mongodb": "ok",
    "redis": "ok",
    "worker": "ok"
  },
  "active_workers": 2,
  "uptime": "3721s"
}
```

---

## 📋 Recommended Workflow

```
1. POST /auth/login                        → Authenticate, receive JWT
2. POST /assets/upload                     → Upload image or video
3. GET  /assets/{id}/fingerprint-status    → Poll until "completed"
4. GET  /assets/{id}/watermark-status      → Poll until "completed"
5. POST /detect                            → Run similarity search
6. POST /detect/auto/start                 → Kick off external crawl
7. WS   /ws/notifications                  → Listen for real-time detections
8. POST /watermark/verify                  → Prove ownership from leaked content
```

---

## 🗺️ Development Phases

| Phase | Feature |
|-------|---------|
| Phase 1 | Core auth (register, login, JWT) |
| Phase 2 | Password reset, data integrity, UNIQUE indexes |
| Phase 2.5 | Auto-detection engine & scheduler |
| Phase 2.6 | Real-time intelligence layer (WebSocket, ingestion registry) |
| Phase 3 | AI fingerprinting (ResNet50 + FAISS) |
| Phase 4 | Watermarking pipeline (images + video) |
| Phase 5 | Invisible watermarking & ownership trace |
| Phase 6 | SaaS multi-org, Stripe billing, API keys |

---

## 📄 License

This project was built for a hackathon. All rights reserved.

---

<p align="center">Built with ❤️ by the Nerox team</p>
