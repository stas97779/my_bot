import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, SHOPS, ADMIN_ID, TARGET_GROUP_ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

orders = []
active_user = None
custom_shops = []  # магазины добавленные пользователями

# --- Состояния ---
class OrderState(StatesGroup):
    choosing_shop = State()
    entering_custom_shop = State()
    choosing_date = State()
    entering_time = State()
    confirming = State()

class EditState(StatesGroup):
    entering_new_time = State()

# --- Вспомогательные функции ---
def get_next_days(n=7):
    days = []
    for i in range(n):
        date = datetime.now() + timedelta(days=i)
        days.append(date.strftime("%d.%m.%Y"))
    return days

def all_shops():
    return SHOPS + custom_shops

def shops_keyboard():
    builder = InlineKeyboardBuilder()
    for i, shop in enumerate(all_shops()):
        builder.button(text=shop, callback_data=f"shop_{i}")
    # Кнопка добавить свой магазин
    builder.button(text="➕ Добавить свой магазин", callback_data="add_shop")
    builder.adjust(1)
    return builder.as_markup()

def dates_keyboard():
    builder = InlineKeyboardBuilder()
    for date in get_next_days():
        builder.button(text=date, callback_data=f"date_{date}")
    builder.adjust(2)
    return builder.as_markup()

def confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_yes")
    builder.button(text="❌ Отменить", callback_data="confirm_no")
    builder.adjust(2)
    return builder.as_markup()

def build_orders_text_and_keyboard():
    if not orders:
        return "📭 Предзаказов пока нет.", None

    text = "📋 Все предзаказы:\n\n"
    builder = InlineKeyboardBuilder()

    for o in orders:
        text += (
            f"#{o['number']} | {o['date']} в {o['time']}\n"
            f"🏪 {o['shop']}\n"
        )
        if o.get("comment"):
            text += f"💬 {o['comment']}\n"
        text += f"{'─' * 25}\n"

        builder.button(
            text=f"🗑 Удалить #{o['number']}",
            callback_data=f"delete_{o['number']}"
        )
        builder.button(
            text=f"✏️ Изменить #{o['number']}",
            callback_data=f"edit_{o['number']}"
        )

    builder.adjust(1)
    return text, builder.as_markup()

def parse_time_and_comment(text):
    parts = text.strip().split(maxsplit=1)
    time_str = parts[0]
    comment = parts[1] if len(parts) > 1 else ""
    try:
        datetime.strptime(time_str, "%H:%M")
        return time_str, comment
    except ValueError:
        return None, None

# --- Хэндлеры ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    global active_user

    if active_user is not None and active_user != message.from_user.id:
        await message.answer(
            "⏳ Подожди — сейчас другой пользователь оформляет предзаказ.\n"
            "Попробуй через минуту!"
        )
        return

    active_user = message.from_user.id
    await state.clear()
    await message.answer(
        "👋 Привет! Я помогу оформить предзаказ.\n\nШаг 1️⃣ — выбери магазин:",
        reply_markup=shops_keyboard()
    )
    await state.set_state(OrderState.choosing_shop)

@dp.callback_query(OrderState.choosing_shop, F.data == "add_shop")
async def add_shop(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "➕ Введи название своего магазина:\n"
        "Пример: Магазин на Садовой, 15"
    )
    await state.set_state(OrderState.entering_custom_shop)

@dp.message(OrderState.entering_custom_shop)
async def custom_shop_entered(message: Message, state: FSMContext):
    shop_name = message.text.strip()
    custom_shops.append(f"🏪 {shop_name}")
    await state.update_data(shop=f"🏪 {shop_name}")
    await message.answer(
        f"✅ Магазин добавлен: 🏪 {shop_name}\n\nШаг 2️⃣ — выбери дату:",
        reply_markup=dates_keyboard()
    )
    await state.set_state(OrderState.choosing_date)

@dp.callback_query(OrderState.choosing_shop, F.data.startswith("shop_"))
async def shop_chosen(call: CallbackQuery, state: FSMContext):
    index = int(call.data.split("_")[1])
    shop = all_shops()[index]
    await state.update_data(shop=shop)
    await call.message.edit_text(
        f"✅ Магазин: {shop}\n\nШаг 2️⃣ — выбери дату:",
        reply_markup=dates_keyboard()
    )
    await state.set_state(OrderState.choosing_date)

@dp.callback_query(OrderState.choosing_date, F.data.startswith("date_"))
async def date_chosen(call: CallbackQuery, state: FSMContext):
    date = call.data.replace("date_", "")
    await state.update_data(date=date)
    await call.message.edit_text(
        f"✅ Дата: {date}\n\n"
        f"Шаг 3️⃣ — введи время и комментарий одной строкой:\n\n"
        f"Формат: ЧЧ:ММ комментарий\n"
        f"Пример: 14:30 забирать от базы Вадима\n\n"
        f"Или просто время:\n"
        f"Пример: 14:30"
    )
    await state.set_state(OrderState.entering_time)

@dp.message(OrderState.entering_time)
async def time_entered(message: Message, state: FSMContext):
    time_str, comment = parse_time_and_comment(message.text)

    if not time_str:
        await message.answer(
            "⚠️ Неверный формат! Введи время в формате ЧЧ:ММ\n"
            "Пример: 14:30 или 14:30 Без лука"
        )
        return

    await state.update_data(time=time_str, comment=comment)
    data = await state.get_data()
    comment_text = f"\n💬 Комментарий: {comment}" if comment else ""

    await message.answer(
        f"📋 Проверь предзаказ:\n\n"
        f"🏪 Магазин: {data['shop']}\n"
        f"📅 Дата: {data['date']}\n"
        f"🕐 Время: {time_str}"
        f"{comment_text}\n\n"
        f"Всё верно?",
        reply_markup=confirm_keyboard()
    )
    await state.set_state(OrderState.confirming)

@dp.callback_query(OrderState.confirming, F.data == "confirm_yes")
async def order_confirmed(call: CallbackQuery, state: FSMContext):
    global active_user
    data = await state.get_data()

    order_number = len(orders) + 1
    order = {
        "number": order_number,
        "shop": data["shop"],
        "date": data["date"],
        "time": data["time"],
        "comment": data.get("comment", ""),
    }
    orders.append(order)

    comment_text = f"\n💬 {data.get('comment')}" if data.get("comment") else ""

    await call.message.edit_text(
        f"🎉 Предзаказ №{order_number} оформлен!\n\n"
        f"🏪 {data['shop']}\n"
        f"📅 {data['date']} в {data['time']}"
        f"{comment_text}\n\n"
        f"Чтобы оформить новый — /start"
    )

    text, keyboard = build_orders_text_and_keyboard()
    await call.message.answer(text, reply_markup=keyboard)
    active_user = None
    await state.clear()

@dp.callback_query(OrderState.confirming, F.data == "confirm_no")
async def order_cancelled(call: CallbackQuery, state: FSMContext):
    global active_user
    active_user = None
    await state.clear()
    await call.message.edit_text(
        "❌ Заказ отменён. Чтобы начать заново — /start"
    )

@dp.callback_query(F.data.startswith("delete_"))
async def delete_order(call: CallbackQuery):
    order_number = int(call.data.split("_")[1])
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await call.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    orders.remove(order)
    await call.answer(f"✅ Предзаказ #{order_number} удалён.", show_alert=True)

    text, keyboard = build_orders_text_and_keyboard()
    if keyboard:
        await call.message.edit_text(text, reply_markup=keyboard)
    else:
        await call.message.edit_text(text)

@dp.callback_query(F.data.startswith("edit_"))
async def edit_order(call: CallbackQuery, state: FSMContext):
    order_number = int(call.data.split("_")[1])
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await call.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    await state.update_data(edit_order_number=order_number)
    await call.message.answer(
        f"✏️ Редактирование предзаказа #{order_number}\n\n"
        f"Текущее время: {order['time']}\n"
        f"Текущий комментарий: {order.get('comment') or 'нет'}\n\n"
        f"Введи новое время и комментарий:\n"
        f"Пример: 16:00 Позвоните за час"
    )
    await state.set_state(EditState.entering_new_time)

@dp.message(EditState.entering_new_time)
async def save_edited_order(message: Message, state: FSMContext):
    time_str, comment = parse_time_and_comment(message.text)

    if not time_str:
        await message.answer(
            "⚠️ Неверный формат! Введи время в формате ЧЧ:ММ\n"
            "Пример: 16:00 или 16:00 Позвоните за час"
        )
        return

    data = await state.get_data()
    order_number = data["edit_order_number"]
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await message.answer("⚠️ Заказ не найден.")
        await state.clear()
        return

    order["time"] = time_str
    order["comment"] = comment

    comment_text = f"\n💬 {comment}" if comment else ""
    await message.answer(
        f"✅ Предзаказ #{order_number} обновлён!\n\n"
        f"🕐 Новое время: {time_str}"
        f"{comment_text}"
    )

    text, keyboard = build_orders_text_and_keyboard()
    await message.answer(text, reply_markup=keyboard)
    await state.clear()

@dp.message(Command("send"))
async def send_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return

    text, keyboard = build_orders_text_and_keyboard()
    await bot.send_message(TARGET_GROUP_ID, text, reply_markup=keyboard)
    await message.answer("✅ Список предзаказов отправлен в группу!")

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())