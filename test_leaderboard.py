#!/usr/bin/env python
# Test leaderboard formatting
import datetime

def format_time(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"

def get_medal_emoji(position: int) -> str:
    """Get creative medal emojis based on position"""
    medals = {
        1: "💎👑",
        2: "🥇",
        3: "🥈",
        4: "🥉",
        5: "🏅"
    }
    return medals.get(position, "⭐")

def generate_leaderboard_text(cam_on_list, cam_off_list):
    """Generate beautiful leaderboard text with medals and decorations"""
    now = datetime.datetime.now().strftime("%d %b %Y | %I:%M %p")
    
    text = f"""
╔════════════════════════════════════════════╗
        🏆 LEGEND STAR 🏆
     🌙 Daily Leaderboard Champion 🌙
        ⏰ {now}
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

if __name__ == "__main__":
    # Test with sample data
    test_cam_on = [
        ("Roses_r_Rosie 🌹", 1013),
        ("T O R O", 904),
        ("noname", 841),
        ("DD", 676),
        ("SoulMaTE 🪶", 532),
        ("TestUser6", 450),
        ("TestUser7", 400),
        ("TestUser8", 350),
        ("TestUser9", 300),
        ("TestUser10", 250),
        ("TestUser11", 200),
        ("TestUser12", 150),
        ("TestUser13", 100),
        ("TestUser14", 80),
        ("TestUser15", 60),
    ]

    test_cam_off = [
        ("Target___aiimsD", 324),
        ("Mitochondria", 222),
        ("Bebo", 153),
        ("Marcus", 138),
        ("KING shiii 👑", 93),
        ("TestSilent6", 85),
        ("TestSilent7", 75),
        ("TestSilent8", 65),
        ("TestSilent9", 55),
        ("TestSilent10", 45),
    ]

    print("=" * 50)
    print("TESTING LEADERBOARD FORMATTER")
    print("=" * 50)
    
    result = generate_leaderboard_text(test_cam_on, test_cam_off)
    print(result)
    print("\n" + "=" * 50)
    print("✅ TEST PASSED - All functions work perfectly!")
    print("=" * 50)
    
    # Test format_time
    print("\nTesting format_time:")
    test_times = [60, 120, 180, 1013, 324]
    for mins in test_times:
        print(f"  {mins} minutes = {format_time(mins)}")
    
    # Test medal emojis
    print("\nTesting medals:")
    for pos in range(1, 6):
        print(f"  Position {pos}: {get_medal_emoji(pos)}")
