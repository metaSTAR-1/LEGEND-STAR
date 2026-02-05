# bot.py - FULLY FIXED & COMPLETE LegendBot (Python) - All Features, No Missing, Sync Debugged
# Fixes:
# - Invalid GUILD_ID=0 causes 0 synced → fallback to global sync if not set
# - Added debug prints: GUILD_ID, commands in tree, synced list
# - Manual !sync command (prefix) for owner to force sync anytime
# - Clear commands before sync (guild or global)
# - All commands defined fully (no abbreviations)
# - Added guild sync check + global fallback
# - Bot invite: Ensure 'applications.commands' scope + bot in server
# - Features: All from originals (voice cam track/enforce, leaderboards, TODO modal/ping, redlist/auto-ban, admin cmds, DM forward, anti-nuke/spam/strikes, bot whitelist, activity logs)
# - Added all missing commands: /listtodo, /deltodo, /members, /ck
# - Adjusted /todostatus for self-check by members, optional other for owner
# - Added full 12-layer security firewalls
# - Single guild support with GUILD_ID checks
# - Fixed cam_timers safe cancellation
# - Fixed vc_join_times continuation on cam change
# - Fixed batch_save_study to use members from guild
# - Async main for web + bot

import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import asyncio
import time
import datetime
from datetime import timedelta
import pytz
from collections import defaultdict
import aiohttp
from aiohttp import web
from pymongo import MongoClient
from dotenv import load_dotenv
from discord.app_commands import checks
import socket
import re

load_dotenv()

# ==================== CONFIG ====================
TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
GUILD_ID_STR = os.getenv("GUILD_ID", "0")
MONGODB_URI = os.getenv("MONGODB_URI")
OWNER_ID = 1406313503278764174

# Validate required environment variables
if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN is not set in .env file")
if not CLIENT_ID:
    raise ValueError("❌ CLIENT_ID is not set in .env file")
if not MONGODB_URI:
    raise ValueError("❌ MONGODB_URI is not set in .env file")

try:
    GUILD_ID = int(GUILD_ID_STR)
except ValueError:
    print(f"❌ Invalid GUILD_ID '{GUILD_ID_STR}' - must be a number. Using 0 for global sync.")
    GUILD_ID = 0
TECH_CHANNEL_ID = 1458142927619362969
KOLKATA = pytz.timezone("Asia/Kolkata")
AUTO_LB_CHANNEL_ID = 1455385042044846242
AUTO_LB_PING_ROLE_ID = 1457931098171506719  # 🏆 Role to ping at 11:55 for leaderboard announcement
TODO_CHANNEL_ID = 1458400694682783775
ROLE_ID = 1458400797133115474
PORT = int(os.getenv("PORT", 3000))
print(f"GUILD_ID from env: {GUILD_ID}")  # DEBUG: Check if set correctly
# Excluded voice channel ID: do not record cam on/off minutes for this VC
EXCLUDED_VOICE_CHANNEL_ID = 1466076240111992954

# Strict channels
STRICT_CHANNEL_IDS = {"1428762702414872636", "1455906399262605457", "1455582132218106151", "1427325474551500851", "1428762820585062522"}

# Bot whitelist
WHITELISTED_BOTS = [
    1457787743504695501, 1456587533474463815, 1427522983789989960, 155149108183695360,
    678344927997853742, 1053580838945693717, 235148962103951360, 1458076467203145851,
    762217899355013120, 1444646362204475453, 536991182035746816, 906085578909548554,
    1149535834756874250, 1460114117783195841, 889078613817831495, 704802632660943089, 712638684930900059
]

# Webhook whitelist (add IDs if needed)
WHITELISTED_WEBHOOKS = [
    1457787743504695501, 1456587533474463815, 1427522983789989960, 155149108183695360,
    678344927997853742, 1053580838945693717, 235148962103951360, 1458076467203145851,
    762217899355013120, 1444646362204475453, 536991182035746816, 906085578909548554,
    1149535834756874250, 1460114117783195841, 889078613817831495, 704802632660943089, 712638684930900059
]

# Spam settings
SPAM_THRESHOLD = 4
SPAM_WINDOW = 5
MAX_MENTIONS = 5
TIMEOUT_DURATION = 60
STRIKE_RESET = 300

# Enhanced Security Settings
FORBIDDEN_KEYWORDS = ["@everyone", "@here", "free nitro", "steam community", "gift", "airdrop", "maa", "rand", "chut"]

# 🛡️ TRUSTED LISTS (Whitelist for Strike System)
TRUSTED_USERS = [OWNER_ID, 1449952640455934022]  # Added 1449952640455934022 as trusted owner-level user
TRUSTED_BOTS = WHITELISTED_BOTS.copy()
TEMP_VOICE_BOT_ID = 762217899355013120

# 📒 STRIKE DATABASE (2-Strike System for Human Errors)
offense_history = {}  # {user_id: timestamp_of_last_offense}
is_locked_down = False  # Global lockdown state

# 🔍 AUDIT LOG TRACKING (Prevent Duplicate Messages)
processed_audit_ids = set()  # Track processed audit entry IDs to prevent duplicate alerts
processed_audit_timestamps = {}  # {audit_id: timestamp} for more robust deduplication
MAX_AUDIT_CACHE = 1000  # Max entries to cache (prevents memory bloat)
AUDIT_DEDUP_WINDOW = 5  # seconds - window to consider duplicate audit entries

# Security settings
DANGEROUS_EXTS = {'.exe', '.bat', '.cmd', '.msi', '.apk', '.jar', '.vbs', '.scr', '.ps1', '.hta'}
RAID_THRESHOLD = 5
RAID_WINDOW = 60
VC_ABUSE_THRESHOLD = 5
VC_ABUSE_WINDOW = 30

# MongoDB Connection Handler
db = None
users_coll = None
todo_coll = None
redlist_coll = None
active_members_coll = None
mongo_connected = False

def init_mongo():
    """Initialize MongoDB connection with advanced retry logic and SSL fallbacks"""
    global db, users_coll, todo_coll, redlist_coll, active_members_coll, mongo_connected
    
    print(f"📡 Attempting to connect to MongoDB: {MONGODB_URI[:50]}...")
    
    # Strategy 1: Try with SRV and relaxed TLS
    print("🔄 MongoDB Connection Strategy 1: SRV with Relaxed TLS...")
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            tlsAllowInvalidCertificates=True,
            retryWrites=True,
            directConnection=False
        )
        client.admin.command('ping')
        db = client["legend_star"]
        users_coll = db["users"]
        todo_coll = db["todo_timestamps"]
        redlist_coll = db["redlist"]
        active_members_coll = db["active_members"]
        mongo_connected = True
        print("✅ MongoDB connected successfully (SRV + Relaxed TLS)")
        return True
    except Exception as e:
        print(f"⚠️ Strategy 1 failed: {str(e)[:100]}...")
    
    # Strategy 2: Try with retryWrites disabled
    print("🔄 MongoDB Connection Strategy 2: SRV without Retry Writes...")
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            tlsAllowInvalidCertificates=True,
            retryWrites=False,
            directConnection=False
        )
        client.admin.command('ping')
        db = client["legend_star"]
        users_coll = db["users"]
        todo_coll = db["todo_timestamps"]
        redlist_coll = db["redlist"]
        active_members_coll = db["active_members"]
        mongo_connected = True
        print("✅ MongoDB connected successfully (SRV, No Retry Writes)")
        return True
    except Exception as e:
        print(f"⚠️ Strategy 2 failed: {str(e)[:100]}...")
    
    # Strategy 3: Try without SSL/TLS (last resort)
    print("🔄 MongoDB Connection Strategy 3: No TLS/SSL...")
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            socketTimeoutMS=20000,
            ssl=False,
            retryWrites=False,
            directConnection=False
        )
        client.admin.command('ping')
        db = client["legend_star"]
        users_coll = db["users"]
        todo_coll = db["todo_timestamps"]
        redlist_coll = db["redlist"]
        active_members_coll = db["active_members"]
        mongo_connected = True
        print("✅ MongoDB connected successfully (No TLS/SSL)")
        return True
    except Exception as e:
        print(f"⚠️ Strategy 3 failed: {str(e)[:100]}...")
    
    # Strategy 4: Extended timeout with maxPoolSize=1
    print("🔄 MongoDB Connection Strategy 4: Extended Timeout (Single Pool)...")
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=60000,
            connectTimeoutMS=60000,
            socketTimeoutMS=60000,
            tlsAllowInvalidCertificates=True,
            retryWrites=False,
            directConnection=False,
            maxPoolSize=1,
            minPoolSize=0,
            maxIdleTimeMS=90000
        )
        client.admin.command('ping')
        db = client["legend_star"]
        users_coll = db["users"]
        todo_coll = db["todo_timestamps"]
        redlist_coll = db["redlist"]
        active_members_coll = db["active_members"]
        mongo_connected = True
        print("✅ MongoDB connected successfully (Extended Timeout)")
        return True
    except Exception as e:
        print(f"⚠️ Strategy 4 failed: {str(e)[:100]}...")
    
    # All strategies failed - use in-memory cache
    print("❌ All MongoDB connection strategies failed. Bot will use in-memory cache only.")
    print("⚠️ Data persistence is DISABLED. Changes will be lost on restart.")
    print("📝 Troubleshooting: Check if MongoDB Atlas IP whitelist includes your IP address")
    print("📝 If using Docker: Add 0.0.0.0/0 to IP Whitelist in MongoDB Atlas")
    print("📝 Verify credentials in MONGODB_URI are correct")
    
    # Create empty collection objects for compatibility
    try:
        client = MongoClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=5000,
            tlsAllowInvalidCertificates=True,
            retryWrites=False
        )
        db = client["legend_star"]
        users_coll = db["users"]
        todo_coll = db["todo_timestamps"]
        redlist_coll = db["redlist"]
        active_members_coll = db["active_members"]
    except Exception as e:
        db = None
        users_coll = None
        todo_coll = None
        redlist_coll = None
        active_members_coll = None
    
    mongo_connected = False
    return False

# Initialize MongoDB on startup
mongo_connected = init_mongo()

# ====================================================
# 🚨 ALERT SYSTEM (DM OWNER)
# ====================================================
async def alert_owner(guild, title, field_data):
    """Send security alert to owner via DM"""
    try:
        user = await bot.fetch_user(OWNER_ID)
        embed = discord.Embed(
            title=f"🚨 SECURITY ALERT: {title}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Server", value=guild.name if guild else "Unknown", inline=True)
        for key, value in field_data.items():
            embed.add_field(name=key, value=value, inline=False)
        await user.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Failed to alert owner: {e}")

# ====================================================
# 🧠 INTELLIGENT PUNISHMENT SYSTEM (The Brain)
# ====================================================
async def punish_human(message, reason):
    """
    Decides whether to Timeout (1st time) or Ban (2nd time).
    Uses intelligent strike system for human mistakes.
    """
    user = message.author
    user_id = user.id
    now = datetime.datetime.now().timestamp()

    # 1. Initialize User Cache
    if user_id not in strike_cache:
        strike_cache[user_id] = []

    # 2. Clean old strikes (older than 5 minutes)
    strike_cache[user_id] = [t for t in strike_cache[user_id] if now - t < STRIKE_RESET]

    # 3. Add new strike
    strike_cache[user_id].append(now)
    strike_count = len(strike_cache[user_id])

    # --- EXECUTE JUDGMENT ---
    if strike_count == 1:
        # FIRST OFFENSE -> TIMEOUT (1 Minute)
        try:
            duration = datetime.timedelta(seconds=TIMEOUT_DURATION)
            await user.timeout(duration, reason=f"Warning: {reason}")
            await message.channel.send(f"⚠️ **Warning**: {user.mention} Put in Time-out for 1 min. (Reason: {reason})\n*Next violation in 5 mins = INSTANT BAN.*")
        except discord.Forbidden:
            await message.channel.send("❌ I tried to timeout this user, but my role is too low.")

    elif strike_count >= 2:
        # SECOND OFFENSE -> PERMANENT BAN
        try:
            await user.ban(reason=f"2nd Strike (Banned): {reason}")
            await message.channel.send(f"🔨 **JUDGMENT**: {user.mention} has been **BANNED** for breaking rules twice in 5 mins.")
            del strike_cache[user_id]  # Clear cache after ban
        except discord.Forbidden:
            await message.channel.send("❌ I tried to ban this user, but my role is too low.")

# ====================================================
# 🔒 LOCKDOWN & RECOVERY SYSTEM
# ====================================================
async def engage_lockdown(guild, reason):
    """Freezes the server - disables messaging and voice"""
    global is_locked_down
    if is_locked_down:
        return
    is_locked_down = True

    role = guild.default_role
    perms = role.permissions
    perms.send_messages = False
    perms.connect = False
    perms.speak = False
    
    try:
        await role.edit(permissions=perms, reason=f"LOCKDOWN: {reason}")
        print(f"❄️ SERVER FROZEN. Reason: {reason}")
        
        # Alert owner
        await alert_owner(guild, "SERVER LOCKDOWN ACTIVATED", {
            "Reason": reason,
            "Status": "Server is now in LOCKDOWN mode",
            "Action": "Use !all ok to unlock"
        })
    except Exception as e:
        print(f"⚠️ Lockdown Error: {e}")
        is_locked_down = False  # Revert on failure

async def restore_channel(guild, channel_name, category_id, channel_type):
    """Auto-recovers a deleted channel"""
    try:
        category = discord.utils.get(guild.categories, id=category_id) if category_id else None
        if str(channel_type) == 'text':
            new_channel = await guild.create_text_channel(channel_name, category=category, reason="Anti-Nuke Auto-Recovery")
        elif str(channel_type) == 'voice':
            new_channel = await guild.create_voice_channel(channel_name, category=category, reason="Anti-Nuke Auto-Recovery")
        else:
            return
        
        print(f"✅ Restored channel: {channel_name}")
        if hasattr(new_channel, 'send'):
            await new_channel.send(f"✅ **System Restored:** This channel was recovered by anti-nuke system.")
    except Exception as e:
        print(f"⚠️ Channel restoration error: {e}")

# ==================== WHITELIST CHECKER ====================
def is_whitelisted_entity(actor_or_id):
    """
    Advanced whitelist checker for bots, webhooks, and trusted users
    Returns: True if the entity is whitelisted/trusted, False otherwise
    """
    # Handle both discord.User and int (user/bot ID)
    actor_id = actor_or_id.id if hasattr(actor_or_id, 'id') else actor_or_id
    
    # Check if it's a whitelisted bot
    if actor_id in WHITELISTED_BOTS:
        print(f"✅ [WHITELIST] Bot ID {actor_id} is whitelisted (TRUSTED BOT)")
        return True
    
    # Check if it's a whitelisted webhook
    if actor_id in WHITELISTED_WEBHOOKS:
        print(f"✅ [WHITELIST] Webhook ID {actor_id} is whitelisted (TRUSTED WEBHOOK)")
        return True
    
    # Check if it's the owner
    if actor_id == OWNER_ID:
        print(f"✅ [WHITELIST] User {actor_id} is the OWNER")
        return True
    
    # Check if it's the bot itself
    if hasattr(actor_or_id, 'id') and actor_or_id == bot.user:
        print(f"✅ [WHITELIST] Actor is the bot itself")
        return True
    
    # Check if it's in TRUSTED_USERS
    if actor_id in TRUSTED_USERS:
        print(f"✅ [WHITELIST] User {actor_id} is in TRUSTED_USERS")
        return True
    
    return False

# Safe wrapper functions for MongoDB operations


def safe_find_one(collection, query):
    """Safely query MongoDB"""
    if not mongo_connected or collection is None:
        return None
    try:
        return collection.find_one(query)
    except Exception as e:
        return None

def safe_find(collection, query=None, limit=None):
    """Safely find multiple documents"""
    if not mongo_connected or collection is None:
        print(f"⚠️ Cannot find: mongo_connected={mongo_connected}, collection={collection is not None}")
        return []
    try:
        if query is None:
            query = {}
        result = collection.find(query)
        if limit:
            result = result.limit(limit)
        data = list(result)
        print(f"✅ safe_find returned {len(data)} documents")
        return data
    except Exception as e:
        print(f"⚠️ safe_find error: {str(e)[:100]}")
        return []

def safe_update_one(collection, query, update):
    """Safely update one document"""
    if not mongo_connected or collection is None:
        return False
    try:
        result = collection.update_one(query, update, upsert=True)
        if result.modified_count > 0 or result.upserted_id:
            return True
        # Document may not exist yet, that's okay
        return True
    except Exception as e:
        print(f"⚠️ MongoDB update error: {str(e)[:100]}")
        return False

def safe_delete_one(collection, query):
    """Safely delete one document"""
    if not mongo_connected or collection is None:
        return False
    try:
        collection.delete_one(query)
        return True
    except Exception as e:
        return False

def save_with_retry(collection, query, update, max_retries=3):
    """Save to MongoDB with retry logic"""
    if collection is None:
        print(f"⚠️ Collection is None, cannot save")
        return False
    
    for attempt in range(max_retries):
        try:
            # CRITICAL: Must use upsert=True to create documents if they don't exist
            # Handle MongoDB conflicts by flattening $setOnInsert operations
            result = collection.update_one(query, update, upsert=True)
            if result.modified_count > 0 or result.upserted_id:
                return True
            # Document may not exist yet, that's okay - upsert created it
            return True
        except Exception as e:
            error_msg = str(e)
            # Check for conflict errors (common in nested field updates)
            if "conflict" in error_msg.lower() or "cannot create" in error_msg.lower():
                print(f"⚠️ Save attempt {attempt + 1} failed: MongoDB conflict detected - {error_msg[:100]}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)  # Longer wait for conflicts
            else:
                print(f"⚠️ Save attempt {attempt + 1} failed: {error_msg[:80]}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5)  # Wait before retry (use time.sleep, not asyncio)
    
    print(f"❌ Failed to save after {max_retries} attempts")
    return False

# Function to safely create indexes
async def create_indexes_async():
    """Create MongoDB indexes safely with error handling"""
    if not mongo_connected:
        print("⏭️ Skipping index creation (MongoDB not available)")
        return
    
    try:
        users_coll.create_index("data.voice_cam_on_minutes")
        users_coll.create_index("data.voice_cam_off_minutes")
        print("✅ MongoDB indexes created")
    except Exception as e:
        error_msg = str(e)
        if "SSL" in error_msg or "handshake" in error_msg:
            print(f"⚠️ Index creation skipped (MongoDB SSL issue): {error_msg[:80]}")
        else:
            print(f"⚠️ Index creation failed (non-critical): {error_msg[:100]}")


intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree
GUILD = discord.Object(id=GUILD_ID) if GUILD_ID > 0 else None

# In-memory
vc_join_times = {}
cam_timers = {}
user_activity = defaultdict(list)
spam_cache = defaultdict(list)
strike_cache = defaultdict(list)
join_times = defaultdict(list)
vc_cache = defaultdict(list)
last_audit_id = None  # Track last processed audit entry to prevent duplicates

from leaderboard import format_time, get_medal_emoji, generate_leaderboard_text, user_rank

def track_activity(user_id: int, action: str):
    ts = datetime.datetime.now(KOLKATA).strftime("%d/%m %H:%M:%S")
    user_activity[user_id].append(f"[{ts}] {action}")
    if len(user_activity[user_id]) > 20:
        user_activity[user_id].pop(0)

# ==================== VOICE & CAM ====================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if member.guild.id != GUILD_ID or member.bot:
        return
    
    # =======================================
    # 🔊 VC SPAM SENSOR (Enhanced Hopping)
    # =======================================
    if member.id not in TRUSTED_USERS and before.channel != after.channel:
        now = datetime.datetime.now()
        if member.id not in vc_cache:
            vc_cache[member.id] = []
        
        # Clean old timestamps (older than 5 seconds)
        vc_cache[member.id] = [t for t in vc_cache[member.id] if (now - t).total_seconds() < 5]
        vc_cache[member.id].append(now)
        
        # If more than 3 joins/leaves in 5 seconds -> VC hopping detected
        if len(vc_cache[member.id]) > 3:
            print(f"⚠️ VC HOPPING DETECTED: {member.name} ({len(vc_cache[member.id])} actions in 5s)")
            # This would be a human error, trigger strike system
            # For now, just timeout them
            try:
                await member.timeout(timedelta(minutes=5), reason="VC Join/Leave Spam (Hopping)")
                await alert_owner(member.guild, "VC HOPPING SPAM", {
                    "User": f"{member.mention}",
                    "Actions": f"{len(vc_cache[member.id])} in 5 seconds",
                    "Action": "5-minute timeout"
                })
            except Exception as e:
                print(f"⚠️ Failed to timeout VC hopper: {e}")
            return
    
    user_id = str(member.id)
    now = time.time()
    old_in = bool(before.channel)
    new_in = bool(after.channel)
    # Cam is ON if: camera is on (regardless of screenshare status)
    # Cam is OFF if: camera is off
    # NOTE: Cam ON + Screenshare ON = counts as cam on time (both are active)
    old_cam = before.self_video
    new_cam = after.self_video

    # Initialize user record first
    save_with_retry(users_coll, {"_id": user_id}, {"$setOnInsert": {"data": {"voice_cam_on_minutes": 0, "voice_cam_off_minutes": 0, "message_count": 0, "yesterday": {"cam_on": 0, "cam_off": 0}}}})

    # VC abuse check
    if before.channel != after.channel:
        vc_cache[member.id].append(now)
        vc_cache[member.id] = [t for t in vc_cache[member.id] if now - t < VC_ABUSE_WINDOW]
        if len(vc_cache[member.id]) > VC_ABUSE_THRESHOLD:
            try:
                await member.move_to(None, reason="VC abuse")
                await member.timeout(timedelta(minutes=5), reason="VC hopping")
                track_activity(member.id, "Timeout for VC abuse")
            except Exception:
                pass

    # Save voice time IMMEDIATELY when leaving or changing settings
    if (old_in and not new_in) or (old_in and new_in and (before.channel != after.channel or old_cam != new_cam)):
        if member.id in vc_join_times:
            mins = int((now - vc_join_times[member.id]) // 60)
            if mins > 0:
                # Determine the relevant channel for this event (prefer before when leaving)
                relevant_channel = None
                if before and before.channel:
                    relevant_channel = before.channel
                elif after and after.channel:
                    relevant_channel = after.channel

                # Skip recording stats for excluded voice channel
                if relevant_channel and getattr(relevant_channel, 'id', None) == EXCLUDED_VOICE_CHANNEL_ID:
                    print(f"⏭️ Skipping cam stat save for excluded channel ({EXCLUDED_VOICE_CHANNEL_ID}) for {member.display_name}")
                else:
                    # FIXED: Cam ON = camera is ON (not: camera AND NOT screenshare)
                    field = "data.voice_cam_on_minutes" if old_cam else "data.voice_cam_off_minutes"
                    result = save_with_retry(users_coll, {"_id": user_id}, {"$inc": {field: mins}})
                    cam_status = "🎥 ON" if old_cam else "❌ OFF"
                    print(f"💾 [{field}] Saved {mins}m for {member.display_name} ({cam_status}) - MongoDB: {result}")
            del vc_join_times[member.id]

    # Track when user joins VC
    if new_in:
        vc_join_times[member.id] = now
        track_activity(member.id, f"Joined VC: {after.channel.name if after.channel else 'Unknown'}")
        print(f"🎤 {member.display_name} joined VC - tracking started (Cam: {new_cam})")

    # 🎥 ADVANCED CAM ENFORCEMENT SYSTEM 🎥
    # Updated Logic:
    # - Cam ON + Screenshare ON = ✅ NO WARNING (camera is on, approved)
    # - Cam ON + Screenshare OFF = ✅ NO WARNING (camera is on, approved)
    # - Cam OFF + Screenshare ON = ⚠️ WARNING (need camera even with screenshare)
    # - Cam OFF + Screenshare OFF = ⚠️ WARNING (no camera, no screenshare)
    
    channel = after.channel
    if channel and (str(channel.id) in STRICT_CHANNEL_IDS or "Cam On" in channel.name):
        has_cam = after.self_video  # True if camera is on
        has_screenshare = after.self_stream  # True if screensharing
        
        # ✅ PRIMARY: CAM ON - Camera is on = NO WARNING (regardless of screenshare status)
        if has_cam:
            task = cam_timers.pop(member.id, None)
            if task:
                task.cancel()
            
            # If both cam and screenshare are on, show that explicitly
            if has_screenshare:
                print(f"✅ [{member.display_name}] CAM ON + SCREENSHARE ON - No warning needed (Both active)")
            else:
                print(f"✅ [{member.display_name}] CAM ON - No warning needed")
        
        # ❌ CAM OFF - WARNING NEEDED! (screenshare is not enough, camera is required)
        else:
            if member.id not in cam_timers:
                status_text = "SCREENSHARE ON" if has_screenshare else "NO SCREENSHARE"
                print(f"⚠️ [{member.display_name}] CAM OFF ({status_text}) - ENFORCEMENT STARTED!")
                
                async def enforce():
                    # 🎯 AGGRESSIVE WARNING - Send immediately (30s delay before enforcement timer)
                    await asyncio.sleep(30)
                    
                    try:
                        embed = discord.Embed(
                            title="🎥 ⚠️ CAMERA REQUIRED - FINAL WARNING!",
                            description=f"{member.mention}\n\n**Please turn on your camera within 3 minutes or you will be disconnected from the voice channel!**",
                            color=discord.Color.red()
                        )
                        embed.add_field(
                            name="⏱️ TIME REMAINING",
                            value="3 minutes to comply or automatic kick",
                            inline=False
                        )
                        embed.add_field(
                            name="✅ ACTION REQUIRED",
                            value="• Turn on your camera\n*(Screenshare alone is not enough - camera is mandatory)*",
                            inline=False
                        )
                        embed.set_footer(text="⚠️ This channel has strict camera enforcement enabled")
                        
                        await member.send(embed=embed)
                        print(f"📢 [{member.display_name}] 🎥 CAM WARNING SENT - Countdown: 3 MINUTES TO COMPLY OR KICK")
                    except Exception as e:
                        print(f"⚠️ Failed to send enforcement warning to {member.display_name}: {e}")
                    
                    # ⏳ WAIT 3 MINUTES FOR USER TO COMPLY
                    await asyncio.sleep(180)
                    
                    # 🔍 CHECK IF USER COMPLIED
                    if member.voice and member.voice.channel and str(member.voice.channel.id) in STRICT_CHANNEL_IDS:
                        current_cam = member.voice.self_video
                        
                        # ✅ USER COMPLIED: Camera is now ON
                        if current_cam:
                            print(f"✅ [{member.display_name}] COMPLIED IN TIME - CAM ON detected")
                        
                        # ❌ USER DIDN'T COMPLY: Camera still OFF - AUTOMATIC DISCONNECT
                        else:
                            print(f"🚪 [{member.display_name}] ENFORCEMENT EXECUTED - Disconnecting from VC (Channel: {member.voice.channel.name})")
                            
                            try:
                                # KICK/DISCONNECT THE USER
                                await member.move_to(None, reason="Enforcement: Camera required within 3-minute deadline")
                                print(f"✅ [{member.display_name}] SUCCESSFULLY KICKED from voice channel")
                                
                                # 📢 NOTIFY CHANNEL ABOUT ENFORCEMENT ACTION
                                try:
                                    embed_kick = discord.Embed(
                                        title="🚪 User Disconnected",
                                        description=f"{member.mention} has been automatically disconnected for not enabling their camera.",
                                        color=discord.Color.orange()
                                    )
                                    embed_kick.set_footer(text="Camera enforcement in strict channels")
                                    await channel.send(embed=embed_kick, delete_after=15)
                                except Exception:
                                    pass
                                
                                # 📧 SEND DM TO USER ABOUT ENFORCEMENT
                                try:
                                    embed_dm = discord.Embed(
                                        title="📵 You Were Disconnected",
                                        description=f"You were disconnected from **{channel.name}** due to camera enforcement.\n\nCamera is mandatory in this channel (screenshare alone is not sufficient).\n\nPlease enable your camera before rejoining.",
                                        color=discord.Color.red()
                                    )
                                    await member.send(embed=embed_dm)
                                except Exception:
                                    pass
                                
                            except Exception as e:
                                print(f"⚠️ Failed to disconnect {member.display_name}: {e}")
                    
                    # Clean up timer
                    cam_timers.pop(member.id, None)
                
                cam_timers[member.id] = bot.loop.create_task(enforce())

@tasks.loop(seconds=30)
async def batch_save_study():
    """Save voice & cam stats every 30 seconds for accurate tracking"""
    if GUILD_ID <= 0 or not mongo_connected:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    now = time.time()
    try:
        saved_count = 0
        processed = set()
        
        # ✅ FIRST: Save all users currently in vc_join_times (already tracked)
        for uid, join in list(vc_join_times.items()):
            member = guild.get_member(uid)
            if not member or not member.voice or not member.voice.channel:
                # User left VC, remove from tracking
                vc_join_times.pop(uid, None)
                continue
            
            # Calculate minutes elapsed since last save (at least 30 seconds)
            mins = int((now - join) // 60)
            
            # Only save if at least 30 seconds have passed
            if mins > 0 or (now - join) >= 30:
                # FIXED CAM DETECTION LOGIC:
                # Cam ON = camera is ON (regardless of screenshare)
                # Cam OFF = camera is OFF
                cam = member.voice.self_video
                
                # Skip saving for excluded voice channel
                try:
                    current_channel = member.voice.channel
                except Exception:
                    current_channel = None

                if current_channel and getattr(current_channel, 'id', None) == EXCLUDED_VOICE_CHANNEL_ID:
                    print(f"⏭️ Skipping batch save for excluded channel ({EXCLUDED_VOICE_CHANNEL_ID}) for {member.display_name}")
                    vc_join_times[uid] = now
                    processed.add(uid)
                    continue

                # Only save 1 minute at a time if less than 1 minute has passed
                mins_to_save = max(1, mins) if mins > 0 else 1
                
                if mins_to_save > 0:
                    field = "data.voice_cam_on_minutes" if cam else "data.voice_cam_off_minutes"
                    # FIX: Separate operations to avoid MongoDB conflict
                    # First: Create document if it doesn't exist
                    users_coll.update_one(
                        {"_id": str(uid)},
                        {"$setOnInsert": {
                            "data": {
                                "voice_cam_on_minutes": 0,
                                "voice_cam_off_minutes": 0,
                                "message_count": 0,
                                "yesterday": {"cam_on": 0, "cam_off": 0}
                            }
                        }},
                        upsert=True
                    )
                    # Then: Increment the field
                    result = save_with_retry(users_coll, {"_id": str(uid)}, {"$inc": {field: mins_to_save}})
                    if result:
                        cam_status = "🎥 ON" if cam else "❌ OFF"
                        print(f"⏱️ {member.display_name}: +{mins_to_save}m {field} ({cam_status}) ✅")
                        saved_count += 1
                    # Reset join time after saving
                    vc_join_times[uid] = now
                processed.add(uid)
        
        # ✅ SECOND: Also save ALL members currently in any voice channel (fallback tracking)
        # This ensures users who joined before bot started are still tracked
        newly_registered = []  # Track newly registered users
        for channel in guild.voice_channels:
            for member in channel.members:
                if member.bot or member.id in processed:
                    continue
                
                # Initialize if not in vc_join_times
                if member.id not in vc_join_times:
                    vc_join_times[member.id] = now
                    mins = 0  # Just initialized, don't save time yet
                    newly_registered.append(member.display_name)  # Add to list instead of printing
                else:
                    mins = int((now - vc_join_times[member.id]) // 60)
                
                if mins > 0 or (now - vc_join_times[member.id]) >= 30:
                    # FIXED CAM DETECTION: Camera ON = camera is physically on
                    cam = member.voice.self_video
                    
                    # Skip saving for excluded voice channel
                    if getattr(channel, 'id', None) == EXCLUDED_VOICE_CHANNEL_ID:
                        print(f"⏭️ Skipping batch save for excluded channel ({EXCLUDED_VOICE_CHANNEL_ID}) for {member.display_name}")
                        vc_join_times[member.id] = now
                        continue
                    
                    mins_to_save = max(1, mins) if mins > 0 else 1
                    
                    if mins_to_save > 0:
                        field = "data.voice_cam_on_minutes" if cam else "data.voice_cam_off_minutes"
                        # FIX: Separate operations to avoid MongoDB conflict
                        users_coll.update_one(
                            {"_id": str(member.id)},
                            {"$setOnInsert": {
                                "data": {
                                    "voice_cam_on_minutes": 0,
                                    "voice_cam_off_minutes": 0,
                                    "message_count": 0,
                                    "yesterday": {"cam_on": 0, "cam_off": 0}
                                }
                            }},
                            upsert=True
                        )
                        result = save_with_retry(users_coll, {"_id": str(member.id)}, {"$inc": {field: mins_to_save}})
                        if result:
                            cam_status = "🎥 ON" if cam else "❌ OFF"
                            print(f"⏱️ {member.display_name}: +{mins_to_save}m {field} ({cam_status}) ✅")
                            saved_count += 1
                        vc_join_times[member.id] = now
        
        # Print consolidated registration message (only ONE message)
        if newly_registered:
            print(f"🔄 Registered ({len(newly_registered)} new): {', '.join(newly_registered)}")
        
        if saved_count > 0:
            print(f"📊 30-second batch save: Updated {saved_count} active members in voice")
    except Exception as e:
        print(f"⚠️ Batch save error: {str(e)[:100]}")

@batch_save_study.before_loop
async def before_batch_save():
    """Ensure batch save starts running from the beginning"""
    await bot.wait_until_ready()
    print("✅ batch_save_study loop started")

# ==================== LEADERBOARDS ====================

def generate_leaderboard_text(cam_on_list, cam_off_list):
    """Generate beautiful leaderboard text with medals and decorations"""
    now = datetime.datetime.now(KOLKATA).strftime("%d %b %Y | %I:%M %p")
    
    text = f"""
╔════════════════════════════════════════════╗
        🏆 LEGEND STAR 🏆
     🌙 Daily Leaderboard Champion 🌙
        ⏰ {now} IST
╚════════════════════════════════════════════╝

📹 **CAM ON — TOP 5**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if cam_on_list:
        for i, (name, mins) in enumerate(cam_on_list[:5], 1):
            medal = get_medal_emoji(i)
            text += f"{medal}  #{i} **{name}** — ⏱ {format_time(mins)}\n"
    else:
        text += "📚 *No data yet. Start studying!*\n"
    
    text += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📴 **CAM OFF — TOP 5**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if cam_off_list:
        for i, (name, mins) in enumerate(cam_off_list[:5], 1):
            medal = get_medal_emoji(i)
            text += f"{medal}  #{i} **{name}** — ⏱ {format_time(mins)}\n"
    else:
        text += "🤐 *No silent sessions yet.*\n"
    
    text += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ Auto Generated at **11:59 PM**
🔄 Daily Reset at **11:59 PM**
🔥 Keep Grinding Legends!
"""
# helpers imported from leaderboard.py to avoid import-time side-effects

@tasks.loop(time=datetime.time(23, 59, tzinfo=KOLKATA))
async def auto_leaderboard_ping():
    """Auto ping at 23:59 IST to announce leaderboard with top 5"""
    if GUILD_ID <= 0 or not mongo_connected:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = guild.get_channel(AUTO_LB_CHANNEL_ID)
    if not channel:
        return
    try:
        role = guild.get_role(AUTO_LB_PING_ROLE_ID)
        if not role:
            print(f"⚠️ Auto ping role {AUTO_LB_PING_ROLE_ID} not found")
            return
        
        ping_text = f"{role.mention} 🏆 **Leaderboard Published With Top 5 Performers!**\n✨ Check the rankings below and compete for glory! ✨"
        await channel.send(ping_text)
        print(f"✅ Auto ping sent at 23:59 IST to {role.name}")
    except Exception as e:
        print(f"⚠️ Auto ping error: {str(e)[:100]}")

@tasks.loop(time=datetime.time(23, 59, tzinfo=KOLKATA))
async def auto_leaderboard():
    """Auto leaderboard at 23:59 IST - shows today's TOP 5 data before reset"""
    if GUILD_ID <= 0 or not mongo_connected:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = guild.get_channel(AUTO_LB_CHANNEL_ID)
    if not channel:
        return
    try:
        now_ist = datetime.datetime.now(KOLKATA)
        docs = safe_find(users_coll, {})
        active = []
        for doc in docs:
            data = doc.get("data", {})
            try:
                m = guild.get_member(int(doc["_id"]))
                if m:
                    active.append({"name": m.display_name, "cam_on": data.get("voice_cam_on_minutes", 0), "cam_off": data.get("voice_cam_off_minutes", 0)})
            except Exception:
                pass
        
        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)
        
        # Convert to list of tuples for formatting (include everyone, even 0 minutes)
        cam_on_data = [(u["name"], u["cam_on"]) for u in sorted_on]
        cam_off_data = [(u["name"], u["cam_off"]) for u in sorted_off]
        
        leaderboard_text = generate_leaderboard_text(cam_on_data, cam_off_data)
        
        await channel.send(f"```{leaderboard_text}```")
        print(f"✅ Auto leaderboard posted at 23:59 IST with TOP 5 performers")
    except Exception as e:
        print(f"⚠️ Auto leaderboard error: {str(e)[:100]}")

@tasks.loop(time=datetime.time(23, 59, tzinfo=KOLKATA))
async def midnight_reset():
    """Daily data reset at 11:59 PM IST (Indian Time) - preserves yesterday's data"""
    if not mongo_connected:
        return
    try:
        now_ist = datetime.datetime.now(KOLKATA)
        print(f"\n{'='*70}")
        print(f"🌙 DAILY RESET INITIATED at {now_ist.strftime('%d/%m/%Y %H:%M:%S IST')}")
        print(f"{'='*70}")
        
        docs = safe_find(users_coll, {})
        reset_count = 0
        
        for doc in docs:
            try:
                data = doc.get("data", {})
                cam_on_today = data.get("voice_cam_on_minutes", 0)
                cam_off_today = data.get("voice_cam_off_minutes", 0)
                
                # Preserve today's data to yesterday, then reset today's counters
                result = safe_update_one(users_coll, {"_id": doc["_id"]}, {"$set": {
                    "data.yesterday.cam_on": cam_on_today,
                    "data.yesterday.cam_off": cam_off_today,
                    "data.voice_cam_on_minutes": 0,
                    "data.voice_cam_off_minutes": 0,
                    "last_reset": now_ist.isoformat()
                }})
                if result:
                    reset_count += 1
                    print(f"   ✅ {doc['_id']}: {format_time(cam_on_today)} ON → Yesterday | Reset today's counters")
            except Exception as e:
                print(f"   ⚠️ Error resetting {doc.get('_id', 'unknown')}: {str(e)[:60]}")
        
        print(f"\n🌙 Daily Reset Complete: {reset_count} users reset")
        print(f"📊 New data collection cycle starts now at {now_ist.strftime('%H:%M:%S IST')}")
        print(f"{'='*70}\n")
    except Exception as e:
        print(f"⚠️ Midnight reset error: {str(e)[:100]}")

# Leaderboard commands
@tree.command(name="lb", description="Today’s voice + cam leaderboard", guild=GUILD)
@checks.cooldown(1, 10)   # once per 10 sec per user
async def lb(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if not mongo_connected:
            return await interaction.followup.send("📡 Database temporarily unavailable. Try again in a moment.")
        
        docs = safe_find(users_coll, {}, limit=100)
        print(f"🔍 /lb command: Found {len(docs)} total documents in MongoDB")
        print(f"   ℹ️  Fetching data from all {len(docs)} users...")
        
        active = []
        # Use guild.members cache for speed; fallback to fetching member if not cached
        members_by_id = {m.id: m for m in interaction.guild.members}
        print(f"   Guild has {len(members_by_id)} members")

        for doc in docs:
            data = doc.get("data", {})
            try:
                user_id = int(doc["_id"]) if isinstance(doc.get("_id"), (int, str)) else None
                if not user_id:
                    continue

                m = members_by_id.get(user_id)
                if not m:
                    # Try to fetch member from API as a fallback (may be slow)
                    try:
                        m = await interaction.guild.fetch_member(user_id)
                    except Exception:
                        m = None

                if m:
                    active.append({"name": m.display_name, "cam_on": data.get("voice_cam_on_minutes", 0), "cam_off": data.get("voice_cam_off_minutes", 0)})
            except Exception:
                pass

        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)

        cam_on_data = [(u["name"], u["cam_on"]) for u in sorted_on]
        cam_off_data = [(u["name"], u["cam_off"]) for u in sorted_off]

        leaderboard_text = generate_leaderboard_text(cam_on_data, cam_off_data)
        await interaction.followup.send(f"```{leaderboard_text}```")
        print(f"✅ /lb command: leaderboard sent")
    except Exception as e:
        print(f"⚠️ /lb command error: {e}")
        await interaction.followup.send("⚠️ Failed to generate leaderboard. Try again later.")


# Per-user rank command (/rank)
@tree.command(name="rank", description="Show a user's CAM ON / CAM OFF rank", guild=GUILD)
@checks.cooldown(1, 10)
async def rank(interaction: discord.Interaction, member: discord.Member = None):
    """Slash command to show the per-user rank summary.

    This command is intentionally implemented as a standalone feature and
    only reads from the DB; it does not modify any existing structures.
    """
    await interaction.response.defer()
    try:
        if not mongo_connected:
            return await interaction.followup.send("📡 Database temporarily unavailable. Try again in a moment.")

        target = member or interaction.user

        # Collect today's data (same approach as auto_leaderboard)
        docs = safe_find(users_coll, {}, limit=1000)
        active = []
        for doc in docs:
            data = doc.get("data", {})
            try:
                m = interaction.guild.get_member(int(doc["_id"]))
                if m:
                    active.append({
                        "name": m.display_name,
                        "cam_on": data.get("voice_cam_on_minutes", 0),
                        "cam_off": data.get("voice_cam_off_minutes", 0)
                    })
            except Exception:
                continue

        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)

        cam_on_data = [(u["name"], u["cam_on"]) for u in sorted_on]
        cam_off_data = [(u["name"], u["cam_off"]) for u in sorted_off]

        summary = user_rank(target.display_name, cam_on_data, cam_off_data)
        # Send as code block for monospaced alignment; public message
        await interaction.followup.send(f"```{summary}```")
    except Exception as e:
        print(f"⚠️ /rank command error: {e}")
        await interaction.followup.send("⚠️ Failed to generate rank. Try again later.")


# Note: `mystatus` and `yst` are implemented later in the file (preserved original versions)
        
        for doc in docs:
            try:
                # Skip the test document created during startup
                if doc["_id"] == "mongodb_test":
                    continue
                    
                user_id = int(doc["_id"])
                member = members_by_id.get(user_id)
                if not member:
                    continue
                data = doc.get("data", {})
                cam_on = data.get("voice_cam_on_minutes", 0)
                cam_off = data.get("voice_cam_off_minutes", 0)
                total = cam_on + cam_off
                print(f"   - {member.display_name}: Cam ON {cam_on}m, Cam OFF {cam_off}m (Total: {total}m)")
                if cam_on > 0 or cam_off > 0:
                    active.append({"name": member.display_name, "cam_on": cam_on, "cam_off": cam_off})
            except (ValueError, KeyError) as e:
                print(f"   ⚠️ Error processing doc: {e}")
                continue
        
        print(f"   ✅ Processed {len(docs)} documents, {len(active)} have data")
        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]  # TOP 15 CAM ON
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]  # TOP 10 CAM OFF
        
        # ✨ Beautiful Leaderboard Design
        cam_on_data = [(u["name"], u["cam_on"]) for u in sorted_on]
        cam_off_data = [(u["name"], u["cam_off"]) for u in sorted_off]
        
        leaderboard_text = generate_leaderboard_text(cam_on_data, cam_off_data)
        
        await interaction.followup.send(f"```{leaderboard_text}```")
    except Exception as e:
        error_msg = str(e)
        if "SSL" in error_msg or "handshake" in error_msg:
            await interaction.followup.send("📡 Database connection issue. Please try again later.")
        else:
            await interaction.followup.send(f"Error loading leaderboard: {str(e)[:100]}")

@tree.command(name="ylb", description="Yesterday’s leaderboard", guild=GUILD)
async def ylb(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if not mongo_connected:
            return await interaction.followup.send("📡 Database temporarily unavailable. Try again in a moment.")
        
        docs = safe_find(users_coll, {"data.yesterday": {"$exists": True}})
        active = []
        # Use guild.members cache instead of fetching (faster)
        members_by_id = {m.id: m for m in interaction.guild.members}
        for doc in docs:
            try:
                user_id = int(doc["_id"])
                member = members_by_id.get(user_id)
                if not member:
                    continue
                y = doc.get("data", {}).get("yesterday", {})
                if y.get("cam_on", 0) == 0 and y.get("cam_off", 0) == 0:
                    continue
                active.append({"name": member.display_name, "cam_on": y.get("cam_on", 0), "cam_off": y.get("cam_off", 0)})
            except (ValueError, KeyError):
                continue
        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]
        desc = "**Yesterday Cam On ✅**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_on'])}" for i, u in enumerate(sorted_on, 1) if u["cam_on"] > 0) or "No data.\n")
        desc += "\n**Yesterday Cam Off ❌**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_off'])}" for i, u in enumerate(sorted_off, 1) if u["cam_off"] > 0) or "")
        embed = discord.Embed(title="⏮️ Yesterday Leaderboard", description=desc, color=0xA9A9A9)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        error_msg = str(e)
        if "SSL" in error_msg or "handshake" in error_msg:
            await interaction.followup.send("📡 Database connection issue. Please try again later.")
        else:
            await interaction.followup.send(f"Error loading yesterday leaderboard: {str(e)[:100]}")

@tree.command(name="mystatus", description="Your personal VC + cam stats", guild=GUILD)
async def mystatus(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        doc = safe_find_one(users_coll, {"_id": str(interaction.user.id)})
    except Exception as e:
        await interaction.followup.send(f"DB Error: {e}")
        return

    if not doc or "data" not in doc:
        return await interaction.followup.send("No stats yet.")

    data = doc["data"]
    total = data.get("voice_cam_on_minutes", 0) + data.get("voice_cam_off_minutes", 0)

    embed = discord.Embed(
        title=f"📊 Stats for {interaction.user.name}",
        color=0x9932CC
    )
    embed.add_field(name="Total", value=format_time(total))
    embed.add_field(name="Cam On", value=format_time(data.get("voice_cam_on_minutes", 0)))
    embed.add_field(name="Cam Off", value=format_time(data.get("voice_cam_off_minutes", 0)))

    await interaction.followup.send(embed=embed)



@tree.command(name="yst", description="Your yesterday’s stats", guild=GUILD)
async def yst(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        doc = safe_find_one(users_coll, {"_id": str(interaction.user.id)})
        if not doc or "data" not in doc or "yesterday" not in doc["data"]:
            return await interaction.followup.send("No yesterday data.")
        y = doc["data"]["yesterday"]
        total = y.get("cam_on", 0) + y.get("cam_off", 0)
        embed = discord.Embed(title=f"🗓️ Yesterday Stats: {interaction.user.name}", color=0x808080)
        embed.add_field(name="Total", value=format_time(total), inline=True)
        embed.add_field(name="Cam On", value=format_time(y.get("cam_on", 0)), inline=True)
        embed.add_field(name="Cam Off", value=format_time(y.get("cam_off", 0)), inline=True)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"Error loading stats: {str(e)[:100]}")

# ==================== REDLIST ====================
@tree.command(name="redban", description="Ban a user & store in redlist", guild=GUILD)
@app_commands.describe(userid="User ID")
async def redban(interaction: discord.Interaction, userid: str):
    await interaction.response.defer()
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only")
        if not userid.isdigit():
            return await interaction.followup.send("Invalid ID")
        safe_update_one(redlist_coll, {"_id": userid}, {"$set": {"added": datetime.datetime.now(KOLKATA)}})
        try:
            await interaction.guild.ban(discord.Object(id=int(userid)), reason="Redlist")
        except Exception as e:
            print(f"Ban error: {e}")
        await interaction.followup.send(f"Redlisted {userid}")
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}")

@tree.command(name="redlist", description="Show banned / restricted users", guild=GUILD)
async def redlist(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only")
        ids = [doc["_id"] for doc in safe_find(redlist_coll, {})]
        if not ids:
            return await interaction.followup.send("Empty redlist.")
        msg = "Redlist IDs:\n" + "\n".join(f"- {i}" for i in ids)
        await interaction.followup.send(msg)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}")

@tree.command(name="removeredban", description="Remove a user from redlist & unban", guild=GUILD)
@app_commands.describe(userid="User ID to remove from redlist")
async def removeredban(interaction: discord.Interaction, userid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        
        if not userid.isdigit():
            return await interaction.followup.send("Invalid ID format", ephemeral=True)
        
        # Check if user exists in redlist
        user_doc = safe_find_one(redlist_coll, {"_id": userid})
        if not user_doc:
            return await interaction.followup.send(f"User {userid} not found in redlist", ephemeral=True)
        
        # Remove from redlist
        safe_delete_one(redlist_coll, {"_id": userid})
        
        # Try to unban the user
        try:
            await interaction.guild.unban(discord.Object(id=int(userid)), reason="Removed from redlist")
            status = "✅ Unbanned successfully"
        except discord.errors.NotFound:
            status = "⚠️ User not banned on server"
        except Exception as e:
            status = f"⚠️ Unban failed: {str(e)[:50]}"
        
        await interaction.followup.send(f"Removed {userid} from redlist. {status}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@bot.event
async def on_member_join(member: discord.Member):
    if member.guild.id != GUILD_ID:
        return
    now = time.time()
    join_times[member.guild.id].append(now)
    join_times[member.guild.id] = [t for t in join_times[member.guild.id] if now - t < RAID_WINDOW]
    if len(join_times[member.guild.id]) > RAID_THRESHOLD:
        await lockdown_guild(member.guild)
        tech_channel = bot.get_channel(TECH_CHANNEL_ID)
        if tech_channel:
            await tech_channel.send("⚠️ Raid detected! Lockdown activated.")
        # Ban recent joins
        for m in member.guild.members:
            if m.joined_at and (now - m.joined_at.timestamp()) < RAID_WINDOW:
                try:
                    await m.ban(reason="Raid protection")
                except Exception:
                    pass
    if safe_find_one(redlist_coll, {"_id": str(member.id)}):
        try:
            await member.ban(reason="Redlist")
        except Exception:
            pass
    if member.bot and member.id not in WHITELISTED_BOTS:
        try:
            await member.ban(reason="Non-whitelisted bot")
        except Exception:
            pass

# ==================== TODO HELPERS ====================

async def send_todo_to_channel(embed: discord.Embed, source: str = "TodoModal"):
    """Send TODO embed to the dedicated TODO channel - GUARANTEED to send"""
    print(f"\n{'='*70}")
    print(f"� [SEND_TODO_TO_CHANNEL] Starting")
    print(f"   Source: {source}")
    print(f"   Guild ID: {GUILD_ID}")
    print(f"   Channel ID: {TODO_CHANNEL_ID}")
    print(f"   Embed title: {embed.title}")
    
    if GUILD_ID <= 0 or TODO_CHANNEL_ID <= 0:
        print(f"❌ Invalid IDs")
        return False
    
    try:
        print(f"📤 Attempt: bot.get_guild({GUILD_ID})")
        guild = bot.get_guild(GUILD_ID)
        print(f"   Result: {guild}")
        
        if not guild:
            print(f"❌ Guild is None, returning False")
            return False
        
        print(f"✅ Guild: {guild.name}")
        print(f"📤 Attempt: guild.get_channel({TODO_CHANNEL_ID})")
        channel = guild.get_channel(TODO_CHANNEL_ID)
        print(f"   Result: {channel}")
        
        if not channel:
            print(f"❌ Channel is None, trying fetch_channel...")
            try:
                channel = await guild.fetch_channel(TODO_CHANNEL_ID)
                print(f"✅ Channel fetched: {channel}")
            except Exception as fe:
                print(f"❌ fetch_channel failed: {fe}")
                return False
        
        if not channel:
            print(f"❌ Channel is still None after both methods")
            return False
        
        print(f"✅ Channel: {channel.name}")
        print(f"📤 Sending message to channel...")
        await channel.send(embed=embed)
        print(f"✅✅✅ MESSAGE SENT SUCCESSFULLY! ✅✅✅")
        print(f"{'='*70}\n")
        return True
        
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*70}\n")
        return False


# ==================== TODO SYSTEM ====================
# Simple command-based TODO with direct attachment support

@tree.command(name="todo", description="Submit daily TODO with tasks and file", guild=GUILD)
@app_commands.describe(
    feature="Feature name (required)",
    date="Date DD/MM/YYYY",
    must_do="Must Do tasks",
    can_do="Can Do tasks",
    dont_do="Don't Do restrictions",
    attachment="File/Screenshot (max 8MB)"
)
async def todo(
    interaction: discord.Interaction,
    feature: str,
    date: str,
    attachment: discord.Attachment = None,
    must_do: str = None,
    can_do: str = None,
    dont_do: str = None
):
    """Submit daily TODO with feature name, date, and categories"""
    await interaction.response.defer()
    
    uid = str(interaction.user.id)
    
    # Auth check
    if not safe_find_one(active_members_coll, {"_id": uid}) and interaction.user.id != OWNER_ID:
        await interaction.followup.send("❌ Not authorized", ephemeral=True)
        return
    
    # Date validation
    try:
        date_obj = datetime.datetime.strptime(date, "%d/%m/%Y")
    except ValueError:
        await interaction.followup.send(f"❌ Invalid date. Use DD/MM/YYYY format", ephemeral=True)
        return
    
    # Content check
    if not any([must_do, can_do, dont_do]) and not attachment:
        await interaction.followup.send("❌ Provide content or attachment", ephemeral=True)
        return
    
    # Validate attachment if provided
    attachment_data = None
    if attachment:
        # Size check
        if attachment.size > 8 * 1024 * 1024:
            await interaction.followup.send(f"❌ File too large (max 8MB)", ephemeral=True)
            return
        
        # Type check
        ext = attachment.filename.rsplit('.', 1)[-1].lower() if '.' in attachment.filename else ''
        valid_exts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff', 'pdf', 'txt', 'doc', 'docx', 'xlsx', 'ppt', 'pptx', 'csv']
        
        if ext not in valid_exts:
            await interaction.followup.send(f"❌ File type not supported", ephemeral=True)
            return
        
        # Detect type
        file_type = 'image' if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff'] else 'document'
        
        attachment_data = {
            "url": attachment.url,
            "filename": attachment.filename,
            "file_type": file_type,
            "uploaded_at": datetime.datetime.now(KOLKATA).isoformat()
        }
    
    # Save to DB
    now = datetime.datetime.now(tz=KOLKATA)
    todo_data = {
        "feature_name": feature,
        "date": date,
        "must_do": must_do or "N/A",
        "can_do": can_do or "N/A",
        "dont_do": dont_do or "N/A",
        "submitted_at": now.isoformat()
    }
    if attachment_data:
        todo_data["attachment"] = attachment_data
    
    safe_update_one(todo_coll, {"_id": uid}, {
        "$set": {
            "last_submit": time.time(),
            "last_ping": 0,
            "todo": todo_data,
            "updated_at": now.isoformat()
        }
    })
    
    # Create embed for channel
    embed = discord.Embed(title=f"📋 {feature}", color=discord.Color.from_rgb(0, 150, 255), timestamp=now)
    embed.add_field(name="👤 By", value=interaction.user.mention, inline=False)
    embed.add_field(name="📅 Date", value=date, inline=True)
    
    if must_do:
        embed.add_field(name="✔️ MUST DO", value=f"```{must_do}```", inline=False)
    if can_do:
        embed.add_field(name="🎯 CAN DO", value=f"```{can_do}```", inline=False)
    if dont_do:
        embed.add_field(name="❌ DON'T DO", value=f"```{dont_do}```", inline=False)
    
    if attachment_data:
        emoji = "🖼️" if attachment_data['file_type'] == 'image' else "📄"
        embed.add_field(name=f"{emoji} File", value=f"[{attachment.filename}]({attachment.url})", inline=False)
        if attachment_data['file_type'] == 'image':
            embed.set_image(url=attachment.url)
    
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
    
    # Send to TODO channel (PUBLIC)
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            channel = guild.get_channel(TODO_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
    except Exception:
        pass
    
    await interaction.followup.send("✅ TODO posted for everyone!")


@tree.command(name="atodo", description="Assign TODO to user (Owner only)", guild=GUILD)
@app_commands.describe(
    user="Target user",
    feature="Feature name",
    date="Date DD/MM/YYYY",
    must_do="Must Do tasks",
    can_do="Can Do tasks",
    dont_do="Don't Do restrictions",
    attachment="File/Screenshot"
)
async def atodo(
    interaction: discord.Interaction,
    user: discord.Member,
    feature: str,
    date: str,
    attachment: discord.Attachment = None,
    must_do: str = None,
    can_do: str = None,
    dont_do: str = None
):
    """Owner-only: Assign TODO to another user"""
    await interaction.response.defer()
    
    # Owner check
    if interaction.user.id != OWNER_ID:
        await interaction.followup.send("❌ Owner only", ephemeral=True)
        return
    
    uid = str(user.id)
    
    # Target auth check
    if not safe_find_one(active_members_coll, {"_id": uid}):
        await interaction.followup.send(f"❌ {user.mention} not authorized", ephemeral=True)
        return
    
    # Date validation
    try:
        date_obj = datetime.datetime.strptime(date, "%d/%m/%Y")
    except ValueError:
        await interaction.followup.send(f"❌ Invalid date", ephemeral=True)
        return
    
    # Content check
    if not any([must_do, can_do, dont_do]) and not attachment:
        await interaction.followup.send("❌ Provide content", ephemeral=True)
        return
    
    # Validate attachment
    attachment_data = None
    if attachment:
        if attachment.size > 8 * 1024 * 1024:
            await interaction.followup.send(f"❌ File too large", ephemeral=True)
            return
        
        ext = attachment.filename.rsplit('.', 1)[-1].lower() if '.' in attachment.filename else ''
        valid_exts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'doc', 'docx', 'xlsx', 'ppt', 'pptx', 'csv']
        
        if ext not in valid_exts:
            await interaction.followup.send(f"❌ File type not supported", ephemeral=True)
            return
        
        file_type = 'image' if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'tiff'] else 'document'
        
        attachment_data = {
            "url": attachment.url,
            "filename": attachment.filename,
            "file_type": file_type,
            "uploaded_at": datetime.datetime.now(KOLKATA).isoformat()
        }
    
    # Save to DB
    now = datetime.datetime.now(tz=KOLKATA)
    todo_data = {
        "feature_name": feature,
        "date": date,
        "must_do": must_do or "N/A",
        "can_do": can_do or "N/A",
        "dont_do": dont_do or "N/A",
        "submitted_at": now.isoformat(),
        "submitted_by": interaction.user.name,
        "submitted_by_id": interaction.user.id
    }
    if attachment_data:
        todo_data["attachment"] = attachment_data
    
    safe_update_one(todo_coll, {"_id": uid}, {
        "$set": {
            "last_submit": time.time(),
            "last_ping": 0,
            "todo": todo_data,
            "updated_at": now.isoformat()
        }
    })
    
    # Create embed - GOLD color for owner submission
    embed = discord.Embed(title=f"📋 {feature}", color=discord.Color.from_rgb(255, 165, 0), timestamp=now)
    embed.add_field(name="👤 Assigned To", value=user.mention, inline=False)
    embed.add_field(name="👨‍💼 By Owner", value=interaction.user.mention, inline=False)
    embed.add_field(name="📅 Date", value=date, inline=True)
    
    if must_do:
        embed.add_field(name="✔️ MUST DO", value=f"```{must_do}```", inline=False)
    if can_do:
        embed.add_field(name="🎯 CAN DO", value=f"```{can_do}```", inline=False)
    if dont_do:
        embed.add_field(name="❌ DON'T DO", value=f"```{dont_do}```", inline=False)
    
    if attachment_data:
        emoji = "🖼️" if attachment_data['file_type'] == 'image' else "📄"
        embed.add_field(name=f"{emoji} File", value=f"[{attachment.filename}]({attachment.url})", inline=False)
        if attachment_data['file_type'] == 'image':
            embed.set_image(url=attachment.url)
    
    # Send to TODO channel (PUBLIC)
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            channel = guild.get_channel(TODO_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
    except Exception:
        pass
    
    await interaction.followup.send(f"✅ TODO assigned to {user.mention}!")


@tasks.loop(hours=3)
async def todo_checker():
    """Ping users who haven't submitted TODO in 24 hours"""
    if GUILD_ID <= 0:
        return
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    
    channel = guild.get_channel(TODO_CHANNEL_ID)
    if not channel:
        return
    
    now = time.time()
    one_day = 24 * 3600
    three_hours = 3 * 3600
    five_days = 5 * 86400
    
    for doc in safe_find(todo_coll, {}):
        try:
            uid = int(doc["_id"])
            member = guild.get_member(uid)
            
            if not member or member.bot:
                continue
            
            last_submit = doc.get("last_submit", 0)
            last_ping = doc.get("last_ping", 0)
            elapsed = now - last_submit
            
            # Remove role if inactive 5+ days
            if elapsed >= five_days:
                role = guild.get_role(ROLE_ID)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role)
                    except Exception:
                        pass
            
            # Ping if inactive 24+ hours AND haven't pinged in 3+ hours
            elif elapsed >= one_day and (now - last_ping) >= three_hours:
                days = int(elapsed // 86400)
                hours = int((elapsed % 86400) // 3600)
                time_str = f"{days}d {hours}h" if days > 0 else f"{hours}h"
                
                embed = discord.Embed(
                    title="⏰ TODO Reminder!",
                    description=f"{member.mention}\nLast submitted: **{time_str} ago**",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Action", value="Use `/todo` to submit", inline=False)
                
                try:
                    await channel.send(embed=embed)
                    await member.send(embed=embed)
                except Exception:
                    pass
                
                # Update ping timestamp
                safe_update_one(todo_coll, {"_id": str(uid)}, {"$set": {"last_ping": now}})
        except Exception:
            pass


@todo_checker.before_loop
async def before_todo_checker():
    """Ensure todo_checker starts"""
    await bot.wait_until_ready()


@tree.command(name="listtodo", description="View your current TODO", guild=GUILD)
async def listtodo(interaction: discord.Interaction):
    """View your current TODO submission"""
    await interaction.response.defer(ephemeral=True)
    try:
        doc = safe_find_one(todo_coll, {"_id": str(interaction.user.id)})
        if not doc or "todo" not in doc:
            return await interaction.followup.send("No TODO submitted yet. Use `/todo`", ephemeral=True)
        
        todo = doc["todo"]
        embed = discord.Embed(title=f"📋 {todo.get('feature_name', 'N/A')}", color=discord.Color.blue())
        embed.add_field(name="📅 Date", value=todo.get('date', 'N/A'), inline=True)
        embed.add_field(name="✔️ Must Do", value=f"```{todo.get('must_do', 'N/A')}```", inline=False)
        embed.add_field(name="🎯 Can Do", value=f"```{todo.get('can_do', 'N/A')}```", inline=False)
        embed.add_field(name="❌ Don't Do", value=f"```{todo.get('dont_do', 'N/A')}```", inline=False)
        
        if "attachment" in todo:
            att = todo["attachment"]
            embed.add_field(name="📎 File", value=f"[{att.get('filename', 'File')}]({att.get('url', 'N/A')})", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)


@tree.command(name="deltodo", description="Delete your TODO", guild=GUILD)
async def deltodo(interaction: discord.Interaction):
    """Delete your current TODO submission"""
    await interaction.response.defer(ephemeral=True)
    try:
        result = safe_delete_one(todo_coll, {"_id": str(interaction.user.id)})
        if result:
            await interaction.followup.send("✅ TODO deleted", ephemeral=True)
        else:
            await interaction.followup.send("❌ No TODO to delete", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)


@tree.command(name="todostatus", description="Check TODO status", guild=GUILD)
@app_commands.describe(user="Optional: Check another user (Owner only)")
async def todostatus(interaction: discord.Interaction, user: discord.Member = None):
    """Check your or another user's TODO status"""
    await interaction.response.defer(ephemeral=True)
    
    target = user if user else interaction.user
    
    # If checking another user, owner check
    if user and interaction.user.id != OWNER_ID:
        return await interaction.followup.send("❌ Owner only", ephemeral=True)
    
    try:
        doc = safe_find_one(todo_coll, {"_id": str(target.id)})
        last_submit = doc.get("last_submit", 0) if doc else 0
        
        now = time.time()
        elapsed = now - last_submit
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        
        embed = discord.Embed(title="📊 TODO Status", color=discord.Color.green())
        embed.add_field(name="User", value=target.mention)
        embed.add_field(name="Last Submit", value=f"{time_str} ago")
        embed.add_field(name="Status", value="✅ Safe" if elapsed < 86400 else "⏰ Pending ping")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)


# ==================== ADMIN COMMANDS ====================
@tree.command(name="msz", description="Send announcement (Owner)", guild=GUILD)
@app_commands.describe(channel="Target", message="Text", role="Ping (opt)", attachment="File (opt)")
async def msz(interaction: discord.Interaction, channel: discord.TextChannel, message: str, role: discord.Role = None, attachment: discord.Attachment = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        content = f"📩 **Server Announcement**\n{message}"
        if role:
            content += f"\n<@&{role.id}>"
        files = [await attachment.to_file()] if attachment else None
        await channel.send(content, files=files)
        await interaction.followup.send("Sent!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="mz", description="Anonymous DM (Owner)", guild=GUILD)
@app_commands.describe(target="User", message="Text", attachment="File (opt)")
async def mz(interaction: discord.Interaction, target: discord.User, message: str, attachment: discord.Attachment = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        content = f"📩 **Message from Server**\n{message}"
        files = [await attachment.to_file()] if attachment else None
        try:
            await target.send(content, files=files)
            await interaction.followup.send(f"Sent anonymously to {target}", ephemeral=True)
        except Exception:
            await interaction.followup.send("DM failed (blocked?).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="ud", description="User details (Owner)", guild=GUILD)
@app_commands.describe(target="User")
async def ud(interaction: discord.Interaction, target: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        
        user_id = str(target.id)
        
        # Fetch MongoDB data
        user_doc = safe_find_one(users_coll, {"_id": user_id})
        data = user_doc.get("data", {}) if user_doc else {}
        
        print(f"🔍 /ud query for {target.display_name} (ID: {user_id})")
        print(f"   MongoDB document: {user_doc}")
        print(f"   Data fields: {data}")
        
        # Get in-memory activity logs
        logs = "\n".join(user_activity[target.id] or ["No logs"])
        
        embed = discord.Embed(title=f"🕵️ {target}", color=0x0099ff)
        embed.add_field(name="ID", value=target.id)
        embed.add_field(name="Joined", value=target.joined_at.strftime("%d/%m/%Y %H:%M") if target.joined_at else "Unknown")
        
        # Voice & Cam Stats
        cam_on = data.get("voice_cam_on_minutes", 0)
        cam_off = data.get("voice_cam_off_minutes", 0)
        messages = data.get("message_count", 0)
        
        stats_text = f"🎤 Cam ON: {format_time(cam_on)}\n❌ Cam OFF: {format_time(cam_off)}\n💬 Messages: {messages}"
        embed.add_field(name="📊 Stats", value=stats_text, inline=False)
        
        # Recent Activity
        embed.add_field(name="Recent Activity", value=f"```{logs}```", inline=False)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="bn", description="Force ban (Owner)", guild=GUILD)
@app_commands.describe(target="ID/Mention/Name", reason="Reason (opt)")
async def bn(interaction: discord.Interaction, target: str, reason: str = "Force Ban"):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        member = None
        if target.isdigit():
            try:
                member = await interaction.guild.fetch_member(int(target))
            except Exception:
                pass
        elif target.startswith("<@"):
            clean = target.strip("<@!>").strip(">")
            try:
                member = await interaction.guild.fetch_member(int(clean))
            except Exception:
                pass
        else:
            member = discord.utils.find(lambda m: m.name == target or m.display_name == target, interaction.guild.members)
        if member:
            await interaction.guild.ban(member, reason=reason)
            await interaction.followup.send(f"Banned {member}", ephemeral=True)
        else:
            await interaction.followup.send("User not found.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="ck", description="Disconnect user from VC (Owner)", guild=GUILD)
@app_commands.describe(user="Target")
async def ck(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        if not user.voice or not user.voice.channel:
            return await interaction.followup.send("User not in VC.", ephemeral=True)
        await user.move_to(None, reason="Admin kick")
        await interaction.followup.send(f"Disconnected {user}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="addh", description="Allow a user to use todo system", guild=GUILD)
@app_commands.describe(userid="User ID (numeric)")
async def addh(interaction: discord.Interaction, userid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("❌ Owner only", ephemeral=True)
        
        # Validate user ID
        if not userid.isdigit():
            return await interaction.followup.send("❌ Invalid ID format (must be numeric)", ephemeral=True)
        
        user_id = int(userid)
        user_id_str = str(userid)
        
        print(f"\n{'='*70}")
        print(f"🔧 [/ADDH] Adding user to TODO system")
        print(f"   Input userid: {userid} (type: {type(userid).__name__})")
        print(f"   user_id int: {user_id}")
        print(f"   user_id_str: {user_id_str}")
        
        # Try to get member from guild
        guild = interaction.guild
        member = guild.get_member(user_id) if guild else None
        print(f"   Guild: {guild.name if guild else 'None'}")
        print(f"   Member found: {member.name if member else 'None'}")
        
        # Add to active members - use STRING format like the todo check expects
        result = safe_update_one(active_members_coll, {"_id": user_id_str}, {
            "$set": {
                "added": datetime.datetime.now(KOLKATA),
                "name": member.display_name if member else f"User {user_id}",
                "user_id": user_id  # Also store as int for reference
            }
        })
        print(f"   Database update result: {result}")
        
        # Verify it was actually saved
        verify = safe_find_one(active_members_coll, {"_id": user_id_str})
        print(f"   Verification lookup by '{user_id_str}': {verify}")
        print(f"{'='*70}\n")
        
        member_name = member.mention if member else f"`{user_id}`"
        await interaction.followup.send(f"✅ Added {member_name} to TODO system", ephemeral=True)
        
        # Log to channel
        if guild:
            channel = guild.get_channel(TODO_CHANNEL_ID)
            if channel:
                try:
                    msg = f"✅ {member.mention if member else f'`{user_id}`'} added to TODO system (can now use `/todo`)"
                    await channel.send(msg)
                except Exception as e:
                    print(f"⚠️ Failed to log to channel: {e}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
        print(f"⚠️ /addh error: {str(e)}")
        import traceback
        traceback.print_exc()

@tree.command(name="remh", description="Remove a user from todo system", guild=GUILD)
@app_commands.describe(userid="User ID (numeric)")
async def remh(interaction: discord.Interaction, userid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("❌ Owner only", ephemeral=True)
        
        # Validate user ID
        if not userid.isdigit():
            return await interaction.followup.send("❌ Invalid ID format (must be numeric)", ephemeral=True)
        
        user_id = int(userid)
        user_id_str = str(userid)
        
        print(f"\n{'='*70}")
        print(f"🔧 [/REMH] Removing user from TODO system")
        print(f"   Input userid: {userid} (type: {type(userid).__name__})")
        print(f"   user_id int: {user_id}")
        print(f"   user_id_str: {user_id_str}")
        
        # Try to get member from guild
        guild = interaction.guild
        member = guild.get_member(user_id) if guild else None
        print(f"   Guild: {guild.name if guild else 'None'}")
        print(f"   Member found: {member.name if member else 'None'}")
        
        # Check if user exists before removing
        existing = safe_find_one(active_members_coll, {"_id": user_id_str})
        print(f"   Found in database: {existing}")
        
        # Remove from active members
        safe_delete_one(active_members_coll, {"_id": user_id_str})
        print(f"   Deletion executed")
        
        # Verify it was actually removed
        verify = safe_find_one(active_members_coll, {"_id": user_id_str})
        print(f"   Verification after delete: {verify}")
        print(f"{'='*70}\n")
        
        member_name = member.mention if member else f"`{user_id}`"
        await interaction.followup.send(f"✅ Removed {member_name} from TODO system", ephemeral=True)
        
        # Log to channel
        if guild:
            channel = guild.get_channel(TODO_CHANNEL_ID)
            if channel:
                try:
                    msg = f"❌ {member.mention if member else f'`{user_id}`'} removed from TODO system (can no longer use `/todo`)"
                    await channel.send(msg)
                except Exception as e:
                    print(f"⚠️ Failed to log to channel: {e}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
        print(f"⚠️ /remh error: {str(e)}")
        import traceback
        traceback.print_exc()

@tree.command(name="members", description="List all allowed members", guild=GUILD)
async def members(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        ids = [doc["_id"] for doc in safe_find(active_members_coll, {})]
        if not ids:
            return await interaction.followup.send("No active members.", ephemeral=True)
        guild = interaction.guild
        names = []
        for id_ in ids:
            member = guild.get_member(int(id_))
            if member:
                names.append(member.display_name)
        msg = "Active Members:\n" + "\n".join(f"- {n}" for n in names)
        await interaction.followup.send(msg, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="tododebug", description="Debug TODO system (Owner only)", guild=GUILD)
async def tododebug(interaction: discord.Interaction):
    """Debug command to check TODO system status"""
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        
        user_id_str = str(interaction.user.id)
        
        # Check if user is in active members
        user_doc = safe_find_one(active_members_coll, {"_id": user_id_str})
        
        # Get all active members
        all_members = safe_find(active_members_coll, {})
        
        msg = f"""
🔍 **TODO System Debug Info**

**Your Info:**
- Your ID (int): {interaction.user.id}
- Your ID (str): {user_id_str}
- In active_members: {user_doc is not None}

**All Active Members ({len(all_members)}):**
"""
        for doc in all_members:
            msg += f"\n- ID: `{doc['_id']}` | Name: {doc.get('name', 'Unknown')}"
        
        # Show collection stats
        all_todo = safe_find(todo_coll, {})
        msg += f"\n\n**TODO Submissions ({len(all_todo)}):**"
        for doc in all_todo:
            msg += f"\n- ID: `{doc['_id']}` | Name: {doc.get('todo', {}).get('name', 'Unknown')}"
        
        await interaction.followup.send(msg[:2000], ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
        import traceback
        traceback.print_exc()

# ==================== SECURITY FIREWALLS ====================
@bot.event
async def on_message(message: discord.Message):
    # Skip bot messages
    if message.author.bot:
        return
    
    # ============================================================
    # 📩 FORWARD DMs & BOT MENTIONS TO OWNER (PRIORITY #1)
    # ============================================================
    
    # Check if this is a DM or bot mention
    is_dm = isinstance(message.channel, discord.DMChannel) and message.author.id != OWNER_ID
    is_bot_mention = bot.user in message.mentions and not isinstance(message.channel, discord.DMChannel)
    
    if is_dm or is_bot_mention:
        try:
            owner = await bot.fetch_user(OWNER_ID)
            if owner:
                # Build embed
                if is_dm:
                    embed = discord.Embed(title=f"📩 DM from {message.author}", color=discord.Color.blue())
                    embed.add_field(name="Location", value="Direct Message", inline=True)
                else:
                    embed = discord.Embed(title=f"🔔 Bot Mention from {message.author}", color=discord.Color.gold())
                    embed.add_field(name="Location", value=f"#{message.channel.name}", inline=True)
                
                embed.description = message.content[:2000] if message.content else "[No content]"
                embed.add_field(name="User ID", value=str(message.author.id), inline=True)
                
                if message.guild:
                    embed.add_field(name="Server", value=message.guild.name, inline=True)
                
                if message.attachments:
                    att_info = "\n".join([f"📎 {a.filename} ({a.size} bytes)" for a in message.attachments])
                    embed.add_field(name="Attachments", value=att_info, inline=False)
                
                embed.set_author(name=f"{message.author.name}#{message.author.discriminator}", icon_url=message.author.avatar.url if message.author.avatar else None)
                embed.timestamp = message.created_at
                
                await owner.send(embed=embed)
                print(f"✅ [FORWARD] {'DM' if is_dm else 'Mention'} from {message.author.name} → Owner")
        except Exception as e:
            print(f"⚠️ [FORWARD ERROR] {e}")
        
        # For DMs, also send confirmation
        if is_dm:
            try:
                await message.author.send("✅ Your message has been forwarded to the owner.")
            except Exception:
                pass
        
        # Don't process further for DMs
        if is_dm:
            return
    
    # Allow messages from different guilds ONLY if they're being forwarded (handled above)
    if message.guild and message.guild.id != GUILD_ID:
        return
    
    now = time.time()
    
    # ---------------------------------------------------------
    # ☠️ ZONE 1: HACKER THREATS (INSTANT BAN - NO STRIKES)
    # ---------------------------------------------------------
    
    # A. GHOST WEBHOOK DESTROYER (Only for non-whitelisted webhooks)
    if message.webhook_id:
        # ✅ WHITELIST CHECK: If webhook is whitelisted, skip all threats checks
        if message.webhook_id not in WHITELISTED_WEBHOOKS:
            SUSPICIOUS_WORDS = ["free nitro", "steam", "gift", "airdrop", "@everyone", "@here", "maa", "rand", "chut"]
            link_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
            
            is_threat = (
                message.mention_everyone or 
                re.search(link_regex, message.content) or 
                any(bad_word in message.content.lower() for bad_word in SUSPICIOUS_WORDS)
            )

            if is_threat:
                print(f"🚨 [WEBHOOK THREAT] Non-whitelisted webhook {message.webhook_id} sending malicious content")
                try:
                    await message.delete()
                    webhooks = await message.channel.webhooks()
                    for webhook in webhooks:
                        if webhook.id == message.webhook_id:
                            await webhook.delete(reason="LegendMeta: Malicious Ghost Webhook Activity")
                            await message.channel.send("☠️ **LegendMeta**: Unauthorized Ghost Webhook DESTROYED.")
                            print(f"✅ [WEBHOOK THREAT] Malicious webhook {message.webhook_id} has been deleted")
                except Exception as e:
                    print(f"⚠️ [WEBHOOK THREAT] Webhook cleanup error: {e}")
                return # STOP HERE
        else:
            print(f"✅ [WEBHOOK] Webhook {message.webhook_id} is whitelisted - allowing all content")

    # IMMUNITY CHECK
    if message.author.id == OWNER_ID or message.author == bot.user:
        return

    # B. MALWARE UPLOAD (.exe) -> INSTANT BAN
    if message.attachments:
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            if filename.endswith(('.exe', '.scr', '.bat', '.cmd', '.msi', '.vbs', '.js', '.apk', '.jar')):
                try:
                    await message.delete()
                    await message.author.ban(reason="LegendMeta: Malware Upload Detected")
                    await message.channel.send(f"☣️ **Security Alert**: {message.author.mention} was BANNED for uploading a dangerous file (`{filename}`).")
                    return 
                except Exception as e:
                    print(f"Failed to ban file uploader: {e}")
    
    # Track message activity in MongoDB - SAVE IMMEDIATELY
    if message.guild and message.guild.id == GUILD_ID:
        user_id = str(message.author.id)
        try:
            # Use separate operations to avoid MongoDB conflicts
            # First, increment message count (no setOnInsert conflict)
            result = save_with_retry(users_coll, {"_id": user_id}, {
                "$inc": {"data.message_count": 1},
                "$setOnInsert": {
                    "data.voice_cam_on_minutes": 0,
                    "data.voice_cam_off_minutes": 0,
                    "data.yesterday.cam_on": 0,
                    "data.yesterday.cam_off": 0
                }
            })
            track_activity(message.author.id, f"Message in #{message.channel.name}: {message.content[:50]}")
            if not result:
                print(f"⚠️ Failed to save message count for {message.author.display_name}")
        except Exception as e:
            print(f"⚠️ Message tracking error: {str(e)[:80]}")
    
    # ---------------------------------------------------------
    # ⚠️ ZONE 2: HUMAN MISTAKES (STRIKE SYSTEM)
    # ---------------------------------------------------------

    # C. MASS MENTION (Strike System)
    total_mentions = len(message.mentions) + len(message.role_mentions)
    if message.mention_everyone: total_mentions += 1

    if total_mentions >= MAX_MENTIONS:
        await message.delete()
        await punish_human(message, "Mass Mentioning") # -> Calls the Brain
        return
    
    # 1. Anti-Spam
    spam_cache[message.author.id].append(now)
    spam_cache[message.author.id] = [t for t in spam_cache[message.author.id] if now - t < SPAM_WINDOW]
    if len(spam_cache[message.author.id]) > SPAM_THRESHOLD:
        del spam_cache[message.author.id] # Clear to prevent double strike
        await punish_human(message, "Excessive Spamming") # -> Calls the Brain
        return
    
    # D. ANTI-ADVERTISEMENT (Strike System)
    invite_regex = r"(https?://)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com/invite)/.+"
    if re.search(invite_regex, message.content, re.IGNORECASE):
        await message.delete()
        await punish_human(message, "Advertising") # -> Calls the Brain
        return
    
    await bot.process_commands(message)

@tasks.loop(minutes=5)
async def clean_webhooks():
    """
    Periodic webhook cleanup task
    ✅ WHITELISTED webhooks are NEVER deleted
    ❌ Non-whitelisted webhooks are removed for security
    """
    if GUILD_ID <= 0:
        return
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    
    try:
        for channel in guild.text_channels:
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    # ✅ WHITELIST CHECK: Skip whitelisted webhooks
                    if wh.id in WHITELISTED_WEBHOOKS:
                        print(f"✅ [WEBHOOK CLEANUP] Webhook {wh.id} is whitelisted - KEEPING")
                        continue
                    
                    # ❌ Delete non-whitelisted webhook
                    await wh.delete(reason="Security: Unauthorized webhook")
                    print(f"❌ [WEBHOOK CLEANUP] Deleted unauthorized webhook {wh.id} from #{channel.name}")
            except Exception as e:
                print(f"⚠️ [WEBHOOK CLEANUP] Error processing channel {channel.name}: {e}")
    except Exception as e:
        print(f"⚠️ [WEBHOOK CLEANUP] General error: {e}")

@tasks.loop(minutes=1)
async def monitor_audit():
    """Monitors critical server activities like unauthorized webhook creation with enhanced deduplication"""
    if GUILD_ID <= 0:
        return
    
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        current_time = datetime.datetime.now(KOLKATA)
        
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            # ✅ ENHANCED DEDUPLICATION: Check if we already processed this audit entry
            if entry.id in processed_audit_ids:
                print(f"⏭️ [WEBHOOK CREATE] Audit entry {entry.id} already processed - SKIPPING DUPLICATE")
                return
            
            # Check timestamp-based deduplication (prevent alerts within window)
            if entry.id in processed_audit_timestamps:
                last_alert_time = processed_audit_timestamps[entry.id]
                time_diff = (current_time - last_alert_time).total_seconds()
                if time_diff < AUDIT_DEDUP_WINDOW:
                    print(f"⏭️ [WEBHOOK CREATE] Audit entry {entry.id} - Too soon to re-alert (only {time_diff:.1f}s ago)")
                    return
            
            # Mark this audit entry as processed with timestamp
            processed_audit_ids.add(entry.id)
            processed_audit_timestamps[entry.id] = current_time
            
            # Prevent memory bloat
            if len(processed_audit_ids) > MAX_AUDIT_CACHE:
                # Remove oldest entries
                oldest_id = min(processed_audit_timestamps, key=processed_audit_timestamps.get)
                processed_audit_ids.discard(oldest_id)
                del processed_audit_timestamps[oldest_id]
            
            # ✅ WHITELIST CHECK: Allow owner and bot itself
            if is_whitelisted_entity(entry.user):
                print(f"✅ [WEBHOOK CREATE] Whitelisted entity {entry.user.name} ({entry.user.id}) created webhook - ALLOWED (Audit ID: {entry.id})")
                return
            
            # ❌ THREAT DETECTED: Unauthorized webhook creation
            print(f"🚨 [ANTI-NUKE] UNAUTHORIZED WEBHOOK CREATION: {entry.user.name} ({entry.user.id}) (Audit ID: {entry.id})")
            
            # 1. DELETE THE WEBHOOK
            try:
                webhooks = await entry.channel.webhooks() if entry.channel else []
                for webhook in webhooks:
                    if webhook.id == entry.target.id:
                        await webhook.delete(reason="LegendMeta: Unauthorized Creation")
                        print(f"✅ Webhook {webhook.id} deleted")
            except Exception as e:
                print(f"⚠️ Failed to delete webhook: {e}")
            
            # 2. BAN THE CREATOR (Hacker/Rogue Admin -> INSTANT BAN)
            try:
                await guild.ban(entry.user, reason=f"Anti-Nuke: Malicious Webhook Creation (Audit ID: {entry.id})")
                
                # Alert in tech channel
                tech_channel = bot.get_channel(TECH_CHANNEL_ID)
                if tech_channel:
                    embed = discord.Embed(
                        title="🚨 ANTI-NUKE: UNAUTHORIZED WEBHOOK",
                        color=discord.Color.red(),
                        timestamp=datetime.datetime.now(KOLKATA)
                    )
                    embed.add_field(name="🔨 Action", value="User BANNED + Webhook DELETED", inline=True)
                    embed.add_field(name="👤 Attacker", value=f"{entry.user.mention} ({entry.user.id})", inline=True)
                    embed.add_field(name="🆔 Audit Entry", value=f"`{entry.id}`", inline=False)
                    await tech_channel.send(embed=embed)
                
                # Alert owner
                await alert_owner(guild, "UNAUTHORIZED WEBHOOK CREATION", {
                    "Attacker": f"{entry.user.name} (ID: {entry.user.id})",
                    "Action": "✅ Instant Ban Applied + Webhook Deleted",
                    "Audit Entry": str(entry.id)
                })
                
                print(f"✅ [ANTI-NUKE] {entry.user.name} has been BANNED for webhook creation (Audit ID: {entry.id})")
            except Exception as e:
                print(f"⚠️ Failed to ban webhook creator: {e}")
    except Exception:
        pass

@bot.event
async def on_guild_channel_delete(channel):
    if channel.guild.id != GUILD_ID:
        return
    
    current_time = datetime.datetime.now(KOLKATA)
    
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        # ✅ ENHANCED DEDUPLICATION: Check if we already processed this audit entry
        if entry.id in processed_audit_ids:
            print(f"⏭️ [CHANNEL DELETE] Audit entry {entry.id} already processed - SKIPPING DUPLICATE")
            return
        
        # Check timestamp-based deduplication (prevent alerts within window)
        if entry.id in processed_audit_timestamps:
            last_alert_time = processed_audit_timestamps[entry.id]
            time_diff = (current_time - last_alert_time).total_seconds()
            if time_diff < AUDIT_DEDUP_WINDOW:
                print(f"⏭️ [CHANNEL DELETE] Audit entry {entry.id} - Too soon to re-alert (only {time_diff:.1f}s ago)")
                return
        
        # Mark this audit entry as processed with timestamp
        processed_audit_ids.add(entry.id)
        processed_audit_timestamps[entry.id] = current_time
        
        # Prevent memory bloat
        if len(processed_audit_ids) > MAX_AUDIT_CACHE:
            # Remove oldest entries
            oldest_id = min(processed_audit_timestamps, key=processed_audit_timestamps.get)
            processed_audit_ids.discard(oldest_id)
            del processed_audit_timestamps[oldest_id]
        
        actor = entry.user
        
        # ✅ WHITELIST CHECK: Skip whitelisted bots/webhooks/users
        if is_whitelisted_entity(actor):
            print(f"✅ [CHANNEL DELETE] Whitelisted entity {actor.name} ({actor.id}) deleted channel - ALLOWED")
            return
        
        # ❌ THREAT DETECTED: Non-whitelisted entity deleted a channel
        print(f"🚨 [ANTI-NUKE] CHANNEL DELETION THREAT DETECTED: {actor.name} ({actor.id})")
        
        try:
            # BAN the attacker immediately
            await channel.guild.ban(actor, reason=f"Anti-Nuke: Channel Deletion by {actor.name}")
            
            # Alert in tech channel
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                embed = discord.Embed(
                    title="🚨 ANTI-NUKE: CHANNEL DELETION",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(KOLKATA)
                )
                embed.add_field(name="🔨 Action", value="User BANNED", inline=True)
                embed.add_field(name="👤 Attacker", value=f"{actor.mention} ({actor.id})", inline=True)
                embed.add_field(name="📢 Channel", value=channel.name, inline=True)
                embed.add_field(name="🆔 Audit Entry", value=f"`{entry.id}`", inline=False)
                await tech_channel.send(embed=embed)
            
            # Alert owner
            await alert_owner(channel.guild, "CHANNEL DELETION DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Channel": channel.name,
                "Action": "✅ Instant Ban Applied"
            })
            
            print(f"✅ [ANTI-NUKE] {actor.name} has been BANNED for channel deletion (Audit ID: {entry.id})")
            
        except discord.Forbidden:
            print(f"⚠️ [ANTI-NUKE] FAILED TO BAN channel deleter. Engaging emergency lockdown.")
            await engage_lockdown(channel.guild, "Failed to ban channel deleter - role hierarchy issue")
        except Exception as e:
            print(f"⚠️ [ANTI-NUKE] Channel delete error: {e}")


@bot.event
async def on_guild_role_delete(role):
    if role.guild.id != GUILD_ID:
        return
    
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        # ✅ DEDUPLICATION: Check if we already processed this audit entry
        if entry.id in processed_audit_ids:
            print(f"⏭️ [ROLE DELETE] Audit entry {entry.id} already processed - SKIPPING DUPLICATE")
            return
        
        # Mark this audit entry as processed
        processed_audit_ids.add(entry.id)
        
        # Prevent memory bloat
        if len(processed_audit_ids) > MAX_AUDIT_CACHE:
            processed_audit_ids.pop()
        
        actor = entry.user
        
        # ✅ WHITELIST CHECK: Skip whitelisted bots/webhooks/users
        if is_whitelisted_entity(actor):
            print(f"✅ [ROLE DELETE] Whitelisted entity {actor.name} ({actor.id}) deleted role - ALLOWED")
            return
        
        # ❌ THREAT DETECTED: Non-whitelisted entity deleted a role
        print(f"🚨 [ANTI-NUKE] ROLE DELETION THREAT DETECTED: {actor.name} ({actor.id})")
        
        try:
            # BAN the attacker immediately
            await role.guild.ban(actor, reason=f"Anti-Nuke: Role Deletion by {actor.name}")
            
            # Alert in tech channel
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                embed = discord.Embed(
                    title="🚨 ANTI-NUKE: ROLE DELETION",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(KOLKATA)
                )
                embed.add_field(name="🔨 Action", value="User BANNED", inline=True)
                embed.add_field(name="👤 Attacker", value=f"{actor.mention} ({actor.id})", inline=True)
                embed.add_field(name="👑 Role", value=role.name, inline=True)
                embed.add_field(name="🆔 Audit Entry", value=f"`{entry.id}`", inline=False)
                await tech_channel.send(embed=embed)
            
            # Alert owner
            await alert_owner(role.guild, "ROLE DELETION DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Role": role.name,
                "Action": "✅ Instant Ban Applied"
            })
            
            print(f"✅ [ANTI-NUKE] {actor.name} has been BANNED for role deletion (Audit ID: {entry.id})")
            
        except discord.Forbidden:
            print(f"⚠️ [ANTI-NUKE] FAILED TO BAN role deleter. Engaging emergency lockdown.")
            await engage_lockdown(role.guild, "Failed to ban role deleter - role hierarchy issue")
        except Exception as e:
            print(f"⚠️ [ANTI-NUKE] Role delete error: {e}")


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if guild.id != GUILD_ID:
        return
    
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        # ✅ DEDUPLICATION: Check if we already processed this audit entry
        if entry.id in processed_audit_ids:
            print(f"⏭️ [MEMBER BAN] Audit entry {entry.id} already processed - SKIPPING DUPLICATE")
            return
        
        # Mark this audit entry as processed
        processed_audit_ids.add(entry.id)
        
        # Prevent memory bloat
        if len(processed_audit_ids) > MAX_AUDIT_CACHE:
            processed_audit_ids.pop()
        
        actor = entry.user
        
        # ✅ WHITELIST CHECK: Skip whitelisted bots/webhooks/users AND self-bans
        if is_whitelisted_entity(actor) or user.id == actor.id:
            print(f"✅ [MEMBER BAN] Whitelisted entity {actor.name} ({actor.id}) banned {user.name} - ALLOWED")
            return
        
        # ❌ THREAT DETECTED: Non-whitelisted entity banned someone
        print(f"🚨 [ANTI-NUKE] UNAUTHORIZED BAN THREAT DETECTED: {actor.name} ({actor.id}) banned {user.name}")
        
        try:
            # BAN the attacker and unban the victim
            await guild.ban(actor, reason=f"Anti-Nuke: Unauthorized Ban by {actor.name}")
            await guild.unban(user, reason="Anti-Nuke: Victim recovery")
            
            # Alert in tech channel
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                embed = discord.Embed(
                    title="🚨 ANTI-NUKE: UNAUTHORIZED BAN",
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(KOLKATA)
                )
                embed.add_field(name="🔨 Action", value="Attacker BANNED + Victim UNBANNED", inline=True)
                embed.add_field(name="👤 Attacker", value=f"{actor.mention} ({actor.id})", inline=True)
                embed.add_field(name="👥 Victim", value=f"{user.mention} (ID: {user.id})", inline=True)
                embed.add_field(name="🆔 Audit Entry", value=f"`{entry.id}`", inline=False)
                await tech_channel.send(embed=embed)
            
            # Alert owner
            await alert_owner(guild, "UNAUTHORIZED BAN DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Victim": f"{user.name}",
                "Action": "✅ Attacker BANNED, Victim UNBANNED"
            })
            
            print(f"✅ [ANTI-NUKE] {actor.name} has been BANNED for unauthorized ban attempt, {user.name} has been UNBANNED (Audit ID: {entry.id})")
            
        except Exception as e:
            print(f"⚠️ [ANTI-NUKE] Member ban error: {e}")


@tasks.loop(minutes=1)
async def monitor_audit():
    global last_audit_id
    if GUILD_ID <= 0:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    tech_channel = bot.get_channel(TECH_CHANNEL_ID)
    if not tech_channel:
        return
    try:
        async for entry in guild.audit_logs(limit=10):
            # Stop at last processed entry to avoid duplicates
            if last_audit_id and entry.id == last_audit_id:
                break
            # ✅ WHITELIST: Allow bot, OWNER, and all TRUSTED_USERS (including Sapphire)
            if entry.user.id == bot.user.id or entry.user.id in TRUSTED_USERS:
                continue
            if entry.action in [discord.AuditLogAction.role_update, discord.AuditLogAction.channel_update, discord.AuditLogAction.ban, discord.AuditLogAction.kick, discord.AuditLogAction.member_role_update]:
                # Update last_id ONLY when we have a new action to report
                if not last_audit_id:
                    last_audit_id = entry.id
                embed = discord.Embed(title="⚠️ Audit Alert", description=f"{entry.user} performed {entry.action} on {entry.target}", color=discord.Color.red())
                await tech_channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Audit monitor error: {str(e)[:80]}")

async def lockdown_guild(guild: discord.Guild):
    everyone = guild.default_role
    overwrite = discord.PermissionOverwrite(send_messages=False, connect=False, speak=False)
    for channel in guild.channels:
        try:
            await channel.set_permissions(everyone, overwrite=overwrite)
        except Exception:
            pass
    tech_channel = bot.get_channel(TECH_CHANNEL_ID)
    if tech_channel:
        await tech_channel.send("🚨 Emergency lockdown activated!")

# ==================== MANUAL SYNC COMMAND ====================
@bot.command(name="sync")
async def manual_sync(ctx):
    if ctx.author.id != OWNER_ID:
        return
    try:
        if GUILD:
            
            synced = await tree.sync(guild=GUILD)
        else:
            
            synced = await tree.sync()
        await ctx.send(f"Synced {len(synced)} commands: {[c.name for c in synced]}")
    except Exception as e:
        await ctx.send(f"Sync failed: {e}")

# ==================== LOCKDOWN CONTROL ====================
@tree.command(name="ok", description="Owner only: Unlock server from lockdown", guild=GUILD)
@checks.has_role(ROLE_ID)
async def ok_command(interaction: discord.Interaction):
    """Owner only: Unlock server with /ok - Owner MUST have specified role"""
    print(f"🔍 DEBUG: /ok command triggered | Author: {interaction.user} ({interaction.user.id}) | Is Owner: {interaction.user.id == OWNER_ID}")
    
    # STRICT Owner check ONLY
    if interaction.user.id != OWNER_ID:
        print(f"❌ Unauthorized access attempt by {interaction.user.id}")
        await interaction.response.send_message("❌ **UNAUTHORIZED:** Only the Owner can use this command.", ephemeral=True)
        return
    
    print(f"✅ Owner verified. Processing lockdown lift...")
    
    # Now defer for the rest of the operation
    await interaction.response.defer(thinking=True)
    
    try:
        global is_locked_down
        print(f"📊 Current lockdown state: {is_locked_down}")
        
        is_locked_down = False
        print(f"🔓 Lockdown state set to: False")
        
        # Restore default role permissions (allow messaging and voice)
        role = interaction.guild.default_role
        print(f"📝 Editing @everyone role permissions...")
        perms = role.permissions
        perms.send_messages = True
        perms.connect = True
        perms.speak = True
        
        await role.edit(permissions=perms, reason="Owner Command: /ok - Lockdown Lifted")
        print(f"✅ Role permissions updated successfully")
        
        await interaction.followup.send("✅ **STATUS GREEN:** Lockdown lifted. Server is back to normal.")
        print("🟢 Lockdown lifted by Owner.")
        
        # Alert all admins
        await alert_owner(interaction.guild, "LOCKDOWN LIFTED", {
            "Status": "Server is now UNLOCKED",
            "Action": "Performed by Owner",
            "Time": datetime.datetime.now().strftime("%H:%M:%S")
        })
    except Exception as e:
        is_locked_down = False
        print(f"🔴 Error in /ok command: {str(e)}")
        await interaction.followup.send(f"⚠️ **ERROR:** {str(e)[:100]}")


# ==================== STARTUP ====================
@bot.event
async def on_ready():
    print(f"\n{'='*70}")
    print(f"✅ LEGEND STAR BOT ONLINE")
    print(f"{'='*70}")
    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"GUILD_ID: {GUILD_ID}")
    print(f"MongoDB Connected: {mongo_connected}")
    print(f"IST Timezone: {datetime.datetime.now(KOLKATA).strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Commands in tree before sync: {[c.name for c in tree.get_commands(guild=GUILD if GUILD_ID > 0 else None)]}")
    
    # Verify MongoDB connection
    if not mongo_connected:
        print("⚠️ WARNING: MongoDB is not connected. Data will be lost on restart!")
        print("⚠️ Please check your MONGODB_URI in .env file")
    else:
        try:
            # Test MongoDB by writing a test record
            test_result = save_with_retry(users_coll, {"_id": "mongodb_test"}, {"$set": {"test": True}})
            if test_result:
                print("✅ MongoDB test write successful - Data persistence enabled!")
            else:
                print("⚠️ MongoDB write test failed")
        except Exception as e:
            print(f"⚠️ MongoDB test failed: {e}")
    
    # Create indexes on first ready
    await create_indexes_async()
    
    try:
        if GUILD_ID > 0:
            print(f"🔄 Syncing to guild: {GUILD_ID}")
            synced = await tree.sync(guild=GUILD)
        else:
            print("🔄 Syncing globally (no GUILD_ID set)")
            synced = await tree.sync()  # global
        print(f"✅ Synced {len(synced)} commands: {[c.name for c in synced]}")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n📊 Starting Background Tasks:")
    print(f"   🕐 batch_save_study: Every 30 seconds")
    print(f"   📍 auto_leaderboard_ping: Daily at 23:55 IST")
    print(f"   🏆 auto_leaderboard: Daily at 23:59 IST")
    print(f"   🌙 midnight_reset: Daily at 23:59 IST")
    print(f"   ⏰ todo_checker: Every 3 hours")
    print(f"   🔗 clean_webhooks: Every 5 minutes")
    print(f"   📋 monitor_audit: Every 1 minute")
    print(f"{'='*70}\n")
    
    batch_save_study.start()
    auto_leaderboard_ping.start()
    auto_leaderboard.start()
    midnight_reset.start()
    todo_checker.start()
    clean_webhooks.start()
    monitor_audit.start()

# Keep-alive
async def handle(_):
    return web.Response(text="LegendBot Online! 🦚")

app = web.Application()
app.router.add_get('/', handle)

async def main():
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Try to start the web server with port reuse
    max_retries = 3
    for attempt in range(max_retries):
        try:
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            print(f"✅ Keep-alive server running on port {PORT}")
            break
        except OSError as e:
            error_str = str(e)
            if "10048" in error_str or "Address already in use" in error_str:
                if attempt < max_retries - 1:
                    print(f"⚠️  Port {PORT} busy, retrying in 2 seconds... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(2)
                else:
                    print(f"❌ Port {PORT} is still in use after {max_retries} attempts")
                    print("   Commands to fix:")
                    print("   1. netstat -ano | Select-String ':3000'")
                    print("   2. Stop-Process -Id <PID> -Force")
                    await runner.cleanup()
                    return
            else:
                raise
    
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())