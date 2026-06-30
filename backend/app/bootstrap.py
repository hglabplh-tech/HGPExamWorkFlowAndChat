import argparse
import asyncio

from sqlalchemy import select

from .database import SessionLocal
from .models import Role, User
from .security import hash_password


async def create_user(email: str, password: str, name: str, role: Role) -> None:
    async with SessionLocal() as db:
        if await db.scalar(select(User).where(User.email == email)):
            raise SystemExit(f"User {email} already exists")
        db.add(User(email=email, display_name=name, password_hash=hash_password(password), role=role))
        await db.commit()
        print(f"Created {role.value}: {email}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--role", choices=[role.value for role in Role], default="admin")
    args = parser.parse_args()
    asyncio.run(create_user(args.email, args.password, args.name, Role(args.role)))

