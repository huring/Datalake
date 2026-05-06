import sqlite3
from pathlib import Path

from config import get_settings


def _sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:"):
        return None

    path = database_url.removeprefix("sqlite:///")
    return Path(path)


def check_database_readiness() -> dict[str, object]:
    settings = get_settings()
    sqlite_path = _sqlite_path(settings.database_url)

    if sqlite_path is None:
        return {
            "status": "unknown",
            "engine": "unsupported",
            "message": "database health check only supports sqlite in card 02",
        }

    try:
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(sqlite_path, timeout=1)
        connection.execute("PRAGMA journal_mode")
        connection.close()
    except OSError as exc:
        return {
            "status": "degraded",
            "engine": "sqlite",
            "path": str(sqlite_path),
            "message": str(exc),
        }
    except sqlite3.Error as exc:
        return {
            "status": "degraded",
            "engine": "sqlite",
            "path": str(sqlite_path),
            "message": str(exc),
        }

    return {
        "status": "ok",
        "engine": "sqlite",
        "path": str(sqlite_path),
    }
