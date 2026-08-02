"""Inspect or apply the assistant-first LIFE retirement migration."""

from __future__ import annotations

import argparse
import os
import sys


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app import db  # noqa: E402


def snapshot() -> dict[str, object]:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        tables = {
            item[0] for item in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in db.RETIRED_LIFE_TABLES if table in tables
        }
        migrated_reminders = (
            conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE source_kind='retired_important_date'"
            ).fetchone()[0]
            if "reminders" in tables else 0
        )
        migrated_tasks = (
            conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE source='retired_user_goal'"
            ).fetchone()[0]
            if "tasks" in tables else 0
        )
        return {
            "schema": row[0] if row else "0",
            "retired_tables": len(counts),
            "retired_rows": sum(counts.values()),
            "nonempty_tables": sum(1 for count in counts.values() if count),
            "migrated_reminders": migrated_reminders,
            "migrated_tasks": migrated_tasks,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    before = snapshot()
    print("before", before)
    if not args.apply:
        return 0
    db.init_db()
    after = snapshot()
    backup = os.path.join(
        db.DATA_DIR, "backups", "life-retirement-before-schema-84.json",
    )
    print("after", after)
    print("backup_exists", os.path.exists(backup))
    if after["schema"] != "84" or after["retired_tables"] != 0 or not os.path.exists(backup):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
