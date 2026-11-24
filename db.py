import sqlite3
import threading

import config
from utils import now_iso, today_str

_lock = threading.RLock()
_conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")
_conn.execute("PRAGMA synchronous=NORMAL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(
  discord_id INTEGER PRIMARY KEY,
  credits INTEGER NOT NULL DEFAULT 0,
  total_likes INTEGER NOT NULL DEFAULT 0,
  banned INTEGER NOT NULL DEFAULT 0,
  created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS daily(
  user_id INTEGER NOT NULL, day TEXT NOT NULL,
  likes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS guests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
  account_id TEXT, jwt TEXT, device TEXT, region TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  likes_today INTEGER NOT NULL DEFAULT 0, day TEXT,
  fails INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, last_used TEXT);
CREATE TABLE IF NOT EXISTS logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, target TEXT,
  amount INTEGER, ok INTEGER, guest TEXT, note TEXT, created TEXT);
"""

DEFAULTS = {
    "api_enabled": "1",
    "cost_per_cmd": str(config.COST_PER_CMD),
    "cost_per_like": str(config.COST_PER_LIKE),
    "daily_limit": str(config.DAILY_LIMIT),
    "max_amount": str(config.MAX_AMOUNT),
    "maintenance_msg": "",
}


def init():
    with _lock:
        _conn.executescript(SCHEMA)
        for k, v in DEFAULTS.items():
            _conn.execute("INSERT OR IGNORE INTO settings(k, v) VALUES(?,?)", (k, v))
        _conn.commit()


def get_setting(key: str) -> str:
    with _lock:
        row = _conn.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        return row["v"] if row else DEFAULTS.get(key, "")


def set_setting(key: str, value) -> None:
    with _lock:
        _conn.execute("INSERT INTO settings(k, v) VALUES(?,?) "
                      "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
        _conn.commit()


def settings() -> dict:
    return {
        "api_enabled": get_setting("api_enabled") == "1",
        "cost_per_cmd": int(get_setting("cost_per_cmd")),
        "cost_per_like": int(get_setting("cost_per_like")),
        "daily_limit": int(get_setting("daily_limit")),
        "max_amount": int(get_setting("max_amount")),
        "maintenance_msg": get_setting("maintenance_msg"),
    }


def ensure_user(discord_id: int) -> dict:
    with _lock:
        _conn.execute("INSERT OR IGNORE INTO users(discord_id, credits, created) "
                      "VALUES(?,?,?)", (discord_id, config.WELCOME_CREDITS, now_iso()))
        _conn.commit()
        return dict(_conn.execute("SELECT * FROM users WHERE discord_id=?",
                                  (discord_id,)).fetchone())


def get_user(discord_id: int):
    with _lock:
        row = _conn.execute("SELECT * FROM users WHERE discord_id=?",
                            (discord_id,)).fetchone()
        return dict(row) if row else None


def add_credits(discord_id: int, delta: int) -> int:
    with _lock:
        ensure_user(discord_id)
        _conn.execute("UPDATE users SET credits=MAX(0, credits+?) WHERE discord_id=?",
                      (delta, discord_id))
        _conn.commit()
        return get_user(discord_id)["credits"]


def set_credits(discord_id: int, value: int) -> int:
    with _lock:
        ensure_user(discord_id)
        _conn.execute("UPDATE users SET credits=? WHERE discord_id=?",
                      (max(0, value), discord_id))
        _conn.commit()
        return get_user(discord_id)["credits"]


def try_charge(discord_id: int, cost: int) -> bool:
    with _lock:
        cur = _conn.execute("UPDATE users SET credits=credits-? "
                            "WHERE discord_id=? AND credits>=? AND banned=0",
                            (cost, discord_id, cost))
        _conn.commit()
        return cur.rowcount == 1


def refund(discord_id: int, amount: int) -> None:
    with _lock:
        _conn.execute("UPDATE users SET credits=credits+? WHERE discord_id=?",
                      (amount, discord_id))
        _conn.commit()


def set_banned(discord_id: int, banned: bool) -> None:
    with _lock:
        ensure_user(discord_id)
        _conn.execute("UPDATE users SET banned=? WHERE discord_id=?",
                      (1 if banned else 0, discord_id))
        _conn.commit()


def bump_total(discord_id: int, n: int) -> None:
    with _lock:
        _conn.execute("UPDATE users SET total_likes=total_likes+? WHERE discord_id=?",
                      (n, discord_id))
        _conn.commit()


def daily_used(user_id: int, day: str = None) -> int:
    day = day or today_str()
    with _lock:
        row = _conn.execute("SELECT likes FROM daily WHERE user_id=? AND day=?",
                            (user_id, day)).fetchone()
        return row["likes"] if row else 0


def add_daily(user_id: int, n: int, day: str = None) -> None:
    day = day or today_str()
    with _lock:
        _conn.execute("INSERT INTO daily(user_id, day, likes) VALUES(?,?,?) "
                      "ON CONFLICT(user_id, day) DO UPDATE SET likes=likes+excluded.likes",
                      (user_id, day, n))
        _conn.commit()


def add_guest(uid: str, password: str, device_json: str, region: str) -> int:
    with _lock:
        cur = _conn.execute(
            "INSERT INTO guests(uid, password, device, region, created) "
            "VALUES(?,?,?,?,?)", (uid, password, device_json, region, now_iso()))
        _conn.commit()
        return cur.lastrowid


def get_guest(gid: int):
    with _lock:
        row = _conn.execute("SELECT * FROM guests WHERE id=?", (gid,)).fetchone()
        return dict(row) if row else None


def set_guest(gid: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        _conn.execute(f"UPDATE guests SET {cols} WHERE id=?",
                      (*fields.values(), gid))
        _conn.commit()


def claim_guest(region: str, cap: int, day: str):
    with _lock:
        rows = _conn.execute(
            "SELECT * FROM guests WHERE region=? AND status='ready' "
            "AND (day IS NULL OR day<>? OR likes_today<?) "
            "ORDER BY COALESCE(last_used,'') ASC LIMIT 8",
            (region, day, cap)).fetchall()
        for row in rows:
            cur = _conn.execute("UPDATE guests SET status='busy', last_used=? "
                                "WHERE id=? AND status='ready'", (now_iso(), row["id"]))
            _conn.commit()
            if cur.rowcount == 1:
                return dict(row)
        return None


def bump_guest_likes(gid: int, n: int, day: str) -> None:
    with _lock:
        _conn.execute("UPDATE guests SET likes_today=CASE WHEN day=? THEN likes_today+? "
                      "ELSE ? END, day=? WHERE id=?", (day, n, n, day, gid))
        _conn.commit()


def pool_counts() -> dict:
    with _lock:
        out = {"ready": 0, "busy": 0, "new": 0, "dead": 0}
        for row in _conn.execute("SELECT status, COUNT(*) c FROM guests GROUP BY status"):
            out[row["status"]] = row["c"]
        return out


def ready_count(region: str, cap: int, day: str) -> int:
    with _lock:
        row = _conn.execute(
            "SELECT COUNT(*) c FROM guests WHERE region=? AND status='ready' "
            "AND (day IS NULL OR day<>? OR likes_today<?)", (region, day, cap)).fetchone()
        return row["c"]


def guest_list(limit: int = 100):
    with _lock:
        return [dict(r) for r in _conn.execute(
            "SELECT id, uid, region, status, likes_today, fails, last_used, created "
            "FROM guests ORDER BY id DESC LIMIT ?", (limit,))]


def purge_dead() -> int:
    with _lock:
        cur = _conn.execute("DELETE FROM guests WHERE status='dead'")
        _conn.commit()
        return cur.rowcount


def log_like(user_id, target, amount, ok, guest, note="") -> None:
    with _lock:
        _conn.execute("INSERT INTO logs(user_id, target, amount, ok, guest, note, created) "
                      "VALUES(?,?,?,?,?,?,?)",
                      (user_id, target, amount, 1 if ok else 0, guest, note, now_iso()))
        _conn.commit()


def recent_logs(limit: int = 50):
    with _lock:
        return [dict(r) for r in _conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))]


def stats() -> dict:
    with _lock:
        users = _conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        likes = _conn.execute("SELECT COALESCE(SUM(total_likes),0) c FROM users").fetchone()["c"]
        today = _conn.execute("SELECT COALESCE(SUM(likes),0) c FROM daily WHERE day=?",
                              (today_str(),)).fetchone()["c"]
        return {"users": users, "total_likes": likes, "today_likes": today}


def users_list(limit: int = 200):
    with _lock:
        rows = _conn.execute(
            "SELECT u.discord_id, u.credits, u.total_likes, u.banned, "
            "COALESCE(d.likes,0) AS today FROM users u "
            "LEFT JOIN daily d ON d.user_id=u.discord_id AND d.day=? "
            "ORDER BY u.credits DESC LIMIT ?", (today_str(), limit)).fetchall()
        return [dict(r) for r in rows]
