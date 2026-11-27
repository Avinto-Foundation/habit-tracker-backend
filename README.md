# Social Habit Tracker: Backend

A web app where friends build habits together. Users track daily habits, keep their streaks alive, see their squad's check-ins live, react to them and nudge friends who are slipping. Friends can also join challenges with optional money pledges (test mode only).

This repo is the **Django REST API**. The web app lives in [habit-tracker-frontend](https://github.com/Avinto-Foundation/habit-tracker-frontend).

> **Status:** 🚧 Sprint 1 (setup & authentication). Sections marked *(planned)* are not built yet.

AMPW Capstone Project · 28 Oct 2026 to 4 Jan 2027 · Student: Samikshya Adhikari · Supervisor: Prayusha Giri

## Features

- [ ] User registration & login (email + password, JWT)
- [ ] Google sign-in
- [ ] Habits with flexible schedules, check-ins and time-zone-aware streaks
- [ ] Squads: invites, live check-ins (WebSockets), reactions, nudges
- [ ] Challenges with pledges (eSewa / Stripe **test mode only**)
- [ ] Points, levels & badges
- [ ] Email reminders
- [ ] Roles & permissions: Member, Squad owner, Admin
- [ ] Public communities, GitHub/Strava integrations *(stretch)*

## Tech stack

| Area | Tool |
|---|---|
| Language | Python 3.12+ |
| Framework | [Django](https://www.djangoproject.com) + [Django REST Framework](https://www.django-rest-framework.org) |
| Database | [PostgreSQL](https://www.postgresql.org) |
| Auth | JWT (`djangorestframework-simplejwt`), Google ID token verification (`google-auth`) |
| API docs | Swagger / OpenAPI (`drf-spectacular`) |
| CORS | `django-cors-headers` |
| Config | `python-dotenv` |
| Real-time | Django Channels *(planned, Sprint 3)* |
| Testing | [pytest](https://pytest.org) + `pytest-django` |

## Prerequisites

- Python **3.12 or newer** (check with `python --version`)
- PostgreSQL **15 or newer** running locally (check with `psql --version`)
- Git

## Getting started

```bash
# 1. Clone the repo
git clone https://github.com/Avinto-Foundation/habit-tracker-backend.git
cd habit-tracker-backend

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create the database (in psql or pgAdmin)
#    CREATE DATABASE habit_tracker;

# 5. Create your environment file and fill in the values
copy .env.example .env         # macOS / Linux: cp .env.example .env

# 6. Run migrations and create an admin user
python manage.py migrate
python manage.py createsuperuser

# 7. Start the server
python manage.py runserver
```

| URL | What |
|---|---|
| http://localhost:8000/api/health/ | Health check (no login needed) |
| http://localhost:8000/api/docs/ | **Swagger UI** (interactive API docs) |
| http://localhost:8000/api/schema/ | OpenAPI schema (YAML) |
| http://localhost:8000/admin/ | Django admin |

## Run with Docker

Runs the database, this API and the React app together, with no local Python,
Node or PostgreSQL needed. You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

The frontend repo must be cloned **next to** this one:

```
Habit_Tracker/
  habit-tracker-backend/     <- run the commands here
  habit-tracker-frontend/
```

```bash
# 1. Create .env from .env.example and set at least SECRET_KEY and DB_PASSWORD
#    (DB_HOST/DB_PORT are set to the Docker database automatically).
#    Optional: habit-tracker-frontend/.env for VITE_GOOGLE_CLIENT_ID.

# 2. Build and start everything (first time takes a few minutes)
docker compose up --build

# 3. Create an admin user (in a second terminal)
docker compose exec backend python manage.py createsuperuser
```

| Service | Address |
|---|---|
| React app | http://localhost:5173 |
| API + Swagger | http://localhost:8000/api/docs/ |
| PostgreSQL (Docker) | `localhost:5433` (5433, so it doesn't clash with a local PostgreSQL on 5432) |

| Task | Command |
|---|---|
| Stop | `Ctrl+C`, or `docker compose down` |
| Run the backend tests | `docker compose run --rm backend pytest` |
| See the logs of one part | `docker compose logs -f backend` |
| Start again after changing code | `docker compose up --build` |
| Delete the Docker database too | `docker compose down -v` (removes all data in it) |

Notes:
- Ports 8000 and 5173 must be free: stop a local `runserver` / `npm run dev` first.
- The code is copied into the images, so after changing code run `up --build` again. For day-to-day coding, the normal setup above (venv + `runserver`) is quicker.
- The Docker database is separate from your local PostgreSQL: accounts made in one don't exist in the other.
- Don't use `$` in `.env` values: Docker Compose treats `$...` as a variable.

## Environment variables

Create a `.env` file in the project root. Never commit `.env`; only commit `.env.example`.

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key (long random string) | `change-me` |
| `DEBUG` | Debug mode, `True` only in development | `True` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `localhost,127.0.0.1` |
| `DB_NAME` | PostgreSQL database name | `habit_tracker` |
| `DB_USER` | PostgreSQL user | `postgres` |
| `DB_PASSWORD` | PostgreSQL password | `your-password` |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `CORS_ALLOWED_ORIGINS` | Frontend URL(s) allowed to call the API | `http://localhost:5173` |
| `GOOGLE_CLIENT_ID` | OAuth Client ID from Google Cloud Console (same as frontend) | `1234-abc.apps.googleusercontent.com` |
| `FRONTEND_URL` | Frontend address, used for links in emails | `http://localhost:5173` |
| `EMAIL_BACKEND` | *(optional)* How emails are sent. Default prints them in the runserver terminal | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | *(optional)* SMTP login, e.g. a Gmail address + App Password | `you@gmail.com` |
| `DEFAULT_FROM_EMAIL` | *(optional)* Sender shown on emails | `HabitSquad <you@gmail.com>` |

More variables (Stripe, eSewa) will be added in later sprints.

**Emails in development:** by default nothing is really sent; emails (like password reset links) are printed in the terminal where `python manage.py runserver` is running. See `.env.example` to send real emails with Gmail.

## API documentation

Every endpoint is documented with Swagger/OpenAPI, including request body, responses and errors. Open **http://localhost:8000/api/docs/** while the server is running.

### Auth endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Create an account |
| POST | `/api/auth/login/` | Log in with email + password (+ optional `remember_me`), returns access + refresh tokens and the user |
| POST | `/api/auth/token/refresh/` | Get a new access token (and a new refresh token) |
| POST | `/api/auth/logout/` | Log out (blacklist refresh token) |
| POST | `/api/auth/google/` | Sign in / sign up with a Google ID token (201 if a new account was made, 200 if it already existed) |
| GET | `/api/auth/me/` | Get the logged-in user (needs an access token) |
| PATCH | `/api/auth/me/` | Update your own full name, username, time zone or bio |
| PUT | `/api/auth/me/avatar/` | Upload a profile photo (multipart, JPG/PNG/WebP, max 2 MB; saved as a 512 px WebP without hidden data) |
| DELETE | `/api/auth/me/avatar/` | Remove your profile photo |
| POST | `/api/auth/me/password/` | Change your password (needs the current one; logs out other devices) |
| POST | `/api/auth/password-reset/` | Email a one-time reset link (same answer whether or not the email exists; 5 per hour) |
| POST | `/api/auth/password-reset/confirm/` | Set a new password with the link's `uid` + `token`; logs out everywhere |

**Using tokens:** send the access token on every request as `Authorization: Bearer <access>`. Access tokens last 15 minutes; refresh tokens last 1 day (7 days with `remember_me`). Each refresh returns a new refresh token and blocks the old one. In Swagger, click **Authorize** and paste an access token.

### Friends endpoints

| Method | URL | What it does |
|---|---|---|
| GET | `/api/users/search/?q=` | Find people by username or name (min 2 characters; never by email). Each result says how you relate: `none`, `request_sent`, `request_received`, `friends` |
| GET | `/api/friends/requests/` | Your pending requests: `incoming` and `outgoing` |
| POST | `/api/friends/requests/` | Send a request (`{"username": "..."}`); if they already asked you, you become friends at once. Max 20 per hour |
| POST | `/api/friends/requests/<id>/accept/` | Accept a request sent to you |
| POST | `/api/friends/requests/<id>/decline/` | Decline a request sent to you (silently deleted) |
| DELETE | `/api/friends/requests/<id>/` | Cancel a request you sent |
| GET | `/api/friends/` | Your friends, sorted by name |
| DELETE | `/api/friends/<id>/` | Unfriend (either person can; silent) |

Other people are only ever shown as a "card": name, @username, photo and bio. Emails are never shown.

## Testing

Every API endpoint has pytest tests (project guideline).

```bash
pytest                 # run all tests
pytest -v              # verbose
pytest --cov           # with coverage (needs pytest-cov)
```

## Project structure

```
habit-tracker-backend/
├── config/            # Django settings, urls, asgi/wsgi
├── accounts/          # Custom user, auth, Google sign-in
├── habits/            # Habits, schedules, check-ins, streaks (Sprint 2)
├── squads/            # Squads, reactions, nudges (Sprint 3)
├── challenges/        # Challenges, pledges, payments (Sprint 4)
├── manage.py
├── requirements.txt
├── pytest.ini
└── .env.example
```

## Contributing / Git workflow

- Never commit directly to `main`.
- One issue → one branch → one pull request.
- Branch names: `<name>/<type>/<short-description>`, e.g. `samikshya/feat/register-api`
  (types: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`)
- Commit messages: `feat: add register endpoint`
- PR description must link the issue: `Closes #12`
- Tasks are tracked on the GitHub Projects board (Backlog → In Progress → Review → Done).

## Related

- Frontend repo: https://github.com/Avinto-Foundation/habit-tracker-frontend
- Project board: *link coming soon*
