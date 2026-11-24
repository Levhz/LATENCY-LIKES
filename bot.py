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


async def admin_gate(inter: discord.Interaction) -> bool:
    if not is_admin(inter.user.id):
        await inter.response.send_message(
            f"Admin only. Your ID: `{inter.user.id}`", ephemeral=True)
        return False
    return True


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
        print(f"commands synced: {len(bot.tree.get_commands())}")
    except Exception as e:
        print("sync failed:", e)


# ---------------------------------------------------------------- user commands

@bot.command(name="like", aliases=["l"])
@commands.cooldown(1, config.CMD_COOLDOWN, commands.BucketType.user)
async def like_cmd(ctx, *args):
    if not channel_ok(ctx.channel.id) and not is_admin(ctx.author.id):
        return await ctx.reply(channel_hint())

    args = list(args)
    if not args:
        return await ctx.reply("Usage: `!like [region] <uid> [amount]`\n"
                               f"Example: `!like ind {clean_uid('123456789') or '123456789'} 5`")

    region = config.DEFAULT_REGION
    if len(args) >= 2 and args[0].lower() in REGIONS:
        region = args.pop(0).upper()

    uid = clean_uid(args.pop(0)) if args else None
    if not uid:
        return await ctx.reply("Invalid UID. Digits only, 5-12 long.")

    amount = 1
    if args:
        raw = args.pop(0).lstrip("+")
        if not raw.isdigit() or int(raw) < 1:
            return await ctx.reply("Amount must be a positive number.")
        amount = int(raw)

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


@bot.tree.command(name="balance", description="Your credits and daily quota")
async def balance_slash(inter: discord.Interaction):
    u = db.ensure_user(inter.user.id)
    q = quota(inter.user.id)
    await inter.response.send_message(
        f"Credits: **{u['credits']}** | Today: {q['used']}/{q['limit']} "
        f"(resets in {q['reset_in']}) | Total likes: {u['total_likes']}", ephemeral=True)


@bot.tree.command(name="whoami", description="Show the Discord ID the bot bills you on")
async def whoami(inter: discord.Interaction):
    u = db.ensure_user(inter.user.id)
    await inter.response.send_message(
        f"Your ID: `{inter.user.id}`\nCredits: **{u['credits']}**\n"
        f"Admin: {'yes' if is_admin(inter.user.id) else 'no'}", ephemeral=True)


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


@bot.tree.command(name="profile", description="View a Free Fire profile")
@app_commands.describe(uid="Free Fire UID", region="region code")
async def profile_slash(inter: discord.Interaction, uid: str,
                        region: str = config.DEFAULT_REGION):
    uid = clean_uid(uid)
    if not uid:
        return await inter.response.send_message("Invalid UID.", ephemeral=True)
    await inter.response.defer()
    try:
        p = await pool.get_profile(uid, region.upper())
    except Exception:
        p = None
    if not p:
        return await inter.followup.send("Could not fetch that profile. Try again.")
    await inter.followup.send(f"**{p['nickname']}** | Level {p['level']} | Likes {p['likes']}")


@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="FF Like Bot", color=0x00c2ff)
    e.add_field(name="Commands", value=(
        "`!like [region] <uid> [amount]` - send likes\n"
        "`!balance` - credits and daily quota\n"
        "`!profile <uid>` - view a profile\n"
        "`!whoami` - your billed ID\n"
        "`!help` - this list"), inline=False)
    if is_admin(ctx.author.id):
        e.add_field(name="Admin", value=(
            "`/admin addcredits` `/admin removecredits` `/admin setcredits`\n"
            "`/admin ban` `/admin unban`\n"
            "`/admin apion` `/admin apioff` `/admin maintenance`\n"
            "`/admin refill` `/admin pool` `/admin stats`\n"
            "Prefix: `!addcredits @u <n>` `!removecredits` `!setcredits` "
            "`!ban` `!unban` `!refill` `!pool` `!stats`"), inline=False)
    await ctx.reply(embed=e)


# ---------------------------------------------------------------- admin group

admin = app_commands.Group(name="admin", description="Admin only",
                           default_permissions=discord.Permissions(manage_guild=True))


@admin.command(name="addcredits", description="Add credits to a user")
@app_commands.describe(member="target user", amount="credits to add")
async def a_addcredits(inter: discord.Interaction, member: discord.Member, amount: int):
    if not await admin_gate(inter):
        return
    bal = db.add_credits(member.id, abs(amount))
    await inter.response.send_message(
        f"Added {abs(amount)} to {member.mention}. Balance: **{bal}**", ephemeral=True)


@admin.command(name="removecredits", description="Remove credits from a user")
@app_commands.describe(member="target user", amount="credits to remove")
async def a_removecredits(inter: discord.Interaction, member: discord.Member, amount: int):
    if not await admin_gate(inter):
        return
    bal = db.add_credits(member.id, -abs(amount))
    await inter.response.send_message(
        f"Removed {abs(amount)} from {member.mention}. Balance: **{bal}**", ephemeral=True)


@admin.command(name="setcredits", description="Set a user's balance exactly")
@app_commands.describe(member="target user", amount="new balance")
async def a_setcredits(inter: discord.Interaction, member: discord.Member, amount: int):
    if not await admin_gate(inter):
        return
    bal = db.set_credits(member.id, amount)
    await inter.response.send_message(
        f"Set {member.mention} to **{bal}**", ephemeral=True)


@admin.command(name="ban", description="Block a user from the API")
@app_commands.describe(member="target user")
async def a_ban(inter: discord.Interaction, member: discord.Member):
    if not await admin_gate(inter):
        return
    db.set_banned(member.id, True)
    await inter.response.send_message(f"Banned {member.mention}.", ephemeral=True)


@admin.command(name="unban", description="Unblock a user")
@app_commands.describe(member="target user")
async def a_unban(inter: discord.Interaction, member: discord.Member):
    if not await admin_gate(inter):
        return
    db.set_banned(member.id, False)
    await inter.response.send_message(f"Unbanned {member.mention}.", ephemeral=True)


@admin.command(name="apion", description="Turn the like API on")
async def a_apion(inter: discord.Interaction):
    if not await admin_gate(inter):
        return
    db.set_setting("api_enabled", "1")
    await inter.response.send_message("API is now ON.", ephemeral=True)


@admin.command(name="apioff", description="Turn the like API off")
async def a_apioff(inter: discord.Interaction):
    if not await admin_gate(inter):
        return
    db.set_setting("api_enabled", "0")
    await inter.response.send_message("API is now OFF.", ephemeral=True)


@admin.command(name="maintenance", description="Set the maintenance message")
@app_commands.describe(message="message shown while API is off, empty to clear")
async def a_maintenance(inter: discord.Interaction, message: str = ""):
    if not await admin_gate(inter):
        return
    db.set_setting("maintenance_msg", message)
    await inter.response.send_message(f"Maintenance message: `{message}`", ephemeral=True)


@admin.command(name="refill", description="Queue guest accounts for generation")
@app_commands.describe(count="how many to queue (max 20)")
async def a_refill(inter: discord.Interaction, count: int = 3):
    if not await admin_gate(inter):
        return
    await pool.warm(min(20, max(1, count)))
    await inter.response.send_message(f"{count} account(s) queued.", ephemeral=True)


@admin.command(name="pool", description="Pool counts")
async def a_pool(inter: discord.Interaction):
    if not await admin_gate(inter):
        return
    c = db.pool_counts()
    await inter.response.send_message(
        f"ready={c.get('ready',0)} busy={c.get('busy',0)} "
        f"new={c.get('new',0)} dead={c.get('dead',0)}", ephemeral=True)


@admin.command(name="stats", description="Bot stats")
async def a_stats(inter: discord.Interaction):
    if not await admin_gate(inter):
        return
    s = db.stats()
    await inter.response.send_message(
        f"users={s['users']} total_likes={s['total_likes']} today={s['today_likes']}",
        ephemeral=True)


bot.tree.add_command(admin)


# ---------------------------------------------------------------- prefix admin

def _target_id(raw: str):
    if raw.startswith("<@") and raw.endswith(">"):
        raw = raw.strip("<@!>")
    return int(raw) if raw.isdigit() else None


@bot.command(name="addcredits", aliases=["give"])
async def addcredits(ctx, member: str, amount: int):
    if not is_admin(ctx.author.id):
        return await ctx.reply(f"Admin only. Your ID: `{ctx.author.id}`")
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


@bot.command(name="whoami")
async def whoami_cmd(ctx):
    u = db.ensure_user(ctx.author.id)
    await ctx.reply(f"Your ID: `{ctx.author.id}` | Credits: **{u['credits']}**")


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


# ---------------------------------------------------------------- errors

@like_cmd.error
async def like_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"Slow down, wait {error.retry_after:.1f}s.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.reply(f"Slow down, wait {error.retry_after:.1f}s.")
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.reply(f"Missing argument: `{error.param.name}`. Try `!help`.")
    if isinstance(error, commands.BadArgument):
        return await ctx.reply("Bad argument. Check `!help`.")


async def run_bot():
    async with bot:
        await bot.start(config.BOT_TOKEN)
