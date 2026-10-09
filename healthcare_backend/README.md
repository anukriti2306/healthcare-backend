# Healthcare Backend

A REST API for managing patients, doctors and patient-doctor assignments, built with **Django**, **Django REST Framework**, **PostgreSQL** and **JWT authentication** (`djangorestframework-simplejwt`).

- Users register and log in with email + password and receive JWTs.
- Authenticated users create and manage patients and doctors.
- Doctors can be assigned to (and removed from) patients.
- Every endpoint in the assignment is implemented, tested (470+ automated pytest tests on PostgreSQL, 100% line and branch coverage) and documented (Swagger UI + Postman collection).

---

## Table of contents

1. [Tech stack](#tech-stack)
2. [Project structure](#project-structure)
3. [Setup](#setup)
4. [Running the tests](#running-the-tests)
5. [API reference](#api-reference)
6. [Error format](#error-format)
7. [Design decisions](#design-decisions)
8. [Trying it out](#trying-it-out)
9. [Troubleshooting](#troubleshooting)

---

## Tech stack

| Concern | Choice |
|---|---|
| Framework | Django 5.2 + Django REST Framework |
| Database | PostgreSQL (via `psycopg` 3), Django ORM |
| Auth | JWT with `djangorestframework-simplejwt` |
| Config | Environment variables (`python-dotenv` loads a local `.env`) |
| Filtering | `django-filter` + DRF search/ordering |
| API docs | `drf-spectacular` (OpenAPI 3 + Swagger UI) |

Requires **Python 3.10+** (developed and tested on 3.13) and **PostgreSQL 14+** (tested on 16).

## Project structure

```
healthcare_backend/
├── manage.py
├── requirements.txt
├── .env.example               # copy to .env
├── config/                    # project: settings, root urls, wsgi/asgi
├── apps/
│   ├── core/                  # shared: error handler, permissions, pagination, validators, health check
│   ├── accounts/              # custom email-based User, register/login/refresh/me
│   ├── patients/              # Patient model + CRUD
│   ├── doctors/               # Doctor model + CRUD
│   └── mappings/              # Patient<->Doctor assignments
├── tests/                     # pytest suite (see "Running the tests")
│   ├── conftest.py            # shared fixtures: clients, users, factories
│   ├── factories.py           # factory_boy factories (deterministic data)
│   ├── unit/                  # error handler, validators, permissions, models, constraints, settings
│   ├── api/                   # one module per resource + security, error contract, performance, ops
│   └── integration/           # multi-user, multi-step scenarios through the public API
├── scripts/
│   ├── setup_db.sql           # creates the DB role + database
│   └── smoke_test.py          # end-to-end check against a running server
├── pytest.ini  .coveragerc  requirements-dev.txt
├── .github/workflows/ci.yml   # PostgreSQL service, Python 3.10/3.12/3.13 matrix, coverage gate
└── postman/
    └── Healthcare_Backend.postman_collection.json
```

Each app owns its models, serializers, views, urls, admin and tests.

---

## Setup

### 1. Get the code and create a virtual environment

**Windows (PowerShell)**
```powershell
cd healthcare_backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**
```bash
cd healthcare_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

Open **DBeaver** (or `psql`), connect as your superuser (usually `postgres`), open a SQL editor and run the contents of [`scripts/setup_db.sql`](scripts/setup_db.sql):

```sql
CREATE ROLE healthcare_user WITH LOGIN PASSWORD 'healthcare_pass' CREATEDB;
CREATE DATABASE healthcare_db OWNER healthcare_user ENCODING 'UTF8';
```

> **Prefer to use your existing `postgres` user?** Skip the `CREATE ROLE` line, create only `healthcare_db`, and put `DB_USER=postgres` and your own password in `.env` in the next step.

### 3. Configure environment variables

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

Generate a secret key and paste it into `.env` as `SECRET_KEY`:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

| Variable | Purpose | Default / example |
|---|---|---|
| `SECRET_KEY` | Django signing key (**required**) | – |
| `DEBUG` | Debug mode | `False` (set `True` locally) |
| `ALLOWED_HOSTS` | Comma-separated hosts | `localhost,127.0.0.1` |
| `DB_NAME` `DB_USER` `DB_PASSWORD` | Database credentials (**required**) | `healthcare_db` / `healthcare_user` / ... |
| `DB_HOST` `DB_PORT` | Database location | `localhost` / `5432` |
| `ACCESS_TOKEN_LIFETIME_MINUTES` | JWT access lifetime | `60` |
| `REFRESH_TOKEN_LIFETIME_DAYS` | JWT refresh lifetime | `7` |
| `AUTH_THROTTLE_RATE` | Rate limit on register/login/refresh | `30/min` |

The app refuses to start with a clear error if a required variable is missing. `.env` is git-ignored, so no secrets are committed.

### 4. Create the tables and run the server

```bash
python manage.py migrate
python manage.py runserver
```

The API is now at **http://127.0.0.1:8000/**.

- Swagger UI: http://127.0.0.1:8000/api/docs/
- OpenAPI schema: http://127.0.0.1:8000/api/schema/
- Health check: http://127.0.0.1:8000/api/health/

Optional: `python manage.py createsuperuser` to use the Django admin at `/admin/`.

In **DBeaver**, create a PostgreSQL connection (`localhost:5432`, database `healthcare_db`, user `healthcare_user`) to browse the tables: `accounts_user`, `patients_patient`, `doctors_doctor`, `mappings_patientdoctormapping`.

---

## Running the tests

```bash
pip install -r requirements-dev.txt     # adds pytest, pytest-django, pytest-cov, factory-boy
pytest                                  # whole suite (~6 s)
pytest --cov --cov-report=term-missing  # with line + branch coverage
pytest -m unit                          # or: -m api, -m integration
pytest tests/api/test_mappings.py -k duplicate
```

The suite runs against PostgreSQL in a temporary `test_healthcare_db` that is created and dropped automatically (this is why the DB role has `CREATEDB`). Only `SECRET_KEY` has a test fallback; database settings come from `.env` or real environment variables, so tests always run on the production engine.

**What is covered**

| Layer | Folder | What it proves |
|---|---|---|
| Unit | `tests/unit/` | Error handler (409/500 mapping, no leaks, rollback), phone validator, permission class, pagination, env helpers, model constraints enforced *by the database* (case-insensitive unique email, unique mapping, cascades), migrations in sync with models, secure-by-default settings, public URL contract |
| API | `tests/api/` | Every endpoint: success paths, boundary values, validation, filtering/search/ordering, pagination, JWT edge cases (expired, tampered, wrong key, `alg: none`, deleted/inactive user), rate limiting, user-enumeration resistance, mass-assignment protection |
| Security | `tests/api/test_security.py` | Parametrized matrices: every endpoint rejects anonymous callers; one user can never read or change another's patients or mappings; 404 for "not yours" is identical to "doesn't exist" |
| Contract | `tests/api/test_error_contract.py` | Thirteen different failure modes all return the same error envelope |
| Performance | `tests/api/test_performance.py` | Query count must not grow with row count (guards against N+1) |
| Integration | `tests/integration/` | Full clinician journey, two-tenant sharing rules, cascade clean-up |

The original Django-runner tests inside each app (`apps/*/tests.py`, 87 tests) are kept and still pass: `python manage.py test`. CI runs both.

To check a **running** server over real HTTP (standard library only, no extra install):

```bash
python scripts/smoke_test.py http://127.0.0.1:8000
```

---

## API reference

Base URL: `http://127.0.0.1:8000`. All bodies are JSON. Protected endpoints need the header:

```
Authorization: Bearer <access_token>
```

Paths end with a trailing slash, as in the assignment.

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register/` | – | Register with `name`, `email`, `password`. Returns the user and a token pair. |
| POST | `/api/auth/login/` | – | Log in with `email`, `password`. Returns `access`, `refresh` and the user. |
| POST | `/api/auth/token/refresh/` | – | Exchange `refresh` for a new `access` token. *(extra)* |
| GET | `/api/auth/me/` | ✔ | The authenticated user. *(extra)* |

```http
POST /api/auth/register/
{ "name": "Dr Demo", "email": "demo@example.com", "password": "Str0ng!Pass#2026" }

201 Created
{
  "user":   { "id": 2, "name": "Dr Demo", "email": "demo@example.com", "date_joined": "..." },
  "tokens": { "refresh": "eyJ...", "access": "eyJ..." }
}
```

Passwords must pass Django's validators (min. 8 characters, not too common, not all numeric, not similar to the email/name).

### Patients

Users only ever see and change **their own** patients.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/patients/` | Add a patient |
| GET | `/api/patients/` | All patients created by the authenticated user |
| GET | `/api/patients/<id>/` | Patient details |
| PUT | `/api/patients/<id>/` | Update (full). `PATCH` is also supported for partial updates |
| DELETE | `/api/patients/<id>/` | Delete (`204`) |

| Field | Type | Notes |
|---|---|---|
| `name` | string | **required**, max 150 |
| `age` | integer | **required**, 0-130 |
| `gender` | string | optional: `male`, `female`, `other` (also accepts `M`/`F`/`O`, any case) |
| `phone` | string | optional, 7-20 chars (digits, optional leading `+`, spaces, hyphens) |
| `address`, `medical_history` | string | optional |
| `id`, `created_by`, `created_at`, `updated_at` | | read-only |

```http
POST /api/patients/
{ "name": "John Doe", "age": 42, "gender": "male", "phone": "+91 98765 43210" }

201 Created
{ "id": 2, "name": "John Doe", "age": 42, "gender": "male", "phone": "+91 98765 43210",
  "address": "", "medical_history": "", "created_by": 2,
  "created_at": "2026-10-09T12:16:48+05:30", "updated_at": "2026-10-09T12:16:48+05:30" }
```

List options: `?gender=female`, `?min_age=18&max_age=65`, `?search=john` (name/phone), `?ordering=-age`.

### Doctors

Doctors are a shared directory: **every authenticated user can list and read all doctors**, but only the user who added a doctor can edit or delete that record (others get `403`).

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/doctors/` | Add a doctor |
| GET | `/api/doctors/` | All doctors |
| GET | `/api/doctors/<id>/` | Doctor details |
| PUT | `/api/doctors/<id>/` | Update (full). `PATCH` also supported |
| DELETE | `/api/doctors/<id>/` | Delete (`204`) |

| Field | Type | Notes |
|---|---|---|
| `name` | string | **required** |
| `specialization` | string | **required** |
| `email` | string | optional; unique (case-insensitive) when provided |
| `phone` | string | optional |
| `years_of_experience` | integer | optional, 0-70, default 0 |

List options: `?specialization=cardiology`, `?min_experience=10`, `?search=asha`, `?ordering=-years_of_experience`.

### Patient-doctor mappings

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/mappings/` | Assign a doctor to a patient: `{ "patient": <patient_id>, "doctor": <doctor_id> }` |
| GET | `/api/mappings/` | All mappings for the authenticated user's patients (`?patient=<id>`, `?doctor=<id>`) |
| GET | `/api/mappings/<patient_id>/` | All doctors assigned to that patient |
| DELETE | `/api/mappings/<id>/` | Remove a doctor from a patient (`<id>` is the **mapping** id) |

> `GET /api/mappings/<n>/` and `DELETE /api/mappings/<n>/` share a URL shape, as in the assignment, but `<n>` means *patient id* for `GET` and *mapping id* for `DELETE`.

```http
GET /api/mappings/2/        (doctors of patient 2)

200 OK
[
  { "id": 5, "patient": 2, "created_at": "...",
    "doctor": { "id": 3, "name": "Dr. Asha Rao", "specialization": "Cardiology", ... } }
]
```

The `id` in each item is the mapping id, so the client can pass it straight to `DELETE /api/mappings/<id>/`.

### Pagination

Lists return a plain JSON array by default. Add `?limit=` (max 100) and optionally `?offset=` to paginate; the response then becomes `{ "count", "next", "previous", "results" }`.

### Status codes

`200` OK · `201` created · `204` deleted · `400` validation error · `401` missing/invalid/expired token · `403` not allowed (editing another user's doctor) · `404` not found (including other users' patients/mappings) · `409` conflict · `429` rate limited · `500` unexpected error.

---

## Error format

Every error uses the same envelope:

```json
{
  "error": {
    "status": 400,
    "code": "validation_error",
    "message": "Validation failed.",
    "details": { "age": ["Ensure this value is greater than or equal to 0."] }
  }
}
```

`details` appears only for validation errors. Other examples: `not_authenticated`, `token_not_valid`, `no_active_account` (bad login), `permission_denied`, `not_found`, `throttled`, `server_error`. Unexpected exceptions are logged server-side and never leak stack traces to clients when `DEBUG=False`.

---

## Design decisions

- **Email as the login identifier.** A custom `User` model (`email` + `name`) replaces Django's username. Emails are stored lowercase and compared case-insensitively, so `Alice@x.com` and `alice@x.com` are the same account.
- **Ownership is enforced in the queryset.** Patients and mappings are filtered by the current user, so someone else's record returns `404` rather than `403`. This avoids leaking which IDs exist. A user can only assign doctors to patients they own.
- **Doctors are shared, edits are owner-only.** The brief says `GET /api/doctors/` returns *all* doctors, so doctors are a common directory; write access is restricted to the creator via an object-level permission.
- **Data integrity lives in the database too.** Unique constraint on `(patient, doctor)`; case-insensitive unique doctor email; foreign keys with sensible delete rules (deleting a patient or doctor removes its mappings; a doctor outlives the account that created them). A race that slips past validation becomes a clean `409`, not a crash.
- **No ID probing through filters.** `?patient=<id>` on the mappings list is a plain numeric filter, so another user's patient and a nonexistent one both return an empty list. A choice-style filter would answer differently and reveal which ids exist.
- **Atomic requests** (`ATOMIC_REQUESTS`): each request is one transaction, so a failure never leaves partial writes.
- **Secure by default.** Passwords hashed with PBKDF2 and validated; secrets only from environment variables; auth endpoints rate limited; login/register ignore a stale `Authorization` header; refresh tokens cannot be used as access tokens.
- **Plain-array lists** match the stated API contract; pagination is opt-in so it never changes the response shape unexpectedly.

---

## Trying it out

**Swagger UI** - open `/api/docs/`, call `POST /api/auth/login/`, click **Authorize** and paste the access token.

**Postman** - import [`postman/Healthcare_Backend.postman_collection.json`](postman/Healthcare_Backend.postman_collection.json) and run the folders in order (or use the Collection Runner). Register/Login save the token into `{{access_token}}`, and created IDs are saved as `{{patient_id}}`, `{{doctor_id}}`, `{{mapping_id}}` automatically. Change `base_url` if you run on another host/port.

**curl**

```bash
# log in and keep the token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"Str0ng!Pass#2026"}' | python -c "import sys,json; print(json.load(sys.stdin)['access'])")

curl -s http://127.0.0.1:8000/api/patients/ -H "Authorization: Bearer $TOKEN"
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImproperlyConfigured: Missing required environment variable ...` | You haven't created `.env` (copy `.env.example`) or a required value is empty. |
| `password authentication failed for user ...` | `DB_USER` / `DB_PASSWORD` in `.env` don't match the role in PostgreSQL. |
| `database "healthcare_db" does not exist` | Run the SQL in `scripts/setup_db.sql`, or create the database manually in DBeaver. |
| `permission denied to create database` when running tests | Give the role `CREATEDB`: `ALTER ROLE healthcare_user CREATEDB;` (or use the `postgres` user). |
| `connection refused` on port 5432 | The PostgreSQL service isn't running, or it uses another port (set `DB_PORT`). |
| `permission denied for schema public` (PostgreSQL 15+) | The DB must be *owned* by the role you connect with: `ALTER DATABASE healthcare_db OWNER TO healthcare_user;` |
| `401` right after logging in | Header must be exactly `Authorization: Bearer <access_token>` (the access token, not the refresh token). |
| `404`/redirect error on POST | Include the trailing slash: `/api/patients/`, not `/api/patients`. |
