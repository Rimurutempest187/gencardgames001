import json
import aiosqlite
from typing import Optional, List, Dict, Any, Tuple

RARITIES = ["Common", "Rare", "Epic", "Legendary", "Mythic"]

RARITY_EMOJI = {
    "Common": "🪔",
    "Rare": "✨",
    "Epic": "🔮",
    "Legendary": "🧿",
    "Mythic": "💠",
}

RARITY_WEIGHTS = {
    "Common": 60,
    "Rare": 25,
    "Epic": 10,
    "Legendary": 4,
    "Mythic": 1,
}

RARITY_PRICE = {
    "Common": 100,
    "Rare": 300,
    "Epic": 800,
    "Legendary": 2000,
    "Mythic": 5000,
}

RARITY_POWER = {
    "Common": (8, 15),
    "Rare": (16, 28),
    "Epic": (29, 45),
    "Legendary": (46, 70),
    "Mythic": (71, 100),
}

def norm_name(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

class Database:
    def __init__(self, path: str = "game.db"):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                coins INTEGER NOT NULL DEFAULT 300,
                bank INTEGER NOT NULL DEFAULT 0,
                daily_last TEXT DEFAULT NULL,
                fav_char_id INTEGER DEFAULT NULL,
                fight_last INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS characters (
                char_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                movie TEXT NOT NULL,
                rarity TEXT NOT NULL,
                image_file_id TEXT NOT NULL,
                price INTEGER NOT NULL,
                power INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_chars (
                user_id INTEGER NOT NULL,
                char_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, char_id)
            );

            CREATE TABLE IF NOT EXISTS groups (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                drop_every INTEGER NOT NULL DEFAULT 50,
                msg_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS active_drops (
                chat_id INTEGER PRIMARY KEY,
                char_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sudo (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS group_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS polls (
                chat_id INTEGER PRIMARY KEY,
                poll_message_id INTEGER,
                poll_id TEXT
            );
            """)
            await db.commit()

    async def ensure_user(self, user_id: int, name: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users(user_id, name) VALUES(?, ?)",
                (user_id, name),
            )
            await db.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT user_id,name,coins,bank,daily_last,fav_char_id,fight_last FROM users WHERE user_id=?",
                                   (user_id,))
            row = await cur.fetchone()
            if not row:
                return None
            keys = ["user_id","name","coins","bank","daily_last","fav_char_id","fight_last"]
            return dict(zip(keys, row))

    async def add_coins(self, user_id: int, delta: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (delta, user_id))
            await db.commit()

    async def set_coins(self, user_id: int, value: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET coins=? WHERE user_id=?", (value, user_id))
            await db.commit()

    async def add_bank(self, user_id: int, delta: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET bank = bank + ? WHERE user_id=?", (delta, user_id))
            await db.commit()

    async def set_daily_last(self, user_id: int, date_str: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET daily_last=? WHERE user_id=?", (date_str, user_id))
            await db.commit()

    async def set_fight_last(self, user_id: int, ts: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET fight_last=? WHERE user_id=?", (ts, user_id))
            await db.commit()

    async def set_favorite(self, user_id: int, char_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET fav_char_id=? WHERE user_id=?", (char_id, user_id))
            await db.commit()

    async def is_sudo(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT 1 FROM sudo WHERE user_id=?", (user_id,))
            return (await cur.fetchone()) is not None

    async def add_sudo(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO sudo(user_id) VALUES(?)", (user_id,))
            await db.commit()

    async def del_sudo(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sudo WHERE user_id=?", (user_id,))
            await db.commit()

    async def list_sudo(self) -> List[int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT user_id FROM sudo ORDER BY user_id")
            rows = await cur.fetchall()
            return [r[0] for r in rows]

    async def upsert_group(self, chat_id: int, title: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT OR IGNORE INTO groups(chat_id, title) VALUES(?,?)", (chat_id, title))
            await db.execute("UPDATE groups SET title=? WHERE chat_id=?", (title, chat_id))
            await db.commit()

    async def set_drop_every(self, chat_id: int, n: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE groups SET drop_every=? WHERE chat_id=?", (n, chat_id))
            await db.commit()

    async def get_group(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT chat_id,title,drop_every,msg_count FROM groups WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
            if not row:
                return None
            keys = ["chat_id","title","drop_every","msg_count"]
            return dict(zip(keys, row))

    async def inc_group_msg(self, chat_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE groups SET msg_count = msg_count + 1 WHERE chat_id=?", (chat_id,))
            await db.commit()
            cur = await db.execute("SELECT msg_count FROM groups WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def reset_group_msg(self, chat_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE groups SET msg_count=0 WHERE chat_id=?", (chat_id,))
            await db.commit()

    async def get_active_drop(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT chat_id,char_id,name,message_id,created_at FROM active_drops WHERE chat_id=?",
                                   (chat_id,))
            row = await cur.fetchone()
            if not row:
                return None
            keys = ["chat_id","char_id","name","message_id","created_at"]
            return dict(zip(keys, row))

    async def set_active_drop(self, chat_id: int, char_id: int, name: str, message_id: int, created_at: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO active_drops(chat_id,char_id,name,message_id,created_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    char_id=excluded.char_id,
                    name=excluded.name,
                    message_id=excluded.message_id,
                    created_at=excluded.created_at
            """, (chat_id, char_id, name, message_id, created_at))
            await db.commit()

    async def clear_active_drop(self, chat_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM active_drops WHERE chat_id=?", (chat_id,))
            await db.commit()

    async def add_member_seen(self, chat_id: int, user_id: int, name: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO group_members(chat_id,user_id,name)
                VALUES(?,?,?)
                ON CONFLICT(chat_id,user_id) DO UPDATE SET name=excluded.name
            """, (chat_id, user_id, name))
            await db.commit()

    async def get_members(self, chat_id: int, limit: int = 50) -> List[Tuple[int,str]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT user_id, COALESCE(name,'User') FROM group_members WHERE chat_id=? ORDER BY user_id LIMIT ?",
                (chat_id, limit),
            )
            return await cur.fetchall()

    async def upsert_poll(self, chat_id: int, poll_message_id: int, poll_id: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO polls(chat_id,poll_message_id,poll_id)
                VALUES(?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    poll_message_id=excluded.poll_message_id,
                    poll_id=excluded.poll_id
            """, (chat_id, poll_message_id, poll_id))
            await db.commit()

    async def get_poll(self, chat_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT chat_id,poll_message_id,poll_id FROM polls WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return {"chat_id": row[0], "poll_message_id": row[1], "poll_id": row[2]}

    # -------- Characters --------
    async def add_character(self, name: str, movie: str, rarity: str, image_file_id: str, price: int, power: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                INSERT INTO characters(name,movie,rarity,image_file_id,price,power)
                VALUES(?,?,?,?,?,?)
            """, (name, movie, rarity, image_file_id, price, power))
            await db.commit()
            return cur.lastrowid

    async def delete_character(self, char_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM characters WHERE char_id=?", (char_id,))
            await db.execute("DELETE FROM user_chars WHERE char_id=?", (char_id,))
            await db.commit()

    async def get_character(self, char_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT char_id,name,movie,rarity,image_file_id,price,power FROM characters WHERE char_id=?",
                                   (char_id,))
            row = await cur.fetchone()
            if not row:
                return None
            keys = ["char_id","name","movie","rarity","image_file_id","price","power"]
            return dict(zip(keys, row))

    async def find_characters(self, q: str, limit: int = 25) -> List[Dict[str, Any]]:
        qn = f"%{q.strip().lower()}%"
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT char_id,name,movie,rarity,image_file_id,price,power
                FROM characters
                WHERE lower(name) LIKE ? OR lower(movie) LIKE ?
                ORDER BY char_id DESC
                LIMIT ?
            """, (qn, qn, limit))
            rows = await cur.fetchall()
            keys = ["char_id","name","movie","rarity","image_file_id","price","power"]
            return [dict(zip(keys, r)) for r in rows]

    async def list_characters(self, offset: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT char_id,name,movie,rarity,image_file_id,price,power
                FROM characters
                ORDER BY char_id DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = await cur.fetchall()
            keys = ["char_id","name","movie","rarity","image_file_id","price","power"]
            return [dict(zip(keys, r)) for r in rows]

    async def count_characters(self) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM characters")
            return (await cur.fetchone())[0]

    async def list_all_characters(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT char_id,name,movie,rarity,image_file_id,price,power
                FROM characters
                ORDER BY char_id DESC
            """)
            rows = await cur.fetchall()
            keys = ["char_id","name","movie","rarity","image_file_id","price","power"]
            return [dict(zip(keys, r)) for r in rows]

    async def add_user_char(self, user_id: int, char_id: int, delta: int = 1):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                INSERT INTO user_chars(user_id,char_id,count)
                VALUES(?,?,?)
                ON CONFLICT(user_id,char_id) DO UPDATE SET
                    count = count + excluded.count
            """, (user_id, char_id, delta))
            await db.execute("DELETE FROM user_chars WHERE user_id=? AND char_id=? AND count<=0", (user_id, char_id))
            await db.commit()

    async def get_user_char_count(self, user_id: int, char_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT count FROM user_chars WHERE user_id=? AND char_id=?", (user_id, char_id))
            row = await cur.fetchone()
            return row[0] if row else 0

    async def get_user_collection(self, user_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT c.char_id,c.name,c.movie,c.rarity,c.image_file_id,c.price,c.power, uc.count
                FROM user_chars uc
                JOIN characters c ON c.char_id = uc.char_id
                WHERE uc.user_id=?
                ORDER BY c.rarity DESC, c.power DESC, c.char_id DESC
            """, (user_id,))
            rows = await cur.fetchall()
            keys = ["char_id","name","movie","rarity","image_file_id","price","power","count"]
            return [dict(zip(keys, r)) for r in rows]

    async def get_user_total_cards(self, user_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COALESCE(SUM(count),0) FROM user_chars WHERE user_id=?", (user_id,))
            return (await cur.fetchone())[0]

    async def get_user_rarity_counts(self, user_id: int) -> Dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT c.rarity, COALESCE(SUM(uc.count),0)
                FROM user_chars uc
                JOIN characters c ON c.char_id = uc.char_id
                WHERE uc.user_id=?
                GROUP BY c.rarity
            """, (user_id,))
            rows = await cur.fetchall()
            out = {r: 0 for r in RARITIES}
            for rarity, cnt in rows:
                out[rarity] = cnt
            return out

    async def top_by_wealth(self, limit: int = 10) -> List[Tuple[int,str,int,int]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT user_id, COALESCE(name,'User'), coins, bank
                FROM users
                ORDER BY (coins + bank) DESC
                LIMIT ?
            """, (limit,))
            return await cur.fetchall()

    async def top_by_cards(self, limit: int = 10) -> List[Tuple[int,str,int]]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
                SELECT u.user_id, COALESCE(u.name,'User'), COALESCE(SUM(uc.count),0) AS total_cards
                FROM users u
                LEFT JOIN user_chars uc ON uc.user_id = u.user_id
                GROUP BY u.user_id
                ORDER BY total_cards DESC
                LIMIT ?
            """, (limit,))
            return await cur.fetchall()

    async def stats(self) -> Dict[str, int]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users")
            users = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM groups")
            groups = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM characters")
            chars = (await cur.fetchone())[0]
            return {"users": users, "groups": groups, "characters": chars}

    async def export_json(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            def rowdict(keys, row): return dict(zip(keys, row))

            out = {}
            for table, keys in [
                ("users", ["user_id","name","coins","bank","daily_last","fav_char_id","fight_last"]),
                ("characters", ["char_id","name","movie","rarity","image_file_id","price","power"]),
                ("user_chars", ["user_id","char_id","count"]),
                ("groups", ["chat_id","title","drop_every","msg_count"]),
                ("active_drops", ["chat_id","char_id","name","message_id","created_at"]),
                ("sudo", ["user_id"]),
                ("group_members", ["chat_id","user_id","name"]),
                ("polls", ["chat_id","poll_message_id","poll_id"]),
            ]:
                cur = await db.execute(f"SELECT * FROM {table}")
                rows = await cur.fetchall()
                out[table] = [rowdict(keys, r) for r in rows]
            return out

    async def import_json(self, data: Dict[str, Any]):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                DELETE FROM polls;
                DELETE FROM group_members;
                DELETE FROM sudo;
                DELETE FROM active_drops;
                DELETE FROM groups;
                DELETE FROM user_chars;
                DELETE FROM characters;
                DELETE FROM users;
            """)

            for row in data.get("users", []):
                await db.execute("""INSERT INTO users(user_id,name,coins,bank,daily_last,fav_char_id,fight_last)
                                    VALUES(?,?,?,?,?,?,?)""",
                                 (row["user_id"], row.get("name"), row.get("coins",300), row.get("bank",0),
                                  row.get("daily_last"), row.get("fav_char_id"), row.get("fight_last",0)))

            for row in data.get("characters", []):
                await db.execute("""INSERT INTO characters(char_id,name,movie,rarity,image_file_id,price,power)
                                    VALUES(?,?,?,?,?,?,?)""",
                                 (row["char_id"], row["name"], row["movie"], row["rarity"], row["image_file_id"],
                                  row.get("price", 100), row.get("power", 10)))

            for row in data.get("user_chars", []):
                await db.execute("""INSERT INTO user_chars(user_id,char_id,count) VALUES(?,?,?)""",
                                 (row["user_id"], row["char_id"], row.get("count", 1)))

            for row in data.get("groups", []):
                await db.execute("""INSERT INTO groups(chat_id,title,drop_every,msg_count) VALUES(?,?,?,?)""",
                                 (row["chat_id"], row.get("title"), row.get("drop_every",50), row.get("msg_count",0)))

            for row in data.get("active_drops", []):
                await db.execute("""INSERT INTO active_drops(chat_id,char_id,name,message_id,created_at)
                                    VALUES(?,?,?,?,?)""",
                                 (row["chat_id"], row["char_id"], row["name"], row["message_id"], row["created_at"]))

            for row in data.get("sudo", []):
                await db.execute("INSERT INTO sudo(user_id) VALUES(?)", (row["user_id"],))

            for row in data.get("group_members", []):
                await db.execute("INSERT INTO group_members(chat_id,user_id,name) VALUES(?,?,?)",
                                 (row["chat_id"], row["user_id"], row.get("name")))

            for row in data.get("polls", []):
                await db.execute("INSERT INTO polls(chat_id,poll_message_id,poll_id) VALUES(?,?,?)",
                                 (row["chat_id"], row.get("poll_message_id"), row.get("poll_id")))

            await db.commit()

    async def all_clear(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript("""
                DELETE FROM polls;
                DELETE FROM group_members;
                DELETE FROM sudo;
                DELETE FROM active_drops;
                DELETE FROM groups;
                DELETE FROM user_chars;
                DELETE FROM characters;
                DELETE FROM users;
            """)
            await db.commit()
