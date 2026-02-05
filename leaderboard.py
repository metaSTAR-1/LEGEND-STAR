import datetime

KOLKATA = None  # Keep placeholder; main defines timezone if needed


def format_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def get_medal_emoji(position: int) -> str:
    # Updated medal logic:
    # 1 -> 💎👑, 2 -> 🥇, 3 -> 🥈, 4-10 -> 🥉, 11+ -> 🎯
    if position == 1:
        return "💎👑"
    if position == 2:
        return "🥇"
    if position == 3:
        return "🥈"
    if 4 <= position <= 10:
        return "🥉"
    return "🎯"


def generate_leaderboard_text(cam_on_list, cam_off_list):
    now = datetime.datetime.now().strftime("%d %b %Y | %I:%M %p")

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
✨ Auto Generated at **11:55 PM**
🔄 Daily Reset at **11:59 PM**
🔥 Keep Grinding Legends!
"""
    return text


def user_rank(username: str, cam_on_data, cam_off_data):
    # sort descending by minutes
    cam_on_sorted = sorted(cam_on_data, key=lambda x: x[1], reverse=True)
    cam_off_sorted = sorted(cam_off_data, key=lambda x: x[1], reverse=True)

    result = []
    result.append("╔══════════════════════╗")
    result.append("      🏆 YOUR RANK 🏆")
    result.append("╚══════════════════════╝")
    result.append(f"👤 User: {username}")
    result.append("━━━━━━━━━━━━━━━━━━━━━━")

    # CAM ON
    cam_on_users = [u[0] for u in cam_on_sorted]
    if username in cam_on_users:
        rank = cam_on_users.index(username) + 1
        mins = cam_on_sorted[rank - 1][1]
        medal = get_medal_emoji(rank)
        result.append("🎥 CAM ON")
        result.append(f"{medal} Rank: #{rank} / {len(cam_on_sorted)}")
        result.append(f"⏱ Time: {format_time(mins)}")
        result.append("")
    else:
        result.append("🎥 CAM ON")
        result.append("❌ Not active today")
        result.append("")

    # CAM OFF
    cam_off_users = [u[0] for u in cam_off_sorted]
    if username in cam_off_users:
        rank = cam_off_users.index(username) + 1
        mins = cam_off_sorted[rank - 1][1]
        medal = get_medal_emoji(rank)
        result.append("📴 CAM OFF")
        result.append(f"{medal} Rank: #{rank} / {len(cam_off_sorted)}")
        result.append(f"⏱ Time: {format_time(mins)}")
    else:
        result.append("📴 CAM OFF")
        result.append("❌ Not active today")

    result.append("")
    result.append("🔥 Keep pushing. Legends rise daily!")
    return "\n".join(result)
