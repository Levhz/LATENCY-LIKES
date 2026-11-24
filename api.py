import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import db
import guestgen
from likesvc import process_like, quota
from panel import PAGE
from pool import pool, LikeError

db.init()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pool.start()
    bot_task = None
    if config.BOT_TOKEN:
        import bot as botmod
        bot_task = asyncio.create_task(botmod.run_bot())
    yield
    await pool.stop()
    if bot_task:
        bot_task.cancel()


app = FastAPI(title="FF Like API", lifespan=lifespan)


def api_auth(x_api_key: str = Header(None)):
    if x_api_key != config.API_KEY:
        raise HTTPException(401, "bad api key")


def admin_auth(authorization: str = Header(None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token != config.ADMIN_TOKEN:
        raise HTTPException(401, "unauthorized")


class LikeIn(BaseModel):
    uid: str
    amount: int = 1
    region: str = config.DEFAULT_REGION
    discord_id: int


class LoginIn(BaseModel):
    password: str


class CreditsIn(BaseModel):
    discord_id: int
    delta: int = 0
    value: int | None = None


class SettingsIn(BaseModel):
    api_enabled: bool | None = None
    cost_per_cmd: int | None = None
    cost_per_like: int | None = None
    daily_limit: int | None = None
    max_amount: int | None = None
    maintenance_msg: str | None = None


class RefillIn(BaseModel):
    count: int = 3


@app.get("/", response_class=HTMLResponse)
async def index():
    return PAGE


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    st = db.settings()
    return {"api_enabled": st["api_enabled"], "cost_per_cmd": st["cost_per_cmd"],
            "daily_limit": st["daily_limit"], "max_amount": st["max_amount"],
            "maintenance_msg": st["maintenance_msg"],
            "regions": guestgen.gen.sUpPoRtEd_ReGiOnS,
            "tor": guestgen.gen.uSe_tOr_PrOxY}


@app.get("/api/profile/{uid}")
async def profile(uid: str, region: str = config.DEFAULT_REGION, _=Depends(api_auth)):
    try:
        p = await pool.get_profile(uid, region.upper())
    except Exception as e:
        raise HTTPException(503, f"account unavailable: {e}")
    if not p:
        raise HTTPException(404, "not found")
    return p


@app.post("/api/like")
async def api_like(body: LikeIn, _=Depends(api_auth)):
    try:
        return await process_like(body.discord_id, body.region, body.uid, body.amount)
    except LikeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/quota/{discord_id}")
async def api_quota(discord_id: int, _=Depends(api_auth)):
    u = db.ensure_user(discord_id)
    return {"quota": quota(discord_id), "credits": u["credits"]}


@app.post("/admin/login")
async def admin_login(body: LoginIn):
    if body.password != config.ADMIN_TOKEN:
        raise HTTPException(401, "wrong password")
    return {"token": config.ADMIN_TOKEN}


@app.get("/admin/overview", dependencies=[Depends(admin_auth)])
async def admin_overview():
    return {"settings": db.settings(), "stats": db.stats(), "pool": db.pool_counts(),
            "guests": db.guest_list(50), "logs": db.recent_logs(25)}


@app.get("/admin/users", dependencies=[Depends(admin_auth)])
async def admin_users():
    return db.users_list()


@app.post("/admin/settings", dependencies=[Depends(admin_auth)])
async def admin_settings(body: SettingsIn):
    for k, v in body.model_dump(exclude_none=True).items():
        if k == "api_enabled":
            v = "1" if v else "0"
        db.set_setting(k, v)
    return db.settings()


@app.post("/admin/credits", dependencies=[Depends(admin_auth)])
async def admin_credits(body: CreditsIn):
    if body.value is not None:
        bal = db.set_credits(body.discord_id, body.value)
    else:
        bal = db.add_credits(body.discord_id, body.delta)
    return {"discord_id": body.discord_id, "credits": bal}


@app.post("/admin/ban", dependencies=[Depends(admin_auth)])
async def admin_ban(discord_id: int, banned: bool = True):
    db.set_banned(discord_id, banned)
    return {"discord_id": discord_id, "banned": banned}


@app.post("/admin/pool/refill", dependencies=[Depends(admin_auth)])
async def admin_refill(body: RefillIn):
    await pool.warm(min(20, max(1, body.count)))
    return {"queued": body.count}


@app.post("/admin/pool/purge", dependencies=[Depends(admin_auth)])
async def admin_purge():
    return {"removed": db.purge_dead()}
