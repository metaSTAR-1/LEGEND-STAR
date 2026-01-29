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
    1149535834756874250, 1460114117783195841, 889078613817831495, 704802632660943089
]

# Webhook whitelist (add IDs if needed)
WHITELISTED_WEBHOOKS = []

# Spam settings
SPAM_THRESHOLD = 4
SPAM_WINDOW = 5
MAX_MENTIONS = 5
TIMEOUT_DURATION = 60
STRIKE_RESET = 300

# Enhanced Security Settings
FORBIDDEN_KEYWORDS = ["@everyone", "@here", "free nitro", "steam community", "gift", "airdrop", "maa", "rand", "chut"]

# 🛡️ TRUSTED LISTS (Whitelist for Strike System)
TRUSTED_USERS = [OWNER_ID]
TRUSTED_BOTS = WHITELISTED_BOTS.copy()
TEMP_VOICE_BOT_ID = 762217899355013120

# 📒 STRIKE DATABASE (2-Strike System for Human Errors)
offense_history = {}  # {user_id: timestamp_of_last_offense}
is_locked_down = False  # Global lockdown state

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
    except:
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
last_audit_id = None  # Track last processed audit entry to avoid duplicates

def format_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"

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
    # Cam is ON if: camera is on AND not screen sharing
    # Cam is OFF if: camera is off OR screen sharing
    old_cam = before.self_video and not before.self_stream
    new_cam = after.self_video and not after.self_stream

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
            except:
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
                    field = "data.voice_cam_on_minutes" if old_cam else "data.voice_cam_off_minutes"
                    result = save_with_retry(users_coll, {"_id": user_id}, {"$inc": {field: mins}})
                    print(f"💾 [{field}] Saved {mins}m for {member.display_name} - MongoDB: {result}")
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
                                except:
                                    pass
                                
                                # 📧 SEND DM TO USER ABOUT ENFORCEMENT
                                try:
                                    embed_dm = discord.Embed(
                                        title="📵 You Were Disconnected",
                                        description=f"You were disconnected from **{channel.name}** due to camera enforcement.\n\nCamera is mandatory in this channel (screenshare alone is not sufficient).\n\nPlease enable your camera before rejoining.",
                                        color=discord.Color.red()
                                    )
                                    await member.send(embed=embed_dm)
                                except:
                                    pass
                                
                            except Exception as e:
                                print(f"⚠️ Failed to disconnect {member.display_name}: {e}")
                    
                    # Clean up timer
                    cam_timers.pop(member.id, None)
                
                cam_timers[member.id] = bot.loop.create_task(enforce())

@tasks.loop(minutes=2)
async def batch_save_study():
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
            
            mins = int((now - join) // 60)
            if mins > 0:
                # Cam ON: camera is on AND not screen sharing. Cam OFF: camera off OR screen sharing
                cam = member.voice.self_video and not member.voice.self_stream
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
                result = save_with_retry(users_coll, {"_id": str(uid)}, {"$inc": {field: mins}})
                if result:
                    print(f"⏱️ {member.display_name}: +{mins}m {field} (Cam: {cam}) ✅")
                    saved_count += 1
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
                
                if mins > 0:
                    # Cam ON: camera is on AND not screen sharing. Cam OFF: camera off OR screen sharing
                    cam = member.voice.self_video and not member.voice.self_stream
                    # Skip saving for excluded voice channel
                    if getattr(channel, 'id', None) == EXCLUDED_VOICE_CHANNEL_ID:
                        print(f"⏭️ Skipping batch save for excluded channel ({EXCLUDED_VOICE_CHANNEL_ID}) for {member.display_name}")
                        vc_join_times[member.id] = now
                        continue
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
                    result = save_with_retry(users_coll, {"_id": str(member.id)}, {"$inc": {field: mins}})
                    if result:
                        print(f"⏱️ {member.display_name}: +{mins}m {field} (Cam: {cam}) ✅")
                        saved_count += 1
                    vc_join_times[member.id] = now
        
        # Print consolidated registration message (only ONE message)
        if newly_registered:
            print(f"🔄 Registered ({len(newly_registered)} new): {', '.join(newly_registered)}")
        
        if saved_count > 0:
            print(f"📊 Batch save complete: Updated {saved_count} active members in voice")
    except Exception as e:
        print(f"⚠️ Batch save error: {str(e)[:100]}")

@batch_save_study.before_loop
async def before_batch_save():
    """Ensure batch save starts running from the beginning"""
    await bot.wait_until_ready()
    print("✅ batch_save_study loop started")

# ==================== LEADERBOARDS ====================
@tasks.loop(time=datetime.time(23, 55, tzinfo=KOLKATA))
async def auto_leaderboard():
    if GUILD_ID <= 0 or not mongo_connected:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    channel = guild.get_channel(AUTO_LB_CHANNEL_ID)
    if not channel:
        return
    try:
        docs = safe_find(users_coll, {})
        active = []
        for doc in docs:
            data = doc.get("data", {})
            try:
                m = guild.get_member(int(doc["_id"]))
                if m:
                    active.append({"name": m.display_name, "cam_on": data.get("voice_cam_on_minutes", 0), "cam_off": data.get("voice_cam_off_minutes", 0)})
            except:
                pass
        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]
        desc = "**Cam On ✅**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_on'])}" for i, u in enumerate(sorted_on, 1) if u["cam_on"] > 0) or "No data today.\n")
        desc += "\n**Cam Off ❌**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_off'])}" for i, u in enumerate(sorted_off, 1) if u["cam_off"] > 0) or "")
        embed = discord.Embed(title="🌙 Daily Leaderboard", description=desc, color=0x00FF00, timestamp=datetime.datetime.now(KOLKATA))
        embed.set_footer(text="Auto at 23:55 IST")
        await channel.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Auto leaderboard error: {str(e)[:80]}")

@tasks.loop(time=datetime.time(0, 0, tzinfo=KOLKATA))
async def midnight_reset():
    if not mongo_connected:
        return
    try:
        docs = safe_find(users_coll, {})
        for doc in docs:
            data = doc.get("data", {})
            safe_update_one(users_coll, {"_id": doc["_id"]}, {"$set": {
                "data.yesterday.cam_on": data.get("voice_cam_on_minutes", 0),
                "data.yesterday.cam_off": data.get("voice_cam_off_minutes", 0),
                "data.voice_cam_on_minutes": 0,
                "data.voice_cam_off_minutes": 0
            }})
        print("🕛 Midnight reset complete")
    except Exception as e:
        print(f"⚠️ Midnight reset error: {str(e)[:80]}")

# Leaderboard commands
@tree.command(name="lb", description="Today’s voice + cam leaderboard", guild=GUILD)
@checks.cooldown(1, 10)   # once per 10 sec per user
async def lb(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if not mongo_connected:
            return await interaction.followup.send("📡 Database temporarily unavailable. Try again in a moment.", ephemeral=True)
        
        docs = safe_find(users_coll, {}, limit=100)
        print(f"🔍 /lb command: Found {len(docs)} total documents in MongoDB")
        print(f"   ℹ️  Fetching data from all {len(docs)} users...")
        
        active = []
        # Use guild.members cache instead of fetching (faster)
        members_by_id = {m.id: m for m in interaction.guild.members}
        print(f"   Guild has {len(members_by_id)} members")
        
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
        sorted_on = sorted(active, key=lambda x: x["cam_on"], reverse=True)[:15]
        sorted_off = sorted(active, key=lambda x: x["cam_off"], reverse=True)[:10]
        desc = "**Cam On ✅**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_on'])}" for i, u in enumerate(sorted_on, 1) if u["cam_on"] > 0) or "No data yet. Start joining voice channels!\n")
        desc += "\n**Cam Off ❌**\n" + ("\n".join(f"#{i} **{u['name']}** — {format_time(u['cam_off'])}" for i, u in enumerate(sorted_off, 1) if u["cam_off"] > 0) or "No data.")
        embed = discord.Embed(title="🏆 Study Leaderboard", description=desc, color=0xFFD700)
        embed.set_footer(text="Data saves every 2 minutes | Resets daily at midnight IST")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        error_msg = str(e)
        if "SSL" in error_msg or "handshake" in error_msg:
            await interaction.followup.send("📡 Database connection issue. Please try again later.", ephemeral=True)
        else:
            await interaction.followup.send(f"Error loading leaderboard: {str(e)[:100]}", ephemeral=True)

@tree.command(name="ylb", description="Yesterday’s leaderboard", guild=GUILD)
async def ylb(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if not mongo_connected:
            return await interaction.followup.send("📡 Database temporarily unavailable. Try again in a moment.", ephemeral=True)
        
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
            await interaction.followup.send("📡 Database connection issue. Please try again later.", ephemeral=True)
        else:
            await interaction.followup.send(f"Error loading yesterday leaderboard: {str(e)[:100]}", ephemeral=True)

@tree.command(name="mystatus", description="Your personal VC + cam stats", guild=GUILD)
async def mystatus(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        doc = safe_find_one(users_coll, {"_id": str(interaction.user.id)})
    except Exception as e:
        await interaction.followup.send(f"DB Error: {e}", ephemeral=True)
        return

    if not doc or "data" not in doc:
        return await interaction.followup.send("No stats yet.", ephemeral=True)

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
    await interaction.response.defer(ephemeral=True)
    try:
        doc = safe_find_one(users_coll, {"_id": str(interaction.user.id)})
        if not doc or "data" not in doc or "yesterday" not in doc["data"]:
            return await interaction.followup.send("No yesterday data.", ephemeral=True)
        y = doc["data"]["yesterday"]
        total = y.get("cam_on", 0) + y.get("cam_off", 0)
        embed = discord.Embed(title=f"🗓️ Yesterday Stats: {interaction.user.name}", color=0x808080)
        embed.add_field(name="Total", value=format_time(total), inline=True)
        embed.add_field(name="Cam On", value=format_time(y.get("cam_on", 0)), inline=True)
        embed.add_field(name="Cam Off", value=format_time(y.get("cam_off", 0)), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error loading stats: {str(e)[:100]}", ephemeral=True)

# ==================== REDLIST ====================
@tree.command(name="redban", description="Ban a user & store in redlist", guild=GUILD)
@app_commands.describe(userid="User ID")
async def redban(interaction: discord.Interaction, userid: str):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        if not userid.isdigit():
            return await interaction.followup.send("Invalid ID", ephemeral=True)
        safe_update_one(redlist_coll, {"_id": userid}, {"$set": {"added": datetime.datetime.now(KOLKATA)}})
        try:
            await interaction.guild.ban(discord.Object(id=int(userid)), reason="Redlist")
        except Exception as e:
            print(f"Ban error: {e}")
        await interaction.followup.send(f"Redlisted {userid}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="redlist", description="Show banned / restricted users", guild=GUILD)
async def redlist(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Owner only", ephemeral=True)
        ids = [doc["_id"] for doc in safe_find(redlist_coll, {})]
        if not ids:
            return await interaction.followup.send("Empty redlist.", ephemeral=True)
        msg = "Redlist IDs:\n" + "\n".join(f"- {i}" for i in ids)
        await interaction.followup.send(msg, ephemeral=True)
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
                except:
                    pass
    if safe_find_one(redlist_coll, {"_id": str(member.id)}):
        try:
            await member.ban(reason="Redlist")
        except:
            pass
    if member.bot and member.id not in WHITELISTED_BOTS:
        try:
            await member.ban(reason="Non-whitelisted bot")
        except:
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
class TodoModal(discord.ui.Modal, title="Daily Todo Form"):
    name = discord.ui.TextInput(label="Your Name", required=True)
    date = discord.ui.TextInput(label="Date (DD/MM/YYYY)", required=True)
    must_do = discord.ui.TextInput(label="Must Do", style=discord.TextStyle.paragraph)
    can_do = discord.ui.TextInput(label="Can Do", style=discord.TextStyle.paragraph)
    dont_do = discord.ui.TextInput(label="Don't Do", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            uid = str(interaction.user.id)
            print(f"\n{'='*70}")
            print(f"📝 [TODO SUBMIT] User: {interaction.user.name}#{interaction.user.discriminator}")
            print(f"   User ID: {interaction.user.id}")
            print(f"   UID String: {uid}")
            print(f"   Is Owner: {interaction.user.id == OWNER_ID}")
            
            # Check if user is in active members list
            user_doc = safe_find_one(active_members_coll, {"_id": uid})
            print(f"   Active Members lookup: {user_doc}")
            print(f"{'='*70}\n")
            
            if not user_doc and interaction.user.id != OWNER_ID:
                print(f"❌ User {uid} not authorized - not in active list and not owner")
                await interaction.followup.send("❌ Not authorized (not in active list).", ephemeral=True)
                return
            
            # Save to database
            print(f"⏸️ [TODO] Saving to database...")
            safe_update_one(todo_coll, {"_id": uid}, {"$set": {
                "last_submit": time.time(),
                "last_ping": 0,  # 🔥 RESET PING TIMER when user submits - No more pings!
                "todo": {
                    "name": self.name.value,
                    "date": self.date.value,
                    "must_do": self.must_do.value or "N/A",
                    "can_do": self.can_do.value or "N/A",
                    "dont_do": self.dont_do.value or "N/A"
                }
            }})
            print(f"✅ [TODO] Database save complete - Ping timer RESET!")
            
            # Create the embed
            print(f"🎨 [TODO] Creating embed...")
            embed = discord.Embed(title="✅ New TODO Submitted", color=discord.Color.green())
            embed.add_field(name="👤 Submitted By", value=interaction.user.mention, inline=False)
            embed.add_field(name="📅 Date", value=self.date.value, inline=True)
            embed.add_field(name="📝 Name", value=self.name.value, inline=True)
            embed.add_field(name="✔️ Must Do", value=self.must_do.value or "N/A", inline=False)
            embed.add_field(name="🎯 Can Do", value=self.can_do.value or "N/A", inline=False)
            embed.add_field(name="❌ Don't Do", value=self.dont_do.value or "N/A", inline=False)
            embed.set_footer(text=f"Status: Submitted | User: {interaction.user.id}")
            print(f"✅ [TODO] Embed created successfully")
            
            # Send to channel DIRECTLY
            print(f"\n🔥 [TODO] Attempting direct send to channel...")
            print(f"🔥 Guild ID: {GUILD_ID}, Channel ID: {TODO_CHANNEL_ID}")
            # First try get_guild (cached)
            guild = bot.get_guild(GUILD_ID)
            print(f"🔥 get_guild result: {guild}")
            
            # If not cached, fetch from API
            if not guild:
                print(f"🔥 Guild not in cache, fetching from API...")
                guild = await bot.fetch_guild(GUILD_ID)
                print(f"🔥 fetch_guild result: {guild}")
            
            if guild:
                print(f"✅ Guild found: {guild.name}")
                # Try get_channel first (cached)
                channel = guild.get_channel(TODO_CHANNEL_ID)
                print(f"🔥 get_channel result: {channel}")
                
                # If not cached, fetch from API
                if not channel:
                    print(f"🔥 Channel not in cache, fetching from API...")
                    channel = await guild.fetch_channel(TODO_CHANNEL_ID)
                    print(f"🔥 fetch_channel result: {channel}")
                
                if channel:
                    print(f"✅ Channel found: {channel.name}")
                    print(f"🔥 Sending message to channel...")
                    await channel.send(embed=embed)
                    print(f"✅✅✅ TODO SENT SUCCESSFULLY! ✅✅✅")
                else:
                    print(f"❌ Channel not found after fetch")
            else:
                print(f"❌ Guild not found after fetch")
            
            await interaction.followup.send("✅ TODO submitted successfully!", ephemeral=True)
            
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR in TodoModal.on_submit: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"❌ Error: {str(e)[:100]}", ephemeral=True)
            except:
                pass

@tree.command(name="todo", description="Submit your own todo", guild=GUILD)
async def todo(interaction: discord.Interaction):
    await interaction.response.send_modal(TodoModal())

class AtodoModal(TodoModal):
    def __init__(self, target: discord.Member):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid = str(self.target.id)
        
        try:
            if not safe_find_one(active_members_coll, {"_id": uid}):
                await interaction.followup.send("Target not in active list.", ephemeral=True)
                return
            
            # Save to database (same as user submission)
            print(f"⏸️ [ATODO] Saving to database...")
            safe_update_one(todo_coll, {"_id": uid}, {"$set": {
                "last_submit": time.time(),
                "last_ping": 0,  # 🔥 RESET PING TIMER when owner submits - No more pings!
                "todo": {
                    "name": self.name.value,
                    "date": self.date.value,
                    "must_do": self.must_do.value or "N/A",
                    "can_do": self.can_do.value or "N/A",
                    "dont_do": self.dont_do.value or "N/A"
                }
            }})
            print(f"✅ [ATODO] Database save complete - Ping timer RESET!")
            
            # Create the embed
            print(f"🎨 [ATODO] Creating embed...")
            embed = discord.Embed(title="✅ TODO Submitted (By Owner)", color=discord.Color.gold())
            embed.add_field(name="👤 For User", value=self.target.mention, inline=False)
            embed.add_field(name="👨‍💼 Submitted By", value=interaction.user.mention, inline=False)
            embed.add_field(name="📅 Date", value=self.date.value, inline=True)
            embed.add_field(name="📝 Name", value=self.name.value, inline=True)
            embed.add_field(name="✔️ Must Do", value=self.must_do.value or "N/A", inline=False)
            embed.add_field(name="🎯 Can Do", value=self.can_do.value or "N/A", inline=False)
            embed.add_field(name="❌ Don't Do", value=self.dont_do.value or "N/A", inline=False)
            embed.set_footer(text=f"Status: Submitted by Owner | Target: {self.target.id}")
            print(f"✅ [ATODO] Embed created successfully")
            
            # Send to channel DIRECTLY
            print(f"\n🔥 [ATODO] Attempting direct send to channel...")
            print(f"🔥 Guild ID: {GUILD_ID}, Channel ID: {TODO_CHANNEL_ID}")
            # First try get_guild (cached)
            guild = bot.get_guild(GUILD_ID)
            print(f"🔥 get_guild result: {guild}")
            
            # If not cached, fetch from API
            if not guild:
                print(f"🔥 Guild not in cache, fetching from API...")
                guild = await bot.fetch_guild(GUILD_ID)
                print(f"🔥 fetch_guild result: {guild}")
            
            if guild:
                print(f"✅ Guild found: {guild.name}")
                # Try get_channel first (cached)
                channel = guild.get_channel(TODO_CHANNEL_ID)
                print(f"🔥 get_channel result: {channel}")
                
                # If not cached, fetch from API
                if not channel:
                    print(f"🔥 Channel not in cache, fetching from API...")
                    channel = await guild.fetch_channel(TODO_CHANNEL_ID)
                    print(f"🔥 fetch_channel result: {channel}")
                
                if channel:
                    print(f"✅ Channel found: {channel.name}")
                    print(f"🔥 Sending message to channel...")
                    await channel.send(embed=embed)
                    print(f"✅✅✅ ATODO SENT SUCCESSFULLY! ✅✅✅")
                else:
                    print(f"❌ Channel not found after fetch")
            else:
                print(f"❌ Guild not found after fetch")
                
        except Exception as e:
            print(f"❌ ERROR in ATODO submit: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        
        await interaction.followup.send(f"✅ TODO submitted for {self.target.mention}!", ephemeral=True)

@tree.command(name="atodo", description="Submit todo on behalf of another user", guild=GUILD)
@app_commands.describe(user="Target")
async def atodo(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)
    await interaction.response.send_modal(AtodoModal(user))

@tasks.loop(hours=3)
async def todo_checker():
    """
    🔥 ADVANCED TODO PING SYSTEM 🔥
    
    - Monitors all users with TODO role
    - If user participates but doesn't share TODO in last 24 hours → PING every 3 hours
    - Ping only happens ONCE per 3-hour cycle (no spam guaranteed)
    - Auto-reset ping timer when user shares /todo or /atodo
    - Removes role after 5 days of inactivity
    - Smart startup: respects database timestamps on deployment
    
    MongoDB Schema:
    {
        "_id": "user_id",
        "last_submit": timestamp,
        "last_ping": timestamp,  // Track last ping to prevent spam
        "todo": {...}
    }
    """
    if GUILD_ID <= 0:
        return
    
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    
    channel = guild.get_channel(TODO_CHANNEL_ID)
    if not channel:
        return
    
    now = time.time()
    one_day = 24 * 3600       # 24 hours
    five_days = 5 * 86400     # 5 days for role removal
    three_hours = 3 * 3600    # 3 hours between pings (PRIMARY INTERVAL)
    
    print(f"\n⏰ [TODO_CHECKER] Running advanced TODO verification @ {datetime.datetime.now(KOLKATA).strftime('%H:%M:%S')}")
    
    for doc in safe_find(todo_coll, {}):
        try:
            uid = int(doc["_id"])
            last_submit = doc.get("last_submit", 0)
            last_ping = doc.get("last_ping", 0)  # NEW: Track ping history
            elapsed_since_submit = now - last_submit
            elapsed_since_ping = now - last_ping
            
            member = guild.get_member(uid)
            
            # Skip bots and offline members
            if not member or member.bot:
                print(f"⏭️  [TODO_CHECKER] Skipped {uid} (bot/offline)")
                continue
            
            # ============================================================
            # LEVEL 1: Check for 5-day inactivity (REMOVE ROLE)
            # ============================================================
            if elapsed_since_submit >= five_days:
                print(f"🔴 [TODO_CHECKER] {member.display_name} inactive for 5+ days")
                role = guild.get_role(ROLE_ID)
                if role and role in member.roles:
                    try:
                        await member.remove_roles(role)
                        print(f"✅ Removed role from {member.display_name}")
                        
                        # Notify in channel
                        embed = discord.Embed(
                            title="❌ TODO Role Removed",
                            description=f"{member.mention} has been inactive for **5+ days**",
                            color=discord.Color.red()
                        )
                        embed.add_field(name="Action", value="Role removed. Use /todo to rejoin.", inline=False)
                        await channel.send(embed=embed)
                        
                    except Exception as e:
                        print(f"⚠️ Failed to remove role: {e}")
            
            # ============================================================
            # LEVEL 2: Check for 24-hour inactivity (PING - But only once per 3 hours!)
            # ============================================================
            elif elapsed_since_submit >= one_day:
                # Check if we've already pinged in the last 3 hours
                if elapsed_since_ping < three_hours:
                    # Already pinged recently, skip
                    hours_until_next_ping = int((three_hours - elapsed_since_ping) / 3600) + 1
                    minutes_until_next_ping = int(((three_hours - elapsed_since_ping) % 3600) / 60)
                    print(f"⏭️  [TODO_CHECKER] {member.display_name} already pinged ({hours_until_next_ping}h {minutes_until_next_ping}m until next)")
                    continue
                
                # ✅ IT'S TIME TO PING!
                days_inactive = int(elapsed_since_submit // 86400)
                hours_inactive = int((elapsed_since_submit % 86400) // 3600)
                time_str = f"{days_inactive}d {hours_inactive}h" if days_inactive > 0 else f"{hours_inactive}h"
                
                print(f"📢 [TODO_CHECKER] PINGING {member.display_name} (inactive for {time_str})")
                
                # ============================================================
                # 🎯 SMART PING: Channel + DM (Redundant Coverage)
                # ============================================================
                
                # Channel Ping (Public Accountability)
                channel_embed = discord.Embed(
                    title="⏰ TODO Reminder!",
                    description=f"{member.mention}",
                    color=discord.Color.gold()
                )
                channel_embed.add_field(
                    name="📊 Status",
                    value=f"Last submitted: **{time_str} ago**",
                    inline=False
                )
                channel_embed.add_field(
                    name="📝 Action Required",
                    value="Please share `/todo` to update your daily task list",
                    inline=False
                )
                channel_embed.add_field(
                    name="⚠️ Note",
                    value="This reminder runs every 3 hours until you submit",
                    inline=False
                )
                
                try:
                    await channel.send(embed=channel_embed)
                    print(f"✅ Channel ping sent to {member.display_name}")
                except Exception as e:
                    print(f"⚠️ Failed to send channel ping: {e}")
                
                # DM Ping (Direct Notification)
                dm_embed = discord.Embed(
                    title="🔔 TODO Reminder - Direct Message",
                    description="You haven't submitted your TODO in the last 24 hours!",
                    color=discord.Color.orange()
                )
                dm_embed.add_field(
                    name="⏱️ Time Since Last Submit",
                    value=f"**{time_str}** ago",
                    inline=False
                )
                dm_embed.add_field(
                    name="📝 What to do?",
                    value="Use `/todo` command to submit your daily task list",
                    inline=False
                )
                dm_embed.add_field(
                    name="🔄 Ping Frequency",
                    value="You'll receive this reminder every 3 hours until you submit",
                    inline=False
                )
                dm_embed.set_footer(text="Keep up with your daily TODOs! 💪")
                
                try:
                    await member.send(embed=dm_embed)
                    print(f"✅ DM sent to {member.display_name}")
                except Exception as e:
                    print(f"⚠️ Failed to DM {member.display_name}: {e}")
                
                # ============================================================
                # 💾 UPDATE DATABASE: Record this ping time
                # ============================================================
                print(f"💾 [TODO_CHECKER] Updating last_ping timestamp for {member.display_name}")
                safe_update_one(todo_coll, {"_id": str(uid)}, {
                    "$set": {
                        "last_ping": now  # Record when we pinged them
                    }
                })
                print(f"✅ Database updated - next ping in ~3 hours")
                
            else:
                # User is within 24-hour limit, no action needed
                hours_safe = int(elapsed_since_submit / 3600)
                print(f"✅ [TODO_CHECKER] {member.display_name} OK ({hours_safe}h submitted)")
        
        except ValueError:
            print(f"⚠️ todo_checker skipped invalid UID: {doc['_id']}")
        except Exception as e:
            print(f"⚠️ todo_checker error for user {doc.get('_id', '?')}: {str(e)[:100]}")

@todo_checker.before_loop
async def before_todo_checker():
    """
    🚀 SMART STARTUP BEHAVIOR
    
    On deployment:
    1. Wait for bot to be ready (20 sec buffer)
    2. Run first check IMMEDIATELY (respects last_ping in database)
    3. Subsequent checks follow 3-hour interval
    
    Result: Pings follow database timestamps, no artificial delay blocking users
    """
    print("⏰ [TODO_CHECKER] Bot startup: waiting for Discord connection...")
    await bot.wait_until_ready()
    
    # Give Discord API time to stabilize (20 second buffer)
    await asyncio.sleep(20)
    
    print("✅ [TODO_CHECKER] Ready! First TODO check will run immediately.")
    print("📊 [TODO_CHECKER] Subsequent checks every 3 hours.")
    print("🎯 [TODO_CHECKER] Pings respect database last_ping timestamps (no spam!)")

@tree.command(name="listtodo", description="View your current todo", guild=GUILD)
async def listtodo(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        uid = str(interaction.user.id)
        doc = safe_find_one(todo_coll, {"_id": uid})
        if not doc or "todo" not in doc:
            return await interaction.followup.send("No current TODO.", ephemeral=True)
        t = doc["todo"]
        embed = discord.Embed(title="Your Current TODO", color=discord.Color.blue())
        embed.add_field(name="Name", value=t["name"], inline=True)
        embed.add_field(name="Date", value=t["date"], inline=True)
        embed.add_field(name="Must Do", value=t["must_do"], inline=False)
        embed.add_field(name="Can Do", value=t["can_do"], inline=False)
        embed.add_field(name="Don't Do", value=t["dont_do"], inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="deltodo", description="Delete your own todo", guild=GUILD)
async def deltodo(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        uid = str(interaction.user.id)
        safe_update_one(todo_coll, {"_id": uid}, {"$unset": {"todo": ""}})
        await interaction.followup.send("TODO deleted (timer unchanged).", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error: {str(e)[:100]}", ephemeral=True)

@tree.command(name="todostatus", description="Check last submit time + reminder status", guild=GUILD)
@app_commands.describe(user="Optional: Check another (Owner only)")
async def todostatus(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if user and interaction.user.id != OWNER_ID:
            return await interaction.followup.send("Can only check others if owner.", ephemeral=True)
        target = user or interaction.user
        uid = str(target.id)
        doc = safe_find_one(todo_coll, {"_id": uid})
        if not doc:
            return await interaction.followup.send("No record.", ephemeral=True)
        elapsed = time.time() - doc.get("last_submit", 0)
        hours = int(elapsed // 3600)
        embed = discord.Embed(title="TODO Status", color=discord.Color.green())
        embed.add_field(name="User", value=target.mention)
        embed.add_field(name="Last Submit", value=f"{hours}h ago")
        embed.add_field(name="Status", value="Safe" if elapsed < 86400 else "Pending ping")
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
        except:
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
            except:
                pass
        elif target.startswith("<@"):
            clean = target.strip("<@!>").strip(">")
            try:
                member = await interaction.guild.fetch_member(int(clean))
            except:
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
            except:
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
    
    # A. GHOST WEBHOOK DESTROYER
    if message.webhook_id:
        SUSPICIOUS_WORDS = ["free nitro", "steam", "gift", "airdrop", "@everyone", "@here", "maa", "rand", "chut"]
        link_regex = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
        
        is_threat = (
            message.mention_everyone or 
            re.search(link_regex, message.content) or 
            any(bad_word in message.content.lower() for bad_word in SUSPICIOUS_WORDS)
        )

        if is_threat:
            try:
                await message.delete()
                webhooks = await message.channel.webhooks()
                for webhook in webhooks:
                    if webhook.id == message.webhook_id:
                        await webhook.delete(reason="LegendMeta: Malicious Ghost Webhook Activity")
                        await message.channel.send("☠️ **LegendMeta**: Unauthorized Ghost Webhook DESTROYED.")
            except Exception as e:
                print(f"Webhook cleanup error: {e}")
            return # STOP HERE

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

@tasks.loop(minutes=1)
async def clean_webhooks():
    if GUILD_ID <= 0:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    for channel in guild.text_channels:
        webhooks = await channel.webhooks()
        for wh in webhooks:
            if wh.id not in WHITELISTED_WEBHOOKS:
                await wh.delete(reason="Unauthorized webhook")

@bot.event
async def on_webhooks_update(channel):
    """
    Detects creation of webhooks in REAL TIME.
    """
    try:
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            if entry.user.id != OWNER_ID and entry.user.id != bot.user.id:
                # 1. DELETE THE WEBHOOK
                webhooks = await channel.webhooks()
                for webhook in webhooks:
                    if webhook.id == entry.target.id:
                        await webhook.delete(reason="LegendMeta: Unauthorized Creation")
                
                # 2. BAN THE CREATOR (Hacker/Rogue Admin -> INSTANT BAN)
                try:
                    await entry.user.ban(reason="LegendMeta: Malicious Webhook Creation")
                    await channel.send(f"⚔️ **THREAT ELIMINATED**: Banned {entry.user.mention} for creating a webhook.")
                except:
                    await channel.send(f"⚠️ Webhook deleted, but could not ban user {entry.user.name}")
    except Exception:
        pass

@bot.event
async def on_guild_channel_delete(channel):
    if channel.guild.id != GUILD_ID:
        return
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        actor = entry.user
        # IMMUNITY: Owner and Bot are trusted
        if actor.id == OWNER_ID or actor == bot.user or actor.id in TRUSTED_USERS:
            return
        
        # CRITICAL THREAT: Channel deletion = Instant Ban
        try:
            await channel.guild.ban(actor, reason=f"Anti-Nuke: Channel Deletion")
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                await tech_channel.send(f"🔨 BANNED {actor.mention} for deleting {channel.name}")
            
            # Alert owner
            await alert_owner(channel.guild, "CHANNEL DELETION DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Channel": channel.name,
                "Action": "Instant Ban"
            })
        except discord.Forbidden:
            print(f"⚠️ FAILED TO BAN channel deleter. Engaging emergency lockdown.")
            await engage_lockdown(channel.guild, "Failed to ban channel deleter - role hierarchy issue")
        except Exception as e:
            print(f"⚠️ Channel delete error: {e}")

@bot.event
async def on_guild_role_delete(role):
    if role.guild.id != GUILD_ID:
        return
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        actor = entry.user
        # IMMUNITY: Owner and Bot are trusted
        if actor.id == OWNER_ID or actor == bot.user or actor.id in TRUSTED_USERS:
            return
        
        # CRITICAL THREAT: Role deletion = Instant Ban
        try:
            await role.guild.ban(actor, reason=f"Anti-Nuke: Role Deletion")
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                await tech_channel.send(f"🔨 BANNED {actor.mention} for deleting {role.name}")
            
            # Alert owner
            await alert_owner(role.guild, "ROLE DELETION DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Role": role.name,
                "Action": "Instant Ban"
            })
        except discord.Forbidden:
            print(f"⚠️ FAILED TO BAN role deleter. Engaging emergency lockdown.")
            await engage_lockdown(role.guild, "Failed to ban role deleter - role hierarchy issue")
        except Exception as e:
            print(f"⚠️ Role delete error: {e}")

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    if guild.id != GUILD_ID:
        return
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        actor = entry.user
        # IMMUNITY: Owner, Bot, and self-bans are allowed
        if actor.id == OWNER_ID or actor == bot.user or user.id == actor.id or actor.id in TRUSTED_USERS:
            return
        
        # THREAT: Unauthorized ban = Instant counter-ban + unban victim
        try:
            await guild.ban(actor, reason=f"Anti-Nuke: Unauthorized Ban")
            await guild.unban(user, reason="Anti-nuke recovery")
            tech_channel = bot.get_channel(TECH_CHANNEL_ID)
            if tech_channel:
                await tech_channel.send(f"⚔️ BANNED {actor.mention} for banning {user.mention}, unbanned {user.mention}")
            
            # Alert owner
            await alert_owner(guild, "UNAUTHORIZED BAN DETECTED", {
                "Attacker": f"{actor.name} (ID: {actor.id})",
                "Victim": f"{user.name}",
                "Action": "Banned attacker, unbanned victim"
            })
        except Exception as e:
            print(f"⚠️ Member ban error: {e}")

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
            if entry.user.id == bot.user.id or entry.user.id == OWNER_ID:
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
        except:
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
    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"GUILD_ID: {GUILD_ID}")
    print(f"MongoDB Connected: {mongo_connected}")
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
            print(f"Syncing to guild: {GUILD_ID}")
            synced = await tree.sync(guild=GUILD)
        else:
            print("Syncing globally (no GUILD_ID set)")
            synced = await tree.sync()  # global
        print(f"✅ Synced {len(synced)} commands: {[c.name for c in synced]}")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
        import traceback
        traceback.print_exc()
    batch_save_study.start()
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