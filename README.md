# Social Habit Tracker: Backend

A web app where friends build habits together. Users track daily habits, keep their streaks alive, see their squad's check-ins live, react to them and nudge friends who are slipping. Friends can also join challenges with optional money pledges (test mode only).

This repo is the **Django REST API**. The web app lives in [habit-tracker-frontend](https://github.com/iamsamikshya-git/habit-tracker-frontend).

> **Status:** 🚧 Sprint 0 (planning & design). Project setup starts in Sprint 1 (11 Nov 2026). Sections marked *(planned)* will be confirmed once the setup PR is merged.

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
| Config | `python-dotenv` *(planned)* |
| Real-time | Django Channels *(planned, Sprint 3)* |
| Testing | [pytest](https://pytest.org) + `pytest-django` |

## Prerequisites

- Python **3.12 or newer** (check with `python --version`)
- PostgreSQL **15 or newer** running locally (check with `psql --version`)
- Git

## Getting started *(planned)*

```bash
# 1. Clone the repo
git clone https://github.com/iamsamikshya-git/habit-tracker-backend.git
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
| http://localhost:8000/api/ | API root |
| http://localhost:8000/api/docs/ | **Swagger UI** (interactive API docs) |
| http://localhost:8000/api/schema/ | OpenAPI schema (YAML) |
| http://localhost:8000/admin/ | Django admin |

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

More variables (email, Stripe, eSewa) will be added in later sprints.

## API documentation

Every endpoint is documented with Swagger/OpenAPI, including request body, responses and errors. Open **http://localhost:8000/api/docs/** while the server is running.

### Auth endpoints *(planned, Sprint 1)*

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Create an account |
| POST | `/api/auth/login/` | Log in, returns access + refresh tokens |
| POST | `/api/auth/token/refresh/` | Get a new access token |
| POST | `/api/auth/logout/` | Log out (blacklist refresh token) |
| POST | `/api/auth/google/` | Sign in / sign up with a Google ID token |
| GET | `/api/auth/me/` | Get the logged-in user |

## Testing

Every API endpoint has pytest tests (project guideline).

```bash
pytest                 # run all tests
pytest -v              # verbose
pytest --cov           # with coverage (needs pytest-cov)
```

## Project structure *(planned)*

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

- Frontend repo: https://github.com/iamsamikshya-git/habit-tracker-frontend
- Project board: *link coming soon*
