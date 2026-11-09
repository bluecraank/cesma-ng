"""Command line administration: ``cesma <command>``."""

import argparse
import asyncio
import getpass

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import Database
from app.models import User


async def _list_users(db: Database) -> None:
    async with db.sessionmaker() as session:
        for user in (await session.execute(select(User).order_by(User.username))).scalars():
            flags = "superadmin" if user.is_superadmin else ""
            print(f"{user.id:5}  {user.username:30} {flags}")


async def _set_superadmin(db: Database, username: str, value: bool) -> None:
    async with db.sessionmaker() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"User {username!r} not found (users are created on first login)")
        user.is_superadmin = value
        await session.commit()
        print(f"{username}: superadmin={value}")


async def _set_password(db: Database, username: str, superadmin: bool) -> None:
    """Emergency password; creates the user if it has never logged in (LDAP not working yet)."""
    from app.auth.passwords import MIN_LENGTH, hash_password

    password = getpass.getpass(f"Emergency password for {username} (min. {MIN_LENGTH} chars): ")
    if len(password) < MIN_LENGTH:
        raise SystemExit(f"At least {MIN_LENGTH} characters required")
    if getpass.getpass("Repeat: ") != password:
        raise SystemExit("The passwords do not match")
    async with db.sessionmaker() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is None:
            first = (await session.scalar(select(func.count()).select_from(User))) == 0
            user = User(username=username, is_superadmin=first or superadmin, site_roles=[])
            session.add(user)
            print(
                f"User {username} created{' as super administrator' if user.is_superadmin else ''}"
            )
        elif superadmin:
            user.is_superadmin = True
        user.local_password_hash = hash_password(password)
        await session.commit()
    print(f"{username}: emergency password set (only accepted while LDAP is not reachable)")


async def _import_legacy(db: Database, args: argparse.Namespace) -> None:
    from app.core.crypto import SecretBox
    from app.legacy_import import LaravelDecrypter, import_legacy, read_mysql

    settings = get_settings()
    tables = await asyncio.to_thread(read_mysql, args.mysql, args.with_backups)
    async with db.sessionmaker() as session:
        result = await import_legacy(
            session,
            tables,
            LaravelDecrypter(args.app_key),
            SecretBox(settings.secret_key.get_secret_value()),
            api_user=args.api_user,
            with_backups=args.with_backups,
        )
        await session.commit()
    for what, count in sorted(result.counts.items()):
        print(f"{count:6}  {what}")
    for warning in result.warnings:
        print(f"WARNING {warning}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="cesma")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("users", help="List users")
    p = sub.add_parser("set-superadmin", help="Grant or revoke super administrator rights")
    p.add_argument("username")
    p.add_argument("--revoke", action="store_true")
    pw = sub.add_parser(
        "set-password", help="Set an emergency password (login while LDAP is not reachable)"
    )
    pw.add_argument("username")
    pw.add_argument("--superadmin", action="store_true", help="also make the user superadmin")
    imp = sub.add_parser("import-legacy", help="Import data from cesma-on-premise (MySQL)")
    imp.add_argument("--mysql", required=True, help="mysql://user:password@host:3306/cesma")
    imp.add_argument("--app-key", required=True, help="APP_KEY of cesma-on-premise (base64:...)")
    imp.add_argument("--api-user", default="admin", help="API_USERNAME of cesma-on-premise")
    imp.add_argument("--with-backups", action="store_true", help="also import backups")
    args = parser.parse_args()

    db = Database(get_settings().database_url)

    async def run() -> None:
        try:
            if args.command == "users":
                await _list_users(db)
            elif args.command == "set-superadmin":
                await _set_superadmin(db, args.username, not args.revoke)
            elif args.command == "set-password":
                await _set_password(db, args.username, args.superadmin)
            elif args.command == "import-legacy":
                await _import_legacy(db, args)
        finally:
            await db.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
