import argparse
import sys
from pathlib import Path

from app.adapters.storage.migrations import (
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
    subparsers.add_parser("migrate", help="应用所有待执行的 migration")
    subparsers.add_parser("status", help="查看 migration 状态")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    db_path = Path(settings.database_path)

    try:
        if args.command == "migrate":
            applied = apply_migrations(db_path)
            if applied:
                print(f"已应用 migration：{', '.join(applied)}")
            else:
                print("数据库已是最新，无待应用 migration。")
        else:
            status = migration_status(db_path)
            print(f"数据库：{db_path}")
            print(f"当前版本：{status.current or '无'}")
            print(f"最新版本：{status.head or '无'}")
            print(f"待应用：{'是' if status.pending else '否'}")
        return 0
    except MigrationError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
