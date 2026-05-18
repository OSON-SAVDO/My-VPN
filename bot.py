import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ⚠️ ТАНЗИМОТИ АСОСӢ (МАЪЛУМОТИ ХУДРО ИНҶО НАВИСЕД)
API_TOKEN = '8560757080:AAE3a7-R5hml1tp9W8aOkjVHlBkhd_5HlZo'
ADMIN_ID = 5863448768  # 👈 ИД-и Телеграми худро гузоред
CARD_NUMBER = "4444"  # 👈 16 рақами корти худро БЕ пробел нависед
BANK_NAME = "Алиф Банк (Корти Миллӣ)"  # 👈 Номи бонки кортатон
SUPPORT_LINK = "@your_admin_username"  # 👈 Ники Телеграми шумо

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Ҳолатҳо (States)
class BotStates(StatesGroup):
    waiting_for_contact = State()  # Қабули рақами телефон дар аввал
    waiting_for_receipt = State()  # Қабули скриншоти чек

# ---- БАЗАИ МАЪЛУМОТ ----
def init_db():
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone TEXT,
            status TEXT DEFAULT 'inactive',
            expire_date TEXT,
            has_used_test INTEGER DEFAULT 0
        )
    ''')
    # Навсозии база агар аз коти кӯҳна бошад
    try: cursor.execute("ALTER TABLE users ADD COLUMN has_used_test INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status, expire_date, has_used_test, phone FROM users WHERE user_id = ?', (user_id,))
    data = cursor.fetchone()
    conn.close()
    return data

def save_user_phone(user_id, username, phone):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, username, phone, status, expire_date, has_used_test)
        VALUES (?, ?, ?, 'inactive', NULL, 0)
        ON CONFLICT(user_id) DO UPDATE SET phone=?
    ''', (user_id, username, phone, phone))
    conn.commit()
    conn.close()

def activate_test_db(user_id, username):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    now = datetime.now()
    expire_test = now + timedelta(days=1)
    expire_str = expire_test.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET status="active", expire_date=?, has_used_test=1 WHERE user_id=?', (expire_str, user_id))
    conn.commit()
    conn.close()

def add_or_extend_subscription(user_id, days=30):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    user = get_user_data(user_id)
    now = datetime.now()
    if user and user[1]: # агар expire_date дошта бошад
        current_expire = datetime.strptime(user[1], '%Y-%m-%d %H:%M:%S')
        if current_expire > now:
            new_expire = current_expire + timedelta(days=days)
        else:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)
    new_expire_str = new_expire.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET status="active", expire_date=? WHERE user_id=?', (new_expire_str, user_id))
    conn.commit()
    conn.close()

def get_one_vpn_key():
    file_name = "keys.txt"
    if not os.path.exists(file_name) or os.path.getsize(file_name) == 0: return None
    with open(file_name, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines: return None
    chosen_key = lines[0].strip()
    with open(file_name, "w", encoding="utf-8") as f:
        f.writelines(lines[1:])
    return chosen_key

def get_time_left_text(expire_date_str):
    try:
        expire_date = datetime.strptime(expire_date_str, '%Y-%m-%d %H:%M:%S')
        now = datetime.now()
        diff = expire_date - now
        if diff.days < 0: return "❌ Мӯҳлат тамом шудааст"
        return f"🍏 {diff.days} рӯз, {diff.seconds // 3600} соат боқӣ монд"
    except Exception: return "ℹ️ Маълумот нест"

def get_main_menu(user_id):
    user = get_user_data(user_id)
    buttons = []
    if not user or user[2] == 0:
        buttons.append([InlineKeyboardButton(text="🎁 Оғози ройгон (Тест 24 соат)", callback_data="get_free_test")])
    buy_text = "🔄 Дароз кардани обуна (25 сомонӣ) 🔥" if user and user[0] == 'active' else "💳 Хариди Обуна (30 сомонӣ)"
    buttons.append([InlineKeyboardButton(text=buy_text, callback_data="choose_country")])
    buttons.append([InlineKeyboardButton(text="📊 Профили ман", callback_data="my_profile"),
                    InlineKeyboardButton(text="📚 Дастурамал", callback_data="instruction")])
    buttons.append([InlineKeyboardButton(text="👨‍💻 Дастгирии техникӣ", callback_data="support_info")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---- 1️⃣ ҚАДАМ: ФАРМОНИ /start ВА ПУРСИШИ РАҚАМ ----
@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    
    # Агар корбар аллакай рақамашро дода бошад, рост ба меню меравад
    if user and user[3]:
        welcome_text = "👋 Хуш омадед ба боти VPN! Яке аз тугмаҳоро интихоб кунед:"
        await message.answer(welcome_text, reply_markup=get_main_menu(user_id))
    else:
        # Тугмаи худкори фиристодани рақами телефон
        contact_keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Фиристодани рақами телефон", request_contact=True)]
        ], resize_keyboard=True, one_time_keyboard=True)
        
        await state.set_state(BotStates.waiting_for_contact)
        await message.answer(
            "👋 Салом! Ба боти замониавии фурӯши VPN хуш омадед.\n\n"
            "⚠️ *Барои истифодабарии бот, лутфан аввал рақами телефони худро тавассути тугмаи зерин тасдиқ кунед:*",
            parse_mode="Markdown", reply_markup=contact_keyboard
        )

# ---- 2️⃣ ҚАДАМ: ҚАБУЛИ РАҚАМИ ТЕЛЕФОН ВА КУШОДАНИ МЕНЮ ----
@dp.message(BotStates.waiting_for_contact, F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    phone = message.contact.phone_number
    username = message.from_user.username or "user"
    
    save_user_phone(user_id, username, phone)
    
    # Тоза кардани тугмаи кӯҳнаи телефон бо ReplyKeyboardRemove
    await message.answer("✅ Рақами шумо қабул шуд! Менюи асосӣ кушода шуд.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("🚀 Озодона истифода баред:", reply_markup=get_main_menu(user_id))

# ---- 🎁 БАХШИ ТЕСТИ РОЙГОН ----
@dp.callback_query(F.data == "get_free_test")
async def process_free_test(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or "user"
    user = get_user_data(user_id)
    if user and user[2] == 1:
        await bot.send_message(user_id, "❌ Шумо аллакай замони тестро истифода бурдед.")
        return
    vpn_key = get_one_vpn_key()
    if vpn_key:
        activate_test_db(user_id, username)
        await bot.send_message(user_id, f"🎉 *Калиди тези шумо барои 24 соат фаъол шуд!*\n\n🔑 Линки VPN:\n`{vpn_key}`", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
    else:
        await bot.send_message(user_id, "😔 Калидҳои ройгон муваққатан тамом шудаанд.")

# ---- 🌍 ИНТИХОБИ ДАВЛАТ ----
@dp.callback_query(F.data == "choose_country")
async def show_country_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇹🇯 Аз Тоҷикистон (Alif, DC ва ғ.)", callback_data="pay_tj")],
        [InlineKeyboardButton(text="🇷🇺 Аз Русия (Сбербанк, Т-Банк)", callback_data="pay_ru")],
        [InlineKeyboardButton(text="⬅️ Ба орқа", callback_data="back_to_menu")]
    ])
    await bot.send_message(callback_query.from_user.id, "🌍 *Интихоб кунед, ки аз кадом давлат пардохт мекунед:*", parse_mode="Markdown", reply_markup=keyboard)

# ---- 🇹🇯 / 🇷🇺 ДАСТУРҲОИ ПАРДОХТ ----
@dp.callback_query(F.data.in_({"pay_tj", "pay_ru"}))
async def process_payment_instruction(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user = get_user_data(user_id)
    price = 25 if user and user[0] == 'active' else 30
    
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Фиристодани Чек", callback_data="send_receipt_now")]])
    
    if callback_query.data == "pay_tj":
        pay_text = (
            f"💰 *Нарх:* {price} сомонӣ\n\n"
            f"💳 *Реквизитҳо барои Тоҷикистон:*\n📌 Бонк: {BANK_NAME}\n🔢 Корт: `{CARD_NUMBER}`\n\n"
            f"ℹ️ *Дастур:*\n1️⃣ Рақами кортро нусха кунед.\n2️⃣ Дар барномаи худ (Alif, DC) пулро гузаронед.\n3️⃣ Ба ҳамин ҷо баргашта тугмаи *'Фиристодани Чек'*-ро пахш кунед."
        )
    else:
        pay_text = (
            f"💰 *Нарх:* {price} сомонӣ (бо рубл)\n\n"
            f"💳 *Реквизитҳо барои Русия:*\n📌 Бонк: {BANK_NAME}\n🔢 Корт: `{CARD_NUMBER}`\n\n"
            f"ℹ️ *Дастур:*\n1️⃣ Рақами кортро нусха кунед.\n2️⃣ Дар Сбербанк ё Т-Банк ба бахши *'Переводы за рубеж -> По номеру карты'* равед ва пулро фиристед.\n3️⃣ Тугмаи *'Фиристодани Чек'*-ро пахш кунед."
        )
    await bot.send_message(user_id, pay_text, parse_mode="Markdown", reply_markup=pay_keyboard)

# ---- 📸 ҚАДАМИ 3: ҚАБУЛИ ЧЕК (ФОТО) ----
@dp.callback_query(F.data == "send_receipt_now")
async def start_receipt_state(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.set_state(BotStates.waiting_for_receipt)
    await bot.send_message(callback_query.from_user.id, "🖼️ Лутфан *Скриншоти Чек (Расм)*-и пардохтро ба бот равон кунед:", parse_mode="Markdown")

@dp.message(BotStates.waiting_for_receipt, F.photo)
async def received_receipt_photo(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    phone = user_data[3] if user_data else "Номаълум"
    username = f"@{message.from_user.username}" if message.from_user.username else "Нест"
    
    # Расми чекро (акси охирин сурати калон) мегирем
    photo_id = message.photo[-1].file_id
    
    await message.answer("⏳ Чек қабул шуд ва ба админ фиристода шуд! Тезтар санҷида, линкро мефиристем.")
    
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Тасдиқ (Додани Линк)", callback_data=f"adm_yes_{user_id}"),
         InlineKeyboardButton(text="❌ Рад кардан", callback_data=f"adm_no_{user_id}")]
    ])
    
    # Рост ба Телеграми админ расми чекро бо маълумот мефиристад!
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"🔔 *ЧЕКИ НАВ ОМАД!*\n\n👤 Муштарӣ: {message.from_user.full_name}\n🆔 ID: `{user_id}`\n📱 Насаб: {username}\n📞 Телефони тасдиқшуда: `{phone}`\n\nЧекро бинед, агар пул омада бошад, Тасдиқ кунед:",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# ---- КОРКАРДИ ТУГМАҲОИ АДМИН ----
@dp.callback_query(F.data.startswith("adm_"))
async def admin_decision(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data = callback_query.data.split("_")
    action = data[1]
    client_id = int(data[2])
    
    if action == "yes":
        user = get_user_data(client_id)
        add_or_extend_subscription(client_id, days=30)
        if user and user[0] == 'active':
            await bot.send_message(client_id, "🎉 Обунаи шумо 30 рӯзи дигар дароз карда шуд!")
        else:
            vpn_key = get_one_vpn_key()
            if vpn_key:
                await bot.send_message(client_id, f"✅ Пардохт тасдиқ шуд! Линки худро пайваст кунед:\n`{vpn_key}`", parse_mode="Markdown")
            else:
                await bot.send_message(client_id, "⚠️ Пул омад, аммо калидҳо тамом шудаанд. Админ ба зудӣ мефиристад.")
        await callback_query.message.edit_caption(caption=f"🟢 ТАСДИҚ ШУД (ID: {client_id})")
    elif action == "no":
        await bot.send_message(client_id, "❌ Пардохти шумо тасдиқ нашуд. Чек фэйк аст ё пул ба корт наомадааст.")
        await callback_query.message.edit_caption(caption=f"🔴 РАД ШУД (ID: {client_id})")

# ---- БАХШҲОИ ДИГАР ----
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.delete()

@dp.callback_query(F.data == "my_profile")
async def show_profile(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user = get_user_data(user_id)
    status_text = "🟢 🍏 Фаъол" if user and user[0] == 'active' else "🔴 Фаъол нест"
    time_left = get_time_left_text(user[1]) if user and user[0] == 'active' else "Обуна мавҷуд нест"
    await bot.send_message(user_id, f"📊 *ПРОФИЛИ ШУМО:* \n\n🆔 ID: `{user_id}`\n⚙️ Статус: {status_text}\n⏳ Вақти боқимонда:\n* {time_left} *", parse_mode="Markdown", reply_markup=get_main_menu(user_id))

@dp.callback_query(F.data == "instruction")
async def show_instruction(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, "📚 Барномаро барои Android бор кунед:\nhttps://play.google.com/store/apps/details?id=com.v2raytun.android")
    
@dp.callback_query(F.data == "support_info")
async def show_support(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await bot.send_message(callback_query.from_user.id, f"👨‍💻 Дастгирии техникӣ: {SUPPORT_LINK}")

# ---- АВТОМАТӢ МАҲКАМ КАРДАН ----
async def check_subscriptions_loop():
    while True:
        try:
            conn = sqlite3.connect('vpn_bot.db')
            cursor = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("SELECT user_id FROM users WHERE status = 'active' AND expire_date < ?", (now_str,))
            for row in cursor.fetchall():
                cursor.execute("UPDATE users SET status = 'inactive' WHERE user_id = ?", (row[0],))
                conn.commit()
                try: await bot.send_message(row[0], "🚨 Мӯҳлати обунаи VPN-и шумо ба охир расид! Лутфан онро харидорӣ кунед.")
                except Exception: pass
            conn.close()
        except Exception as e: logging.error(f"Error in loop: {e}")
        await asyncio.sleep(1800)

async def main():
    init_db()
    asyncio.create_task(check_subscriptions_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
