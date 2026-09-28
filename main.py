# ==============================================================================
# 🌟 STARDUST BOT — PRODUCTION v2.1
# Cross-domain cookie fix (GitHub Pages ↔ Render)
# ==============================================================================
import os, io, json, time, random, asyncio, secrets, datetime, traceback
from threading import Thread
from functools import wraps

import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ==============================================================================
# 🔐 CONFIGURATION
# ==============================================================================
DISCORD_TOKEN    = os.environ.get("DISCORD_TOKEN")
CLIENT_ID        = os.environ.get("DISCORD_CLIENT_ID")
CLIENT_SECRET    = os.environ.get("DISCORD_CLIENT_SECRET")
OAUTH_REDIRECT   = os.environ.get("OAUTH_REDIRECT", "https://stardust-bot.onrender.com/api/callback")
FRONTEND_URL     = os.environ.get("FRONTEND_URL", "https://zishutron.github.io").rstrip("/")
SESSION_SECRET   = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
DATA_DIR         = os.environ.get("STARDUST_DATA_DIR", "./data")
PORT             = int(os.environ.get("PORT", 8080))

if not DISCORD_TOKEN:
    raise SystemExit("❌ DISCORD_TOKEN env variable required.")

os.makedirs(DATA_DIR, exist_ok=True)

# Allowed CORS origins — frontend + localhost for dev
ALLOWED_ORIGINS = [
    FRONTEND_URL,
    FRONTEND_URL + "/Stardust-discord-bot",  # in case path is passed
    "https://zishutron.github.io",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:8080",
]

print(f"[CONFIG] FRONTEND_URL = {FRONTEND_URL}")
print(f"[CONFIG] OAUTH_REDIRECT = {OAUTH_REDIRECT}")
print(f"[CONFIG] DATA_DIR = {DATA_DIR}")

# ==============================================================================
# 💾 STORAGE LAYER
# ==============================================================================
def _fp(name): return os.path.join(DATA_DIR, f"{name}.json")

def load_data(name, default=None):
    p = _fp(name)
    if not os.path.exists(p):
        return default if default is not None else {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[STORAGE] {name}.json corrupt: {e}")
        try: os.rename(p, p + f".corrupt.{int(time.time())}")
        except Exception: pass
        return default if default is not None else {}

def save_data(name, data):
    p = _fp(name)
    tmp = p + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception as e:
        print(f"[STORAGE] Failed saving {name}: {e}")

SERVER_CONFIGS = load_data("server_configurations", {})
AUTO_RESPONSES = load_data("auto_responses", {})
BLOCK_LIST     = load_data("block_list", {"words": ["fuck","bitch","asshole","slut","dick","bastard"]})
SESSIONS       = load_data("sessions", {})

def persist_server_configs(): save_data("server_configurations", SERVER_CONFIGS)
def persist_auto_responses(): save_data("auto_responses", AUTO_RESPONSES)
def persist_block_list():     save_data("block_list", BLOCK_LIST)
def persist_sessions():       save_data("sessions", SESSIONS)

def guild_cfg(gid):
    gid = str(gid)
    SERVER_CONFIGS.setdefault(gid, {})
    return SERVER_CONFIGS[gid]

# ==============================================================================
# 🤖 BOT INIT
# ==============================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
XP_COOLDOWN = {}

# ==============================================================================
# 🎨 RANK TIERS
# ==============================================================================
def get_ff_rank(level):
    if level < 5:  return "🥉 Bronze I"
    if level < 10: return "🥉 Bronze II"
    if level < 15: return "🥈 Silver I"
    if level < 20: return "🥈 Silver II"
    if level < 25: return "🥇 Gold I"
    if level < 30: return "🥇 Gold II"
    if level < 35: return "💎 Platinum I"
    if level < 40: return "💎 Platinum II"
    if level < 45: return "💎 Diamond I"
    if level < 50: return "💎 Diamond II"
    if level < 60: return "🏆 Heroic"
    return "👑 Grandmaster"

# ==============================================================================
# 🖼️ IMAGE GENERATION
# ==============================================================================
def _font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ):
        try: return ImageFont.truetype(p, size)
        except Exception: continue
    return ImageFont.load_default()

def generate_welcome_card(member):
    desc = (
        "╭🎈━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "   ⭐  *𝑾𝒆𝒍𝒄𝒐𝒎𝒆 𝒕𝒐 𝑺𝒕𝒂𝒓𝒅𝒖𝒔𝒕 𝑪𝒂𝒇𝒆!* ⭐\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━🎈╯\n\n"
        f"𝖧𝖾𝗒 {member.mention}! (⁠◠⁠‿⁠◕⁠)\n\n"
        "*𝑾𝒆 𝒂𝒓𝒆 𝒔𝒐 𝒉𝒂𝒑𝒑𝒚 𝒕𝒐 𝒉𝒂𝒗𝒆 𝒚𝒐𝒖 𝒉𝒆𝒓𝒆!* (⁠≧⁠▽⁠≦⁠)\n"
        "*𝑮𝒓𝒂𝒃 𝒂 𝒄𝒖𝒑 𝒐𝒇 𝒄𝒐𝒇𝒇𝒆𝒆, 𝒄𝒉𝒊𝒍𝒍, 𝒂𝒏𝒅 𝒎𝒂𝒌𝒆 𝒏𝒆𝒘 𝒇𝒓𝒊𝒆𝒏𝒅𝒔!* (⁠✯⁠ᴗ⁠✯⁠)\n\n"
        "📌 𝖣𝗈𝗇'𝗍 𝖿𝗈𝗋𝗀𝖾𝗍 𝗍𝗈 𝖼𝗁𝖾𝖼𝗄 𝗈𝗎𝗋 𝗋𝗎𝗅𝖾𝗌! (⁠◍⁠•⁠ᴗ⁠•⁠◍⁠)\n\n"
        f"**Identity:** {member.name} | **Member Count:** #{member.guild.member_count}"
    )
    embed = discord.Embed(description=desc, color=discord.Color.from_rgb(47, 49, 54))
    embed.set_image(url="https://cdn.discordapp.com/attachments/1515969029708320778/1516977720138006632/CofeeManga__A_Popular_Platform_for_Manga_Enthusiasts.jpg")
    return embed

def generate_rank_card(member, user_data, rank_pos):
    xp = user_data.get("xp", 0); lvl = user_data.get("level", 1)
    msg_count = user_data.get("messages", 0); next_xp = lvl * 375
    if lvl >= 50: tier = "Grandmaster"
    elif lvl >= 25: tier = "Elite Vibe"
    elif lvl >= 10: tier = "Gold Member"
    else: tier = "Rising Star"

    W, H = 950, 420
    card = Image.new("RGBA", (W, H), (245, 238, 227, 255))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([20,20,W-20,H-20], radius=30,
                           fill=(255,254,252,130), outline=(185,170,150,255), width=3)
    bx1,by1,bx2,by2 = 320,310,900,335
    draw.rounded_rectangle([bx1,by1,bx2,by2], radius=12, fill=(215,205,192,255))
    progress = min(xp/next_xp,1.0) if next_xp>0 else 1.0
    if progress>0:
        draw.rounded_rectangle([bx1,by1,bx1+int((bx2-bx1)*progress),by2], radius=12, fill=(84,62,49,255))
    try:
        r = requests.get(member.display_avatar.url, timeout=10)
        pfp = Image.open(io.BytesIO(r.content)).convert("RGBA").resize((210,210))
        mask = Image.new("L",(210,210),0); ImageDraw.Draw(mask).ellipse((0,0,210,210),fill=255)
        card.paste(ImageOps.fit(pfp,(210,210)), (50,50), mask=mask)
        draw.ellipse((46,46,264,264), outline=(150,125,105,255), width=4)
    except Exception as e: print(f"[RANK] {e}")
    tf, bf = _font(36), _font(26)
    tc, sc = (44,34,30,255), (74,58,50,255)
    draw.text((320,45),  f"@{member.name.lower()}", fill=tc, font=tf)
    draw.text((320,110), f"Level: {lvl}  •  Server Rank: #{rank_pos}", fill=sc, font=bf)
    draw.text((320,160), f"Performance: {tier}", fill=sc, font=bf)
    draw.text((320,210), f"Experience: {xp} / {next_xp} XP", fill=sc, font=bf)
    draw.text((320,260), f"Total Chats Logged: {msg_count:,} messages", fill=sc, font=bf)
    draw.text((W//2-110, 370), f"~ {member.guild.name.upper()} ~", fill=(115,95,80,255), font=bf)
    fp = io.BytesIO(); card.save(fp,"PNG"); fp.seek(0)
    return fp

def generate_levelup_card(member, new_lvl):
    W, H = 950, 320
    card = Image.new("RGBA",(W,H),(245,238,227,255)); draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([20,20,W-20,H-20], radius=25,
                           fill=(255,254,252,130), outline=(150,125,105,255), width=3)
    try:
        r = requests.get(member.display_avatar.url, timeout=10)
        pfp = Image.open(io.BytesIO(r.content)).convert("RGBA").resize((180,180))
        mask = Image.new("L",(180,180),0); ImageDraw.Draw(mask).ellipse((0,0,180,180),fill=255)
        card.paste(ImageOps.fit(pfp,(180,180)), (50,70), mask=mask)
        draw.ellipse((46,66,234,254), outline=(138,105,93,255), width=4)
    except Exception: pass
    tf, bf = _font(38), _font(26)
    tc, sc = (44,34,30,255), (74,58,50,255)
    draw.text((270,65),  "LEVEL UP!", fill=tc, font=tf)
    draw.text((270,130), f"@{member.name.lower()} has reached", fill=sc, font=bf)
    draw.text((270,185), f"LEVEL {new_lvl}", fill=tc, font=tf)
    draw.text((W//2-110, 270), f"~ {member.guild.name.upper()} ~", fill=(115,95,80,255), font=bf)
    fp = io.BytesIO(); card.save(fp,"PNG"); fp.seek(0)
    return fp

# ==============================================================================
# ⚙️ UTILITY
# ==============================================================================
def parse_duration(s):
    import re
    m = re.match(r"(\d+)([smhd])", s.lower().strip())
    if not m: return 0
    n, u = int(m.group(1)), m.group(2)
    return n * {"s":1, "m":60, "h":3600, "d":86400}[u]

# ==============================================================================
# 🎫 PERSISTENT VIEWS
# ==============================================================================
class TicketControlsView(discord.ui.View):
    def __init__(self, owner_id=None):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction, button):
        if not interaction.user.guild_permissions.manage_channels and interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Only staff can close.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing...")
        log = f"--- Transcript {interaction.channel.name} ---\n"
        async for m in interaction.channel.history(limit=500, oldest_first=True):
            log += f"[{m.created_at:%Y-%m-%d %H:%M}] {m.author.name}: {m.content}\n"
            for a in m.attachments: log += f"[ATT] {a.url}\n"
        path = f"/tmp/{interaction.channel.name}.txt"
        with open(path,"w",encoding="utf-8") as f: f.write(log)
        log_ch = discord.utils.get(interaction.guild.text_channels, name="ticket-logs")
        if log_ch:
            try:
                await log_ch.send(f"📜 Ticket closed by {interaction.user.mention}",
                                  file=discord.File(path))
            except Exception: pass
        try: os.remove(path)
        except Exception: pass
        await asyncio.sleep(3)
        try: await interaction.channel.delete()
        except Exception: pass

    @discord.ui.button(label="📜 Claim Ticket", style=discord.ButtonStyle.success, custom_id="ticket_claim")
    async def claim(self, interaction, button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        button.disabled = True
        button.label = f"📜 Claimed by {interaction.user.display_name}"
        button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"🙋 {interaction.user.mention} claimed this ticket.")

class TicketLauncherView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="📩 Create Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_launcher_btn")
    async def launch(self, interaction, button):
        guild, member = interaction.guild, interaction.user
        conf = load_data("ticket_config", {}).get(str(guild.id), {})
        staff_role_id = conf.get("staff_role_id")
        welcome_title = conf.get("welcome_title", "🎫 Support Ticket Opened")
        welcome_msg   = conf.get("welcome_msg", "Welcome! Describe your issue.")
        existing = discord.utils.get(guild.text_channels, name=f"🎫-ticket-{member.name.lower()}")
        if existing:
            return await interaction.response.send_message(f"⚠️ Already open: {existing.mention}", ephemeral=True)
        await interaction.response.send_message("🎫 Creating...", ephemeral=True)
        ow = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        ping = "Staff"
        if staff_role_id:
            role = guild.get_role(int(staff_role_id))
            if role:
                ow[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
                ping = role.mention
        try:
            ch = await guild.create_text_channel(f"🎫-ticket-{member.name}", overwrites=ow)
            embed = discord.Embed(title=welcome_title, description=f"Hey {member.mention},\n\n{welcome_msg}",
                                  color=discord.Color.blue(), timestamp=discord.utils.utcnow())
            embed.set_footer(text=f"Requested by {member.display_name}")
            await ch.send(content=f"{member.mention} | {ping}", embed=embed, view=TicketControlsView(owner_id=member.id))
            await interaction.edit_original_response(content=f"🚀 Ticket: {ch.mention}")
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ {e}")

# ==============================================================================
# 🎮 GAME VIEWS
# ==============================================================================
async def reward_coins(user_id, amount):
    eco = load_data("economy", {})
    uid = str(user_id)
    eco.setdefault(uid, {"balance": 0, "last_daily": 0, "inventory": [], "messages": 0})
    if "balance" not in eco[uid]: eco[uid]["balance"] = 0
    eco[uid]["balance"] += amount
    save_data("economy", eco)

class RPSView(discord.ui.View):
    def __init__(self, p1, p2=None):
        super().__init__(timeout=60)
        self.p1, self.p2 = p1, p2
        self.choices = {}

    async def resolve(self, interaction):
        c1 = self.choices[self.p1.id]
        c2 = self.choices.get(self.p2.id) if self.p2 else random.choice(["rock","paper","scissors"])
        p2_name = self.p2.display_name if self.p2 else "Stardust Bot"
        msg = f"🪨 **RPS Results**\n{self.p1.mention} → **{c1.upper()}**\n"
        msg += f"{self.p2.mention if self.p2 else '🤖 Bot'} → **{c2.upper()}**\n\n"
        if c1 == c2:
            msg += "🤝 **TIE!**"
        elif (c1=="rock" and c2=="scissors") or (c1=="paper" and c2=="rock") or (c1=="scissors" and c2=="paper"):
            msg += f"🏆 {self.p1.mention} **WINS!** +100 coins"
            await reward_coins(self.p1.id, 100)
        else:
            if self.p2:
                msg += f"🏆 {self.p2.mention} **WINS!** +100 coins"
                await reward_coins(self.p2.id, 100)
            else:
                msg += "🤖 **Bot wins!**"
        self.stop()
        try: await interaction.message.edit(content=msg, view=None)
        except Exception: pass

    async def pick(self, interaction, choice):
        valid = {self.p1.id}
        if self.p2: valid.add(self.p2.id)
        if interaction.user.id not in valid:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.choices[interaction.user.id] = choice
        await interaction.response.send_message("✅ Locked!", ephemeral=True)
        if not self.p2 or (self.p1.id in self.choices and self.p2.id in self.choices):
            await self.resolve(interaction)

    @discord.ui.button(label="Rock 🪨", style=discord.ButtonStyle.primary, custom_id="rps_rock")
    async def rock(self, i, b): await self.pick(i, "rock")
    @discord.ui.button(label="Paper 📄", style=discord.ButtonStyle.success, custom_id="rps_paper")
    async def paper(self, i, b): await self.pick(i, "paper")
    @discord.ui.button(label="Scissors ✂️", style=discord.ButtonStyle.danger, custom_id="rps_scissors")
    async def scissors(self, i, b): await self.pick(i, "scissors")

class TTTButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x, self.y = x, y
    async def callback(self, interaction):
        v: TTTView = self.view
        if interaction.user.id != v.current.id:
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        if v.board[self.y][self.x] != 0:
            return await interaction.response.send_message("Taken.", ephemeral=True)
        if v.current == v.p1:
            self.label, self.style = "❌", discord.ButtonStyle.danger
            v.board[self.y][self.x] = 1
        else:
            self.label, self.style = "⭕", discord.ButtonStyle.success
            v.board[self.y][self.x] = 2
        self.disabled = True
        w = v.winner()
        if w == 1:
            content = f"🏆 {v.p1.mention} wins! +200 coins"
            await reward_coins(v.p1.id, 200); v.stop(); v.disable()
        elif w == 2:
            pm = v.p2.mention if v.p2 else "🤖 Bot"
            content = f"🏆 {pm} wins! " + (f"+200 coins" if v.p2 else "")
            if v.p2: await reward_coins(v.p2.id, 200)
            v.stop(); v.disable()
        elif v.full():
            content = "🤝 Tie!"; v.stop(); v.disable()
        else:
            if v.p2:
                v.current = v.p2 if v.current == v.p1 else v.p1
                content = f"Turn: {v.current.mention}"
            else:
                v.bot_move()
                w2 = v.winner()
                if w2 == 2:
                    content = "🤖 Bot wins!"; v.stop(); v.disable()
                elif v.full():
                    content = "🤝 Tie!"; v.stop(); v.disable()
                else:
                    content = f"Your turn: {v.p1.mention}"
        await interaction.response.edit_message(content=content, view=v)

class TTTView(discord.ui.View):
    def __init__(self, p1, p2=None):
        super().__init__(timeout=180)
        self.p1, self.p2, self.current = p1, p2, p1
        self.board = [[0]*3 for _ in range(3)]
        for y in range(3):
            for x in range(3):
                self.add_item(TTTButton(x, y))
    def winner(self):
        for i in range(3):
            if self.board[i][0] == self.board[i][1] == self.board[i][2] != 0: return self.board[i][0]
            if self.board[0][i] == self.board[1][i] == self.board[2][i] != 0: return self.board[0][i]
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != 0: return self.board[0][0]
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != 0: return self.board[0][2]
        return 0
    def full(self): return all(c != 0 for row in self.board for c in row)
    def disable(self):
        for c in self.children:
            if isinstance(c, discord.ui.Button): c.disabled = True
    def bot_move(self):
        empties = [(x,y) for y in range(3) for x in range(3) if self.board[y][x] == 0]
        if empties:
            x,y = random.choice(empties)
            self.board[y][x] = 2
            for c in self.children:
                if isinstance(c, discord.ui.Button) and c.x==x and c.y==y:
                    c.label, c.style, c.disabled = "⭕", discord.ButtonStyle.success, True

class SlapView(discord.ui.View):
    def __init__(self, p1, p2=None):
        super().__init__(timeout=45)
        self.p1, self.p2 = p1, p2
        self.hp1, self.hp2 = 100, 100
        self.turn = p1
    @discord.ui.button(label="💥 SWING SLAP!", style=discord.ButtonStyle.danger, custom_id="slap_action")
    async def slap(self, interaction, button):
        if interaction.user.id != self.turn.id:
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        dmg = random.randint(15, 35)
        p2n = self.p2.mention if self.p2 else "🤖 Bot"
        log = ""
        if self.turn == self.p1:
            self.hp2 = max(0, self.hp2 - dmg)
            log = f"👋 {self.p1.mention} → {p2n} **{dmg} dmg**\n"
            if self.hp2 == 0:
                log += f"\n🏆 {self.p1.mention} wins! +250 coins"
                await reward_coins(self.p1.id, 250)
                self.stop(); return await interaction.response.edit_message(content=log, view=None)
            self.turn = self.p2 if self.p2 else self.p1
        else:
            self.hp1 = max(0, self.hp1 - dmg)
            log = f"👋 {self.p2.mention} → {self.p1.mention} **{dmg} dmg**\n"
            if self.hp1 == 0:
                log += f"\n🏆 {self.p2.mention} wins! +250 coins"
                await reward_coins(self.p2.id, 250)
                self.stop(); return await interaction.response.edit_message(content=log, view=None)
            self.turn = self.p1
        if not self.p2 and self.hp2 > 0:
            bd = random.randint(12, 30)
            self.hp1 = max(0, self.hp1 - bd)
            log += f"🤖 Bot → {self.p1.mention} **{bd} dmg**\n"
            if self.hp1 == 0:
                log += "\n💀 Bot wins!"; self.stop()
                return await interaction.response.edit_message(content=log, view=None)
        status = f"\n❤️ {self.p1.mention}: `{self.hp1}/100`\n💙 {p2n}: `{self.hp2}/100`\n\n👉 Turn: {self.turn.mention if self.p2 else self.p1.mention}"
        await interaction.response.edit_message(content=log+status, view=self)

# ==============================================================================
# 🎯 BOT EVENTS
# ==============================================================================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
        bot.add_view(TicketLauncherView())
        bot.add_view(TicketControlsView())
        print("✅ Persistent views registered")
    except Exception as e:
        print(f"[SYNC] {e}")
    try:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Stardust | /help"))
    except Exception: pass
    if not reminder_checker_loop.is_running():
        reminder_checker_loop.start()

# --------- UNIFIED on_message ---------
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    g_id = str(message.guild.id)

    # AFK
    afk = load_data("afk", {})
    auid = str(message.author.id)
    if auid in afk:
        del afk[auid]; save_data("afk", afk)
        try: await message.channel.send(embed=discord.Embed(description=f"✨ Welcome back {message.author.mention}!", color=0xF5EAE1), delete_after=5)
        except Exception: pass
    for u in message.mentions:
        uid = str(u.id)
        if uid in afk:
            try: await message.channel.send(embed=discord.Embed(description=f"💤 {u.name} is AFK: `{afk[uid]}`", color=0xF5EAE1), delete_after=7)
            except Exception: pass

    # Auto-responder
    if g_id in AUTO_RESPONSES:
        clean = message.content.lower().strip()
        if clean in AUTO_RESPONSES[g_id]:
            await message.channel.send(AUTO_RESPONSES[g_id][clean])
            return

    # AutoMod
    if SERVER_CONFIGS.get(g_id, {}).get("automod_enabled", True):
        clean = message.content.lower().strip()
        for w in BLOCK_LIST.get("words", []):
            if w and w in clean:
                try:
                    await message.delete()
                    alert = discord.Embed(title="🛡️ System Shield",
                                          description=f"⚠️ {message.author.mention}, blocked word detected.",
                                          color=discord.Color.from_rgb(255,99,71))
                    wm = await message.channel.send(embed=alert)
                    await asyncio.sleep(4)
                    try: await wm.delete()
                    except Exception: pass
                except Exception as e: print(f"[AUTOMOD] {e}")
                return

    # Anime $m/$w
    content = message.content.strip().lower()
    if content in ("$m","$w"):
        pool = ANIME_MALES if content == "$m" else ANIME_FEMALES
        char = random.choice(pool)
        embed = discord.Embed(title=char["name"],
                              description=f"**{char['name']}** ({char['anime']})\n\nReact with 💍 to claim!",
                              color=discord.Color.magenta())
        embed.set_image(url=char["image"])
        bm = await message.channel.send(embed=embed)
        await bm.add_reaction("💍")
        async def wait_claim():
            try:
                def chk(r, u): return r.message.id == bm.id and not u.bot and str(r.emoji) == "💍"
                r, u = await bot.wait_for("reaction_add", timeout=30.0, check=chk)
                db = load_data("marriage", {})
                db.setdefault(str(u.id), []).append(char["name"])
                save_data("marriage", db)
                await bm.channel.send(embed=discord.Embed(title="💖 Married!",
                    description=f"🎉 {u.mention} claimed **{char['name']}**!", color=discord.Color.magenta()))
            except asyncio.TimeoutError: pass
        asyncio.create_task(wait_claim())
        return

    # Economy + XP
    try:
        uid = str(message.author.id)
        eco = load_data("economy", {})
        eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
        eco[uid]["messages"] = eco[uid].get("messages", 0) + 1

        now = time.time()
        if uid not in XP_COOLDOWN or (now - XP_COOLDOWN[uid]) > 60:
            XP_COOLDOWN[uid] = now
            ranks = load_data("rank_config", {})
            ranks.setdefault(uid, {"xp":0, "level":1})
            ranks[uid]["xp"] += random.randint(15,25)
            need = ranks[uid]["level"] * 100
            if ranks[uid]["xp"] >= need:
                ranks[uid]["xp"] -= need
                ranks[uid]["level"] += 1
                new_lvl = ranks[uid]["level"]
                ch_id = SERVER_CONFIGS.get(g_id, {}).get("level_channel")
                if ch_id:
                    ch = message.guild.get_channel(ch_id)
                    if ch:
                        try:
                            fp = generate_levelup_card(message.author, new_lvl)
                            msg = SERVER_CONFIGS.get(g_id, {}).get("level_msg", "GG {member}!").format(member=message.author.mention)
                            await ch.send(content=msg, file=discord.File(fp, "levelup.png"))
                        except Exception as e: print(f"[LVLUP] {e}")
            save_data("rank_config", ranks)

        if random.random() < 0.10:
            rc = SERVER_CONFIGS.get(g_id, {}).get("reward_channel")
            if rc:
                ch = message.guild.get_channel(rc)
                if ch:
                    amt = random.randint(5000, 75000)
                    eco[uid]["balance"] += amt
                    emb = discord.Embed(title="✨ lucky", color=discord.Color.from_rgb(241,196,15))
                    emb.description = f"{message.author.mention}\n\n**+${amt:,}**\n\n*chat wage* · *lvl {ranks.get(uid,{}).get('level',1)}*"
                    await ch.send(content=message.author.mention, embed=emb)
        save_data("economy", eco)
    except Exception as e:
        print(f"[ECON] {e}")

    await bot.process_commands(message)

# --------- on_member_join ---------
@bot.event
async def on_member_join(member):
    cfg = SERVER_CONFIGS.get(str(member.guild.id), {})
    cid = cfg.get("channel")
    if cid:
        ch = member.guild.get_channel(cid)
        if ch:
            try: await ch.send(content=f"Welcome {member.mention}!", embed=generate_welcome_card(member))
            except Exception as e: print(f"[WELCOME] {e}")

# --------- on_member_remove ---------
@bot.event
async def on_member_remove(member):
    gid = str(member.guild.id)
    cfg = SERVER_CONFIGS.get(gid, {})
    cid = cfg.get("channel")
    if cid:
        ch = member.guild.get_channel(cid)
        if ch:
            try:
                await ch.send(embed=discord.Embed(
                    description=f"💔 **{member.name}** left. Total: {member.guild.member_count}.",
                    color=discord.Color.dark_gray()))
            except Exception: pass
    lc = load_data("leave_config", {}).get(gid, {})
    lcid = lc.get("channel_id")
    if lcid:
        lch = member.guild.get_channel(lcid)
        if lch:
            msg = lc.get("custom_message", "has terminated their connection.")
            formatted = msg.replace("{user}", member.mention).replace("{server}", member.guild.name)
            try:
                e = discord.Embed(title="🚪 Connection Disconnected",
                                  description=f"{formatted}\n\n**Identity:** {member.name}",
                                  color=0xF5EAE1)
                e.add_field(name="Remaining", value=f"`{member.guild.member_count}` members")
                e.set_thumbnail(url=member.display_avatar.url)
                await lch.send(content=f"⚠️ {member.mention}", embed=e)
            except Exception: pass

# --------- on_member_update (boost) ---------
@bot.event
async def on_member_update(before, after):
    if not before.premium_since and after.premium_since:
        uid = str(after.id)
        eco = load_data("economy", {})
        eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
        eco[uid]["balance"] += 10000
        if "booster_elite" not in eco[uid]["inventory"]:
            eco[uid]["inventory"].append("booster_elite")
        save_data("economy", eco)
        ch = after.guild.system_channel or (after.guild.text_channels[0] if after.guild.text_channels else None)
        if ch:
            try:
                await ch.send(embed=discord.Embed(title="✨ BOOST DETECTED ✨",
                    description=f"💖 Thank you {after.mention}!\n🎁 +10,000 coins + Booster badge!",
                    color=discord.Color.from_rgb(244,127,255)))
            except Exception: pass

# ==============================================================================
# 🎬 SLASH COMMANDS — WELCOME / REWARD / LEVEL
# ==============================================================================
@bot.tree.command(name="welcome-set", description="⚙️ Map greeting system to a channel")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_set(i, channel: discord.TextChannel):
    cfg = guild_cfg(i.guild.id); cfg["channel"] = channel.id
    persist_server_configs()
    await i.response.send_message(embed=discord.Embed(description=f"✅ Welcome → {channel.mention}", color=0x57F287))

@bot.tree.command(name="welcome-reset", description="❌ Wipe welcome module")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_reset(i):
    cfg = guild_cfg(i.guild.id); cfg.pop("channel", None); persist_server_configs()
    await i.response.send_message("Welcome cleared.")

@bot.tree.command(name="welcome-test", description="🧪 Test welcome card")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_test(i):
    cid = SERVER_CONFIGS.get(str(i.guild.id), {}).get("channel")
    if not cid: return await i.response.send_message("Set welcome channel first.", ephemeral=True)
    ch = i.guild.get_channel(cid)
    if ch:
        await ch.send(content=f"Welcome {i.user.mention}!", embed=generate_welcome_card(i.user))
        await i.response.send_message("✅ Sent.", ephemeral=True)

@bot.tree.command(name="reward-set", description="💰 Set reward channel")
@app_commands.checks.has_permissions(administrator=True)
async def reward_set(i, channel: discord.TextChannel):
    cfg = guild_cfg(i.guild.id); cfg["reward_channel"] = channel.id; persist_server_configs()
    await i.response.send_message(f"✅ Rewards → {channel.mention}")

@bot.tree.command(name="reward-reset", description="❌ Wipe reward module")
@app_commands.checks.has_permissions(administrator=True)
async def reward_reset(i):
    cfg = guild_cfg(i.guild.id); cfg.pop("reward_channel", None); persist_server_configs()
    await i.response.send_message("Reward system off.")

@bot.tree.command(name="reward-test", description="🧪 Test reward")
@app_commands.checks.has_permissions(administrator=True)
async def reward_test(i):
    cid = SERVER_CONFIGS.get(str(i.guild.id), {}).get("reward_channel")
    if not cid: return await i.response.send_message("Set reward channel first.", ephemeral=True)
    ch = i.guild.get_channel(cid)
    if ch:
        amt = random.randint(5000,75000)
        emb = discord.Embed(title="✨ lucky (TEST)", color=discord.Color.from_rgb(241,196,15))
        emb.description = f"{i.user.mention}\n\n**+${amt:,}**\n\n*chat wage*"
        await ch.send(content=i.user.mention, embed=emb)
        await i.response.send_message("✅ Sent.", ephemeral=True)

@bot.tree.command(name="level-set-channel", description="📊 Set level-up channel")
@app_commands.checks.has_permissions(administrator=True)
async def lvlch(i, channel: discord.TextChannel):
    cfg = guild_cfg(i.guild.id); cfg["level_channel"] = channel.id; persist_server_configs()
    await i.response.send_message(f"✅ Level up → {channel.mention}", ephemeral=True)

@bot.tree.command(name="level-set-msg", description="💬 Custom level-up message")
@app_commands.checks.has_permissions(administrator=True)
async def lvlmsg(i, message: str):
    cfg = guild_cfg(i.guild.id); cfg["level_msg"] = message; persist_server_configs()
    await i.response.send_message(f"✅ Updated: `{message}`", ephemeral=True)

@bot.tree.command(name="rank", description="💳 Display your rank card")
async def rank(i, member: discord.Member = None):
    await i.response.defer()
    t = member or i.user
    uid = str(t.id)
    ranks = load_data("rank_config", {})
    eco = load_data("economy", {})
    ud = {
        "xp": ranks.get(uid, {}).get("xp", 0),
        "level": ranks.get(uid, {}).get("level", 1),
        "balance": eco.get(uid, {}).get("balance", 0) if isinstance(eco.get(uid), dict) else 0,
        "messages": eco.get(uid, {}).get("messages", 0) if isinstance(eco.get(uid), dict) else 0,
    }
    su = sorted(ranks.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    pos = next((idx+1 for idx, (u, _) in enumerate(su) if u == uid), 1)
    fp = generate_rank_card(t, ud, pos)
    await i.followup.send(file=discord.File(fp, "rank.png"))

# ==============================================================================
# 🛡️ MODERATION
# ==============================================================================
@bot.tree.command(name="kick", description="🔒 Kick a member")
@commands.has_permissions(kick_members=True)
async def kick(i, member: discord.Member, reason: str = "No reason"):
    try:
        await member.kick(reason=reason)
        e = discord.Embed(title="🔨 Kicked", description=f"**{member.name}** removed.", color=0xED4245)
        e.add_field(name="Reason", value=reason)
        await i.response.send_message(embed=e)
    except discord.Forbidden: await i.response.send_message("❌ Hierarchy error.", ephemeral=True)

@bot.tree.command(name="ban", description="🚫 Ban a member")
@commands.has_permissions(ban_members=True)
async def ban(i, member: discord.Member, reason: str = "No reason"):
    try:
        await member.ban(reason=reason)
        e = discord.Embed(title="🚨 Banned", description=f"**{member.name}** banned.", color=0x8B0000)
        e.add_field(name="Reason", value=reason)
        await i.response.send_message(embed=e)
    except discord.Forbidden: await i.response.send_message("❌ Permission failed.", ephemeral=True)

@bot.tree.command(name="mute", description="🤫 Timeout a member")
@commands.has_permissions(moderate_members=True)
async def mute(i, member: discord.Member, minutes: int, reason: str = "No reason"):
    try:
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await i.response.send_message(embed=discord.Embed(title="🤫 Muted",
            description=f"**{member.name}** for `{minutes}` min.", color=0xFE814B))
    except Exception as e: await i.response.send_message(f"❌ {e}", ephemeral=True)

@bot.tree.command(name="warn", description="⚠️ Warn a member")
@commands.has_permissions(kick_members=True)
async def warn(i, member: discord.Member, reason: str):
    if member.id == i.user.id: return await i.response.send_message("Can't warn yourself.", ephemeral=True)
    if member.bot: return await i.response.send_message("Can't warn a bot.", ephemeral=True)
    await i.response.defer()
    emb = discord.Embed(title="⚠️ Member Warned",
        description=f"**User:** {member.mention}\n**Reason:** {reason}\n**By:** {i.user.mention}",
        color=0xFF8C00)
    emb.timestamp = discord.utils.utcnow()
    await i.followup.send(embed=emb)
    try:
        dm = discord.Embed(title=f"⚠️ Warning from {i.guild.name}",
            description=f"You received a warning.\n\n**Reason:** {reason}", color=0xFF8C00)
        await member.send(embed=dm)
    except Exception: pass

@bot.tree.command(name="addrole", description="➕ Add a role to a member")
@commands.has_permissions(manage_roles=True)
async def addrole(i, member: discord.Member, role: discord.Role):
    await i.response.defer()
    if role >= i.guild.me.top_role:
        return await i.followup.send("❌ Role above bot's highest.", ephemeral=True)
    try:
        await member.add_roles(role)
        await i.followup.send(embed=discord.Embed(title="✨ Role Granted",
            description=f"{role.mention} → **{member.display_name}**", color=0x57F287))
    except discord.Forbidden: await i.followup.send("❌ No permission.", ephemeral=True)

@bot.tree.command(name="removerole", description="➖ Remove a role from a member")
@commands.has_permissions(manage_roles=True)
async def removerole(i, member: discord.Member, role: discord.Role):
    await i.response.defer()
    if role >= i.guild.me.top_role:
        return await i.followup.send("❌ Role above bot's highest.", ephemeral=True)
    try:
        await member.remove_roles(role)
        await i.followup.send(embed=discord.Embed(title="✨ Role Removed",
            description=f"{role.mention} ← **{member.display_name}**", color=0xED4245))
    except discord.Forbidden: await i.followup.send("❌ No permission.", ephemeral=True)

# ==============================================================================
# ☕ SERVE + ANIME
# ==============================================================================
MENU = {
    "coffee":     {"title":"BARISTA ESPRESSO","item_name":"Premium Barista Coffee","origin":"Milan, Italy 🇮🇹","line":"Rich espresso with velvety crema.","price":50},
    "donuts":     {"title":"GLAZED LUXURY","item_name":"Gourmet Glazed Donuts","origin":"Belgium 🇧🇪","line":"Artisanal dough, white chocolate.","price":60},
    "cold_drink": {"title":"CRYSTAL ICY","item_name":"Chilled Icy Soda","origin":"USA 🇺🇸","line":"Ice-cold with mint.","price":70},
    "burger":     {"title":"GOURMET STACK","item_name":"Double-Stack Burger","origin":"Germany 🇩🇪","line":"Aged cheddar, secret sauce.","price":100},
    "pizza":      {"title":"WOODFIRED ITALIAN","item_name":"Neapolitan Pizza","origin":"Naples 🇮🇹","line":"Fresh mozzarella, torn basil.","price":120},
    "indian_spicy":{"title":"ROYAL CURRY","item_name":"Shahi Mughlai Curry","origin":"Delhi 🇮🇳","line":"Buttery royal spices.","price":150},
    "japan_mochi":{"title":"MATCHA SUPREME","item_name":"Uji Matcha Mochi","origin":"Kyoto 🇯🇵","line":"Red bean paste filled.","price":180},
    "mexico_quesadilla":{"title":"CHEESY SUPREME","item_name":"Smoked Pepper Quesadilla","origin":"Mexico 🇲🇽","line":"Monterey Jack + jalapenos.","price":200},
    "france_croissant":{"title":"BUTTER CRUISE","item_name":"Flurries Croissant","origin":"Paris 🇫🇷","line":"Elite butter pastry.","price":220},
    "italy_pasta":{"title":"CREAMY ALFREDO","item_name":"Truffle Mushroom Alfredo","origin":"Rome 🇮🇹","line":"Parmesan + wild truffle.","price":250},
    "china_dimsum":{"title":"STEAMED BLISS","item_name":"Crystal Veg Dim Sum","origin":"China 🇨🇳","line":"Translucent dumpling wraps.","price":260},
    "turkey_baklava":{"title":"ROYAL PISTACHIO","item_name":"Honey Gold Baklava","origin":"Turkey 🇹🇷","line":"Filo + crushed pistachios.","price":280},
    "korea_tteokbokki":{"title":"SEOUL SPICY","item_name":"Cheesy Tteokbokki","origin":"Korea 🇰🇷","line":"Fiery gochujang glaze.","price":300},
    "thailand_mangorice":{"title":"SIAM SWEET","item_name":"Mango Sticky Rice","origin":"Thailand 🇹🇭","line":"Coconut milk drizzle.","price":320},
    "spain_churros":{"title":"CRISPY CINNAMON","item_name":"Golden Churros","origin":"Spain 🇪🇸","line":"Cinnamon sugar + chocolate dip.","price":340},
    "usa_waffles":{"title":"USA DINER","item_name":"Loaded Buttermilk Waffles","origin":"USA 🇺🇸","line":"Maple syrup, berries, cream.","price":350},
}

@bot.tree.command(name="serve", description="🛎️ Serve a premium meal")
@app_commands.choices(item=[app_commands.Choice(name=k, value=k) for k in MENU])
async def serve(i, item: str, member: discord.Member):
    await i.response.defer()
    if item not in MENU: return await i.followup.send("❌ Invalid item.")
    m = MENU[item]
    uid = str(i.user.id)
    eco = load_data("economy", {})
    eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
    if eco[uid].get("balance", 0) < m["price"]:
        return await i.followup.send(embed=discord.Embed(
            title="💸 Insufficient Funds",
            description=f"Need `{m['price']}` coins, have `{eco[uid]['balance']}`.",
            color=0xED4245))
    eco[uid]["balance"] -= m["price"]
    save_data("economy", eco)
    emb = discord.Embed(title=f"👑 ─── {m['title']} ─── 👑",
        description=(f"**Item:** `{m['item_name']}`\n**Origin:** *{m['origin']}*\n"
                     f"💸 **Cost:** `{m['price']}`\n\n*{m['line']}*\n\n─── *Enjoy!* ───"),
        color=0xF5EAE1)
    emb.set_footer(text=f"Balance: {eco[uid]['balance']} coins")
    await i.followup.send(content=f"🛎️ {member.mention}, served!", embed=emb)

ANIME_MALES = [
    {"name": "Levi Ackerman", "anime": "Attack on Titan", "image": "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=500"},
    {"name": "Gojo Satoru", "anime": "Jujutsu Kaisen", "image": "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=500"},
    {"name": "Naruto Uzumaki", "anime": "Naruto Shippuden", "image": "https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?w=500"},
]
ANIME_FEMALES = [
    {"name": "Helena Croisen", "anime": "Master of the Guardian Stone", "image": "https://images.unsplash.com/photo-1560942485-b2a11cc13456?w=500"},
    {"name": "Mikasa Ackerman", "anime": "Attack on Titan", "image": "https://images.unsplash.com/photo-1580477667995-2b94f01c9516?w=500"},
    {"name": "Nezuko Kamado", "anime": "Demon Slayer", "image": "https://images.unsplash.com/photo-1627556704353-016ed97397b9?w=500"},
]

def _anime_cmd(name, title, verb, verb2, color, gif):
    @bot.tree.command(name=name, description=f"{title}")
    async def cmd(i, member: discord.Member):
        if member.id == i.user.id:
            return await i.response.send_message(f"*Can't {name} yourself!*", ephemeral=True)
        e = discord.Embed(title=title,
            description=f"**{i.user.display_name}** {verb} **{member.display_name}** {verb2}",
            color=color)
        e.set_image(url=gif)
        await i.response.send_message(content=f"{member.mention}!", embed=e)

_anime_cmd("hug","✨ Cuddle Time!","wraps arms around","for a cozy hug!",
           discord.Color.from_rgb(255,182,193),
           "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif")
_anime_cmd("kiss","💖 Sweet Affection","pulls close and kisses","!",
           discord.Color.from_rgb(255,105,180),
           "https://media.giphy.com/media/lTQF0ODLLjhza/giphy.gif")
_anime_cmd("slap","💢 Ouch!","SLAPS","across the face!",
           discord.Color.red(),
           "https://media.giphy.com/media/Zau0yrl17uzdK/giphy.gif")

# ==============================================================================
# 💰 ECONOMY
# ==============================================================================
SHOP_ITEMS = {
    "nebula_kitten":  {"price":1200, "type":"Pet","display":"🐱 Nebula Kitten","desc":"Floating space kitty."},
    "stardust_dragon":{"price":5000, "type":"Pet","display":"🐲 Stardust Dragon","desc":"Legendary protector."},
    "cyber_puppy":    {"price":2500, "type":"Pet","display":"🐶 Cyber Puppy","desc":"Neon glowing puppy."},
    "rich_vibes":     {"price":3000, "type":"Badge","display":"💰 Richie Rich","desc":"Drowning in coins."},
    "elite_gamer":    {"price":1500, "type":"Badge","display":"🎮 Elite Gamer","desc":"True grinder."},
    "stardust_legend":{"price":8000, "type":"Badge","display":"✨ Cosmic Legend","desc":"Ultimate status."},
}

@bot.tree.command(name="daily", description="🎁 Claim daily reward")
async def daily(i):
    await i.response.defer()
    uid = str(i.user.id)
    eco = load_data("economy", {})
    eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
    now = int(time.time())
    if now - eco[uid].get("last_daily", 0) < 86400:
        rem = 86400 - (now - eco[uid].get("last_daily", 0))
        return await i.followup.send(embed=discord.Embed(title="⏳ Cooldown",
            description=f"Wait `{rem//3600}h {(rem%3600)//60}m`.", color=0xF5EAE1))
    eco[uid]["balance"] += 200
    eco[uid]["last_daily"] = now
    save_data("economy", eco)
    await i.followup.send(embed=discord.Embed(title="🌟 DAILY BONUS",
        description=f"🎁 +**200 coins**\n💳 Balance: `{eco[uid]['balance']}`", color=0xF5EAE1))

@bot.tree.command(name="wallet", description="💳 View your balance")
async def wallet(i):
    await i.response.defer()
    uid = str(i.user.id)
    eco = load_data("economy", {})
    eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
    await i.followup.send(embed=discord.Embed(title="💳 Stardust Vault",
        description=f"👤 {i.user.mention}\n\n🪙 **Balance:** `{eco[uid]['balance']}` coins",
        color=0xF5EAE1))

@bot.tree.command(name="menu", description="📜 Global menu card")
async def menu(i):
    lines = ["**☕ HOUSE SPECIALS**"]
    for k, v in list(MENU.items())[:6]:
        lines.append(f"• `{k}` ── {v['item_name']} ── **{v['price']}**")
    lines.append("\n**✈️ PRESTIGE GLOBAL**")
    for k, v in list(MENU.items())[6:]:
        lines.append(f"• `{k}` ── {v['item_name']} ── **{v['price']}**")
    await i.response.send_message(embed=discord.Embed(title="📜 MENU",
        description="\n".join(lines), color=0xF5EAE1))

@bot.tree.command(name="shop", description="🛒 Browse Stardust shop")
async def shop(i):
    emb = discord.Embed(title="🌟 STARDUST SHOP",
        description="Use `/buy <item_id>`.", color=0x9370DB)
    pets = "\n".join(f"**{v['display']}** (`{k}`) — 🪙 {v['price']}\n*{v['desc']}*"
                     for k, v in SHOP_ITEMS.items() if v["type"]=="Pet")
    badges = "\n".join(f"**{v['display']}** (`{k}`) — 🪙 {v['price']}\n*{v['desc']}*"
                       for k, v in SHOP_ITEMS.items() if v["type"]=="Badge")
    emb.add_field(name="🐾 Pets", value=pets or "None", inline=False)
    emb.add_field(name="🏅 Badges", value=badges or "None", inline=False)
    await i.response.send_message(embed=emb)

@bot.tree.command(name="buy", description="🛍️ Buy an item")
async def buy(i, item_id: str):
    await i.response.defer()
    uid = str(i.user.id); item_id = item_id.lower().strip()
    if item_id not in SHOP_ITEMS:
        return await i.followup.send("❌ Invalid item ID. See `/shop`.", ephemeral=True)
    it = SHOP_ITEMS[item_id]
    eco = load_data("economy", {})
    eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
    if item_id in eco[uid]["inventory"]:
        return await i.followup.send(f"❌ Already own {it['display']}.", ephemeral=True)
    if eco[uid]["balance"] < it["price"]:
        return await i.followup.send(f"❌ Need {it['price']-eco[uid]['balance']} more coins.", ephemeral=True)
    eco[uid]["balance"] -= it["price"]
    eco[uid]["inventory"].append(item_id)
    save_data("economy", eco)
    await i.followup.send(embed=discord.Embed(title="🎉 Purchase Successful!",
        description=f"You own **{it['display']}**!\n🪙 -{it['price']} coins",
        color=0x32CD32))

@bot.tree.command(name="inventory", description="🎒 View your inventory")
async def inventory(i):
    uid = str(i.user.id)
    eco = load_data("economy", {})
    eco.setdefault(uid, {"balance":0, "last_daily":0, "inventory":[], "messages":0})
    inv = eco[uid].get("inventory", [])
    emb = discord.Embed(title=f"🎒 {i.user.display_name}'s Vault", color=0x1E90FF)
    if not inv:
        emb.description = "*Empty! Visit `/shop`.*"
    else:
        pets = [SHOP_ITEMS[k]["display"] for k in inv if k in SHOP_ITEMS and SHOP_ITEMS[k]["type"]=="Pet"]
        badges = [SHOP_ITEMS[k]["display"] for k in inv if k in SHOP_ITEMS and SHOP_ITEMS[k]["type"]=="Badge"]
        emb.add_field(name="🐾 Pets", value="\n".join(pets) or "None", inline=True)
        emb.add_field(name="🏅 Badges", value="\n".join(badges) or "None", inline=True)
    await i.response.send_message(embed=emb)

# ==============================================================================
# 🏆 LEADERBOARDS + GIVEAWAYS + TICKETS + EMBED
# ==============================================================================
@bot.tree.command(name="richest", description="🏆 Top 10 richest members")
async def richest(i):
    await i.response.defer()
    eco = load_data("economy", {})
    def bal(d):
        if isinstance(d, int): return d
        if isinstance(d, dict): return d.get("balance", 0)
        return 0
    su = sorted(eco.items(), key=lambda x: bal(x[1]), reverse=True)[:10]
    emb = discord.Embed(title="👑 WEALTH LEADERBOARD", color=0xE6E6FA)
    lines = []
    for idx, (uid, d) in enumerate(su, 1):
        m = i.guild.get_member(int(uid))
        name = m.display_name if m else f"User {uid}"
        medal = ["🥇","🥈","🥉"][idx-1] if idx <= 3 else f"`#{idx}`"
        lines.append(f"{medal} **{name}** — 🪙 `{bal(d):,}`")
    emb.description = "\n".join(lines) or "*No data.*"
    await i.followup.send(embed=emb)

@bot.tree.command(name="gstart", description="🎉 Start a giveaway")
@commands.has_permissions(manage_guild=True)
async def gstart(i, duration: str, winners: int, prize: str):
    secs = parse_duration(duration)
    if secs <= 0: return await i.response.send_message("❌ Invalid duration (30m/5h/1d).", ephemeral=True)
    if winners <= 0: return await i.response.send_message("❌ Winners >= 1.", ephemeral=True)
    await i.response.defer()
    emb = discord.Embed(title=f"🎁 {prize.upper()} 🎁",
        description=(f"♡ React with 🎉 to join!\n♡ **Ends:** in {duration}\n"
                     f"♡ **Hosted by:** {i.user.mention}\n♡ **Winners:** {winners}\n\n"
                     f"━━━━━━━━━━━━━━━━━━━━━━━━━━"),
        color=0xBA55D3)
    emb.set_footer(text="Click 🎉 to enter!")
    gm = await i.followup.send(embed=emb, wait=True)
    await gm.add_reaction("🎉")
    await asyncio.sleep(secs)
    try:
        gm = await i.channel.fetch_message(gm.id)
    except Exception: return
    r = discord.utils.get(gm.reactions, emoji="🎉")
    if not r: return
    users = [u async for u in r.users() if not u.bot]
    if not users:
        return await gm.edit(embed=discord.Embed(title="🎉 ENDED",
            description=f"**Prize:** {prize}\n❌ No entries.", color=0xED4245))
    chosen = random.sample(users, min(len(users), winners))
    mentions = ", ".join(w.mention for w in chosen)
    await gm.edit(embed=discord.Embed(title="🎉 GIVEAWAY ENDED",
        description=f"♡ **Prize:** {prize}\n♡ **Winners:** {mentions}", color=0x32CD32))
    await i.channel.send(f"🎊 Congrats {mentions}! Won **{prize}**!")

@bot.tree.command(name="ticket_config", description="⚙️ Configure ticket system")
@commands.has_permissions(administrator=True)
async def ticket_config(i, panel_description: str = None, welcome_title: str = None,
                        welcome_message: str = None, staff_role: discord.Role = None):
    gid = str(i.guild.id)
    tc = load_data("ticket_config", {})
    tc.setdefault(gid, {})
    if panel_description: tc[gid]["panel_desc"] = panel_description
    if welcome_title: tc[gid]["welcome_title"] = welcome_title
    if welcome_message: tc[gid]["welcome_msg"] = welcome_message
    if staff_role: tc[gid]["staff_role_id"] = str(staff_role.id)
    save_data("ticket_config", tc)
    await i.response.send_message(embed=discord.Embed(title="✅ Ticket Settings Saved",
        color=0x57F287), ephemeral=True)

@bot.tree.command(name="ticket_setup", description="⚙️ Deploy ticket launcher panel")
@commands.has_permissions(administrator=True)
async def ticket_setup(i, channel: discord.TextChannel):
    await i.response.send_message(f"⏳ Deploying to {channel.mention}...", ephemeral=True)
    tc = load_data("ticket_config", {}).get(str(i.guild.id), {})
    desc = tc.get("panel_desc", "Need assistance? Click below for a private support channel.")
    emb = discord.Embed(title="📩 Help & Support Portal", description=desc, color=0x57F287)
    emb.set_footer(text="Automated Helpdesk")
    try:
        await channel.send(embed=emb, view=TicketLauncherView())
        await i.edit_original_response(content=f"✅ Panel deployed in {channel.mention}")
    except discord.Forbidden:
        await i.edit_original_response(content="❌ No permission in that channel.")

class EmbedModal(discord.ui.Modal, title="🎨 Custom Embed Builder"):
    t = discord.ui.TextInput(label="Title", max_length=256)
    d = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=2000)
    c = discord.ui.TextInput(label="HEX color (#FF4500)", required=False, max_length=7)
    img = discord.ui.TextInput(label="Image URL", required=False)
    def __init__(self, ch): super().__init__(); self.ch = ch
    async def on_submit(self, i):
        await i.response.send_message("⏳ Sending...", ephemeral=True)
        try:
            col = discord.Color.blurple()
            if self.c.value:
                h = self.c.value if self.c.value.startswith("#") else f"#{self.c.value}"
                try: col = discord.Color.from_str(h)
                except Exception: pass
            emb = discord.Embed(title=self.t.value, description=self.d.value, color=col,
                                timestamp=discord.utils.utcnow())
            emb.set_footer(text=f"By {i.user.display_name}")
            if self.img.value and self.img.value.startswith("http"):
                emb.set_image(url=self.img.value)
            await self.ch.send(embed=emb)
            await i.edit_original_response(content=f"🚀 Sent to {self.ch.mention}!")
        except Exception as e:
            await i.edit_original_response(content=f"❌ {e}")

@bot.tree.command(name="embed_builder", description="⚙️ Open embed builder")
@commands.has_permissions(manage_messages=True)
async def embed_builder(i, channel: discord.TextChannel):
    await i.response.send_modal(EmbedModal(channel))

# ==============================================================================
# ⏰ REMINDERS, POLLS, UTILS
# ==============================================================================
@bot.tree.command(name="remindme", description="⏰ Set a reminder")
async def remindme(i, time_str: str, text: str):
    secs = parse_duration(time_str)
    if secs <= 0: return await i.response.send_message("❌ Invalid time format.", ephemeral=True)
    await i.response.defer()
    await asyncio.sleep(secs)
    try:
        await i.followup.send(content=i.user.mention, embed=discord.Embed(title="⏰ REMINDER",
            description=f"📝 {text}", color=0x1E90FF))
    except Exception: pass

@bot.tree.command(name="afk", description="💤 Set AFK status")
async def afk_cmd(i, reason: str = "Away"):
    a = load_data("afk", {})
    a[str(i.user.id)] = reason
    save_data("afk", a)
    await i.response.send_message(embed=discord.Embed(title="💤 AFK Set",
        description=f"📝 `{reason}`", color=0xF5EAE1))

@bot.tree.command(name="matrixpoll", description="🗳️ Start a poll")
async def matrixpoll(i, topic: str):
    emb = discord.Embed(title="🗳️ Opinion Poll",
        description=f"\n📊 **{topic}**\n\n👍 APPROVE\n👎 REJECT", color=0xF5EAE1)
    emb.set_footer(text=f"By {i.user.display_name}")
    await i.response.send_message(embed=emb)
    m = await i.original_response()
    await m.add_reaction("👍"); await m.add_reaction("👎")

@bot.tree.command(name="stardustquote", description="🧠 Random tech quote")
async def quote(i):
    q = random.choice([
        "Talk is cheap. Show me the code. — Linus",
        "Programs must be written for people to read. — Abelson",
        "Stay hungry, stay foolish. — Steve Jobs",
        "The matrix is everywhere. — Morpheus"])
    await i.response.send_message(embed=discord.Embed(description=f"**{q}**", color=0xF5EAE1))

@bot.tree.command(name="rollmatrix", description="🎲 Roll 1-100")
async def roll(i):
    r = random.randint(1,100)
    await i.response.send_message(embed=discord.Embed(title="🎲 Roll", description=f"**`{r}`**", color=0xF5EAE1))

@bot.tree.command(name="ping", description="⚡ Check latency")
async def ping(i):
    await i.response.send_message(f"🏓 Pong! `{round(bot.latency*1000)}ms`")

@bot.tree.command(name="help", description="📖 View commands")
async def help_cmd(i):
    e = discord.Embed(title="Stardust Suite", description="Active modules:", color=0x5865F2)
    e.add_field(name="⚙️ Welcome", value="`/welcome-set` `/welcome-test` `/welcome-reset`", inline=False)
    e.add_field(name="🛡️ Moderation", value="`/kick` `/ban` `/mute` `/warn` `/addrole` `/removerole`", inline=False)
    e.add_field(name="💰 Economy", value="`/daily` `/wallet` `/shop` `/buy` `/inventory` `/serve`", inline=False)
    e.add_field(name="📊 Levels", value="`/rank` `/level-set-channel` `/richest`", inline=False)
    e.add_field(name="🎫 Tickets", value="`/ticket_setup` `/ticket_config`", inline=False)
    e.add_field(name="🎉 Fun", value="`/hug` `/kiss` `/slap` `/play_rps` `/play_ttt` `/play_slap`", inline=False)
    e.add_field(name="🎁 Giveaways", value="`/gstart`", inline=False)
    e.add_field(name="🎨 Embeds", value="`/embed_builder`", inline=False)
    e.add_field(name="🛠️ Utilities", value="`/afk` `/remindme` `/matrixpoll` `/rollmatrix` `/stardustquote`", inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="play_rps", description="🪨 Rock Paper Scissors")
async def play_rps(i, opponent: discord.User = None):
    if opponent and opponent.id == i.user.id:
        return await i.response.send_message("❌ Can't play yourself.", ephemeral=True)
    v = RPSView(i.user, opponent)
    await i.response.send_message(f"🎮 {i.user.mention} vs {opponent.mention if opponent else '🤖 Bot'}", view=v)

@bot.tree.command(name="play_ttt", description="❌ Tic Tac Toe")
async def play_ttt(i, opponent: discord.User = None):
    if opponent and opponent.id == i.user.id:
        return await i.response.send_message("❌ Can't play yourself.", ephemeral=True)
    v = TTTView(i.user, opponent)
    await i.response.send_message(
        f"🎮 **TicTacToe!**\n❌ {i.user.mention} vs ⭕ {opponent.mention if opponent else '🤖 Bot'}\n\nTurn: {i.user.mention}",
        view=v)

@bot.tree.command(name="play_slap", description="💥 Slap fight")
async def play_slap(i, opponent: discord.User = None):
    if opponent and opponent.id == i.user.id:
        return await i.response.send_message("❌ Can't slap yourself.", ephemeral=True)
    v = SlapView(i.user, opponent)
    await i.response.send_message(f"💥 **Slap Fight!** {i.user.mention} vs {opponent.mention if opponent else '🤖 Bot'}\n\nTurn: {i.user.mention}", view=v)

# ==============================================================================
# 🔄 BACKGROUND LOOPS
# ==============================================================================
@tasks.loop(seconds=60)
async def reminder_checker_loop():
    # Cleanup expired sessions
    now = time.time()
    changed = False
    for sid in list(SESSIONS.keys()):
        if SESSIONS[sid].get("expires", 0) < now:
            del SESSIONS[sid]
            changed = True
    if changed:
        persist_sessions()

# ==============================================================================
# 🌐 FLASK APP + REAL API
# ==============================================================================
flask_app = Flask(__name__)
flask_app.secret_key = SESSION_SECRET
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Cross-domain CORS with credentials
CORS(
    flask_app,
    supports_credentials=True,
    origins=ALLOWED_ORIGINS,
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    expose_headers=["Content-Type"],
    max_age=3600
)

# --------- Helpers for cross-domain cookies ---------
def set_session_cookie(resp, sid, max_age=7*86400):
    """
    Sets the session cookie with cross-domain friendly attributes.
    SameSite=None requires Secure=True; browsers only accept it over HTTPS.
    """
    resp.set_cookie(
        "stardust_session",
        sid,
        max_age=max_age,
        httponly=True,
        secure=True,          # REQUIRED for SameSite=None
        samesite="None",      # allows cross-site (GitHub Pages → Render)
        path="/",
        domain=None           # host-only cookie for onrender.com
    )

def clear_session_cookie(resp):
    resp.delete_cookie(
        "stardust_session",
        path="/",
        secure=True,
        samesite="None",
        httponly=True
    )

# --------- Public ---------
@flask_app.route("/")
def home():
    return jsonify({"status": "ok", "service": "Stardust API", "version": "2.1.0"})

@flask_app.route("/api/health")
def health():
    try:
        ready = bot.is_ready()
        return jsonify({
            "success": True,
            "data": {
                "api": "ok",
                "bot_ready": ready,
                "bot_latency_ms": round(bot.latency * 1000) if ready else None,
                "guild_count": len(bot.guilds) if ready else 0,
                "timestamp": int(time.time())
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "HEALTH_ERR", "message": str(e)}}), 500

# --------- OAuth Step 1 ---------
@flask_app.route("/api/login")
def api_login():
    if not CLIENT_ID:
        return jsonify({"success": False, "error": {"code": "NO_CLIENT", "message": "Server misconfigured"}}), 500
    state = secrets.token_urlsafe(24)
    scope = "identify guilds"
    url = (
        f"https://discord.com/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={requests.utils.quote(OAUTH_REDIRECT, safe='')}"
        f"&response_type=code"
        f"&scope={scope.replace(' ', '%20')}"
        f"&state={state}"
        f"&prompt=consent"
    )
    return jsonify({"success": True, "data": {"url": url, "state": state}})

# --------- OAuth Step 2 (callback) ---------
@flask_app.route("/api/callback")
def api_callback():
    code = request.args.get("code")
    if not code:
        return redirect(f"{FRONTEND_URL}/?login_error=missing_code")
    try:
        r = requests.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        if r.status_code != 200:
            print(f"[OAUTH] token exchange failed: {r.status_code} {r.text}")
            return redirect(f"{FRONTEND_URL}/?login_error=oauth_failed")

        tok = r.json()
        access_token = tok.get("access_token")

        u = requests.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15
        ).json()

        uid = u.get("id")
        if not uid:
            return redirect(f"{FRONTEND_URL}/?login_error=user_fetch")

        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = {
            "user_id": uid,
            "username": u.get("username"),
            "global_name": u.get("global_name"),
            "avatar": u.get("avatar"),
            "access_token": access_token,
            "created": int(time.time()),
            "expires": int(time.time()) + 7*86400
        }
        persist_sessions()

        resp = make_response(redirect(f"{FRONTEND_URL}/?login=success"))
        set_session_cookie(resp, sid)
        return resp
    except Exception as e:
        print(f"[OAUTH] exception: {e}")
        traceback.print_exc()
        return redirect(f"{FRONTEND_URL}/?login_error=server")

# --------- Session helpers ---------
def get_session():
    sid = request.cookies.get("stardust_session")
    if not sid or sid not in SESSIONS:
        return None
    s = SESSIONS[sid]
    if s.get("expires", 0) < time.time():
        del SESSIONS[sid]
        persist_sessions()
        return None
    return s

# --------- Auth endpoints ---------
@flask_app.route("/api/auth/me")
def auth_me():
    s = get_session()
    if not s:
        return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Not logged in"}}), 401
    return jsonify({"success": True, "data": {
        "id": s["user_id"],
        "username": s["username"],
        "global_name": s.get("global_name"),
        "avatar": s.get("avatar")
    }})

@flask_app.route("/api/logout", methods=["POST", "OPTIONS"])
def auth_logout():
    if request.method == "OPTIONS":
        return ("", 204)
    sid = request.cookies.get("stardust_session")
    if sid and sid in SESSIONS:
        del SESSIONS[sid]
        persist_sessions()
    resp = make_response(jsonify({"success": True}))
    clear_session_cookie(resp)
    return resp

@flask_app.route("/api/auth/servers")
def auth_servers():
    s = get_session()
    if not s:
        return jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Not logged in"}}), 401
    try:
        r = requests.get(
            "https://discord.com/api/users/@me/guilds",
            headers={"Authorization": f"Bearer {s['access_token']}"},
            timeout=15
        )
        if r.status_code != 200:
            return jsonify({"success": False, "error": {"code": "DISCORD_ERROR", "message": "Couldn't fetch guilds"}}), 502
        guilds = r.json()
        bot_guild_ids = {str(g.id) for g in bot.guilds} if bot.is_ready() else set()
        out = []
        for g in guilds:
            perms = int(g.get("permissions", 0))
            is_admin = bool(perms & 0x8) or bool(perms & 0x20)
            out.append({
                "id": g["id"],
                "name": g["name"],
                "icon": g.get("icon"),
                "owner": g.get("owner", False),
                "permissions": perms,
                "can_manage": is_admin,
                "bot_present": g["id"] in bot_guild_ids
            })
        return jsonify({"success": True, "data": out})
    except Exception as e:
        print(f"[SERVERS] {e}")
        return jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": "Failed"}}), 500

# --------- Guild access validation ---------
def _require_guild_access(guild_id):
    s = get_session()
    if not s:
        return None, (jsonify({"success": False, "error": {"code": "UNAUTHORIZED", "message": "Not logged in"}}), 401)
    try:
        r = requests.get(
            "https://discord.com/api/users/@me/guilds",
            headers={"Authorization": f"Bearer {s['access_token']}"},
            timeout=15
        )
        guilds = r.json() if r.status_code == 200 else []
        target = next((g for g in guilds if g["id"] == guild_id), None)
        if not target:
            return None, (jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Not a member of this server"}}), 403)
        perms = int(target.get("permissions", 0))
        if not (perms & 0x8 or perms & 0x20):
            return None, (jsonify({"success": False, "error": {"code": "FORBIDDEN", "message": "Missing administrator permission"}}), 403)
        if not bot.is_ready() or not bot.get_guild(int(guild_id)):
            return None, (jsonify({"success": False, "error": {"code": "BOT_MISSING", "message": "Stardust is not on this server"}}), 409)
        return s, None
    except Exception as e:
        print(f"[GUILD_ACCESS] {e}")
        return None, (jsonify({"success": False, "error": {"code": "SERVER_ERROR", "message": "Failed"}}), 500)

# --------- Guild overview ---------
@flask_app.route("/api/guilds/<guild_id>/overview")
def guild_overview(guild_id):
    s, err = _require_guild_access(guild_id)
    if err: return err
    g = bot.get_guild(int(guild_id))
    if not g:
        return jsonify({"success": False, "error": {"code": "BOT_MISSING", "message": "Bot not present"}}), 409
    cfg = SERVER_CONFIGS.get(guild_id, {})
    return jsonify({"success": True, "data": {
        "id": g.id,
        "name": g.name,
        "icon": g.icon.url if g.icon else None,
        "member_count": g.member_count,
        "channel_count": len(g.channels),
        "role_count": len(g.roles),
        "bot_latency_ms": round(bot.latency * 1000),
        "bot_present": True,
        "modules": {
            "welcome": bool(cfg.get("channel")),
            "automod": cfg.get("automod_enabled", True),
            "reward": bool(cfg.get("reward_channel")),
            "leveling": bool(cfg.get("level_channel")),
            "tickets": bool(load_data("ticket_config", {}).get(guild_id)),
            "leave": bool(load_data("leave_config", {}).get(guild_id, {}).get("channel_id")),
        }
    }})

# --------- Config ---------
@flask_app.route("/api/guilds/<guild_id>/config", methods=["GET"])
def get_config(guild_id):
    s, err = _require_guild_access(guild_id)
    if err: return err
    return jsonify({"success": True, "data": SERVER_CONFIGS.get(guild_id, {})})

@flask_app.route("/api/guilds/<guild_id>/config", methods=["PATCH", "OPTIONS"])
def patch_config(guild_id):
    if request.method == "OPTIONS":
        return ("", 204)
    s, err = _require_guild_access(guild_id)
    if err: return err
    body = request.get_json(silent=True) or {}
    allowed = {"channel", "reward_channel", "level_channel", "level_msg", "automod_enabled"}
    cfg = SERVER_CONFIGS.setdefault(guild_id, {})
    for k, v in body.items():
        if k in allowed:
            cfg[k] = v
    persist_server_configs()
    return jsonify({"success": True, "data": cfg})

# --------- AutoMod words ---------
@flask_app.route("/api/guilds/<guild_id>/automod/words", methods=["GET", "POST", "DELETE", "OPTIONS"])
def automod_words(guild_id):
    if request.method == "OPTIONS":
        return ("", 204)
    s, err = _require_guild_access(guild_id)
    if err: return err
    words = BLOCK_LIST.setdefault("words", [])
    if request.method == "GET":
        return jsonify({"success": True, "data": words})
    body = request.get_json(silent=True) or {}
    w = (body.get("word") or "").lower().strip()
    if not w:
        return jsonify({"success": False, "error": {"code": "INVALID", "message": "Word required"}}), 400
    if request.method == "POST":
        if w not in words:
            words.append(w)
    else:
        if w in words:
            words.remove(w)
    persist_block_list()
    return jsonify({"success": True, "data": words})

# --------- Economy leaderboard ---------
@flask_app.route("/api/guilds/<guild_id>/economy/leaderboard")
def economy_lb(guild_id):
    s, err = _require_guild_access(guild_id)
    if err: return err
    eco = load_data("economy", {})
    def bal(d):
        if isinstance(d, int): return d
        if isinstance(d, dict): return d.get("balance", 0)
        return 0
    su = sorted(eco.items(), key=lambda x: bal(x[1]), reverse=True)[:20]
    g = bot.get_guild(int(guild_id))
    out = []
    for uid, d in su:
        m = g.get_member(int(uid)) if g else None
        out.append({
            "user_id": uid,
            "name": m.display_name if m else f"User {uid}",
            "avatar": m.display_avatar.url if m else None,
            "balance": bal(d)
        })
    return jsonify({"success": True, "data": out})

# --------- Giveaway ---------
@flask_app.route("/api/guilds/<guild_id>/giveaway", methods=["POST", "OPTIONS"])
def api_giveaway(guild_id):
    if request.method == "OPTIONS":
        return ("", 204)
    s, err = _require_guild_access(guild_id)
    if err: return err
    body = request.get_json(silent=True) or {}
    prize = body.get("prize")
    duration = body.get("duration")
    winners = int(body.get("winners", 1))
    channel_id = body.get("channel_id")
    if not (prize and duration and channel_id):
        return jsonify({"success": False, "error": {"code": "INVALID", "message": "Missing fields"}}), 400
    asyncio.run_coroutine_threadsafe(
        _deploy_giveaway(guild_id, channel_id, duration, winners, prize, s["user_id"]),
        bot.loop
    )
    return jsonify({"success": True, "data": {"queued": True}})

async def _deploy_giveaway(guild_id, channel_id, duration, winners, prize, host_id):
    secs = parse_duration(duration)
    if secs <= 0: return
    g = bot.get_guild(int(guild_id))
    ch = g.get_channel(int(channel_id)) if g else None
    if not ch: return
    emb = discord.Embed(title=f"🎁 {prize.upper()} 🎁",
        description=(f"♡ React with 🎉!\n♡ **Ends:** in {duration}\n"
                     f"♡ **Hosted by:** <@{host_id}>\n♡ **Winners:** {winners}"),
        color=0xBA55D3)
    m = await ch.send(embed=emb)
    await m.add_reaction("🎉")
    await asyncio.sleep(secs)
    try:
        m = await ch.fetch_message(m.id)
    except Exception:
        return
    r = discord.utils.get(m.reactions, emoji="🎉")
    if not r: return
    users = [u async for u in r.users() if not u.bot]
    if not users:
        return await m.edit(embed=discord.Embed(title="🎉 ENDED", description=f"**{prize}**\nNo entries.", color=0xED4245))
    chosen = random.sample(users, min(len(users), winners))
    await m.edit(embed=discord.Embed(title="🎉 ENDED",
        description=f"♡ **{prize}**\n♡ Winners: {', '.join(w.mention for w in chosen)}", color=0x32CD32))

# --------- Embed send ---------
@flask_app.route("/api/guilds/<guild_id>/embed", methods=["POST", "OPTIONS"])
def api_embed(guild_id):
    if request.method == "OPTIONS":
        return ("", 204)
    s, err = _require_guild_access(guild_id)
    if err: return err
    body = request.get_json(silent=True) or {}
    ch_id = body.get("channel_id")
    if not ch_id:
        return jsonify({"success": False, "error": {"code": "INVALID", "message": "channel_id required"}}), 400
    asyncio.run_coroutine_threadsafe(_send_embed(guild_id, ch_id, body, s["user_id"]), bot.loop)
    return jsonify({"success": True, "data": {"queued": True}})

async def _send_embed(guild_id, ch_id, body, author_id):
    g = bot.get_guild(int(guild_id))
    ch = g.get_channel(int(ch_id)) if g else None
    if not ch: return
    try:
        col = discord.Color.blurple()
        if body.get("color"):
            try: col = discord.Color.from_str(body["color"])
            except Exception: pass
        emb = discord.Embed(title=body.get("title", ""), description=body.get("description", ""),
                            color=col, timestamp=discord.utils.utcnow())
        emb.set_footer(text=f"By {author_id}")
        if body.get("image_url") and str(body["image_url"]).startswith("http"):
            emb.set_image(url=body["image_url"])
        await ch.send(embed=emb)
    except Exception as e:
        print(f"[EMBED_SEND] {e}")

# --------- Ticket deploy ---------
@flask_app.route("/api/guilds/<guild_id>/tickets/deploy", methods=["POST", "OPTIONS"])
def api_ticket_deploy(guild_id):
    if request.method == "OPTIONS":
        return ("", 204)
    s, err = _require_guild_access(guild_id)
    if err: return err
    body = request.get_json(silent=True) or {}
    ch_id = body.get("channel_id")
    if not ch_id:
        return jsonify({"success": False, "error": {"code": "INVALID", "message": "channel_id required"}}), 400
    asyncio.run_coroutine_threadsafe(_deploy_ticket_panel(guild_id, ch_id), bot.loop)
    return jsonify({"success": True, "data": {"queued": True}})

async def _deploy_ticket_panel(guild_id, ch_id):
    g = bot.get_guild(int(guild_id))
    ch = g.get_channel(int(ch_id)) if g else None
    if not ch: return
    tc = load_data("ticket_config", {}).get(str(guild_id), {})
    desc = tc.get("panel_desc", "Need assistance? Click below for a private support channel.")
    emb = discord.Embed(title="📩 Help & Support Portal", description=desc, color=0x57F287)
    emb.set_footer(text="Stardust Helpdesk")
    try:
        await ch.send(embed=emb, view=TicketLauncherView())
    except Exception as e:
        print(f"[TICKET_DEPLOY] {e}")

# ==============================================================================
# 🚀 STARTUP
# ==============================================================================
def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True, use_reloader=False)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

def run_bot():
    if not DISCORD_TOKEN:
        print("❌ Missing DISCORD_TOKEN"); return
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except Exception as e:
        print(f"[BOT] Fatal: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Starting Stardust…")
    keep_alive()
    time.sleep(2)
    run_bot()
