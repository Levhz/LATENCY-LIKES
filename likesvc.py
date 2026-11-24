import asyncio

import config
import db
from pool import pool, LikeError
from utils import today_str, until_reset, clean_uid, norm_region

_user_locks: dict[int, asyncio.Lock] = {}


def _lock_for(uid: int) -> asyncio.Lock:
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]


def quota(user_id: int) -> dict:
    st = db.settings()
    used = db.daily_used(user_id)
    return {"limit": st["daily_limit"], "used": used,
            "remaining": max(0, st["daily_limit"] - used),
            "reset_in": until_reset()}


async def process_like(user_id: int, region: str, target: str, amount: int) -> dict:
    st = db.settings()
    if not st["api_enabled"]:
        raise LikeError(st["maintenance_msg"] or "The like API is currently OFF.")

    target = clean_uid(target)
    if not target:
        raise LikeError("Enter a valid UID (5-12 digits).")

    region = norm_region(region or config.DEFAULT_REGION)
    day = today_str()

    async with _lock_for(user_id):
        user = db.ensure_user(user_id)
        if user["banned"]:
            raise LikeError("You are banned.")

        amount = max(1, min(int(amount or 1), st["max_amount"]))
        used = db.daily_used(user_id, day)
        remaining = st["daily_limit"] - used
        if remaining <= 0:
            raise LikeError(f"Daily limit reached. Resets in {until_reset()}.")
        amount = min(amount, remaining)

        cost = st["cost_per_cmd"] + st["cost_per_like"] * (amount - 1)
        if user["credits"] < cost:
            raise LikeError(f"Not enough credits. Need {cost}, you have {user['credits']}.")
        if not db.try_charge(user_id, cost):
            raise LikeError("Not enough credits.")

        try:
            res = await pool.like_many(target, amount, region)
        except LikeError:
            db.refund(user_id, cost)
            raise
        except Exception as e:
            db.refund(user_id, cost)
            raise LikeError(f"Server error: {e}")

        if res["ok"] == 0:
            db.refund(user_id, cost)
            db.log_like(user_id, target, 0, 0, res["guest"], "0 likes")
            raise LikeError("The server rejected every like. Credits refunded.")

        db.add_daily(user_id, res["ok"], day)
        db.bump_total(user_id, res["ok"])
        db.log_like(user_id, target, res["ok"], 1, res["guest"])

        return {
            "sent": res["ok"], "requested": amount, "cost": cost,
            "nickname": res["nickname"], "before": res["before"], "after": res["after"],
            "credits": db.get_user(user_id)["credits"],
            "remaining": max(0, st["daily_limit"] - used - res["ok"]),
        }
