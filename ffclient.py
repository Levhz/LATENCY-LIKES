"""Game client: profile reads, likes and re-login.

Built directly on najmi_gen primitives — same AES key/IV, same proto writer,
same user agents, same session/proxy rules. No separate FF client.
"""
import random

import najmi_gen as gen

REGION_BASE = {
    "IND": "https://client.ind.freefiremobile.com/",
    "BR": "https://client.us.freefiremobile.com/",
    "US": "https://client.us.freefiremobile.com/",
    "SAC": "https://client.us.freefiremobile.com/",
}


def _base(region: str) -> str:
    base = REGION_BASE.get(region.upper()) or gen.cLiEnT_GlObAl
    return base if base.endswith("/") else base + "/"


def _session():
    s = gen.requests.Session()
    s.verify = False
    if gen.uSe_tOr_PrOxY:
        s.proxies = {"http": gen.tOr_sOcKs_pRoXy, "https": gen.tOr_sOcKs_pRoXy}
    return s


def _headers(jwt: str, content_type: str) -> dict:
    return {
        "User-Agent": random.choice(gen.uNiTy_AgEnTs),
        "Accept": "*/*",
        "Accept-Encoding": "deflate, gzip",
        "Authorization": f"Bearer {jwt}",
        "X-GA": "v1 1",
        "X-GA-SV": gen.gA_sV(),
        "ReleaseVersion": gen.rElEaSe_TaG,
        "X-Unity-Version": "2018.4.12f1",
        "Content-Type": content_type,
    }


def _payload(uid: str, region: str) -> bytes:
    return gen.eNcRyPt_aEs(gen.aSsEmBlE_pRoTo({1: int(uid), 2: region.upper()}))


def _post(path: str, jwt: str, uid: str, region: str):
    s = _session()
    try:
        return s.post(_base(region) + path, headers=_headers(jwt, "application/x-www-form-urlencoded"),
                      data=_payload(uid, region), timeout=30, verify=False)
    finally:
        s.close()


def profile(jwt: str, region: str, uid: str):
    try:
        r = _post("GetPlayerPersonalShow", jwt, uid, region)
    except Exception:
        return None
    if r.status_code not in (200, 201):
        return None
    f = gen.pArSe_pRoTo(r.content)
    nick = f.get(3)
    if isinstance(nick, bytes):
        try:
            nick = nick.decode()
        except Exception:
            nick = None
    return {"nickname": nick, "level": f.get(6), "likes": f.get(8)}


def send_like(jwt: str, region: str, uid: str):
    try:
        return _post("LikeProfile", jwt, uid, region)
    except Exception:
        return None


def relogin(uid: str, password: str, region: str) -> str:
    """Fresh JWT through the Activator API. Raises on failure."""
    ok, jwt, info = gen.aCtIvAtOr_BiNd(uid, password, region.upper())
    if not ok or not jwt:
        raise RuntimeError(f"relogin failed: {info.get('error')}")
    return jwt
