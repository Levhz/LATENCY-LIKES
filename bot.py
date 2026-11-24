import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
import guestgen
from likesvc import process_like, quota
from pool import pool, LikeError
from utils import clean_uid

REGIONS = {r.lower() for r in guestgen.gen.sUpPoRtEd_ReGiOnS}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=("!", "/"), intents=intents, help_command=None)


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


def channel_ok(channel_id: int) -> bool:
    return not config.ALLOWED_CHANNEL_IDS or channel_id in config.ALLOWED_CHANNEL_IDS


def channel_hint() -> str:
    if not config.ALLOWED_CHANNEL_IDS:
        return "Use this in the bot channel."
    return f"Use this in <#{sorted(config.ALLOWED_CHANNEL_IDS)[0]}>."


async def _like_flow(user, region: str, uid: str, amount: int):
    try:
        res = await process_like(user.id, region, uid, amount)
    except LikeError as e:
        return False, str(e)
    q = quota(user.id)
    txt = (f"**{res['nickname'] or uid}** got **{res['sent']}** likes\n"
           f"Likes: {res['before']} -> {res['after']}\n"
           f"Cost: {res['cost']} credits | Balance: {res['credits']}\n"
           f"Daily left: {q['remaining']}/{q['limit']} (resets in {q['reset_in']})")
    return True, txt


@bot.event
async def on_ready():
    print(f"logged in as {bot.user} ({bot.user.id})")
    try:
        if config.GUILD_ID:
            bot.tree.copy_global_to(guild=discord.Object(id=config.GUILD_ID))
            await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))
        else:
            await bot.tree.sync()
    except Exception as e:
        print("sync failed:", e)


@bot.command(name="like", aliases=["l"])
@commands.cooldown(1, config.CMD_COOLDOWN, commands.BucketType.user)
async def like_cmd(ctx, *args):
    if not channel_ok(ctx.channel.id) and not is_admin(ctx.author.id):
        return await ctx.reply(channel_hint())
    args = list(args)
    region = config.DEFAULT_REGION
    if args and args[0].lower() in REGIONS:
        region = args.pop(0).upper()
    if not args:
        return await ctx.reply("Usage: `!like ind <uid> [amount]`")
    uid = clean_uid(args.pop(0))
    if not uid:
        return await ctx.reply("Invalid UID.")
    try:
        amount = int(args.pop(0)) if args else 1
    except ValueError:
        return await ctx.reply("Amount must be a number.")
    ok, msg = await _like_flow(ctx.author, region, uid, amount)
    await ctx.reply(("**Success** - " if ok else "**Failed** - ") + msg)


@bot.tree.command(name="like", description="Send likes to a Free Fire profile")
@app_commands.describe(uid="Free Fire UID", amount="how many likes", region="region code")
async def like_slash(inter: discord.Interaction, uid: str, amount: int = 1,
                     region: str = config.DEFAULT_REGION):
    if not channel_ok(inter.channel_id) and not is_admin(inter.user.id):
        return await inter.response.send_message(channel_hint(), ephemeral=True)
    await inter.response.defer()
    ok, msg = await _like_flow(inter.user, region.upper(), uid, amount)
    await inter.followup.send(("**Success** - " if ok else "**Failed** - ") + msg)


@bot.command(name="balance", aliases=["bal", "credits"])
async def balance(ctx):
    u = db.ensure_user(ctx.author.id)
    q = quota(ctx.author.id)
    await ctx.reply(f"Credits: **{u['credits']}** | Today: {q['used']}/{q['limit']} "
                    f"(resets in {q['reset_in']}) | Total likes: {u['total_likes']}")


@bot.command(name="profile")
async def profile_cmd(ctx, uid: str):
    uid = clean_uid(uid)
    if not uid:
        return await ctx.reply("Invalid UID.")
    try:
        p = await pool.get_profile(uid, config.DEFAULT_REGION)
    except Exception:
        p = None
    if not p:
        return await ctx.reply("Could not fetch that profile. Try again in a moment.")
    await ctx.reply(f"**{p['nickname']}** | Level {p['level']} | Likes {p['likes']}")


@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="FF Like Bot", color=0x00c2ff)
    e.add_field(name="Commands", value=(
        "`!like ind <uid> [amount]` - send likes\n"
        "`!balance` - credits and daily quota\n"
        "`!profile <uid>` - view a profile\n"
        "`!help` - this list"), inline=False)
    if is_admin(ctx.author.id):
        e.add_field(name="Admin", value=(
            "`!addcredits @user <amt>` / `!removecredits` / `!setcredits`\n"
            "`!ban @user` / `!unban @user`\n"
            "`!apion` / `!apioff` / `!maintenance <msg>`\n"
            "`!refill <n>` / `!pool` / `!stats`"), inline=False)
    await ctx.reply(embed=e)


def _target_id(raw: str):
    if raw.startswith("<@") and raw.endswith(">"):
        raw = raw.strip("<@!>")
    return int(raw) if raw.isdigit() else None


@bot.command(name="addcredits", aliases=["give"])
async def addcredits(ctx, member: str, amount: int):
    if not is_admin(ctx.author.id):
        return
    tid = _target_id(member)
    if not tid:
        return await ctx.reply("Give a user mention or ID.")
    await ctx.reply(f"Added {amount} to <@{tid}>. Balance: **{db.add_credits(tid, amount)}**")


@bot.command(name="removecredits", aliases=["take"])
async def removecredits(ctx, member: str, amount: int):
    if not is_admin(ctx.author.id):
        return
    tid = _target_id(member)
    if not tid:
        return await ctx.reply("Give a user mention or ID.")
    await ctx.reply(f"Removed {amount} from <@{tid}>. Balance: **{db.add_credits(tid, -amount)}**")


@bot.command(name="setcredits")
async def setcredits(ctx, member: str, amount: int):
    if not is_admin(ctx.author.id):
        return
    tid = _target_id(member)
    if not tid:
        return await ctx.reply("Give a user mention or ID.")
    await ctx.reply(f"Set <@{tid}> balance to **{db.set_credits(tid, amount)}**")


@bot.command(name="ban")
async def ban(ctx, member: str):
    if not is_admin(ctx.author.id):
        return
    tid = _target_id(member)
    if tid:
        db.set_banned(tid, True)
        await ctx.reply(f"Banned <@{tid}>.")


@bot.command(name="unban")
async def unban(ctx, member: str):
    if not is_admin(ctx.author.id):
        return
    tid = _target_id(member)
    if tid:
        db.set_banned(tid, False)
        await ctx.reply(f"Unbanned <@{tid}>.")


@bot.command(name="apion")
async def apion(ctx):
    if not is_admin(ctx.author.id):
        return
    db.set_setting("api_enabled", "1")
    await ctx.reply("API is now ON.")


@bot.command(name="apioff")
async def apioff(ctx):
    if not is_admin(ctx.author.id):
        return
    db.set_setting("api_enabled", "0")
    await ctx.reply("API is now OFF.")


@bot.command(name="maintenance")
async def maintenance(ctx, *, msg: str = ""):
    if not is_admin(ctx.author.id):
        return
    db.set_setting("maintenance_msg", msg)
    await ctx.reply(f"Maintenance message set: `{msg}`")


@bot.command(name="refill")
async def refill(ctx, count: int = 3):
    if not is_admin(ctx.author.id):
        return
    await pool.warm(min(20, max(1, count)))
    await ctx.reply(f"{count} account(s) queued for generation.")


@bot.command(name="pool")
async def pool_cmd(ctx):
    if not is_admin(ctx.author.id):
        return
    c = db.pool_counts()
    await ctx.reply(f"ready={c.get('ready',0)} busy={c.get('busy',0)} "
                    f"new={c.get('new',0)} dead={c.get('dead',0)}")


@bot.command(name="stats")
async def stats_cmd(ctx):
    if not is_admin(ctx.author.id):
        return
    s = db.stats()
    await ctx.reply(f"users={s['users']} total_likes={s['total_likes']} today={s['today_likes']}")


@like_cmd.error
async def like_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"Slow down, wait {error.retry_after:.1f}s.")


async def run_bot():
    async with bot:
        await bot.start(config.BOT_TOKEN)
