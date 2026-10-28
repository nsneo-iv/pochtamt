"""Пул соединений PostgreSQL и короткие помощники для запросов."""
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(settings.db_dsn, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False)


def open_pool() -> None:
    pool.open()


def close_pool() -> None:
    pool.close()


@contextmanager
def tx() -> Iterator[psycopg.Connection]:
    """Соединение с транзакцией: commit при выходе, rollback при исключении."""
    with pool.connection() as conn:
        yield conn


def fetch_all(sql: str, params: Any = None) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params: Any = None) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(sql, params).fetchone()
