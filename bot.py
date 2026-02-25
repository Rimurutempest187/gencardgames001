
Copyimport asyncio
import json
import random
import time
from datetime import datetime, timezone
from io import BytesIO

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineQuery, InlineQueryResultCachedPhoto,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputFile
)
from aiogram.filters import Command, CommandObject
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest

from config import load_config
from db import Database, RARITY_EMOJI, RARITIES, RARITY_WEIGHTS, RARITY_PRICE, RARITY_POWER, norm_name

router = Router()

HELP_TEXT = """
💎 Character Collection Game Commands

🎮 User Commands
/start - စတင်
/helps - Command list
/profile - မိမိ Profile
/slime <character name> - Drop ကတ်ဖမ်း (Group)
/harem - မိမိ Character များ (5/pg)
/set <card id> - Favorite သတ်မှတ်
/check <id> - Character detail
/fight - Random fight (Cooldown 30s)
/balance - Coins/Bank
/save <amount> - Bank ထဲသို့အပ်
/withdraw <amount> - Bank ထဲမှထုတ်
/daily - Daily bonus
/slots <amount> - Slot gamble
/basket <amount> - Basketball gamble
/givecoin <amount> (reply) - Coin လွဲ
/givechar <id> (reply) - Card လက်ဆောင်
/shop - Shop (Buy cards)
/tops - Top 10
/vote - Active poll ပြန်ပြ
/all - Group members mention (bot မှ စုထားသလောက်)

⚡️ Admin & Sudo
/edit - Admin panel
/upload <Name | Movie | Rarity> (reply photo) - Character အသစ်တင်
/setdrop <number> - Drop interval
/gift coin <amount> <reply/id> - Coin gift
/gift card <amount> <reply/id> - Random card gift
/broadcast - Groups အားလုံးသို့ စာ/ပုံပို့
/stats - Stats
/backup - JSON backup
/restore (reply json file) - Restore
/allclear - DB ဖျက်
/delete card <id> - Card ဖျက်
/delete sudo <id> - Sudo ဖျက်
/addsudo <reply/id> - Sudo ထည့်
/sudolist - Sudo list
/evote option1 | option2 | ... - Poll စ
"""

def now_ts() -> int:
    return int(time.time())

def utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def is_int(s: str) -> bool:
    try:
        int(s)
        return True
    except:
        return False

async def is_admin_or_sudo(bot: Bot, db: Database, message: Message, owner_id: int) -> bool:
    uid = message.from_user.id
    if uid == owner_id:
        return True
    if await db.is_sudo(uid):
        return True
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        try:
            member = await bot.get_chat_member(message.chat.id, uid)
            return member.status in ("administrator", "creator")
        except:
            return False
    return False

def rarity_line(rarity: str) -> str:
    return f"{RARITY_EMOJI.get(rarity,'❔')} {rarity}"

def build_harem_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"harem:{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"harem:{page+1}"))
    row = buttons if buttons else [InlineKeyboardButton(text="✅ OK", callback_data="noop")]
    return InlineKeyboardMarkup(inline_keyboard=[row])

def build_shop_kb(page: int, total_pages: int, char_id: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"shop:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"shop:{page+1}"))
    buy = [InlineKeyboardButton(text="🛒 Buy", callback_data=f"shopbuy:{char_id}")]
    rows = []
    if nav:
        rows.append(nav)
    rows.append(buy)
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def pick_random_character(db: Database) -> dict | None:
    all_chars = await db.list_all_characters()
    if not all_chars:
        return None
    # weighted by rarity
    pool = []
    for c in all_chars:
        w = RARITY_WEIGHTS.get(c["rarity"], 1)
        pool.append((c, w))
    total = sum(w for _, w in pool)
    r = random.randint(1, total)
    s = 0
    for c, w in pool:
        s += w
        if r <= s:
            return c
    return random.choice(all_chars)

# ---------------- USER COMMANDS ----------------

@router.message(Command("start"))
async def cmd_start(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    text = (
        f"မင်္ဂလာပါ {message.from_user.full_name}!\n\n"
        "💎 Character Collection Game မှ ကြိုဆိုပါတယ်။\n"
        "Group ထဲမှာ ကတ်တွေ auto drop ကျလာမယ် — /slime <name> နဲ့ ဖမ်းနိုင်ပါတယ်။\n\n"
        "Command list ကို /helps နဲ့ကြည့်ပါ။\n"
        "> Created by : @Enoch_777"
    )
    await message.reply(text)

@router.message(Command("helps"))
async def cmd_help(message: Message):
    await message.reply(HELP_TEXT)

@router.message(Command("profile"))
async def cmd_profile(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    u = await db.get_user(message.from_user.id)
    total_cards = await db.get_user_total_cards(message.from_user.id)
    rc = await db.get_user_rarity_counts(message.from_user.id)

    fav_txt = "မသတ်မှတ်ရသေးပါ"
    if u.get("fav_char_id"):
        c = await db.get_character(u["fav_char_id"])
        if c:
            fav_txt = f"#{c['char_id']} {c['name']} ({rarity_line(c['rarity'])})"

    rarity_summary = "\n".join([f"{RARITY_EMOJI[r]} {r}: {rc.get(r,0)}" for r in RARITIES])

    text = (
        f"👤 Name: {u['name']}\n"
        f"🆔 ID: {u['user_id']}\n\n"
        f"🎴 Total Characters: {total_cards}\n"
        f"{rarity_summary}\n\n"
        f"🪙 Coins: {u['coins']}\n"
        f"🏦 Bank: {u['bank']}\n\n"
        f"⭐ Favorite: {fav_txt}"
    )
    await message.reply(text)

@router.message(Command("balance"))
async def cmd_balance(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    u = await db.get_user(message.from_user.id)
    await message.reply(f"🪙 Coins: {u['coins']}\n🏦 Bank: {u['bank']}")

@router.message(Command("save"))
async def cmd_save(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /save <amount>")
    amt = int(command.args)
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")
    u = await db.get_user(message.from_user.id)
    if u["coins"] < amt:
        return await message.reply("Coins မလုံလောက်ပါ။")
    await db.add_coins(message.from_user.id, -amt)
    await db.add_bank(message.from_user.id, amt)
    await message.reply(f"✅ Bank ထဲသို့ {amt} coins အပ်ပြီးပါပြီ။")

@router.message(Command("withdraw"))
async def cmd_withdraw(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /withdraw <amount>")
    amt = int(command.args)
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")
    u = await db.get_user(message.from_user.id)
    if u["bank"] < amt:
        return await message.reply("Bank balance မလုံလောက်ပါ။")
    await db.add_bank(message.from_user.id, -amt)
    await db.add_coins(message.from_user.id, amt)
    await message.reply(f"✅ Bank ထဲမှ {amt} coins ထုတ်ပြီးပါပြီ။")

@router.message(Command("daily"))
async def cmd_daily(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    u = await db.get_user(message.from_user.id)
    today = utc_date_str()
    if u["daily_last"] == today:
        return await message.reply("⏳ Daily ကို ဒီနေ့အတွက် ရယူပြီးပါပြီ။ မနက်ဖြန် ပြန်လာပါ။")

    bonus = random.randint(150, 400)
    await db.add_coins(message.from_user.id, bonus)
    await db.set_daily_last(message.from_user.id, today)

    # small chance to get a random card
    card_txt = ""
    if random.random() < 0.25:
        c = await pick_random_character(db)
        if c:
            await db.add_user_char(message.from_user.id, c["char_id"], 1)
            card_txt = f"\n🎴 Bonus Card: #{c['char_id']} {c['name']} ({rarity_line(c['rarity'])})"

    await message.reply(f"🎁 Daily Bonus: +{bonus} coins{card_txt}")

@router.message(Command("set"))
async def cmd_set_fav(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /set <card id>")
    char_id = int(command.args)
    owned = await db.get_user_char_count(message.from_user.id, char_id)
    if owned <= 0:
        return await message.reply("ဒီကတ်ကို မပိုင်ဆိုင်သေးပါ။")
    await db.set_favorite(message.from_user.id, char_id)
    c = await db.get_character(char_id)
    await message.reply(f"⭐ Favorite သတ်မှတ်ပြီးပါပြီ: #{c['char_id']} {c['name']} ({rarity_line(c['rarity'])})")

@router.message(Command("check"))
async def cmd_check(message: Message, command: CommandObject, db: Database):
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /check <id>")
    char_id = int(command.args)
    c = await db.get_character(char_id)
    if not c:
        return await message.reply("မတွေ့ပါ။")
    caption = (
        f"🆔 #{c['char_id']}\n"
        f"👤 {c['name']}\n"
        f"🎬 {c['movie']}\n"
        f"💎 {rarity_line(c['rarity'])}\n"
        f"⚡ Power: {c['power']}\n"
        f"🛒 Price: {c['price']} coins"
    )
    await message.reply_photo(c["image_file_id"], caption=caption)

@router.message(Command("harem"))
async def cmd_harem(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    col = await db.get_user_collection(message.from_user.id)
    if not col:
        return await message.reply("သင့် Collection က ဗလာပါ။ Group ထဲမှာ drop ကတ်ကို /slime နဲ့ဖမ်းပါ။")

    page = 0
    await send_harem_page(message, db, page)

async def send_harem_page(message_or_cb, db: Database, page: int):
    user_id = message_or_cb.from_user.id
    col = await db.get_user_collection(user_id)

    per_page = 5
    total = len(col)
    total_pages = (total + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))

    chunk = col[page*per_page:(page+1)*per_page]
    lines = []
    for it in chunk:
        lines.append(
            f"#{it['char_id']} {it['name']} x{it['count']}  | {RARITY_EMOJI.get(it['rarity'],'❔')} {it['rarity']} | ⚡{it['power']}"
        )
    text = "📒 Your Harem\n\n" + "\n".join(lines) + f"\n\nPage {page+1}/{total_pages}"
    kb = build_harem_kb(page, total_pages)

    if isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(text, reply_markup=kb)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply(text, reply_markup=kb)

@router.callback_query(F.data.startswith("harem:"))
async def cb_harem(callback: CallbackQuery, db: Database):
    page = int(callback.data.split(":")[1])
    await send_harem_page(callback, db, page)

@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()

@router.message(Command("slime"))
async def cmd_slime(message: Message, command: CommandObject, db: Database):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply("ဒီ command ကို Group ထဲမှာပဲ သုံးလို့ရပါတယ်။")

    await db.ensure_user(message.from_user.id, message.from_user.full_name)

    if not command.args:
        return await message.reply("Usage: /slime <character name>")

    drop = await db.get_active_drop(message.chat.id)
    if not drop:
        return await message.reply("အခုဖမ်းစရာ drop ကတ် မရှိသေးပါ။")

    typed = norm_name(command.args)
    real = norm_name(drop["name"])
    if typed != real:
        return await message.reply("❌ အမည်မမှန်ပါ။ (အတိအကျရိုက်ပါ)")

    await db.add_user_char(message.from_user.id, drop["char_id"], 1)
    await db.clear_active_drop(message.chat.id)

    c = await db.get_character(drop["char_id"])
    await message.reply(
        f"✅ {message.from_user.full_name} က ဖမ်းယူလိုက်ပါပြီ!\n"
        f"🎴 #{c['char_id']} {c['name']} ({rarity_line(c['rarity'])})"
    )

@router.message(Command("fight"))
async def cmd_fight(message: Message, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    u = await db.get_user(message.from_user.id)

    if now_ts() - u["fight_last"] < 30:
        left = 30 - (now_ts() - u["fight_last"])
        return await message.reply(f"⏳ Cooldown: {left}s")

    await db.set_fight_last(message.from_user.id, now_ts())

    enemy = await pick_random_character(db)
    if not enemy:
        return await message.reply("Character မရှိသေးပါ။ Admin က /upload နဲ့တင်ပေးရပါမယ်။")

    # simple win logic: base 50% + small bonus from owned cards
    total_cards = await db.get_user_total_cards(message.from_user.id)
    win_chance = min(0.75, 0.50 + (total_cards * 0.01))
    win = random.random() < win_chance

    if win:
        reward = await pick_random_character(db)
        if not reward:
            return await message.reply("Reward card မရနိုင်ပါ (DB empty).")
        await db.add_user_char(message.from_user.id, reward["char_id"], 1)
        await message.reply(
            f"⚔️ Fight Result: ✅ WIN!\n"
            f"Enemy: #{enemy['char_id']} {enemy['name']} ({rarity_line(enemy['rarity'])})\n\n"
            f"🎴 Reward: #{reward['char_id']} {reward['name']} ({rarity_line(reward['rarity'])})"
        )
    else:
        await message.reply(
            f"⚔️ Fight Result: ❌ LOSE!\n"
            f"Enemy: #{enemy['char_id']} {enemy['name']} ({rarity_line(enemy['rarity'])})\n"
            "ကံကောင်းပါစေ နောက်တစ်ခါ ပြန်ကြိုးစားပါ။"
        )

@router.message(Command("slots"))
async def cmd_slots(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /slots <amount>")
    amt = int(command.args)
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")
    u = await db.get_user(message.from_user.id)
    if u["coins"] < amt:
        return await message.reply("Coins မလုံလောက်ပါ။")

    roll = random.random()
    if roll < 0.55:
        # lose
        await db.add_coins(message.from_user.id, -amt)
        return await message.reply(f"🎰 Slots: ❌ LOSE (-{amt})")
    elif roll < 0.80:
        mul = 2
    elif roll < 0.95:
        mul = 3
    else:
        mul = 5

    profit = amt * (mul - 1)
    await db.add_coins(message.from_user.id, profit)
    await message.reply(f"🎰 Slots: ✅ WIN x{mul} (+{profit})")

@router.message(Command("basket"))
async def cmd_basket(message: Message, command: CommandObject, db: Database, bot: Bot):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /basket <amount>")
    amt = int(command.args)
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")
    u = await db.get_user(message.from_user.id)
    if u["coins"] < amt:
        return await message.reply("Coins မလုံလောက်ပါ။")

    # deduct first
    await db.add_coins(message.from_user.id, -amt)
    dice_msg = await bot.send_dice(message.chat.id, emoji="🏀")
    value = dice_msg.dice.value  # usually 1..5

    if value >= 4:
        win = amt * 2
        await db.add_coins(message.from_user.id, win)
        await message.reply(f"🏀 Basket: ✅ SCORE! (+{win})")
    else:
        await message.reply(f"🏀 Basket: ❌ MISS! (-{amt})")

@router.message(Command("givecoin"))
async def cmd_givecoin(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("Usage: /givecoin <amount> (reply user)")
    if not command.args or not is_int(command.args.strip()):
        return await message.reply("Usage: /givecoin <amount> (reply user)")

    amt = int(command.args.strip())
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")

    to_user = message.reply_to_message.from_user
    await db.ensure_user(to_user.id, to_user.full_name)

    u = await db.get_user(message.from_user.id)
    if u["coins"] < amt:
        return await message.reply("Coins မလုံလောက်ပါ။")

    await db.add_coins(message.from_user.id, -amt)
    await db.add_coins(to_user.id, amt)
    await message.reply(f"✅ {to_user.full_name} သို့ {amt} coins လွဲပြီးပါပြီ။")

@router.message(Command("givechar"))
async def cmd_givechar(message: Message, command: CommandObject, db: Database):
    await db.ensure_user(message.from_user.id, message.from_user.full_name)
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("Usage: /givechar <id> (reply user)")
    if not command.args or not is_int(command.args.strip()):
        return await message.reply("Usage: /givechar <id> (reply user)")

    char_id = int(command.args.strip())
    to_user = message.reply_to_message.from_user
    await db.ensure_user(to_user.id, to_user.full_name)

    owned = await db.get_user_char_count(message.from_user.id, char_id)
    if owned <= 0:
        return await message.reply("ဒီကတ်ကို မပိုင်ဆိုင်သေးပါ။")

    await db.add_user_char(message.from_user.id, char_id, -1)
    await db.add_user_char(to_user.id, char_id, +1)
    c = await db.get_character(char_id)
    await message.reply(f"🎁 {to_user.full_name} ကို #{c['char_id']} {c['name']} လက်ဆောင်ပေးပြီးပါပြီ။")

@router.message(Command("shop"))
async def cmd_shop(message: Message, db: Database):
    total = await db.count_characters()
    if total == 0:
        return await message.reply("Shop ထဲမှာ Character မရှိသေးပါ။ Admin က /upload နဲ့တင်ပေးပါ။")
    await send_shop_page(message, db, page=0)

async def send_shop_page(message_or_cb, db: Database, page: int):
    per_page = 1
    total = await db.count_characters()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    items = await db.list_characters(offset=page*per_page, limit=per_page)
    c = items[0]

    caption = (
        f"🛒 Shop\n\n"
        f"🆔 #{c['char_id']}\n"
        f"👤 {c['name']}\n"
        f"🎬 {c['movie']}\n"
        f"💎 {rarity_line(c['rarity'])}\n"
        f"⚡ Power: {c['power']}\n"
        f"💰 Price: {c['price']} coins\n\n"
        f"Page {page+1}/{total_pages}"
    )
    kb = build_shop_kb(page, total_pages, c["char_id"])

    if isinstance(message_or_cb, CallbackQuery):
        try:
            await message_or_cb.message.edit_caption(caption, reply_markup=kb)
        except TelegramBadRequest:
            # if caption edit fails (e.g., message not photo), send new
            await message_or_cb.message.answer_photo(c["image_file_id"], caption=caption, reply_markup=kb)
        await message_or_cb.answer()
    else:
        await message_or_cb.reply_photo(c["image_file_id"], caption=caption, reply_markup=kb)

@router.callback_query(F.data.startswith("shop:"))
async def cb_shop(callback: CallbackQuery, db: Database):
    page = int(callback.data.split(":")[1])
    await send_shop_page(callback, db, page)

@router.callback_query(F.data.startswith("shopbuy:"))
async def cb_shop_buy(callback: CallbackQuery, db: Database):
    await db.ensure_user(callback.from_user.id, callback.from_user.full_name)
    char_id = int(callback.data.split(":")[1])
    c = await db.get_character(char_id)
    if not c:
        return await callback.answer("Not found", show_alert=True)

    u = await db.get_user(callback.from_user.id)
    if u["coins"] < c["price"]:
        return await callback.answer("Coins မလုံလောက်ပါ။", show_alert=True)

    await db.add_coins(callback.from_user.id, -c["price"])
    await db.add_user_char(callback.from_user.id, char_id, 1)
    await callback.answer("✅ ဝယ်ယူပြီးပါပြီ!", show_alert=True)

@router.message(Command("tops"))
async def cmd_tops(message: Message, db: Database):
    topw = await db.top_by_wealth(10)
    topc = await db.top_by_cards(10)

    w_lines = []
    for i,(uid,name,coins,bank) in enumerate(topw, start=1):
        w_lines.append(f"{i}. {name} (ID:{uid}) — 💰 {coins+bank} (🪙{coins}+🏦{bank})")

    c_lines = []
    for i,(uid,name,total_cards) in enumerate(topc, start=1):
        c_lines.append(f"{i}. {name} (ID:{uid}) — 🎴 {total_cards}")

    text = "🏆 TOP 10\n\n💰 Wealth:\n" + "\n".join(w_lines) + "\n\n🎴 Cards:\n" + "\n".join(c_lines)
    await message.reply(text)

@router.message(Command("all"))
async def cmd_all(message: Message, db: Database):
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply("ဒီ command ကို Group ထဲမှာပဲ သုံးလို့ရပါတယ်။")
    members = await db.get_members(message.chat.id, limit=50)
    if not members:
        return await message.reply("Members data မရှိသေးပါ။ Bot ကို group ထဲမှာ လူတွေ စကားပြောလာရင် auto စုပါမယ်။")

    # mention by tg://user?id=
    chunks = []
    for uid, name in members:
        chunks.append(f"[{name}](tg://user?id={uid})")
    text = "📣 All Members:\n" + " ".join(chunks)
    await message.reply(text, parse_mode="Markdown")

# ---------------- INLINE SEARCH ----------------

@router.message(Command("search"))
async def cmd_search(message: Message):
    await message.reply("🔍 Inline Search သုံးရန်:\nBot username ကိုရေးပြီး search လုပ်ပါ\nဥပမာ: @YourBotUsername naruto")

@router.inline_query()
async def inline_query_handler(query: InlineQuery, db: Database):
    q = (query.query or "").strip()
    if not q:
        return await query.answer([], cache_time=1)

    items = await db.find_characters(q, limit=20)
    results = []
    for c in items:
        caption = (
            f"🆔 #{c['char_id']}\n"
            f"👤 {c['name']}\n"
            f"🎬 {c['movie']}\n"
            f"💎 {rarity_line(c['rarity'])}\n"
            f"⚡ Power: {c['power']}\n"
            f"🛒 Price: {c['price']} coins"
        )
        results.append(
            InlineQueryResultCachedPhoto(
                id=str(c["char_id"]),
                photo_file_id=c["image_file_id"],
                caption=caption
            )
        )
    await query.answer(results, cache_time=5, is_personal=True)

# ---------------- GROUP AUTO DROP ----------------

@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_listener(message: Message, db: Database, bot: Bot):
    # track group + member
    await db.upsert_group(message.chat.id, message.chat.title or "Group")
    await db.add_member_seen(message.chat.id, message.from_user.id, message.from_user.full_name)

    # increase msg count, maybe drop
    g = await db.get_group(message.chat.id)
    if not g:
        return

    # do not count bot commands heavily? (we still count)
    msg_count = await db.inc_group_msg(message.chat.id)

    active = await db.get_active_drop(message.chat.id)
    if active:
        return

    if msg_count < g["drop_every"]:
        return

    # reset counter + drop
    await db.reset_group_msg(message.chat.id)
    c = await pick_random_character(db)
    if not c:
        return

    caption = (
        "🎴 A wild card appeared!\n"
        f"💎 {rarity_line(c['rarity'])}\n\n"
        f"To catch: /slime {c['name']}"
    )
    sent = await bot.send_photo(message.chat.id, c["image_file_id"], caption=caption)
    await db.set_active_drop(message.chat.id, c["char_id"], c["name"], sent.message_id, now_ts())

# ---------------- ADMIN / SUDO ----------------

@router.message(Command("edit"))
async def cmd_edit(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    await message.reply(
        "🛠 Admin Panel\n\n"
        "• /upload <Name | Movie | Rarity> (reply photo)\n"
        "• /setdrop <number>\n"
        "• /gift coin <amount> <reply/id>\n"
        "• /gift card <amount> <reply/id>\n"
        "• /broadcast (reply text/photo)\n"
        "• /stats /backup /restore /allclear\n"
        "• /delete card <id> | /delete sudo <id>\n"
        "• /addsudo <reply/id> /sudolist\n"
        "• /evote option1 | option2 | ...\n"
    )

@router.message(Command("setdrop"))
async def cmd_setdrop(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply("ဒီ command ကို Group ထဲမှာပဲ သုံးပါ။")
    if not command.args or not is_int(command.args):
        return await message.reply("Usage: /setdrop <number>")
    n = int(command.args)
    if n < 5 or n > 5000:
        return await message.reply("Number ကို 5 မှ 5000 အတွင်းထားပါ။")
    await db.set_drop_every(message.chat.id, n)
    await message.reply(f"✅ Drop interval set to {n} messages.")

@router.message(Command("upload"))
async def cmd_upload(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")

    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("Usage: /upload <Name | Movie | Rarity> (reply photo)")

    if not command.args:
        return await message.reply("Format: /upload Name | Movie | Rarity\nRarity: Common/Rare/Epic/Legendary/Mythic")

    parts = [p.strip() for p in command.args.split("|")]
    if len(parts) != 3:
        return await message.reply("Format: /upload Name | Movie | Rarity")

    name, movie, rarity = parts
    rarity = rarity.capitalize()
    if rarity not in RARITIES:
        return await message.reply("Rarity invalid. Use: Common, Rare, Epic, Legendary, Mythic")

    photo = message.reply_to_message.photo[-1]
    file_id = photo.file_id

    price = RARITY_PRICE[rarity]
    pmin, pmax = RARITY_POWER[rarity]
    power = random.randint(pmin, pmax)

    try:
        char_id = await db.add_character(name=name, movie=movie, rarity=rarity, image_file_id=file_id, price=price, power=power)
    except Exception as e:
        return await message.reply(f"❌ Upload failed (maybe duplicate name).\n{e}")

    await message.reply(f"✅ Uploaded: #{char_id} {name} | {movie} | {rarity_line(rarity)} | ⚡{power} | 💰{price}")

@router.message(Command("gift"))
async def cmd_gift(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")

    if not command.args:
        return await message.reply("Usage:\n/gift coin <amount> <reply/id>\n/gift card <amount> <reply/id>")

    parts = command.args.split()
    if len(parts) < 3:
        return await message.reply("Usage:\n/gift coin <amount> <reply/id>\n/gift card <amount> <reply/id>")

    kind = parts[0].lower()
    amt_s = parts[1]
    target_s = parts[2]

    if not is_int(amt_s):
        return await message.reply("Amount must be integer.")
    amt = int(amt_s)
    if amt <= 0:
        return await message.reply("Amount > 0 ဖြစ်ရမယ်။")

    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
    elif is_int(target_s):
        target_id = int(target_s)
        target_name = f"ID:{target_id}"
    else:
        return await message.reply("Target must be reply user or user_id.")

    await db.ensure_user(target_id, target_name)

    if kind == "coin":
        await db.add_coins(target_id, amt)
        return await message.reply(f"✅ Gifted {amt} coins to {target_name}.")
    elif kind == "card":
        # gift random cards count=amt
        gifted = []
        for _ in range(amt):
            c = await pick_random_character(db)
            if not c:
                break
            await db.add_user_char(target_id, c["char_id"], 1)
            gifted.append(f"#{c['char_id']} {c['name']}({RARITY_EMOJI.get(c['rarity'],'')})")
        if not gifted:
            return await message.reply("❌ No characters in DB.")
        return await message.reply(f"✅ Gifted cards to {target_name}:\n" + "\n".join(gifted[:20]))
    else:
        return await message.reply("Kind must be: coin or card")

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    if not message.reply_to_message:
        return await message.reply("Usage: /broadcast (reply text/photo)")

    data = await db.export_json()
    groups = [g["chat_id"] for g in data.get("groups", [])]
    if not groups:
        return await message.reply("No groups saved yet.")

    ok = 0
    fail = 0
    for gid in groups:
        try:
            if message.reply_to_message.photo:
                await bot.send_photo(gid, message.reply_to_message.photo[-1].file_id,
                                     caption=message.reply_to_message.caption or "")
            else:
                await bot.send_message(gid, message.reply_to_message.text or "(no text)")
            ok += 1
        except:
            fail += 1

    await message.reply(f"📣 Broadcast done.\n✅ Sent: {ok}\n❌ Failed: {fail}")

@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    s = await db.stats()
    await message.reply(f"📊 Stats\nUsers: {s['users']}\nGroups: {s['groups']}\nCharacters: {s['characters']}")

@router.message(Command("backup"))
async def cmd_backup(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    data = await db.export_json()
    b = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    bio = BytesIO(b)
    bio.name = "backup.json"
    await message.reply_document(InputFile(bio), caption="✅ Backup JSON")

@router.message(Command("restore"))
async def cmd_restore(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    if not message.reply_to_message or not message.reply_to_message.document:
        return await message.reply("Usage: /restore (reply backup.json file)")

    doc = message.reply_to_message.document
    file = await bot.get_file(doc.file_id)
    bio = BytesIO()
    await bot.download_file(file.file_path, bio)
    bio.seek(0)
    try:
        data = json.loads(bio.read().decode("utf-8"))
        await db.import_json(data)
    except Exception as e:
        return await message.reply(f"❌ Restore failed: {e}")

    await message.reply("✅ Restore completed.")

@router.message(Command("allclear"))
async def cmd_allclear(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    await db.all_clear()
    await message.reply("⚠️ DB cleared.")

@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    if not command.args:
        return await message.reply("Usage:\n/delete card <id>\n/delete sudo <id>")

    parts = command.args.split()
    if len(parts) != 2:
        return await message.reply("Usage:\n/delete card <id>\n/delete sudo <id>")

    kind, sid = parts[0].lower(), parts[1]
    if not is_int(sid):
        return await message.reply("ID must be integer.")
    xid = int(sid)

    if kind == "card":
        await db.delete_character(xid)
        return await message.reply(f"✅ Deleted card #{xid}")
    if kind == "sudo":
        await db.del_sudo(xid)
        return await message.reply(f"✅ Removed sudo {xid}")

    await message.reply("Usage:\n/delete card <id>\n/delete sudo <id>")

@router.message(Command("addsudo"))
async def cmd_addsudo(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    # only owner can addsudo
    if message.from_user.id != owner_id:
        return await message.reply("⛔ Owner only.")
    target_id = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif command.args and is_int(command.args.strip()):
        target_id = int(command.args.strip())
    else:
        return await message.reply("Usage: /addsudo <reply/id>")

    await db.add_sudo(target_id)
    await message.reply(f"✅ Added sudo: {target_id}")

@router.message(Command("sudolist"))
async def cmd_sudolist(message: Message, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    s = await db.list_sudo()
    if not s:
        return await message.reply("Sudo list empty.")
    await message.reply("👑 Sudo Users:\n" + "\n".join([str(x) for x in s]))

# ---------------- VOTE SYSTEM ----------------

@router.message(Command("evote"))
async def cmd_evote(message: Message, command: CommandObject, db: Database, bot: Bot, owner_id: int):
    if not await is_admin_or_sudo(bot, db, message, owner_id):
        return await message.reply("⛔ Admin/Sudo only.")
    if not command.args:
        return await message.reply("Usage: /evote option1 | option2 | option3 ...")

    opts = [x.strip() for x in command.args.split("|") if x.strip()]
    if len(opts) < 2:
        return await message.reply("အနည်းဆုံး options 2 ခု လိုပါတယ်။ (| နဲ့ခွဲပါ)")

    poll = await bot.send_poll(
        chat_id=message.chat.id,
        question="🗳 Vote Now!",
        options=opts,
        is_anonymous=False
    )
    await db.upsert_poll(message.chat.id, poll.message_id, poll.poll.id)
    await message.reply("✅ Poll started. /vote နဲ့ပြန်ပို့နိုင်ပါတယ်။")

@router.message(Command("vote"))
async def cmd_vote(message: Message, db: Database, bot: Bot):
    p = await db.get_poll(message.chat.id)
    if not p:
        return await message.reply("Active poll မရှိသေးပါ။ Admin က /evote နဲ့စတင်ပါ။")
    await message.reply("🗳 Poll ရှိပြီးသားပါ။ အပေါ်က poll message မှာ vote ပေးပါ။")

# ---------------- MAIN ----------------

async def main():
    cfg = load_config()
    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()
    db = Database("game.db")
    await db.init()

    # dependency injection
    dp["db"] = db
    dp["owner_id"] = cfg.owner_id
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
