# bot.py - Ultimate Merged LegendBot (Python version)
# Features: Voice study tracking (cam on/off), leaderboards, anti-nuke, anti-spam, TODO, redlist, admin tools
# Requirements: pip install discord.py python-dotenv pymongo aiohttp pytz croniter

import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import asyncio
import time
import datetime
from datetime import timedelta
import pytz
from collections import defaultdict
import aiohttp
from aiohttp import web
import pymongo
from pymongo import MongoClient
from dotenv import load_dotenv

# ==================== CONFIG ====================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # optional if global commands
MONGODB_URI = os.getenv("MONGODB_URI")      # mongodb+srv://...
OWNER_ID = 1406313503278764174

KOLKATA = pytz.timezone("Asia/Kolkata")
AUTO_LB_CHANNEL_ID = 1455385042044846242
TODO_CHANNEL_ID = 1458400694682783775
ROLE_TO_REMOVE_AFTER_5DAYS = 1458400797133115474

# Keep-alive port (for render.com / justrunmy.app / railway)
PORT = int(os.getenv("PORT", 3000))

# ==================== DATABASE (MongoDB Atlas) ====================
client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=30000,
    tls=True
)

db = client["legend_star"]
print("✅ MongoDB connected")
  # uses database name from URI

users_coll = db["users"]           # study time
todo_coll = db["todo_timestamps"]  # last todo submission time
redlist_coll = db["redlist"]       # redlisted user IDs

def init_db():
    # Create indexes if needed
    users_coll.create_index("_id", unique=True)
    todo_coll.create_index("_id", unique=True)
    redlist_coll.create_index("_id", unique=True)

init_db()

# ==================== BOT SETUP ====================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# In-memory helpers
spam_cache = defaultdict(list)
strike_cache = defaultdict(list)
vc_join_times = {}          # {user_id: join_timestamp}
cam_timers = {}             # {user_id: {"warning": task, "kick": task}}

# ==================== KEEP-ALIVE SERVER ====================
async def handle(request):
    return web.Response(text="LegendBot is Online! 🦚")

app = web.Application()
app.router.add_get('/', handle)

# ==================== UTILS ====================
def format_time(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h}h {m}m"

def is_strict_channel(channel_id: int, channel_name: str) -> bool:
    target_ids = ["1428762702414872636", "1455906399262605457", "1455582132218106151", "1428762820585062522"]
    return str(channel_id) in target_ids or "Cam On" in channel_name

# ==================== STUDY TRACKING ====================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.bot:
        return

    user_id = str(member.id)
    now = time.time()

    old_in = bool(before.channel)
    new_in = bool(after.channel)
    old_cam = before.self_video or before.streaming
    new_cam = after.self_video or after.streaming

    # User joined voice
    if not old_in and new_in:
        vc_join_times[member.id] = now

    # User left voice or cam changed → save session
    if (old_in and not new_in) or (old_in and new_in and old_cam != new_cam):
        if member.id in vc_join_times:
            duration_sec = now - vc_join_times[member.id]
            duration_min = int(duration_sec // 60)
            if duration_min > 0:
                field = "voice_cam_on_minutes" if old_cam else "voice_cam_off_minutes"
                users_coll.update_one(
                    {"_id": user_id},
                    {"$inc": {field: duration_min}},
                    upsert=True
                )
            del vc_join_times[member.id]

    # Periodic batch save (every 2 min) - for long sessions
    # (handled in separate task)

# Batch save every 2 minutes
@tasks.loop(minutes=2)
async def batch_save_study():
    now = time.time()
    for member_id, join_time in list(vc_join_times.items()):
        member = bot.get_user(member_id)
        if not member:
            continue
        voice = member.voice
        if not voice or not voice.channel:
            continue

        duration_min = int((now - join_time) // 60)
        if duration_min > 0:
            cam_on = voice.self_video or voice.streaming
            field = "voice_cam_on_minutes" if cam_on else "voice_cam_off_minutes"
            users_coll.update_one(
                {"_id": str(member_id)},
                {"$inc": {field: duration_min}},
                upsert=True
            )
            vc_join_times[member_id] = now  # reset timer

# ==================== DAILY AUTO LEADERBOARD + RESET ====================
@tasks.loop(time=datetime.time(23, 55, tzinfo=KOLKATA))
async def auto_leaderboard():
    channel = bot.get_channel(AUTO_LB_CHANNEL_ID)
    if not channel:
        return

    # Get all users with data
    all_users = list(users_coll.find())
    active = []

    guild = channel.guild
    for doc in all_users:
        uid = int(doc["_id"])
        try:
            member = await guild.fetch_member(uid)
            active.append({
                "name": member.display_name,
                "cam_on": doc.get("voice_cam_on_minutes", 0),
                "cam_off": doc.get("voice_cam_off_minutes", 0)
            })
        except:
            pass

    sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
    sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]

    desc = "**Cam On ✅**\n"
    if not sorted_on:
        desc += "No active study data today.\n"
    for i, u in enumerate(sorted_on, 1):
        if u["cam_on"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_on'])}\n"

    desc += "\n**Cam Off ❌**\n"
    for i, u in enumerate(sorted_off, 1):
        if u["cam_off"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_off'])}\n"

    embed = discord.Embed(
        title="🌙 Daily Final Leaderboard",
        description=desc,
        color=0x00FF00,
        timestamp=datetime.datetime.now(KOLKATA)
    )
    embed.set_footer(text="Auto-Generated at 11:55 PM IST")

    await channel.send(embed=embed)

@tasks.loop(time=datetime.time(0, 0, tzinfo=KOLKATA))
async def midnight_reset():
    # Archive to yesterday and reset today
    for doc in users_coll.find():
        on = doc.get("voice_cam_on_minutes", 0)
        off = doc.get("voice_cam_off_minutes", 0)
        users_coll.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "yesterday.cam_on": on,
                    "yesterday.cam_off": off,
                    "voice_cam_on_minutes": 0,
                    "voice_cam_off_minutes": 0
                }
            }
        )
    print("🕛 Midnight reset complete")

# ==================== LEADERBOARD COMMANDS ====================
@tree.command(name="lb", description="View today's study leaderboard")
async def lb(interaction: discord.Interaction):
    await interaction.response.defer()

    all_users = list(users_coll.find())
    active = []

    for doc in all_users:
        try:
            member = await interaction.guild.fetch_member(int(doc["_id"]))
            active.append({
                "name": member.display_name,
                "cam_on": doc.get("voice_cam_on_minutes", 0),
                "cam_off": doc.get("voice_cam_off_minutes", 0)
            })
        except:
            pass

    sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
    sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]

    desc = "**Cam On ✅**\n"
    if not sorted_on:
        desc += "No active members yet.\n"
    for i, u in enumerate(sorted_on, 1):
        if u["cam_on"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_on'])}\n"

    desc += "\n**Cam Off ❌**\n"
    for i, u in enumerate(sorted_off, 1):
        if u["cam_off"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_off'])}\n"

    embed = discord.Embed(title="🏆 Study Leaderboard", description=desc, color=0xFFD700)
    await interaction.followup.send(embed=embed)

@tree.command(name="ylb", description="View yesterday's leaderboard")
async def ylb(interaction: discord.Interaction):
    await interaction.response.defer()

    all_users = list(users_coll.find({"yesterday": {"$exists": True}}))
    active = []

    for doc in all_users:
        y = doc.get("yesterday", {})
        if y.get("cam_on", 0) == 0 and y.get("cam_off", 0) == 0:
            continue
        try:
            member = await interaction.guild.fetch_member(int(doc["_id"]))
            active.append({
                "name": member.display_name,
                "cam_on": y.get("cam_on", 0),
                "cam_off": y.get("cam_off", 0)
            })
        except:
            pass

    sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
    sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]

    desc = "**Yesterday's Cam On ✅**\n"
    if not sorted_on:
        desc += "No data for yesterday.\n"
    for i, u in enumerate(sorted_on, 1):
        if u["cam_on"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_on'])}\n"

    desc += "\n**Yesterday's Cam Off ❌**\n"
    for i, u in enumerate(sorted_off, 1):
        if u["cam_off"] > 0:
            desc += f"#{i} **{u['name']}** — {format_time(u['cam_off'])}\n"

    embed = discord.Embed(title="⏮️ Yesterday's Leaderboard", description=desc, color=0xA9A9A9)
    await interaction.followup.send(embed=embed)

@tree.command(name="mystatus", description="Your study stats")
async def mystatus(interaction: discord.Interaction):
    doc = users_coll.find_one({"_id": str(interaction.user.id)})
    if not doc:
        return await interaction.response.send_message("You haven't studied yet!", ephemeral=True)

    on = doc.get("voice_cam_on_minutes", 0)
    off = doc.get("voice_cam_off_minutes", 0)
    total = on + off

    embed = discord.Embed(
        title=f"📊 Stats for {interaction.user.name}",
        color=0x9932CC
    )
    embed.add_field(name="Total", value=format_time(total), inline=True)
    embed.add_field(name="Cam On", value=format_time(on), inline=True)
    embed.add_field(name="Cam Off", value=format_time(off), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="yst", description="Yesterday's personal stats")
async def yst(interaction: discord.Interaction):
    doc = users_coll.find_one({"_id": str(interaction.user.id)})
    if not doc or "yesterday" not in doc:
        return await interaction.response.send_message("No data for yesterday yet.", ephemeral=True)

    y = doc["yesterday"]
    on = y.get("cam_on", 0)
    off = y.get("cam_off", 0)
    total = on + off

    embed = discord.Embed(
        title=f"🗓️ Yesterday's Stats: {interaction.user.name}",
        color=0x808080
    )
    embed.add_field(name="Total", value=format_time(total), inline=True)
    embed.add_field(name="Cam On", value=format_time(on), inline=True)
    embed.add_field(name="Cam Off", value=format_time(off), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== REDLIST & AUTO-BAN ====================
@tree.command(name="redban", description="Owner: Add user to redlist & auto-ban")
@app_commands.describe(userid="User ID")
async def redban(interaction: discord.Interaction, userid: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    if not userid.isdigit():
        return await interaction.response.send_message("Invalid ID", ephemeral=True)

    redlist_coll.update_one({"_id": userid}, {"$set": {"added": datetime.datetime.now(KOLKATA)}}, upsert=True)
    await interaction.response.send_message(f"Added {userid} to redlist.", ephemeral=True)

    try:
        await interaction.guild.ban(discord.Object(id=int(userid)), reason="Redlist")
    except:
        pass

@bot.event
async def on_member_join(member):
    if redlist_coll.find_one({"_id": str(member.id)}):
        try:
            await member.ban(reason="Redlist")
        except:
            pass

# ==================== TODO SYSTEM (simplified) ====================
@tree.command(name="todo", description="Submit your daily todo")
async def todo(interaction: discord.Interaction):
    # You can expand this with Modal like in your original code
    # For brevity, just update timestamp
    todo_coll.update_one(
        {"_id": str(interaction.user.id)},
        {"$set": {"last_submit": time.time()}},
        upsert=True
    )
    await interaction.response.send_message("✅ Todo timestamp updated!", ephemeral=True)

@tasks.loop(hours=1)
async def todo_checker():
    channel = bot.get_channel(TODO_CHANNEL_ID)
    if not channel:
        return

    now = time.time()
    for doc in todo_coll.find():
        uid = int(doc["_id"])
        last = doc.get("last_submit", 0)
        elapsed = now - last

        member = channel.guild.get_member(uid)
        if not member:
            continue

        if elapsed >= 5 * 86400:  # 5 days
            role = channel.guild.get_role(ROLE_TO_REMOVE_AFTER_5DAYS)
            if role and role in member.roles:
                await member.remove_roles(role)

        if elapsed >= 86400:  # 24h
            await channel.send(f"{member.mention} ⏰ TODO pending! Last: {elapsed//3600}h ago")

# ==================== ANTI-NUKE / ANTI-SPAM (merged from main.py & main2.py) ====================
@bot.event
async def on_message(message):
    if message.author.bot or message.author.id == OWNER_ID:
        return await bot.process_commands(message)

    # Malware check
    if message.attachments:
        for att in message.attachments:
            fn = att.filename.lower()
            if fn.endswith(('.exe','.bat','.scr','.cmd','.js','.vbs','.jar','.apk')):
                await message.delete()
                await message.author.ban(reason="Malware upload")
                return

    # Spam / mass mention
    if len(message.mentions) > 5 or message.mention_everyone:
        await message.delete()
        await message.channel.send(f"{message.author.mention} Stop spamming.", delete_after=10)
        # You can add strike system here like in original

    await bot.process_commands(message)

# ==================== OWNER ADMIN COMMANDS (simplified) ====================
@tree.command(name="msz", description="Owner: Send server announcement")
@app_commands.describe(channel="Target channel", message="Content")
async def msz(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)
    await channel.send(f"**Server Announcement**\n{message}")
    await interaction.response.send_message("Sent!", ephemeral=True)

# Add more like /mz, /ud, /bn as needed...

# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

    batch_save_study.start()
    auto_leaderboard.start()
    midnight_reset.start()
    todo_checker.start()

# ==================== RUN ====================
async def start_web():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"Keep-alive server running on port {PORT}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_web())
    bot.run(TOKEN)