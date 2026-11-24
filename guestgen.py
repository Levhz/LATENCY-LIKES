"""Non-interactive adapter around najmi_gen.

The build is menu-driven and keeps state in module globals, so it is never
edited — only its globals are rebound before first use. Locking, pacing and a
stable return shape live here.
"""
import os
import threading
import time

import config
import najmi_gen as gen

_gen_lock = threading.Lock()
_state_lock = threading.Lock()
_ready = threading.Event()
_started = False
_last = 0.0


def supported(region: str) -> bool:
    return str(region).upper() in gen.sUpPoRtEd_ReGiOnS


def _apply_paths():
    base = os.path.join(str(config.DATA_DIR), "NAJMI_FF_EXPERIMENT")
    gen.bAsE_dIr = base
    gen.tOkEn_DiR = os.path.join(base, "TOKENS-JWT")
    gen.aCcOuNt_DiR = os.path.join(base, "ACCOUNTS")
    gen.rArE_DiR = os.path.join(base, "RARE ACCOUNTS")
    gen.cOuPlE_DiR = os.path.join(base, "COUPLES ACCOUNTS")
    for path in (gen.bAsE_dIr, gen.tOkEn_DiR, gen.aCcOuNt_DiR,
                 gen.rArE_DiR, gen.cOuPlE_DiR):
        os.makedirs(path, exist_ok=True)


def _apply_network():
    if config.NAJMI_PROXY:
        gen.tOr_sOcKs_pRoXy = config.NAJMI_PROXY
        gen.uSe_tOr_PrOxY = True
        return
    gen.TOR_SETUP_TIMEOUT = config.NAJMI_TOR_TIMEOUT
    if not config.NAJMI_USE_TOR:
        gen.uSe_tOr_PrOxY = False
        return
    if not gen.shutil.which("tor"):
        gen.uSe_tOr_PrOxY = False


def ensure_ready() -> bool:
    """Boot the engine once: paths, proxy, live config, Tor. Idempotent."""
    global _started
    with _state_lock:
        owner = not _started
        _started = True
    if not owner:
        _ready.wait(config.NAJMI_READY_TIMEOUT)
        return _ready.is_set()
    try:
        _apply_paths()
        _apply_network()
        try:
            gen.sYnC_cOnFiG()
        except Exception:
            pass
        if gen.uSe_tOr_PrOxY and not gen.sTaRt_tOr():
            gen.uSe_tOr_PrOxY = False
    finally:
        _ready.set()
    return True


def create(region: str, name_prefix: str = "") -> dict:
    """Blocking single-account creation. Returns uid/password/account_id/jwt."""
    global _last
    region = str(region).upper()
    if not supported(region):
        raise ValueError(f"region {region} not supported")
    ensure_ready()

    with _gen_lock:
        gap = config.REG_GAP - (time.time() - _last)
        if gap > 0:
            time.sleep(gap)
        _last = time.time()
        acc = gen.cReAtE_aCcOuNt(region, name_prefix or config.NAJMI_NAME_PREFIX,
                                 is_ghost=(region == gen.gHoSt_MoDe_rEgIoN))

    if not acc or not acc.get("uid"):
        raise RuntimeError("generator returned no account")
    return {
        "uid": str(acc["uid"]),
        "password": str(acc["password"]),
        "account_id": str(acc.get("account_id") or ""),
        "jwt": str(acc.get("jwt_token") or ""),
        "region": region,
        "nickname": acc.get("name") or "",
    }
