"""Guest account pool — generates on demand via the najmi engine."""
import asyncio
import json

import config
import db
import ffclient
import guestgen
from utils import today_str, now_iso

_reg_lock = asyncio.Lock()
_last_reg = 0.0


class LikeError(Exception):
    pass


class Pool:
    def __init__(self):
        self._task = None
        self._creating = 0
        self._slots = None

    async def start(self):
        self._slots = asyncio.Semaphore(config.POOL_CREATE_CONCURRENCY)
        await asyncio.to_thread(guestgen.ensure_ready)
        await self.warm(config.POOL_MIN)
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(90)
                await self._reap()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(10)

    async def _reap(self):
        day = today_str()
        now = now_iso()
        for row in db.guest_list(400):
            if row["day"] and row["day"] != day and row["likes_today"]:
                db.set_guest(row["id"], likes_today=0, day=day)
            if row["status"] == "busy" and (row["last_used"] or "")[:16] < now[:16]:
                db.set_guest(row["id"], status="ready")
        await self.warm(config.POOL_TARGET)

    async def warm(self, target: int):
        have = db.ready_count(config.DEFAULT_REGION, config.ACCOUNT_DAILY_CAP, today_str())
        for _ in range(max(0, target - have - self._creating)):
            asyncio.create_task(self._create_safe(config.DEFAULT_REGION))

    async def _create_safe(self, region: str):
        async with self._slots:
            self._creating += 1
            try:
                await self._create(region, retries=3)
            except Exception:
                pass
            finally:
                self._creating -= 1

    async def _create(self, region: str, retries: int = 1) -> int:
        global _last_reg
        last = None
        for attempt in range(retries):
            async with _reg_lock:
                gap = config.REG_GAP - (asyncio.get_running_loop().time() - _last_reg)
                if gap > 0:
                    await asyncio.sleep(gap)
                try:
                    acc = await asyncio.to_thread(guestgen.create, region)
                except Exception as e:
                    last = e
                    _last_reg = asyncio.get_running_loop().time()
                    await asyncio.sleep(5 + attempt * 5)
                    continue
                _last_reg = asyncio.get_running_loop().time()

            gid = db.add_guest(acc["uid"], acc["password"], json.dumps({}), region)
            jwt = acc.get("jwt") or ""
            if not jwt:
                try:
                    jwt = await asyncio.to_thread(
                        ffclient.relogin, acc["uid"], acc["password"], region)
                except Exception as e:
                    db.set_guest(gid, status="dead", fails=99)
                    last = e
                    continue

            db.set_guest(gid, status="ready", jwt=jwt,
                         account_id=acc.get("account_id") or "")
            return gid
        raise RuntimeError(f"create failed: {last}")

    async def refresh(self, row: dict) -> dict:
        jwt = await asyncio.to_thread(
            ffclient.relogin, row["uid"], row["password"], row["region"])
        db.set_guest(row["id"], status="ready", jwt=jwt, fails=0)
        return db.get_guest(row["id"])

    async def mark_failed(self, row: dict):
        fails = (row["fails"] or 0) + 1
        status = "dead" if fails >= config.ACCOUNT_MAX_FAILS else "ready"
        db.set_guest(row["id"], status=status, fails=fails)

    async def acquire(self, region: str) -> dict:
        row = db.claim_guest(region, config.ACCOUNT_DAILY_CAP, today_str())
        if row:
            return row
        gid = await self._create(region, retries=2)
        db.set_guest(gid, status="busy")
        return db.get_guest(gid)

    def release(self, row: dict, ok: int):
        status = "dead" if (row.get("fails") or 0) >= config.ACCOUNT_MAX_FAILS else "ready"
        db.set_guest(row["id"], status=status, last_used=now_iso())
        if ok:
            db.bump_guest_likes(row["id"], ok, today_str())

    async def get_profile(self, target: str, region: str):
        row = await self.acquire(region)
        try:
            p = await asyncio.to_thread(ffclient.profile, row["jwt"], region, target)
            if not p:
                row = await self.refresh(row)
                p = await asyncio.to_thread(ffclient.profile, row["jwt"], region, target)
            return p
        finally:
            self.release(row, 0)

    async def like_many(self, target: str, amount: int, region: str) -> dict:
        row = await self.acquire(region)
        ok = 0
        refreshed = False
        try:
            before = await asyncio.to_thread(ffclient.profile, row["jwt"], region, target)
            if not before:
                row = await self.refresh(row)
                before = await asyncio.to_thread(ffclient.profile, row["jwt"], region, target)
            if not before:
                raise LikeError("UID not found on that server.")

            for _ in range(amount):
                r = await asyncio.to_thread(ffclient.send_like, row["jwt"], region, target)
                code = getattr(r, "status_code", None)
                if code in (200, 201):
                    ok += 1
                    await asyncio.sleep(config.LIKE_GAP)
                elif code in (401, 403) and not refreshed:
                    row = await self.refresh(row)
                    refreshed = True
                else:
                    await asyncio.sleep(0.6)

            after = await asyncio.to_thread(ffclient.profile, row["jwt"], region, target) or {}
            return {"ok": ok, "guest": row["uid"], "nickname": before.get("nickname"),
                    "before": before.get("likes"), "after": after.get("likes")}
        except Exception:
            await self.mark_failed(row)
            raise
        finally:
            self.release(row, ok)


pool = Pool()
