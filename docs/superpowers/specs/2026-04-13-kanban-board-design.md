# Shipyard — Kanban Board Design

**Date:** 2026-04-13
**Status:** Approved

---

## Overview

Shipyard is a Trello-like Kanban board application with drag-and-drop support, real-time multi-user collaboration, card dependency enforcement, and a modern dual light/dark mode UI. Data is persisted in PostgreSQL. The system is fully containerized for local development and produces production Docker images for deployment via Kubernetes and Helm.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + TypeScript, Vite 8, Tailwind CSS, shadcn/ui, dnd-kit |
| Backend | Python 3.13, FastAPI, SQLAlchemy (async), Alembic, Pydantic v2, uv (dependency management) |
| Auth | JWT via python-jose (mock user list; designed for easy swap to real auth) |
| Database | PostgreSQL 18 |
| Containerization | Docker (multi-stage builds), docker-compose (dev only) |
| Production | Docker images deployed via Kubernetes + Helm (separate repo) |

---

## Architecture

Three Docker services communicate as follows:

```
Browser ←──REST (HTTP)──→ backend (FastAPI / Uvicorn :8000)
        ←──WebSocket────→
                              └──── db (PostgreSQL :5432)

frontend (Vite dev server :5173) ← dev only, browser proxies through it
```

- **REST** handles all CRUD and auth operations.
- **WebSocket** (`ws://backend/ws/projects/:id`) delivers real-time board events to all connected clients. No writes go over WebSocket — it is receive-only.
- **WebSocket auth** uses a first-message handshake: the client opens the connection with no token in the URL, then immediately sends `{"type": "auth", "token": "<jwt>"}`. The server validates and either acknowledges or closes the connection. This avoids JWT exposure in server access logs.

---

## Data Model

### Tables

**users**
```
id            uuid        PK
email         varchar     unique
display_name  varchar
hashed_password varchar
avatar_url    varchar     nullable
created_at    timestamptz
```

**projects**
```
id            uuid        PK
name          varchar
description   text        nullable
created_by    uuid        FK → users
created_at    timestamptz
```

**project_members** (join table)
```
project_id    uuid        FK → projects
user_id       uuid        FK → users
role          enum        owner | member
joined_at     timestamptz
```

**columns**
```
id            uuid        PK
project_id    uuid        FK → projects
name          varchar
position      integer     ordering within project
created_at    timestamptz
```

**cards**
```
id            uuid        PK
column_id     uuid        FK → columns
project_id    uuid        FK → projects  (denormalized for efficient querying)
title         varchar
description   text        nullable
position      integer     ordering within column
created_by    uuid        FK → users
created_at    timestamptz
```

**card_dependencies** (join table)
```
card_id       uuid        FK → cards
depends_on_id uuid        FK → cards
```
Meaning: `card_id` depends on `depends_on_id`.

### Key conventions

- **"Done" column**: the column with the highest `position` value in a project. No explicit flag required.
- **"Backlog" column**: the column with the lowest `position` value (position = 0) in a project.

---

## Dependency Rules

Three rules are enforced server-side on every card move and reorder operation:

### Rule 1 — Column transition gate
A card can only leave the **leftmost column** (backlog) if **all** of its dependencies are in the **rightmost column** (Done).

- Moving a card from backlog to any other column while a dependency is not yet Done returns HTTP 422 with a descriptive error message.
- Cards already outside the backlog can move freely between intermediate columns regardless of dependency state.

### Rule 2 — Within-column ordering
If card A depends on card B and both cards are in the same column, card A cannot be positioned above card B.

- Attempting to drag A above B reverts the drag and displays a toast: *"[A title] depends on [B title] — [B title] must come first."*
- This is enforced server-side on `POST /cards/:id/move`. The frontend performs an optimistic update and rolls back on a 422 response.

### Rule 3 — No circular dependencies
Checked on insert into `card_dependencies`. Adding a dependency that would create a cycle returns HTTP 422: *"This would create a circular dependency."*

---

## API Design

All REST endpoints are prefixed `/api/v1/`.

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Returns `{access_token, refresh_token}` |
| POST | `/auth/refresh` | Returns new `{access_token}` |

### Projects
| Method | Path | Description |
|---|---|---|
| GET | `/projects` | List projects for current user |
| POST | `/projects` | Create project |
| GET | `/projects/:id` | Full board: project + columns + cards |
| PATCH | `/projects/:id` | Rename project |
| DELETE | `/projects/:id` | Delete project (owner only) |
| POST | `/projects/:id/members` | Add member by email |
| DELETE | `/projects/:id/members/:uid` | Remove member |

### Columns
| Method | Path | Description |
|---|---|---|
| POST | `/projects/:id/columns` | Add column |
| PATCH | `/columns/:id` | Rename column |
| POST | `/projects/:id/columns/reorder` | Reorder columns: `[{id, position}]` |
| DELETE | `/columns/:id` | Delete column |

### Cards
| Method | Path | Description |
|---|---|---|
| POST | `/columns/:id/cards` | Create card |
| PATCH | `/cards/:id` | Edit title / description |
| POST | `/cards/:id/move` | Move card: `{column_id, position}` — enforces dep rules |
| DELETE | `/cards/:id` | Delete card |
| POST | `/cards/:id/dependencies` | Add dependency — checks for cycles |
| DELETE | `/cards/:id/dependencies/:dep_id` | Remove dependency |

### Error codes
| Code | Meaning |
|---|---|
| 401 | Invalid or expired JWT |
| 403 | Not a member of this project |
| 422 | Dependency violation or circular dependency |

### WebSocket events (server → client)

Connection: `ws://backend/ws/projects/:id`

| Event | Payload |
|---|---|
| `card.moved` | `{card_id, column_id, position}` |
| `card.created` | `{card}` |
| `card.updated` | `{card_id, fields}` |
| `card.deleted` | `{card_id}` |
| `column.created` | `{column}` |
| `column.updated` | `{column_id, fields}` |
| `column.deleted` | `{column_id}` |
| `column.reordered` | `[{id, position}]` |
| `member.joined` | `{user}` |

---

## Frontend Architecture

### Routing

| Path | Component | Auth |
|---|---|---|
| `/login` | LoginPage | Public |
| `/register` | RegisterPage | Public |
| `/` | ProjectListPage | Protected |
| `/projects/new` | CreateProjectPage | Protected |
| `/projects/:id` | BoardPage | Protected |
| `/projects/:id/settings` | ProjectSettingsPage | Protected |

### State layers

| Layer | Tool | Responsibility |
|---|---|---|
| Global context | React Context | `AuthContext` (JWT + user), `ThemeContext` (light/dark, persisted to localStorage) |
| Server state | TanStack Query | All data fetching, mutations, cache invalidation |
| WebSocket | `useBoardSocket(projectId)` custom hook | Receives events → invalidates TanStack Query cache; exponential backoff reconnect |
| Local UI | `useState` / dnd-kit | Drag state, modals, toasts, optimistic drag position |

### Component tree (BoardPage)

```
App
└─ AuthProvider
└─ ThemeProvider
└─ Router
   └─ BoardPage
      ├─ BoardHeader         (title, members, theme toggle)
      ├─ WebSocketProvider   (scoped to board)
      └─ DndContext          (dnd-kit root)
         └─ ColumnList
            └─ Column ×n
               ├─ ColumnHeader       (rename, delete)
               ├─ SortableContext
               │  └─ Card ×n         (title, description, dep badges, drag handle)
               └─ AddCardButton
         └─ AddColumnButton
```

### Drag-and-drop behaviour

- dnd-kit `DndContext` wraps the entire board.
- Card drags use **optimistic updates**: the card moves in the UI immediately, then `POST /cards/:id/move` is called. On HTTP 422, the drag reverts and a toast notification displays the dependency violation message.
- Column reorders also use optimistic updates, calling `POST /projects/:id/columns/reorder` on drop.

---

## Auth System (Mock)

JWT-based authentication using `python-jose`. Mock implementation:

- A `MOCK_USERS` environment variable (JSON array) seeds the user list at startup.
- Passwords are hashed with bcrypt even in mock mode, making the swap to a real user database trivial: replace the in-memory lookup with a database query.
- Access tokens: short-lived (15 minutes). Refresh tokens: long-lived (7 days).
- The frontend stores both tokens in `localStorage`, refreshes automatically on 401.

To swap to real auth later: replace the mock user lookup in `core/auth.py` with a database query. No other changes required.

---

## Docker Setup

### Dockerfiles (multi-stage)

**`frontend/Dockerfile`**
```
FROM node:24-alpine AS dev      # Vite dev server, used by docker-compose
FROM dev AS build               # runs vite build → /dist
FROM nginx:alpine AS prod       # serves /dist, used by K8s
```

**`backend/Dockerfile`**

Three stages — `uv` is present only in `dev` and `builder`; the final `prod` image contains only Python and the pre-built virtual environment, keeping it small.

```
FROM python:3.13-slim AS dev
  # uv present, full deps (incl. dev), uvicorn --reload
  # used by docker-compose

FROM python:3.13-slim AS builder
  # uv present, UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
  # uv sync --frozen --no-dev --no-install-project → installs prod deps into .venv

FROM python:3.13-slim AS prod
  # NO uv binary — copies .venv from builder only
  # COPY --from=builder /app/.venv /app/.venv
  # ENV PATH="/app/.venv/bin:$PATH"
  # CMD uvicorn app.main:app (no --reload)
  # used by K8s
```

Key flags used in the builder stage:
- `UV_COMPILE_BYTECODE=1` — pre-compiles `.py` → `.pyc` so the prod container starts faster
- `UV_LINK_MODE=copy` — copies files instead of hardlinking (required across Docker layer boundaries)
- `--no-install-project` — installs dependencies only, not the project package itself
- `--frozen` — uses `uv.lock` exactly, no resolution

### docker-compose.yml (dev only)

Targets the `dev` stage of each Dockerfile. Volume mounts enable hot reload without rebuilds:

```
frontend:  build target=dev, volume ./frontend/src:/app/src, port 5173
backend:   build target=dev, volume ./backend/app:/app/app, port 8000, depends_on db
db:        postgres:18-alpine, named volume postgres_data, port 5432
```

Configuration via `.env` (gitignored). `.env.example` checked in with all required keys: `DATABASE_URL`, `JWT_SECRET`, `MOCK_USERS`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.

### Production

CI/CD builds production images:
```bash
docker build --target prod -t frontend:tag ./frontend
docker build --target prod -t backend:tag ./backend
```

Images are pushed to a registry and deployed via a Helm chart maintained in a separate repository. No `docker-compose.prod.yml` exists.

### Dev workflow

```bash
docker compose up                                              # start everything
docker compose run backend alembic upgrade head               # run migrations
docker compose run backend alembic revision --autogenerate    # generate new migration
```

---

## Project Structure

```
shipyard/
├─ frontend/
│  ├─ src/
│  │  ├─ components/
│  │  ├─ pages/
│  │  ├─ hooks/         (useBoardSocket, useAuth, etc.)
│  │  ├─ lib/           (api client, query keys)
│  │  └─ context/       (AuthContext, ThemeContext)
│  └─ Dockerfile
├─ backend/
│  ├─ app/
│  │  ├─ api/           (FastAPI routers)
│  │  ├─ models/        (SQLAlchemy models)
│  │  ├─ schemas/       (Pydantic schemas)
│  │  ├─ services/      (business logic, dep enforcement)
│  │  ├─ ws/            (WebSocket connection manager)
│  │  └─ core/          (config, auth, JWT)
│  ├─ alembic/
│  ├─ pyproject.toml
│  ├─ uv.lock
│  └─ Dockerfile
├─ docs/
│  └─ superpowers/specs/
│     └─ 2026-04-13-kanban-board-design.md
├─ docker-compose.yml
└─ .env.example
```
