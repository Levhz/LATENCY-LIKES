# FF Like API

Free Fire guest account generator + like API + Discord bot + admin panel.
Built entirely on the **NAJMI FF EXPERIMENT** generator.

## Credits

Generator engine: **NAJMI FF EXPERIMENT** — owner `NAJMI_ADMIN`, developer `NAJMI FF EXPERIMENT`.
`najmi_gen.py` ships unmodified. Integration, client, API, bot and panel are this repo.

## Features

- Guest accounts auto-generate on demand (multi-region, Tor-rotated)
- Accounts get a region-bound JWT via the Activator API
- `!like ind <uid> <amt>` / `/like` slash command
- Credits per command, daily likes cap per user
- Admin credits / ban / pool control
- Web panel for API on/off, pricing, pool, logs
- Channel-locked commands, admin bypass

## Local setup

```
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # values bhar
python run.py
```

Panel: http://localhost:8000 — `.env` ka `ADMIN_TOKEN` password hai.
Tor optional locally; absent hone par direct chalta hai.

## Generator akela chalana

```
python najmi_gen.py
```

Interactive menu. Regions: ME, IND, ID, VN, TH, BD, PK, TW, CIS, SAC, BR (BR = ghost, no token).

## Render deploy

1. Render → New → Blueprint → repo select.
2. `ff-like-secrets` env group: `BOT_TOKEN`, `ADMIN_IDS`, `ALLOWED_CHANNEL_IDS`, `ADMIN_TOKEN`, `API_KEY`.
3. Disk `/data` (Starter). Free plan par `NAJMI_USE_TOR=0` set kar.
4. Deploy ke baad `/` panel, bot same process me chalega.
5. UptimeRobot se `/health` ping kar.

## Bot invite

OAuth2 → scopes `bot applications.commands`, permissions: Send Messages, Embed Links, Read Message History.

## API (X-API-Key header)

```
GET  /api/status
GET  /api/profile/<uid>?region=ind
POST /api/like  {"uid":"123","amount":5,"region":"ind","discord_id":111}
```

## Commands

| cmd | kaam |
| --- | --- |
| `!like ind <uid> [amt]` | likes |
| `!balance` / `!profile <uid>` | info |
| `!addcredits @u <n>` `!removecredits` `!setcredits` | admin credits |
| `!ban` / `!unban` | access |
| `!apion` / `!apioff` / `!maintenance <msg>` | toggle |
| `!refill <n>` / `!pool` / `!stats` | pool |
