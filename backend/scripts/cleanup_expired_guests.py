#!/usr/bin/env python3
"""
Cleanup script for expired guest accounts.

This script deletes guest accounts that have been inactive for more than 90 days.
Run this daily via cron to keep the database clean.

Usage:
    # Dry run (show what would be deleted)
    python -m backend.scripts.cleanup_expired_guests --dry-run

    # Actually delete
    python -m backend.scripts.cleanup_expired_guests

    # Custom expiry days
    python -m backend.scripts.cleanup_expired_guests --days 60

Cron example (run daily at 3 AM):
    0 3 * * * cd /path/to/project && /path/to/venv/bin/python -m backend.scripts.cleanup_expired_guests >> /var/log/guest_cleanup.log 2>&1
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import DATABASE_URL
from backend import models


def cleanup_expired_guests(days: int = 90, dry_run: bool = False) -> int:
    """
    Delete guest accounts that have been inactive for more than `days` days.

    Args:
        days: Number of days of inactivity before deletion (default: 90)
        dry_run: If True, only print what would be deleted without actually deleting

    Returns:
        Number of guests deleted (or would be deleted in dry run)
    """
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Find expired guests
        # A guest is expired if:
        # 1. is_guest = True
        # 2. last_active_at is NULL (never set) OR last_active_at < cutoff
        # 3. For guests without last_active_at, use created_at as fallback
        expired_guests = db.query(models.User).filter(
            models.User.is_guest == True,
        ).filter(
            # Either last_active_at is set and old...
            (models.User.last_active_at != None) & (models.User.last_active_at < cutoff) |
            # ...or last_active_at is NULL and created_at is old
            (models.User.last_active_at == None) & (models.User.created_at < cutoff)
        ).all()

        count = len(expired_guests)

        if dry_run:
            print(f"[DRY RUN] Would delete {count} expired guest accounts:")
            for guest in expired_guests[:10]:  # Show first 10
                last_active = guest.last_active_at or guest.created_at
                print(f"  - {guest.username} (ID={guest.id}, last_active={last_active})")
            if count > 10:
                print(f"  ... and {count - 10} more")
        else:
            # Delete guests (cascade will delete their teams, user_monsters, talents)
            for guest in expired_guests:
                db.delete(guest)

            db.commit()
            print(f"Deleted {count} expired guest accounts (inactive > {days} days)")

        return count

    except Exception as e:
        db.rollback()
        print(f"Error during cleanup: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Clean up expired guest accounts"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Days of inactivity before deletion (default: 90)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )

    args = parser.parse_args()

    print(f"Guest cleanup started at {datetime.now(timezone.utc).isoformat()}")
    print(f"Expiry threshold: {args.days} days")

    try:
        count = cleanup_expired_guests(days=args.days, dry_run=args.dry_run)
        print(f"Cleanup completed. {count} guests {'would be' if args.dry_run else ''} deleted.")
        sys.exit(0)
    except Exception as e:
        print(f"Cleanup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
