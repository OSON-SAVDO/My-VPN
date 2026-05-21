import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from threading import Thread  # 👈 Барои сервери Flask лозим аст
from flask import Flask        # 👈 Барои фиреб додани Render лозим аст
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ⚠️ ТАНЗИМОТИ АСОСӢ
API_TOKEN = '8877992551:AAGfxb2TCk1kYGdKX3w_ty-HkGZtbxivsjY'
ADMIN_ID = 5863448768  # 👈 ИД-и Телеграми худро гузоред
CARD_NUMBER = "4444888812573909"  # 👈 Рақами корт
BANK_NAME = "Алиф Банк"
SUPPORT_LINK = "@Saiddzodaa"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---- 🚀 ВЕБ-СЕРВЕР БАРОИ ХОСТИНИГИ RENDER ----
app = Flask('')

@app.route('/')
def home():
    return "Бот бо муваффақият кор карда истодааст!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

class BotStates(StatesGroup):
    waiting_for_contact = State()
    waiting_for_receipt = State()

# ---- БАЗАИ МАЪЛУМОТ (ВЕРСИЯИ БЕХАТАР) ----
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
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT status, expire_date, has_used_test, phone FROM users WHERE user_id = ?', (user_id,))
        data = cursor.fetchone()
    except sqlite3.OperationalError:
        data = None
    conn.close()
    return data

def save_user_phone(user_id, username, phone):
    conn = sqlite3.connect('vpn_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, username, phone, status, expire_date, has_used_test)
        VALUES (?, ?, ?, 'inactive', NULL, 0)
        ON CONFLICT(user_id) DO UPDATE SET phone=?, username=?
    ''', (user_id, username, phone, phone, username))
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
    user = get_user_data(user_id) # ТАРТИБИ ЭЛЕМЕНТҲО: 0=status, 1=expire_date, 2=has_used_test, 3=phone
    now = datetime.now()
    
    if user and user[1]: # Агар вақти обунаи кӯҳна мавҷуд бошад
        try:
            current_expire = datetime.strptime(user[1], '%Y-%m-%d %H:%M:%S')
            if current_expire > now:
                new_expire = current_expire + timedelta(days=days)
            else:
                new_expire = now + timedelta(days=days)
        except Exception:
            new_expire = now + timedelta(days=days)
    else:
        new_expire = now + timedelta(days=days)
        
    new_expire_str = new_expire.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET status="active", expire_date=? WHERE user_id=?', (new_expire_str, user_id))
    conn.commit()
    conn.close()

# 🛠️ ИСЛОҲШУДА: Функсияи гирифтани калид вобаста аз намуди обуна
def get_one_vpn_key(key_type="premium"):
    """
    key_type метавонад 'test' ё 'premium' бошад.
    Вобаста ба ин калидҳоро аз файлҳои гуногун мехонад ва нест мекунад.
    """
    if key_type == "test":
        file_name = "test_keys.txt"
    else:
        file_name = "premium_keys.txt"
        
    if not os.path.exists(file_name) or os.path.getsize(file_name) == 0: 
        return None
        
    with open(file_name, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    if not lines: 
        return None
        
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
    # Тартиби элементҳо дар функсияи get_user_data: index 2 ин has_used_test аст
    if not user or user[2] == 0:
        buttons.append([InlineKeyboardButton(text="🎁 Оғози ройгон (Тест 24 соат)", callback_data="get_free_test")])
    buy_text = "🔄 Дароз кардани обуна ( 80 рубл )🔥" if user and user[0] == 'active' else "💳 Хариди Обуна ( 120 рубл)"
    buttons.append([InlineKeyboardButton(text=buy_text, callback_data="choose_country")])
    buttons.append([InlineKeyboardButton(text="📊 Профили ман", callback_data="my_profile"),
                    InlineKeyboardButton(text="📚 Дастурамал", callback_data="instruction")])
    buttons.append([InlineKeyboardButton(text="👨‍💻 Дастгирии техникӣ", callback_data="support_info")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user_data(user_id)
    if user and user[3]: # Агар рақами телефон аллакай сабт бошад
        await message.answer("👋 Хуш омадед ба боти VPN! Боз ба кор шурӯъ мекунем:", reply_markup=get_main_menu(user_id))
    else:
        contact_keyboard = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="📱 Фиристодани рақами телефон", request_contact=True)]
        ], resize_keyboard=True, one_time_keyboard=True)
        await state.set_state(BotStates.waiting_for_contact)
        await message.answer(
            "👋 Салом! Ба боти VPN 2Raytun хуш омадед.\n\n"
            "⚠️ *Барои истифодабарии бот, лутфан аввал рақами телефони худро тавассути тугмаи зерин тасдиқ кунед:*",
            parse_mode="Markdown", reply_markup=contact_keyboard
        )

@dp.message(BotStates.waiting_for_contact, F.contact)
async def process_contact(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    phone = message.contact.phone_number
    username = message.from_user.username or "user"
    save_user_phone(user_id, username, phone)
    await message.answer("✅ Рақами шумо қабул шуд! Менюи асосӣ кушода шуд.", reply_markup=types.ReplyKeyboardRemove())
    await message.answer("🚀 Озодона истифода баред:", reply_markup=get_main_menu(user_id))

@dp.callback_query(F.data == "get_free_test")
async def process_free_test(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or "user"
    user = get_user_data(user_id)
    
    if user and user[2] == 1:
        await bot.send_message(user_id, "❌ Шумо аллакай замони тестро истифода бурдед.")
        return
        
    # 🛠️ ИСЛОҲШУДА: Калиди тестро аз файли тестӣ мехонем
    vpn_key = get_one_vpn_key(key_type="test")
    if vpn_key:
        activate_test_db(user_id, username)
        await bot.send_message(user_id, f"🎉 *Калиди тези шумо барои 24 соат фаъол шуд!*\n\n🔑 Линки VPN:\n`{vpn_key}`", parse_mode="Markdown", reply_markup=get_main_menu(user_id))
    else:
        await bot.send_message(user_id, "😔 Калидҳои ройгон муваққатан тамом шудаанд.")

@dp.callback_query(F.data == "choose_country")
async def show_country_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇹🇯 Аз Тоҷикистон (Alif, DC ва ғ.)", callback_data="pay_tj")],
        [InlineKeyboardButton(text="🇷🇺 Аз Русия (Сбербанк, Т-Банк)", callback_data="pay_ru")],
        [InlineKeyboardButton(text="⬅️ Ба орқа", callback_data="back_to_menu")]
    ])
    await bot.send_message(callback_query.from_user.id, "🌍 *Интихоб кунед, ки аз кадом давлат пардохт мекунед:*", parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.in_({"pay_tj", "pay_ru"}))
async def process_payment_instruction(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user = get_user_data(user_id)
    price = 80 if user and user[0] == 'active' else 120
    pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📸 Фиристодани Чек", callback_data="send_receipt_now")]])
    if callback_query.data == "pay_tj":
        pay_text = f"💰 *Нарх:* {price} рубл\n\n💳 *Реквизитҳо барои Тоҷикистон:*\n📌 Бонк: {BANK_NAME}\n🔢 Корт: `{CARD_NUMBER}`\n\nℹ️ *Дастур:*\n1️⃣ Корткуниро нусха кунед.\n2️⃣ Дар барнома пулро гузаронед.\n3️⃣ Тугмаи *'Фиристодани Чек'*-ро пахш кунед."
    else:
        pay_text = f"💰 *Нарх:* {price} рубл\n\n💳 *Реквизитҳо барои Русия:*\n📌 Бонк: {BANK_NAME}\n🔢 Корт: `{CARD_NUMBER}`\n\nℹ️ *Дастур:*\n1️⃣ Кортро нусха кунед.\n2️⃣ Дар Сбербанк ё Т-Банк ба бахши Переводы Таджикистана по карта равед.\n3️⃣ Тугмаи *'Фиристодани Чек'*-ро пахш кунед."
    await bot.send_message(user_id, pay_text, parse_mode="Markdown", reply_markup=pay_keyboard)

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
    photo_id = message.photo[-1].file_id
    await message.answer("⏳ Чек қабул шуд ва ба админ фиристода шуд! Тезтар санҷида, линкро мефиристем.")
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Тасдиқ", callback_data=f"adm_yes_{user_id}"),
         InlineKeyboardButton(text="❌ Рад кардан", callback_data=f"adm_no_{user_id}")]
    ])
    await bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"🔔 *ЧЕКИ НАВ!*\n👤 Муштарӣ: {message.from_user.full_name}\n🆔 ID: `{user_id}`\n📱 Насаб: {username}\n📞 Телефони тасдиқшуда: `{phone}`", parse_mode="Markdown", reply_markup=admin_keyboard)

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
            # 🛠️ ИСЛОҲШУДА: Калиди пулакиро аз файли premium мехонад
            vpn_key = get_one_vpn_key(key_type="premium")
            if vpn_key: 
                await bot.send_message(client_id, f"✅ Пардохт тасдиқ шуд! Линки худро пайваст кунед:\n`{vpn_key}`", parse_mode="Markdown")
            else: 
                await bot.send_message(client_id, "⚠️ Калидҳои премиум тамом шудаанд. Админ ба зудӣ мефиристад.")
        await callback_query.message.edit_caption(caption=f"🟢 ТАСДИҚ ШУД (ID: {client_id})")
        
    elif action == "no":
        await bot.send_message(client_id, "❌ Пардохти шумо тасдиқ нашуд.")
        await callback_query.message.edit_caption(caption=f"🔴 РАД ШУД (ID: {client_id})")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.delete()

@dp.callback_query(F.data == "my_profile")
async def show_profile(callback_query: types.CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    user = get_user_data(user_id)
    status_text = "🟢 Фаъол" if user and user[0] == 'active' else "🔴 Фаъол нест"
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
                try: 
                    await bot.send_message(row[0], "🚨 Мӯҳлати обунаи VPN-и шумо ба охир расид! Лутфан онро харидорӣ кунед.")
                except Exception: 
                    pass
            conn.close()
        except Exception as e: 
            logging.error(f"Error in loop: {e}")
        await asyncio.sleep(1800)

async def main():
    init_db()
    keep_alive()  # 👈 Рӯшан кардани веб-сервер пеш аз шурӯи бот
    asyncio.create_task(check_subscriptions_loop())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
