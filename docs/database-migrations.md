# Database Migrations

This project now includes Alembic for tracked database schema changes.

## Current Policy

- Local MVP startup still calls `Base.metadata.create_all()` for compatibility with existing SQLite/dev databases.
- Alembic is the source of truth for production schema changes going forward.
- The first migration, `20260511_0001_initial_schema`, represents the current model schema.
- Existing databases that were created before Alembic can be stamped after verifying their schema.

## Common Commands

Run commands from the `backend` directory.

```powershell
cd backend
alembic upgrade head
```

Generate a migration after changing SQLAlchemy models:

```powershell
cd backend
alembic revision --autogenerate -m "describe change"
```

Show current database revision:

```powershell
cd backend
alembic current
```

Mark an existing compatible database as already migrated:

```powershell
cd backend
alembic stamp head
```

## Local SQLite Notes

The default local development workflow can still start the backend directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-backend.ps1 -StopExisting
```

For a clean local database, delete the local `.db` file and run:

```powershell
cd backend
alembic upgrade head
```

Then start the backend.

## Production Notes

Before deployment:

1. Back up the database.
2. Run `alembic current` to inspect the current revision.
3. Run `alembic upgrade head`.
4. Start or restart the backend.

Do not rely on automatic `create_all()` behavior for production schema changes.
