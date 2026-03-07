Generic single-database configuration with an async-compatible setup.

Usage:

# Apply all migrations

alembic upgrade head

# Generate a new migration after changing SQLAlchemy models

alembic revision --autogenerate -m "your description"

# Downgrade one step

alembic downgrade -1
