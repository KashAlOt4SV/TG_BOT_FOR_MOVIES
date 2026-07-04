from __future__ import annotations

import re
from typing import Any

import aiosqlite

from bot.database import Database

USERNAME_PATTERN = re.compile(r"^@?([a-zA-Z][a-zA-Z0-9_]{4,31})$")


def normalize_username(raw: str) -> str | None:
    raw = raw.strip()
    match = USERNAME_PATTERN.match(raw)
    if not match:
        return None
    return match.group(1).lower()


def parse_usernames(text: str) -> list[str]:
    parts = re.split(r"[\s,;]+", text.strip())
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        if not part:
            continue
        username = normalize_username(part)
        if username and username not in seen:
            seen.add(username)
            result.append(username)
    return result


class Repository:
    def __init__(self, db: Database):
        self.db = db

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
    ) -> dict[str, Any]:
        async with self.db.connection() as conn:
            await conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name
                """,
                (telegram_id, username.lower() if username else None, first_name),
            )
            await conn.commit()
            return await self._get_user_by_telegram_id(conn, telegram_id)

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            return await self._get_user_by_telegram_id(conn, telegram_id)

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized = normalize_username(username)
        if not normalized:
            return None
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (normalized,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_groups(self, user_id: int) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT g.*, COUNT(gm2.user_id) AS member_count
                FROM groups g
                JOIN group_members gm ON gm.group_id = g.id AND gm.user_id = ?
                JOIN group_members gm2 ON gm2.group_id = g.id
                GROUP BY g.id
                ORDER BY g.created_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_group_members(self, group_id: int) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT u.*
                FROM users u
                JOIN group_members gm ON gm.user_id = u.id
                WHERE gm.group_id = ?
                ORDER BY gm.joined_at
                """,
                (group_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def is_group_member(self, group_id: int, user_id: int) -> bool:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            return await cursor.fetchone() is not None

    async def create_formation(
        self,
        creator_id: int,
        invitee_ids: list[int],
    ) -> dict[str, Any]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "INSERT INTO group_formations (creator_id) VALUES (?)",
                (creator_id,),
            )
            formation_id = cursor.lastrowid
            for invitee_id in invitee_ids:
                await conn.execute(
                    """
                    INSERT INTO formation_invites (formation_id, invitee_id)
                    VALUES (?, ?)
                    """,
                    (formation_id, invitee_id),
                )
            await conn.commit()
            return await self._get_formation(conn, formation_id)

    async def get_pending_invites_for_user(self, user_id: int) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT fi.*, gf.creator_id, u.username AS creator_username,
                       u.first_name AS creator_first_name
                FROM formation_invites fi
                JOIN group_formations gf ON gf.id = fi.formation_id
                JOIN users u ON u.id = gf.creator_id
                WHERE fi.invitee_id = ? AND fi.status = 'pending' AND gf.status = 'pending'
                ORDER BY fi.id DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def respond_to_invite(
        self,
        invite_id: int,
        user_id: int,
        accepted: bool,
    ) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT fi.*, gf.creator_id, gf.status AS formation_status
                FROM formation_invites fi
                JOIN group_formations gf ON gf.id = fi.formation_id
                WHERE fi.id = ? AND fi.invitee_id = ? AND fi.status = 'pending'
                """,
                (invite_id, user_id),
            )
            invite = await cursor.fetchone()
            if not invite:
                return None

            invite = dict(invite)
            new_status = "accepted" if accepted else "rejected"
            await conn.execute(
                """
                UPDATE formation_invites
                SET status = ?, responded_at = datetime('now')
                WHERE id = ?
                """,
                (new_status, invite_id),
            )

            if not accepted:
                await conn.execute(
                    "UPDATE group_formations SET status = 'cancelled' WHERE id = ?",
                    (invite["formation_id"],),
                )
                await conn.commit()
                return {"action": "rejected", "formation_id": invite["formation_id"]}

            pending_cursor = await conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM formation_invites
                WHERE formation_id = ? AND status = 'pending'
                """,
                (invite["formation_id"],),
            )
            pending_count = (await pending_cursor.fetchone())["cnt"]

            if pending_count > 0:
                await conn.commit()
                return {"action": "accepted_pending", "formation_id": invite["formation_id"]}

            group = await self._finalize_formation(conn, invite["formation_id"])
            await conn.commit()
            return {"action": "group_created", "group": group, "formation_id": invite["formation_id"]}

    async def create_media_proposal(
        self,
        group_id: int,
        proposer_id: int,
        title: str,
    ) -> dict[str, Any]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO media_proposals (group_id, proposer_id, title)
                VALUES (?, ?, ?)
                """,
                (group_id, proposer_id, title.strip()),
            )
            proposal_id = cursor.lastrowid
            await conn.commit()
            cursor = await conn.execute(
                "SELECT * FROM media_proposals WHERE id = ?",
                (proposal_id,),
            )
            row = await cursor.fetchone()
            return dict(row)

    async def vote_on_proposal(
        self,
        proposal_id: int,
        voter_id: int,
        approved: bool,
    ) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT mp.* FROM media_proposals mp
                WHERE mp.id = ? AND mp.status = 'pending'
                """,
                (proposal_id,),
            )
            proposal = await cursor.fetchone()
            if not proposal:
                return None
            proposal = dict(proposal)

            if proposal["proposer_id"] == voter_id:
                return None

            member_cursor = await conn.execute(
                """
                SELECT 1 FROM group_members
                WHERE group_id = ? AND user_id = ?
                """,
                (proposal["group_id"], voter_id),
            )
            if not member_cursor.fetchone():
                return None

            await conn.execute(
                """
                INSERT INTO media_votes (proposal_id, voter_id, approved)
                VALUES (?, ?, ?)
                ON CONFLICT(proposal_id, voter_id) DO UPDATE SET
                    approved = excluded.approved,
                    voted_at = datetime('now')
                """,
                (proposal_id, voter_id, 1 if approved else 0),
            )

            if not approved:
                await conn.execute(
                    "UPDATE media_proposals SET status = 'rejected' WHERE id = ?",
                    (proposal_id,),
                )
                await conn.commit()
                return {"action": "rejected", "proposal": proposal}

            members_cursor = await conn.execute(
                """
                SELECT user_id FROM group_members
                WHERE group_id = ? AND user_id != ?
                """,
                (proposal["group_id"], proposal["proposer_id"]),
            )
            other_members = [row["user_id"] for row in await members_cursor.fetchall()]

            votes_cursor = await conn.execute(
                """
                SELECT voter_id, approved FROM media_votes
                WHERE proposal_id = ? AND approved = 1
                """,
                (proposal_id,),
            )
            approved_voters = {row["voter_id"] for row in await votes_cursor.fetchall()}

            if set(other_members).issubset(approved_voters):
                await conn.execute(
                    "UPDATE media_proposals SET status = 'approved' WHERE id = ?",
                    (proposal_id,),
                )
                watch_cursor = await conn.execute(
                    """
                    INSERT INTO watch_items (group_id, title, added_by, status)
                    VALUES (?, ?, ?, 'queued')
                    """,
                    (proposal["group_id"], proposal["title"], proposal["proposer_id"]),
                )
                watch_item_id = watch_cursor.lastrowid
                await conn.commit()
                return {
                    "action": "approved",
                    "proposal": proposal,
                    "watch_item_id": watch_item_id,
                }

            await conn.commit()
            return {"action": "vote_recorded", "proposal": proposal}

    async def get_watch_items(
        self,
        group_id: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        async with self.db.connection() as conn:
            if status:
                cursor = await conn.execute(
                    """
                    SELECT * FROM watch_items
                    WHERE group_id = ? AND status = ?
                    ORDER BY created_at
                    """,
                    (group_id, status),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT * FROM watch_items
                    WHERE group_id = ?
                    ORDER BY
                        CASE status
                            WHEN 'watching' THEN 0
                            WHEN 'queued' THEN 1
                            WHEN 'completed' THEN 2
                        END,
                        created_at
                    """,
                    (group_id,),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def pick_random_watch_item(self, group_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            watching_cursor = await conn.execute(
                """
                SELECT * FROM watch_items
                WHERE group_id = ? AND status = 'watching'
                LIMIT 1
                """,
                (group_id,),
            )
            watching = await watching_cursor.fetchone()
            if watching:
                return {"action": "already_watching", "item": dict(watching)}

            cursor = await conn.execute(
                """
                SELECT * FROM watch_items
                WHERE group_id = ? AND status = 'queued'
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (group_id,),
            )
            item = await cursor.fetchone()
            if not item:
                return None

            item = dict(item)
            await conn.execute(
                """
                UPDATE watch_items
                SET status = 'watching', picked_at = datetime('now')
                WHERE id = ?
                """,
                (item["id"],),
            )
            await conn.commit()
            item["status"] = "watching"
            return {"action": "picked", "item": item}

    async def get_current_watching(self, group_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM watch_items
                WHERE group_id = ? AND status = 'watching'
                LIMIT 1
                """,
                (group_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def mark_watching_completed(self, group_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM watch_items
                WHERE group_id = ? AND status = 'watching'
                LIMIT 1
                """,
                (group_id,),
            )
            item = await cursor.fetchone()
            if not item:
                return None
            item = dict(item)
            await conn.execute(
                """
                UPDATE watch_items
                SET status = 'completed', completed_at = datetime('now')
                WHERE id = ?
                """,
                (item["id"],),
            )
            await conn.commit()
            item["status"] = "completed"
            return item

    async def get_group(self, group_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM media_proposals WHERE id = ?",
                (proposal_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_invite_for_formation(
        self,
        formation_id: int,
        invitee_id: int,
    ) -> dict[str, Any] | None:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM formation_invites
                WHERE formation_id = ? AND invitee_id = ?
                """,
                (formation_id, invitee_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_formation_participants_telegram_ids(
        self,
        formation_id: int,
    ) -> list[int]:
        async with self.db.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT u.telegram_id
                FROM group_formations gf
                JOIN users u ON u.id = gf.creator_id
                WHERE gf.id = ?
                UNION
                SELECT u.telegram_id
                FROM formation_invites fi
                JOIN users u ON u.id = fi.invitee_id
                WHERE fi.formation_id = ? AND fi.status = 'accepted'
                """,
                (formation_id, formation_id),
            )
            rows = await cursor.fetchall()
            return [row["telegram_id"] for row in rows]

    async def _get_user_by_telegram_id(
        self,
        conn: aiosqlite.Connection,
        telegram_id: int,
    ) -> dict[str, Any]:
        cursor = await conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cursor.fetchone()
        return dict(row)

    async def _get_formation(
        self,
        conn: aiosqlite.Connection,
        formation_id: int,
    ) -> dict[str, Any]:
        cursor = await conn.execute(
            "SELECT * FROM group_formations WHERE id = ?",
            (formation_id,),
        )
        row = await cursor.fetchone()
        return dict(row)

    async def _finalize_formation(
        self,
        conn: aiosqlite.Connection,
        formation_id: int,
    ) -> dict[str, Any]:
        cursor = await conn.execute(
            """
            SELECT gf.creator_id, u.first_name, u.username
            FROM group_formations gf
            JOIN users u ON u.id = gf.creator_id
            WHERE gf.id = ?
            """,
            (formation_id,),
        )
        formation = await cursor.fetchone()
        creator_name = formation["first_name"] or formation["username"] or "Группа"
        group_name = f"Группа {creator_name}"

        cursor = await conn.execute(
            "INSERT INTO groups (name) VALUES (?)",
            (group_name,),
        )
        group_id = cursor.lastrowid

        await conn.execute(
            "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, formation["creator_id"]),
        )

        invites_cursor = await conn.execute(
            """
            SELECT invitee_id FROM formation_invites
            WHERE formation_id = ? AND status = 'accepted'
            """,
            (formation_id,),
        )
        for row in await invites_cursor.fetchall():
            await conn.execute(
                "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                (group_id, row["invitee_id"]),
            )

        await conn.execute(
            "UPDATE group_formations SET status = 'completed' WHERE id = ?",
            (formation_id,),
        )

        group_cursor = await conn.execute(
            "SELECT * FROM groups WHERE id = ?",
            (group_id,),
        )
        return dict(await group_cursor.fetchone())
