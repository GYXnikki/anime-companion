import argparse
import sys
from pathlib import Path

from app.adapters.storage.migrations import (
    DEFAULT_MIGRATIONS_DIR,
    MigrationError,
    apply_migrations,
    migration_status,
)
from app.config import settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="anime-companion 数据库迁移工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate", help="应用所有待执行的 migration")
    migrate_parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="migration 文件目录",
    )

    status_parser = subparsers.add_parser("status", help="查看 migration 状态")
    status_parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=DEFAULT_MIGRATIONS_DIR,
        help="migration 文件目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    db_path = Path(settings.database_path)

    try:
        if args.command == "migrate":
            applied = apply_migrations(db_path, args.migrations_dir)
            if applied:
                print(f"已应用 migration：{_format_versions(applied)}")
            else:
                print("数据库已是最新，无待应用 migration。")
        else:
            status = migration_status(db_path, args.migrations_dir)
            print(f"数据库：{db_path}")
            print(f"已应用：{_format_versions(status.applied)}")
            print(f"待应用：{_format_versions(status.pending)}")
        return 0
    except MigrationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


def _format_versions(versions: tuple[int, ...]) -> str:
    return ", ".join(str(version) for version in versions) if versions else "无"


if __name__ == "__main__":
    raise SystemExit(main())
