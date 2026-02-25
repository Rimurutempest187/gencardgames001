#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════╗
║      CHARACTER COLLECTION GAME BOT           ║
║         Created by : @Enoch_777             ║
╚══════════════════════════════════════════════╝
"""

import asyncio, json, os, random, time, logging, threading
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InlineQueryResultCachedPhoto,
    InputTextMessageContent,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, InlineQueryHandler,
    filters, ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# ───────────────────────────── CONFIG
TOKEN    = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DB_FILE  = "data/database.json"
BKUP_DIR = "data/backups"

# ───────────────────────────── LOGGING
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ───────────────────────────── RARITY
RARITIES = {
    "Common":    {"emoji": "🪔", "weight": 50, "price": 100,  "fp": (1,  30)},
    "Rare":      {"emoji": "✨", "weight": 25, "price": 300,  "fp": (25, 55)},
    "Epic":      {"emoji": "🔮", "weight": 15, "price": 700,  "fp": (50, 75)},
    "Legendary": {"emoji": "🧿", "weight":  7, "price": 1500, "fp": (70, 90)},
    "Mythic":    {"emoji": "💠", "weight":  3, "price": 3000, "fp": (85,100)},
}
R_KEYS = list(RARITIES.keys())
R_WTS  = [RARITIES[r]["weight"] for r in R_KEYS]

DAILY_BASE     = 200
DAILY_PER_CHAR = 5
SLOTS_SYMS     = ["🍎","🍊","🍋","🍇","🍓","🎰","💎","⭐","🔔"]


# ══════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════
class DB:
    def __init__(self, path: str):
        self.path = path
        self._lk  = threading.Lock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if not Path(path).exists():
            self._w(self._fresh())

    # ── internals ──────────────────────────────
    def _fresh(self):
        return {
            "users": {}, "characters": {}, "groups": {},
            "sudo_users": [OWNER_ID] if OWNER_ID else [],
            "active_vote": None,
            "settings": {"default_drop": 50},
            "char_counter": 0,
        }

    def _r(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            d = self._fresh(); self._w(d); return d

    def _w(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        with self._lk: return self._r()

    def save(self, data):
        with self._lk: self._w(data)

    # ── USER ───────────────────────────────────
    def get_user(self, uid: int, name="", uname=""):
        d = self.load(); k = str(uid); changed = False
        if k not in d["users"]:
            d["users"][k] = {"name": name or f"User{uid}", "username": uname,
                             "coins": 500, "bank": 0, "characters": [],
                             "favorite": None, "last_daily": None, "last_fight": 0.0}
            changed = True
        else:
            if name  and d["users"][k].get("name")     != name:  d["users"][k]["name"]     = name;  changed = True
            if uname and d["users"][k].get("username") != uname: d["users"][k]["username"] = uname; changed = True
        if changed: self.save(d)
        return d["users"][k]

    def upd_user(self, uid: int, patch: dict):
        d = self.load(); k = str(uid)
        if k in d["users"]: d["users"][k].update(patch); self.save(d)

    def all_users(self): return self.load()["users"]

    # ── CHARACTER ──────────────────────────────
    def get_char(self, cid: str) -> Optional[dict]: return self.load()["characters"].get(cid)
    def all_chars(self) -> dict:                     return self.load()["characters"]

    def add_char(self, payload: dict) -> str:
        d = self.load(); d["char_counter"] += 1
        cid = f"char_{d['char_counter']:04d}"
        payload["id"] = cid; d["characters"][cid] = payload
        self.save(d); return cid

    def del_char(self, cid: str) -> bool:
        d = self.load()
        if cid in d["characters"]: del d["characters"][cid]; self.save(d); return True
        return False

    # ── GROUP ──────────────────────────────────
    def get_group(self, gid: int) -> dict:
        d = self.load(); k = str(gid)
        if k not in d["groups"]:
            d["groups"][k] = {"drop_interval": d["settings"]["default_drop"],
                              "msg_count": 0, "current_drop": None, "members": []}
            self.save(d)
        return d["groups"][k]

    def upd_group(self, gid: int, patch: dict):
        d = self.load(); k = str(gid)
        if k not in d["groups"]: self.get_group(gid); d = self.load()
        d["groups"][k].update(patch); self.save(d)

    def all_groups(self): return self.load()["groups"]

    # ── SUDO ───────────────────────────────────
    def is_sudo(self, uid: int): return uid == OWNER_ID or uid in self.load()["sudo_users"]

    def add_sudo(self, uid: int) -> bool:
        d = self.load()
        if uid not in d["sudo_users"]: d["sudo_users"].append(uid); self.save(d); return True
        return False

    def del_sudo(self, uid: int) -> bool:
        d = self.load()
        if uid in d["sudo_users"] and uid != OWNER_ID:
            d["sudo_users"].remove(uid); self.save(d); return True
        return False

    def sudo_list(self): return self.load()["sudo_users"]

    # ── VOTE ───────────────────────────────────
    def set_vote(self, v): d = self.load(); d["active_vote"] = v; self.save(d)
    def get_vote(self):    return self.load()["active_vote"]

    # ── BACKUP / RESTORE / CLEAR ───────────────
    def backup(self, dest: str):
        import shutil; shutil.copy2(self.path, dest)

    def restore_bytes(self, raw: bytes) -> bool:
        try: self.save(json.loads(raw.decode("utf-8"))); return True
        except Exception: return False

    def clear_all(self): self.save(self._fresh())


db = DB(DB_FILE)


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def rem(r):  return RARITIES.get(r, {}).get("emoji", "❓")
def rfp(r):  lo, hi = RARITIES.get(r, {}).get("fp", (1,50)); return random.randint(lo, hi)
def is_grp(u: Update): return u.effective_chat.type in ("group", "supergroup")

async def sudo_check(upd: Update) -> bool:
    if db.is_sudo(upd.effective_user.id): return True
    await upd.message.reply_text("⛔ Admin / Sudo User များသာ အသုံးပြုနိုင်သည်!")
    return False

def mask(name: str) -> str:
    if len(name) <= 2: return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]

def char_add(uid: int, cid: str):
    u = db.get_user(uid); chars = u.get("characters", [])
    for c in chars:
        if c["id"] == cid: c["count"] = c.get("count", 1) + 1; db.upd_user(uid, {"characters": chars}); return
    chars.append({"id": cid, "count": 1}); db.upd_user(uid, {"characters": chars})

def char_remove(uid: int, cid: str) -> bool:
    u = db.get_user(uid); chars = u.get("characters", [])
    for i, c in enumerate(chars):
        if c["id"] == cid:
            if c.get("count", 1) > 1: c["count"] -= 1
            else: chars.pop(i)
            db.upd_user(uid, {"characters": chars}); return True
    return False

def char_has(uid: int, cid: str) -> bool:
    return any(c["id"] == cid for c in db.get_user(uid).get("characters", []))

def make_profile(ud: dict, uid: int) -> str:
    chars = ud.get("characters", [])
    total = sum(c.get("count", 1) for c in chars)
    rc    = {r: 0 for r in R_KEYS}
    ac    = db.all_chars()
    for c in chars:
        ci = ac.get(c["id"])
        if ci: rc[ci["rarity"]] = rc.get(ci["rarity"], 0) + c.get("count", 1)
    fav   = ac.get(ud.get("favorite", ""))
    uname = f"@{ud['username']}" if ud.get("username") else "N/A"
    txt = (
        "╔══════════════════╗\n"
        "║  👤 PLAYER PROFILE  ║\n"
        "╚══════════════════╝\n\n"
        f"📛 **Name:** {ud['name']}\n"
        f"🆔 **ID:** `{uid}`\n"
        f"🔗 **Username:** {uname}\n\n"
        "💎 **Character Collection:**\n"
        f"├ 🪔 Common    : {rc['Common']}\n"
        f"├ ✨ Rare      : {rc['Rare']}\n"
        f"├ 🔮 Epic      : {rc['Epic']}\n"
        f"├ 🧿 Legendary : {rc['Legendary']}\n"
        f"└ 💠 Mythic    : {rc['Mythic']}\n"
        f"📦 **Total:** {total} Characters\n\n"
        f"💰 **Coins:** {ud['coins']:,}\n"
        f"🏦 **Bank :** {ud['bank']:,}"
    )
    if fav: txt += f"\n\n⭐ **Favorite:** {rem(fav['rarity'])} {fav['name']} ({fav['rarity']})"
    return txt

def do_spin():
    s = [random.choice(SLOTS_SYMS) for _ in range(3)]
    if s[0]==s[1]==s[2]:
        mul = {"💎":5,"⭐":4,"🎰":3}.get(s[0], 2)
    elif s[0]==s[1] or s[1]==s[2] or s[0]==s[2]:
        mul = 1
    else:
        mul = 0
    return s, mul


# ══════════════════════════════════════════════
#  USER COMMANDS
# ══════════════════════════════════════════════
async def c_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    if is_grp(upd):
        g = db.get_group(upd.effective_chat.id)
        if str(u.id) not in g["members"]:
            g["members"].append(str(u.id))
            db.upd_group(upd.effective_chat.id, {"members": g["members"]})
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Help",    callback_data="x_help"),
         InlineKeyboardButton("👤 Profile", callback_data=f"x_prof_{u.id}")],
        [InlineKeyboardButton("🎒 Harem",   callback_data=f"x_harem_{u.id}_0"),
         InlineKeyboardButton("💰 Balance", callback_data=f"x_bal_{u.id}")],
    ])
    txt = (
        "🎮 **Character Collection Game**\n\n"
        f"မင်္ဂလာပါ **{u.first_name}**! ကြိုဆိုပါသည်!\n\n"
        "Group ထဲ Message ပို့တိုင်း Character Card ကျလာမည်!\n"
        "/slime `<name>` ဖြင့် ဖမ်းယူပြီး Collection တည်ဆောက်ပါ!\n\n"
        "💎 **Rarity Tiers:**\n"
        "🪔 Common | ✨ Rare | 🔮 Epic | 🧿 Legendary | 💠 Mythic\n\n"
        f"💰 **Starting Coins:** {ud['coins']:,}\n\n"
        "📖 Commands → /helps\n\n"
        "> Created by : @Enoch\\_777"
    )
    await upd.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")


async def c_helps(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = (
        "📖 **USER COMMANDS**\n\n"
        "🎮 **Basic**\n"
        "├ /start — Bot ကို နှိုးစက်ရန်\n"
        "├ /helps — Command List ကြည့်ရန်\n"
        "├ /profile — Profile စစ်ဆေးရန်\n"
        "└ /balance — Coin လက်ကျန် ကြည့်ရန်\n\n"
        "⚔️ **Game**\n"
        "├ /slime `<name>` — Card ဖမ်းရန်\n"
        "├ /harem — Collection ကြည့်ရန် (5/page)\n"
        "├ /fight — Random ကတ်နှင့် တိုက်ရန် (30s CD)\n"
        "├ /set `<card_id>` — Favorite Character သတ်မှတ်ရန်\n"
        "├ /check `<id>` — Character Info ကြည့်ရန်\n"
        "└ /search — Inline Search\n\n"
        "🎰 **Casino**\n"
        "├ /slots `<amount>` — Slot Machine (2x–5x)\n"
        "└ /basket `<amount>` — Basketball (2x)\n\n"
        "💸 **Economy**\n"
        "├ /daily — Daily Bonus\n"
        "├ /shop — Character Shop\n"
        "├ /save `<amount>` — Bank ထဲ ထည့်ရန်\n"
        "├ /withdraw `<amount>` — Bank မှ ထုတ်ရန်\n"
        "├ /givecoin `<amount>` (reply) — Coin ပေးရန်\n"
        "└ /givechar `<id>` (reply) — Character ပေးရန်\n\n"
        "🏆 **Social**\n"
        "├ /tops — Leaderboard Top 10\n"
        "├ /vote — မဲပေးရန်\n"
        "└ /all — Group Members Mention\n\n"
        "💎 **Rarities:** 🪔 Common | ✨ Rare | 🔮 Epic | 🧿 Legendary | 💠 Mythic\n\n"
        "> Created by : @Enoch\\_777"
    )
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_profile(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    fav = db.get_char(ud.get("favorite",""))
    kb  = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data=f"x_prof_{u.id}")]])
    txt = make_profile(ud, u.id)
    if fav and fav.get("photo_file_id"):
        await upd.message.reply_photo(photo=fav["photo_file_id"], caption=txt,
                                      parse_mode="Markdown", reply_markup=kb)
    else:
        await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)


async def c_slime(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_grp(upd):
        await upd.message.reply_text("❌ Group တွင်သာ အသုံးပြုနိုင်သည်!"); return
    if not ctx.args:
        await upd.message.reply_text("❌ Usage: /slime `<character name>`", parse_mode="Markdown"); return
    gid   = upd.effective_chat.id
    g     = db.get_group(gid)
    drop  = g.get("current_drop")
    if not drop:
        await upd.message.reply_text("❌ ကျလာနေသော Card မရှိပါ!"); return
    char = db.get_char(drop)
    if not char:
        db.upd_group(gid, {"current_drop": None})
        await upd.message.reply_text("❌ Card မတွေ့ပါ!"); return
    guess = " ".join(ctx.args).strip()
    u     = upd.effective_user
    db.get_user(u.id, u.full_name, u.username or "")
    if guess.lower() == char["name"].lower():
        char_add(u.id, drop)
        db.upd_group(gid, {"current_drop": None})
        txt = (
            "🎉 **ဖမ်းယူအောင်မြင်သည်!**\n\n"
            f"👤 **{u.first_name}** ဖမ်းယူပြီး!\n"
            f"{rem(char['rarity'])} **{char['name']}**\n"
            f"🎬 {char.get('movie','?')}\n"
            f"💎 Rarity: **{char['rarity']}**\n\n"
            "✅ Collection ထဲ ထည့်သွင်းပြီးပါပြီ!"
        )
        if char.get("photo_file_id"):
            await upd.message.reply_photo(photo=char["photo_file_id"], caption=txt, parse_mode="Markdown")
        else:
            await upd.message.reply_text(txt, parse_mode="Markdown")
    else:
        await upd.message.reply_text("❌ မှားသည်! ထပ်မံ ကြိုးစားပါ!")


async def c_harem(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _harem(upd, ctx, upd.effective_user.id, 0)

async def _harem(upd: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int, page: int):
    ud    = db.get_user(uid)
    chars = ud.get("characters", [])
    if not chars:
        msg = ("📦 Collection ထဲတွင် Character မရှိသေးပါ!\n"
               "/shop မှ ဝယ်ယူပါ သို့မဟုတ် Group တွင် /slime ဖြင့် ဖမ်းပါ!")
        if upd.callback_query: await upd.callback_query.edit_message_text(msg)
        else:                   await upd.message.reply_text(msg)
        return
    PER   = 5
    pages = max(1, -(-len(chars)//PER))
    page  = max(0, min(page, pages-1))
    chunk = chars[page*PER : page*PER+PER]
    ac    = db.all_chars()
    total = sum(c.get("count",1) for c in chars)
    txt   = (
        f"🎒 **HAREM — {ud['name']}**\n"
        f"📊 Page {page+1}/{pages}  •  Total: {total}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    for c in chunk:
        ci  = ac.get(c["id"])
        cnt = c.get("count",1)
        if ci:
            txt += f"{rem(ci['rarity'])} **{ci['name']}**"
            if cnt > 1: txt += f"  ×{cnt}"
            txt += f"\n   🎬 {ci.get('movie','?')}  •  🆔 `{c['id']}`\n\n"
        else:
            txt += f"❓ Unknown  •  🆔 `{c['id']}`\n\n"
    nav = []
    if page > 0:       nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"x_harem_{uid}_{page-1}"))
    if page < pages-1: nav.append(InlineKeyboardButton("Next ▶", callback_data=f"x_harem_{uid}_{page+1}"))
    kb = [nav] if nav else []
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data=f"x_harem_{uid}_{page}")])
    rm = InlineKeyboardMarkup(kb)
    if upd.callback_query: await upd.callback_query.edit_message_text(txt, parse_mode="Markdown", reply_markup=rm)
    else:                   await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=rm)


async def c_set(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await upd.message.reply_text("❌ Usage: /set `<card_id>`", parse_mode="Markdown"); return
    cid  = ctx.args[0].strip()
    uid  = upd.effective_user.id
    if not char_has(uid, cid):
        await upd.message.reply_text("❌ မိမိ Collection ထဲတွင် ဤ Character မရှိပါ!"); return
    char = db.get_char(cid)
    if not char:
        await upd.message.reply_text("❌ Character မတွေ့ပါ!"); return
    db.upd_user(uid, {"favorite": cid})
    await upd.message.reply_text(
        f"⭐ Favorite သတ်မှတ်ပြီး!\n\n{rem(char['rarity'])} **{char['name']}** ({char['rarity']})",
        parse_mode="Markdown")


async def c_check(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await upd.message.reply_text("❌ Usage: /check `<card_id>`", parse_mode="Markdown"); return
    cid  = ctx.args[0].strip()
    char = db.get_char(cid)
    if not char:
        await upd.message.reply_text("❌ Character မတွေ့ပါ!"); return
    ri  = RARITIES.get(char["rarity"], {})
    txt = (
        "╔══════════════════╗\n"
        "║  💎 CHARACTER INFO  ║\n"
        "╚══════════════════╝\n\n"
        f"{rem(char['rarity'])} **{char['name']}**\n"
        f"🎬 **Series:** {char.get('movie','?')}\n"
        f"💎 **Rarity:** {char['rarity']}\n"
        f"🆔 **ID:** `{cid}`\n"
        f"💰 **Price:** {ri.get('price',0):,} coins\n"
        f"⚔️ **Fight Power:** {ri['fp'][0]}–{ri['fp'][1]}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy", callback_data=f"x_buy_{cid}")]])
    if char.get("photo_file_id"):
        await upd.message.reply_photo(photo=char["photo_file_id"], caption=txt,
                                      parse_mode="Markdown", reply_markup=kb)
    else:
        await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb)


async def c_fight(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = upd.effective_user
    ud  = db.get_user(u.id, u.full_name, u.username or "")
    now = time.time()
    if now - ud.get("last_fight",0) < 30:
        left = int(30-(now-ud["last_fight"]))
        await upd.message.reply_text(f"⏳ Cooldown! **{left}s** ကျန်သည်!", parse_mode="Markdown"); return
    ac = db.all_chars()
    if not ac:
        await upd.message.reply_text("❌ Character မရှိသေးပါ! Admin ထည့်ပါ!"); return
    opp_id  = random.choice(list(ac.keys()))
    opp     = ac[opp_id]
    opp_pow = rfp(opp["rarity"])
    best    = 10
    for c in ud.get("characters",[]):
        ci = ac.get(c["id"])
        if ci: best = max(best, rfp(ci["rarity"]))
    my_pow = best + random.randint(-5, 10)
    db.upd_user(u.id, {"last_fight": now})
    txt = (
        "⚔️ **FIGHT!**\n\n"
        f"**{u.first_name}** VS {rem(opp['rarity'])} **{opp['name']}**\n\n"
        f"🗡️ Your Power : **{my_pow}**\n"
        f"🛡️ Enemy Power: **{opp_pow}**\n\n"
    )
    if my_pow >= opp_pow:
        char_add(u.id, opp_id)
        txt += (
            "🏆 **YOU WIN!**\n\n"
            f"{rem(opp['rarity'])} **{opp['name']}** ရရှိပြီး!\n"
            f"🎬 {opp.get('movie','?')}  •  💎 {opp['rarity']}"
        )
        if opp.get("photo_file_id"):
            await upd.message.reply_photo(photo=opp["photo_file_id"], caption=txt, parse_mode="Markdown"); return
    else:
        txt += (
            "💀 **YOU LOSE!**\n\n"
            "Character ပိုစုပြီး ပြန်ကြိုးစားပါ!\n⏳ Cooldown: 30s"
        )
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_search(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    me = (await ctx.bot.get_me()).username
    await upd.message.reply_text(
        f"🔍 **Inline Search**\n\nChat Box တွင်:\n`@{me} <character name>`\nဟု ရိုက်ပါ!",
        parse_mode="Markdown")


async def c_slots(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ Usage: /slots `<amount>`  (Min: 10)", parse_mode="Markdown"); return
    amt = int(ctx.args[0])
    if amt < 10:
        await upd.message.reply_text("❌ အနည်းဆုံး 10 coins!"); return
    if ud["coins"] < amt:
        await upd.message.reply_text(f"❌ Coins မလုံပါ!  Wallet: {ud['coins']:,}"); return
    s, mul    = do_spin()
    new_coins = ud["coins"] - amt
    txt = (
        "🎰 **SLOT MACHINE**\n\n"
        "╔══════════════╗\n"
        f"║  {s[0]}  {s[1]}  {s[2]}  ║\n"
        "╚══════════════╝\n\n"
        f"💰 Bet: {amt:,} coins\n"
    )
    if mul > 0:
        win       = amt * mul; new_coins += win
        txt += f"🎉 **WIN! ×{mul}** → +{win:,} coins\n"
    else:
        txt += f"💸 **LOSE!** → −{amt:,} coins\n"
    txt += f"💵 Balance: {new_coins:,}"
    db.upd_user(u.id, {"coins": new_coins})
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_basket(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ Usage: /basket `<amount>`  (Min: 10)", parse_mode="Markdown"); return
    amt = int(ctx.args[0])
    if amt < 10:
        await upd.message.reply_text("❌ အနည်းဆုံး 10 coins!"); return
    if ud["coins"] < amt:
        await upd.message.reply_text("❌ Coins မလုံပါ!"); return
    win       = random.random() < 0.45
    anim      = random.choice(["🏀 ➡️ 🎯", "🏀 🌀 🏆", "🏀 💨 🔥", "🏀 ⤴️ 🎯"])
    new_coins = ud["coins"] - amt
    if win:
        new_coins += amt * 2
        result = f"╔══════════╗\n║ 🏆 SCORE! ║\n╚══════════╝\n🎉 Win: +{amt*2:,} coins"
    else:
        result = f"╔══════════╗\n║ 💔 MISS!  ║\n╚══════════╝\n💸 Lost: −{amt:,} coins"
    txt = (
        "🏀 **BASKETBALL GAME**\n\n"
        f"{anim}\n\n"
        f"{result}\n\n"
        f"💰 Bet: {amt:,}  •  💵 Balance: {new_coins:,}"
    )
    db.upd_user(u.id, {"coins": new_coins})
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_givecoin(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not upd.message.reply_to_message:
        await upd.message.reply_text("❌ User ၏ Message ကို Reply ပြုပြီး /givecoin `<amount>`", parse_mode="Markdown"); return
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ Usage: /givecoin `<amount>` (reply)", parse_mode="Markdown"); return
    amt = int(ctx.args[0])
    if amt < 1:
        await upd.message.reply_text("❌ Amount ≥ 1!"); return
    u  = upd.effective_user
    sd = db.get_user(u.id, u.full_name, u.username or "")
    if sd["coins"] < amt:
        await upd.message.reply_text(f"❌ Coins မလုံပါ!  Wallet: {sd['coins']:,}"); return
    t = upd.message.reply_to_message.from_user
    if t.id == u.id:
        await upd.message.reply_text("❌ မိမိကိုယ်တိုင် မပေးနိုင်!"); return
    td = db.get_user(t.id, t.full_name, t.username or "")
    db.upd_user(u.id, {"coins": sd["coins"]-amt})
    db.upd_user(t.id, {"coins": td["coins"]+amt})
    await upd.message.reply_text(
        f"💸 **Coin Transfer ✅**\n\n📤 {u.first_name} → {t.first_name}\n💰 {amt:,} coins",
        parse_mode="Markdown")


async def c_givechar(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not upd.message.reply_to_message:
        await upd.message.reply_text("❌ User ၏ Message ကို Reply ပြုပြီး /givechar `<card_id>`", parse_mode="Markdown"); return
    if not ctx.args:
        await upd.message.reply_text("❌ Usage: /givechar `<card_id>` (reply)", parse_mode="Markdown"); return
    cid  = ctx.args[0].strip()
    u    = upd.effective_user
    if not char_has(u.id, cid):
        await upd.message.reply_text("❌ Collection ထဲ ဤ Character မရှိပါ!"); return
    char = db.get_char(cid)
    if not char:
        await upd.message.reply_text("❌ Character မတွေ့!"); return
    t = upd.message.reply_to_message.from_user
    if t.id == u.id:
        await upd.message.reply_text("❌ မိမိကိုယ်တိုင် မပေးနိုင်!"); return
    char_remove(u.id, cid)
    db.get_user(t.id, t.full_name, t.username or "")
    char_add(t.id, cid)
    await upd.message.reply_text(
        f"🎁 **Character Gift ✅**\n\n📤 {u.first_name} → {t.first_name}\n{rem(char['rarity'])} **{char['name']}** ({char['rarity']})",
        parse_mode="Markdown")


async def c_balance(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    await upd.message.reply_text(
        f"💰 **BALANCE — {u.first_name}**\n\n"
        f"💵 Wallet : {ud['coins']:,} coins\n"
        f"🏦 Bank   : {ud['bank']:,} coins\n"
        f"📊 Total  : {ud['coins']+ud['bank']:,} coins",
        parse_mode="Markdown")


async def c_save(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ Usage: /save `<amount>`", parse_mode="Markdown"); return
    amt = int(ctx.args[0])
    if amt < 1 or ud["coins"] < amt:
        await upd.message.reply_text(f"❌ Amount မမှန်!  Wallet: {ud['coins']:,}"); return
    db.upd_user(u.id, {"coins": ud["coins"]-amt, "bank": ud["bank"]+amt})
    await upd.message.reply_text(
        f"🏦 **Deposit ✅**\n\n+{amt:,} coins → Bank\n"
        f"💵 Wallet: {ud['coins']-amt:,}  •  🏦 Bank: {ud['bank']+amt:,}",
        parse_mode="Markdown")


async def c_withdraw(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u  = upd.effective_user
    ud = db.get_user(u.id, u.full_name, u.username or "")
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ Usage: /withdraw `<amount>`", parse_mode="Markdown"); return
    amt = int(ctx.args[0])
    if amt < 1 or ud["bank"] < amt:
        await upd.message.reply_text(f"❌ Bank: {ud['bank']:,}"); return
    db.upd_user(u.id, {"coins": ud["coins"]+amt, "bank": ud["bank"]-amt})
    await upd.message.reply_text(
        f"💸 **Withdraw ✅**\n\n+{amt:,} coins ← Bank\n"
        f"💵 Wallet: {ud['coins']+amt:,}  •  🏦 Bank: {ud['bank']-amt:,}",
        parse_mode="Markdown")


async def c_daily(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u     = upd.effective_user
    ud    = db.get_user(u.id, u.full_name, u.username or "")
    today = date.today().isoformat()
    if ud.get("last_daily") == today:
        await upd.message.reply_text("⏰ Daily Bonus ယနေ့ ရပြီးပါပြီ!\nမနက်ဖြန် ပြန်လာပါ! 🌅"); return
    base  = DAILY_BASE + len(ud.get("characters",[])) * DAILY_PER_CHAR
    bonus = random.randint(0, 150)
    total = base + bonus
    db.upd_user(u.id, {"coins": ud["coins"]+total, "last_daily": today})
    await upd.message.reply_text(
        "🌟 **DAILY BONUS!**\n\n"
        f"💰 Base : {base:,}\n"
        f"🎁 Extra: +{bonus}\n"
        "━━━━━━━━━━━━\n"
        f"✅ Total: +{total:,} coins\n\n"
        f"💵 New Balance: {ud['coins']+total:,}\n\n"
        "မနက်ဖြန် ထပ်မံ ရယူနိုင်! 🌅",
        parse_mode="Markdown")


async def c_shop(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = upd.effective_user; db.get_user(u.id, u.full_name, u.username or "")
    if not db.all_chars():
        await upd.message.reply_text("🏪 Shop တွင် Character မရှိသေးပါ!"); return
    await _shop(upd, ctx, u.id, 0)

async def _shop(upd: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int, page: int):
    ud   = db.get_user(uid)
    clist= list(db.all_chars().items())
    PER  = 5; pages = max(1,-(-len(clist)//PER)); page = max(0, min(page, pages-1))
    chunk= clist[page*PER : page*PER+PER]
    txt  = (
        "🏪 **CHARACTER SHOP**\n"
        f"💰 Your Coins: {ud['coins']:,}\n"
        f"📊 Page {page+1}/{pages}\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    kb = []
    for cid, c in chunk:
        price = RARITIES.get(c["rarity"],{}).get("price",100)
        txt  += f"{rem(c['rarity'])} **{c['name']}** — {price:,} 💰\n"
        txt  += f"   🎬 {c.get('movie','?')}  •  💎 {c['rarity']}\n\n"
        kb.append([InlineKeyboardButton(f"🛒 {c['name']} ({price:,}💰)", callback_data=f"x_buy_{cid}")])
    nav = []
    if page > 0:       nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"x_shop_{uid}_{page-1}"))
    if page < pages-1: nav.append(InlineKeyboardButton("Next ▶", callback_data=f"x_shop_{uid}_{page+1}"))
    if nav: kb.append(nav)
    rm = InlineKeyboardMarkup(kb)
    if upd.callback_query: await upd.callback_query.edit_message_text(txt, parse_mode="Markdown", reply_markup=rm)
    else:                   await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=rm)


async def c_tops(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users  = db.all_users()
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    t_coin = sorted(users.items(), key=lambda x: x[1].get("coins",0)+x[1].get("bank",0), reverse=True)[:10]
    t_card = sorted(users.items(), key=lambda x: sum(c.get("count",1) for c in x[1].get("characters",[])), reverse=True)[:10]
    txt    = "🏆 **LEADERBOARD**\n\n"
    txt   += "💰 **Top 10 — Richest Players**\n"
    for i,(uid,d) in enumerate(t_coin):
        txt += f"{medals[i]} **{d['name']}**: {d.get('coins',0)+d.get('bank',0):,} coins\n"
    txt += "\n🃏 **Top 10 — Most Characters**\n"
    for i,(uid,d) in enumerate(t_card):
        total = sum(c.get("count",1) for c in d.get("characters",[]))
        txt += f"{medals[i]} **{d['name']}**: {total} cards\n"
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_vote(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    v = db.get_vote()
    if not v:
        await upd.message.reply_text("📊 Active Vote မရှိပါ!\nAdmin က /evote ဖြင့် စတင်နိုင်!"); return
    u     = upd.effective_user
    opts  = v.get("options",[]); votes = v.get("votes",{})
    voted = any(str(u.id) in votes.get(o,[]) for o in opts)
    txt   = "📊 **VOTE NOW!**\n\n"
    kb    = []
    for o in opts:
        cnt  = len(votes.get(o,[])); txt += f"• {o}: {cnt} votes\n"
        kb.append([InlineKeyboardButton(f"🗳 {o}", callback_data=f"x_vote_{o}")])
    if voted: txt += "\n✅ သင် မဲပြီးပါပြီ!"
    kb.append([InlineKeyboardButton("📊 Results", callback_data="x_voteresults")])
    await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def c_all(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_grp(upd):
        await upd.message.reply_text("❌ Group တွင်သာ အသုံးပြုနိုင်!"); return
    g    = db.get_group(upd.effective_chat.id)
    au   = db.all_users(); parts = []
    for m in g.get("members",[]):
        ud = au.get(m)
        if ud:
            parts.append(f"@{ud['username']}" if ud.get("username") else f"[{ud['name']}](tg://user?id={m})")
    if parts: await upd.message.reply_text("📢 **All Members!**\n\n" + " ".join(parts), parse_mode="Markdown")
    else:     await upd.message.reply_text("👥 Member မရှိသေးပါ!")


# ══════════════════════════════════════════════
#  ADMIN / SUDO COMMANDS
# ══════════════════════════════════════════════
async def c_edit(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    await upd.message.reply_text(
        "⚡️ **ADMIN PANEL**\n\n"
        "📤 **Content**\n"
        "├ /upload (reply photo) `<name>|<movie>|<rarity>`\n"
        "└ /delete `<card_id>`\n\n"
        "⚙️ **Settings**\n"
        "├ /setdrop `<n>` — Drop interval\n"
        "├ /addsudo — Sudo ထည့်ရန်\n"
        "├ /delete sudo `<id>` — Sudo ဖယ်ရန်\n"
        "└ /sudolist\n\n"
        "🎁 **Gift**\n"
        "├ /gift coin `<amt>` (reply/id)\n"
        "└ /gift card `<amt>` (reply/id)\n\n"
        "📢 /broadcast\n\n"
        "📊 **Database**\n"
        "├ /stats  ├ /backup  ├ /restore  └ /allclear ⚠️\n\n"
        "🗳️ /evote `<opt1>|<opt2>|…`",
        parse_mode="Markdown")


async def c_upload(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not upd.message.reply_to_message or not upd.message.reply_to_message.photo:
        await upd.message.reply_text(
            "❌ Photo ကို Reply ပြုပြီး:\n"
            "/upload `<name> | <movie> | <rarity>`\n\n"
            f"Rarities: {', '.join(R_KEYS)}", parse_mode="Markdown"); return
    if not ctx.args:
        await upd.message.reply_text("❌ /upload `<name> | <movie> | <rarity>`", parse_mode="Markdown"); return
    parts = [p.strip() for p in " ".join(ctx.args).split("|")]
    if len(parts) < 3:
        await upd.message.reply_text("❌ Format: `name | movie | rarity`", parse_mode="Markdown"); return
    name, movie, rarity = parts[0], parts[1], parts[2]
    if rarity not in RARITIES:
        await upd.message.reply_text(f"❌ Rarity မမှန်!  Valid: {', '.join(R_KEYS)}"); return
    fid = upd.message.reply_to_message.photo[-1].file_id
    cid = db.add_char({"name": name, "movie": movie, "rarity": rarity,
                        "photo_file_id": fid,
                        "added_by": upd.effective_user.id,
                        "added_at": datetime.now().isoformat()})
    await upd.message.reply_text(
        f"✅ **Upload ✅**\n\n{rem(rarity)} **{name}**\n🎬 {movie}  •  💎 {rarity}\n🆔 `{cid}`",
        parse_mode="Markdown")


async def c_setdrop(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not is_grp(upd):
        await upd.message.reply_text("❌ Group ထဲတွင်သာ!"); return
    if not ctx.args or not ctx.args[0].isdigit():
        await upd.message.reply_text("❌ /setdrop `<n>`  (min 5)", parse_mode="Markdown"); return
    n = int(ctx.args[0])
    if n < 5:
        await upd.message.reply_text("❌ Min 5!"); return
    db.upd_group(upd.effective_chat.id, {"drop_interval": n})
    await upd.message.reply_text(f"✅ Drop interval: **{n}** messages", parse_mode="Markdown")


async def c_gift(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if len(ctx.args) < 2:
        await upd.message.reply_text("❌ /gift coin|card `<amount>` (reply/id)", parse_mode="Markdown"); return
    gtype = ctx.args[0].lower()
    if gtype not in ("coin","card") or not ctx.args[1].isdigit():
        await upd.message.reply_text("❌ /gift coin|card `<amount>`", parse_mode="Markdown"); return
    amount = int(ctx.args[1])
    tid = None; tname = "?"
    if upd.message.reply_to_message:
        t = upd.message.reply_to_message.from_user; tid = t.id; tname = t.first_name
    elif len(ctx.args) >= 3 and ctx.args[2].isdigit():
        tid = int(ctx.args[2]); td = db.get_user(tid); tname = td.get("name", str(tid))
    else:
        await upd.message.reply_text("❌ Reply / ID ထည့်ပါ!"); return
    db.get_user(tid)
    if gtype == "coin":
        td = db.get_user(tid); db.upd_user(tid, {"coins": td["coins"]+amount})
        await upd.message.reply_text(f"🎁 **Coin Gift ✅**\n👤 {tname}  +{amount:,} coins", parse_mode="Markdown")
    else:
        ac = db.all_chars()
        if not ac:
            await upd.message.reply_text("❌ Character မရှိ!"); return
        given = []
        for _ in range(amount):
            rid = random.choice(list(ac.keys())); char_add(tid, rid); given.append(ac[rid])
        preview = "\n".join(f"{rem(c['rarity'])} {c['name']}" for c in given[:5])
        extra   = f"\n...+{len(given)-5} more" if len(given) > 5 else ""
        await upd.message.reply_text(
            f"🎁 **Card Gift ✅**\n👤 {tname}  •  {amount} cards\n\n{preview}{extra}",
            parse_mode="Markdown")


async def c_broadcast(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not upd.message.reply_to_message and not ctx.args:
        await upd.message.reply_text("❌ Reply ပြုပါ / /broadcast `<text>`", parse_mode="Markdown"); return
    groups = db.all_groups(); ok = fail = 0
    for gid in groups:
        try:
            if upd.message.reply_to_message:
                rm = upd.message.reply_to_message
                if rm.text: await ctx.bot.send_message(int(gid), rm.text)
                elif rm.photo: await ctx.bot.send_photo(int(gid), rm.photo[-1].file_id, caption=rm.caption or "")
            else:
                await ctx.bot.send_message(int(gid), "📢 **Broadcast**\n\n" + " ".join(ctx.args), parse_mode="Markdown")
            ok += 1; await asyncio.sleep(0.05)
        except Exception: fail += 1
    await upd.message.reply_text(f"📢 **Broadcast ✅**\n✅ {ok}  ❌ {fail}", parse_mode="Markdown")


async def c_stats(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    d  = db.load()
    rc = {r:0 for r in R_KEYS}
    for c in d["characters"].values(): rc[c["rarity"]] = rc.get(c["rarity"],0)+1
    await upd.message.reply_text(
        "📊 **BOT STATISTICS**\n\n"
        f"👥 Users      : {len(d['users']):,}\n"
        f"👥 Groups     : {len(d['groups']):,}\n"
        f"💎 Characters : {len(d['characters']):,}\n"
        f"⚡ Sudo Users : {len(d['sudo_users'])}\n\n"
        "**Characters by Rarity:**\n"
        f"🪔 Common    : {rc['Common']}\n"
        f"✨ Rare      : {rc['Rare']}\n"
        f"🔮 Epic      : {rc['Epic']}\n"
        f"🧿 Legendary : {rc['Legendary']}\n"
        f"💠 Mythic    : {rc['Mythic']}",
        parse_mode="Markdown")


async def c_backup(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    Path(BKUP_DIR).mkdir(parents=True, exist_ok=True)
    dest = f"{BKUP_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    db.backup(dest)
    with open(dest, "rb") as f:
        await upd.message.reply_document(document=f, filename=Path(dest).name,
                                          caption="✅ **Database Backup ✅**", parse_mode="Markdown")


async def c_restore(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not upd.message.reply_to_message or not upd.message.reply_to_message.document:
        await upd.message.reply_text("❌ JSON Backup ကို Reply ပြု၍ /restore"); return
    doc = upd.message.reply_to_message.document
    if not doc.file_name.endswith(".json"):
        await upd.message.reply_text("❌ JSON File သာ!"); return
    try:
        f  = await ctx.bot.get_file(doc.file_id)
        byt= await f.download_as_bytearray()
        if db.restore_bytes(bytes(byt)): await upd.message.reply_text("✅ **Restore ✅**", parse_mode="Markdown")
        else:                             await upd.message.reply_text("❌ File မမှန်ပါ!")
    except Exception as e:
        await upd.message.reply_text(f"❌ Error: {e}")


async def c_allclear(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if upd.effective_user.id != OWNER_ID:
        await upd.message.reply_text("⛔ Owner သာ ခွင့်ပြုသည်!"); return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ YES, Clear All", callback_data="x_confirmclear"),
        InlineKeyboardButton("❌ Cancel",          callback_data="x_cancelclear"),
    ]])
    await upd.message.reply_text(
        "⚠️ **WARNING!**\n\nData အားလုံး ဖျက်မည်!\nသေချာပါသလား?",
        parse_mode="Markdown", reply_markup=kb)


async def c_delete(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not ctx.args:
        await upd.message.reply_text("❌ /delete `<card_id>`  OR  /delete sudo `<id>`", parse_mode="Markdown"); return
    if ctx.args[0].lower() == "sudo":
        if len(ctx.args) < 2 or not ctx.args[1].isdigit():
            await upd.message.reply_text("❌ /delete sudo `<user_id>`", parse_mode="Markdown"); return
        tid = int(ctx.args[1])
        if tid == OWNER_ID:
            await upd.message.reply_text("❌ Owner ကို ဖယ်မရ!"); return
        if db.del_sudo(tid): await upd.message.reply_text(f"✅ `{tid}` Sudo မှ ဖယ်ပြီး!", parse_mode="Markdown")
        else:                 await upd.message.reply_text("❌ Sudo List တွင် မရှိ!")
        return
    cid  = ctx.args[0]; char = db.get_char(cid)
    if not char:
        await upd.message.reply_text("❌ Character မတွေ့!"); return
    db.del_char(cid)
    await upd.message.reply_text(f"✅ **{char['name']}** (`{cid}`) ဖျက်ပြီး!", parse_mode="Markdown")


async def c_addsudo(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    tid = None; tname = "?"
    if upd.message.reply_to_message:
        t = upd.message.reply_to_message.from_user; tid = t.id; tname = t.first_name
    elif ctx.args and ctx.args[0].isdigit():
        tid = int(ctx.args[0]); td = db.get_user(tid); tname = td.get("name", str(tid))
    else:
        await upd.message.reply_text("❌ Reply / ID ထည့်ပါ!"); return
    if db.add_sudo(tid): await upd.message.reply_text(f"✅ **{tname}** (`{tid}`) Sudo ✅", parse_mode="Markdown")
    else:                 await upd.message.reply_text("ℹ️ ရှိနှင့်ပြီးပါပြီ!")


async def c_sudolist(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    sl  = db.sudo_list(); au = db.all_users(); txt = "⚡ **SUDO USERS**\n\n"
    for i, uid in enumerate(sl, 1):
        ud = au.get(str(uid), {}); nm = ud.get("name", f"User {uid}")
        crown = "👑 " if uid == OWNER_ID else ""
        txt += f"{i}. {crown}**{nm}** (`{uid}`)\n"
    await upd.message.reply_text(txt, parse_mode="Markdown")


async def c_evote(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await sudo_check(upd): return
    if not ctx.args:
        await upd.message.reply_text("❌ /evote `<opt1>|<opt2>|…`", parse_mode="Markdown"); return
    opts = [o.strip() for o in " ".join(ctx.args).split("|") if o.strip()]
    if len(opts) < 2:
        await upd.message.reply_text("❌ Options ≥ 2 ဖြစ်ရမည်!"); return
    db.set_vote({"options": opts, "votes": {o:[] for o in opts},
                  "by": upd.effective_user.id, "at": datetime.now().isoformat()})
    txt = "📊 **New Vote Created!**\n\n"
    kb  = []
    for o in opts:
        txt += f"• {o}: 0 votes\n"
        kb.append([InlineKeyboardButton(f"🗳 {o}", callback_data=f"x_vote_{o}")])
    kb.append([InlineKeyboardButton("📊 Results", callback_data="x_voteresults")])
    await upd.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


# ══════════════════════════════════════════════
#  CALLBACK HANDLER
# ══════════════════════════════════════════════
async def on_cb(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = upd.callback_query; await q.answer()
    data = q.data; user = q.from_user

    if data.startswith("x_harem_"):
        parts = data.split("_"); await _harem(upd, ctx, int(parts[2]), int(parts[3]))

    elif data.startswith("x_shop_"):
        parts = data.split("_"); await _shop(upd, ctx, int(parts[2]), int(parts[3]))

    elif data.startswith("x_buy_"):
        cid  = data[6:]; char = db.get_char(cid)
        if not char: await q.answer("❌ Character မတွေ့!", show_alert=True); return
        ud    = db.get_user(user.id, user.full_name, user.username or "")
        price = RARITIES.get(char["rarity"],{}).get("price",100)
        if ud["coins"] < price: await q.answer(f"❌ Coins မလုံ! {price:,} လိုသည်", show_alert=True); return
        db.upd_user(user.id, {"coins": ud["coins"]-price}); char_add(user.id, cid)
        await q.answer(f"✅ {char['name']} ဝယ်ပြီး!", show_alert=True)
        txt = (f"✅ **ဝယ်ယူပြီး!**\n{rem(char['rarity'])} **{char['name']}** ({char['rarity']})\n"
               f"💰 −{price:,}  •  💵 {ud['coins']-price:,}")
        try:
            if char.get("photo_file_id"): await q.edit_message_caption(caption=txt, parse_mode="Markdown")
            else:                          await q.edit_message_text(txt, parse_mode="Markdown")
        except Exception: pass

    elif data.startswith("x_vote_"):
        option = data[7:]; v = db.get_vote()
        if not v: await q.answer("❌ Vote မရှိ!", show_alert=True); return
        opts = v["options"]; votes = v["votes"]
        if option not in opts: await q.answer("❌ Invalid!", show_alert=True); return
        if any(str(user.id) in votes.get(o,[]) for o in opts):
            await q.answer("❌ မဲပြီးပါပြီ!", show_alert=True); return
        votes.setdefault(option,[]).append(str(user.id)); v["votes"] = votes; db.set_vote(v)
        await q.answer(f"✅ '{option}' ကို မဲပေးပြီး!", show_alert=True)
        txt = "📊 **VOTE**\n\n"; kb = []
        for o in opts:
            cnt = len(votes.get(o,[])); txt += f"• {o}: {cnt} votes\n"
            kb.append([InlineKeyboardButton(f"🗳 {o} ({cnt})", callback_data=f"x_vote_{o}")])
        kb.append([InlineKeyboardButton("📊 Results", callback_data="x_voteresults")])
        try: await q.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        except Exception: pass

    elif data == "x_voteresults":
        v = db.get_vote()
        if not v: await q.answer("❌ Vote မရှိ!", show_alert=True); return
        opts = v["options"]; votes = v["votes"]
        total = sum(len(votes.get(o,[])) for o in opts); txt = "📊 **VOTE RESULTS**\n\n"
        for o in opts:
            cnt = len(votes.get(o,[])); pct = cnt/total*100 if total else 0
            bar = "█"*int(pct/10) + "░"*(10-int(pct/10))
            txt += f"**{o}**\n{bar} {cnt} ({pct:.1f}%)\n\n"
        txt += f"📌 Total: {total} votes"
        try: await q.edit_message_text(txt, parse_mode="Markdown")
        except Exception: pass

    elif data.startswith("x_prof_"):
        uid = int(data[7:]); ud = db.get_user(uid); txt = make_profile(ud, uid)
        try: await q.edit_message_text(txt, parse_mode="Markdown")
        except Exception: pass

    elif data.startswith("x_bal_"):
        uid = int(data[6:]); ud = db.get_user(uid)
        txt = f"💰 **BALANCE**\n\n💵 Wallet: {ud['coins']:,}\n🏦 Bank: {ud['bank']:,}"
        try: await q.edit_message_text(txt, parse_mode="Markdown")
        except Exception: pass

    elif data == "x_help":
        txt = ("📖 **Quick Commands**\n\n"
               "/start /helps /profile /balance\n/harem /fight /daily /shop\n/slots /basket /tops /vote")
        try: await q.edit_message_text(txt, parse_mode="Markdown")
        except Exception: pass

    elif data == "x_confirmclear":
        if user.id != OWNER_ID: await q.answer("⛔ Owner Only!", show_alert=True); return
        db.clear_all(); await q.edit_message_text("✅ Database Clear ပြီးပါပြီ!")

    elif data == "x_cancelclear":
        await q.edit_message_text("❌ Cancel ပြုလုပ်ပြီးပါပြီ!")


# ══════════════════════════════════════════════
#  INLINE QUERY
# ══════════════════════════════════════════════
async def on_inline(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = upd.inline_query.query.strip().lower()
    ac  = db.all_chars(); res = []
    for cid, c in ac.items():
        if q and q not in c["name"].lower() and q not in c.get("movie","").lower(): continue
        ri  = RARITIES.get(c["rarity"],{})
        txt = (f"{rem(c['rarity'])} **{c['name']}**\n"
               f"🎬 {c.get('movie','?')}  •  💎 {c['rarity']}\n"
               f"🆔 `{cid}`  •  💰 {ri.get('price',0):,} coins")
        if c.get("photo_file_id"):
            res.append(InlineQueryResultCachedPhoto(
                id=cid, photo_file_id=c["photo_file_id"],
                title=f"{rem(c['rarity'])} {c['name']} ({c['rarity']})",
                description=f"🎬 {c.get('movie','?')} | 💰 {ri.get('price',0)} coins",
                caption=txt, parse_mode="Markdown"))
        else:
            res.append(InlineQueryResultArticle(
                id=cid, title=f"{rem(c['rarity'])} {c['name']} ({c['rarity']})",
                description=f"🎬 {c.get('movie','?')} | 💰 {ri.get('price',0)} coins",
                input_message_content=InputTextMessageContent(txt, parse_mode="Markdown")))
        if len(res) >= 20: break
    await upd.inline_query.answer(res, cache_time=10)


# ══════════════════════════════════════════════
#  MESSAGE HANDLER — Card Drop System
# ══════════════════════════════════════════════
async def on_msg(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_grp(upd) or not upd.message: return
    u = upd.effective_user
    if u.is_bot: return
    gid = upd.effective_chat.id
    g   = db.get_group(gid)
    # register member
    if str(u.id) not in g["members"]:
        g["members"].append(str(u.id)); db.upd_group(gid, {"members": g["members"]})
    db.get_user(u.id, u.full_name, u.username or "")
    cnt  = g.get("msg_count",0) + 1
    intv = g.get("drop_interval",50)
    drop = g.get("current_drop")
    if drop: db.upd_group(gid, {"msg_count": cnt}); return
    if cnt >= intv:
        ac = db.all_chars()
        if not ac: db.upd_group(gid, {"msg_count": 0}); return
        ids    = list(ac.keys())
        wts    = [RARITIES.get(ac[i]["rarity"],{}).get("weight",50) for i in ids]
        chosen = random.choices(ids, weights=wts, k=1)[0]
        c      = ac[chosen]
        db.upd_group(gid, {"msg_count": 0, "current_drop": chosen})
        hint   = mask(c["name"])
        txt = (
            "🌟 **A Wild Character Appeared!**\n\n"
            f"{rem(c['rarity'])} **???**\n"
            f"💎 Rarity: **{c['rarity']}**\n"
            f"🎬 Series: {c.get('movie','?')}\n\n"
            f"❓ Hint: `{hint}`\n\n"
            "✍️ /slime `<name>` ဖြင့် ဖမ်းယူပါ!\n"
            "⏳ မဖမ်းပါက ပျောက်သွားမည်!"
        )
        if c.get("photo_file_id"):
            await upd.message.reply_photo(photo=c["photo_file_id"], caption=txt, parse_mode="Markdown")
        else:
            await upd.message.reply_text(txt, parse_mode="Markdown")
    else:
        db.upd_group(gid, {"msg_count": cnt})


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════
def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    Path(BKUP_DIR).mkdir(parents=True, exist_ok=True)
    if not TOKEN:
        print("❌  BOT_TOKEN not found in .env!"); return
    if not OWNER_ID:
        print("⚠️  OWNER_ID not set.")

    print("🚀  Character Collection Game Bot starting...")
    app = Application.builder().token(TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start",    c_start))
    app.add_handler(CommandHandler("helps",    c_helps))
    app.add_handler(CommandHandler("profile",  c_profile))
    app.add_handler(CommandHandler("slime",    c_slime))
    app.add_handler(CommandHandler("harem",    c_harem))
    app.add_handler(CommandHandler("set",      c_set))
    app.add_handler(CommandHandler("check",    c_check))
    app.add_handler(CommandHandler("fight",    c_fight))
    app.add_handler(CommandHandler("search",   c_search))
    app.add_handler(CommandHandler("slots",    c_slots))
    app.add_handler(CommandHandler("basket",   c_basket))
    app.add_handler(CommandHandler("givecoin", c_givecoin))
    app.add_handler(CommandHandler("givechar", c_givechar))
    app.add_handler(CommandHandler("balance",  c_balance))
    app.add_handler(CommandHandler("save",     c_save))
    app.add_handler(CommandHandler("withdraw", c_withdraw))
    app.add_handler(CommandHandler("daily",    c_daily))
    app.add_handler(CommandHandler("shop",     c_shop))
    app.add_handler(CommandHandler("tops",     c_tops))
    app.add_handler(CommandHandler("vote",     c_vote))
    app.add_handler(CommandHandler("all",      c_all))

    # Admin / Sudo commands
    app.add_handler(CommandHandler("edit",      c_edit))
    app.add_handler(CommandHandler("upload",    c_upload))
    app.add_handler(CommandHandler("setdrop",   c_setdrop))
    app.add_handler(CommandHandler("gift",      c_gift))
    app.add_handler(CommandHandler("broadcast", c_broadcast))
    app.add_handler(CommandHandler("stats",     c_stats))
    app.add_handler(CommandHandler("backup",    c_backup))
    app.add_handler(CommandHandler("restore",   c_restore))
    app.add_handler(CommandHandler("allclear",  c_allclear))
    app.add_handler(CommandHandler("delete",    c_delete))
    app.add_handler(CommandHandler("addsudo",   c_addsudo))
    app.add_handler(CommandHandler("sudolist",  c_sudolist))
    app.add_handler(CommandHandler("evote",     c_evote))

    # Callback / Inline / Message
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_msg))

    print("✅  Bot is running! Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
