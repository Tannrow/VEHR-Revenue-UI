from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.engine import make_url

from alembic import context

from app.db.base import Base
import app.db.models  # register models with SQLAlchemy metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
        try:
            display_url = make_url(database_url).render_as_string(hide_password=True)
        except Exception:
            display_url = database_url
        print(f"Alembic using database URL: {display_url}")
    return database_url


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    database_url = get_database_url()
    configuration["sqlalchemy.url"] = database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
