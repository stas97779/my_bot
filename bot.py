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
custom_shops = []

# --- Состояния ---
class OrderState(StatesGroup):
    choosing_shop = State()
    entering_custom_shop = State()
    choosing_date = State()
    entering_times = State()
    confirming = State()

class EditState(StatesGroup):
    choosing_slot = State()
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

def parse_times(text):
    """Парсит строку вида '10:00, 14:30, 18:00' в список времён"""
    slots = []
    parts = [p.strip() for p in text.split(",")]
    for part in parts:
        try:
            datetime.strptime(part, "%H:%M")
            slots.append(part)
        except ValueError:
            return None
    return slots if slots else None

def build_orders_text_and_keyboard():
    if not orders:
        return "📭 Предзаказов пока нет.", None

    text = "📋 Все предзаказы:\n\n"
    builder = InlineKeyboardBuilder()

    for o in orders:
        text += f"🏪 {o['shop']} | 📅 {o['date']}\n"
        for i, slot in enumerate(o["slots"]):
            text += f"  ⏰ {slot['time']}"
            if slot.get("comment"):
                text += f" — {slot['comment']}"
            text += "\n"
        text += f"{'─' * 25}\n"

        builder.button(
            text=f"🗑 Удалить заказ #{o['number']}",
            callback_data=f"delete_{o['number']}"
        )
        builder.button(
            text=f"✏️ Изменить слот #{o['number']}",
            callback_data=f"edit_{o['number']}"
        )

    builder.adjust(1)
    return text, builder.as_markup()

def slots_keyboard(order_number, slots):
    """Кнопки для выбора слота при редактировании"""
    builder = InlineKeyboardBuilder()
    for i, slot in enumerate(slots):
        builder.button(
            text=f"⏰ {slot['time']} {slot.get('comment', '')}",
            callback_data=f"slot_{order_number}_{i}"
        )
    builder.adjust(1)
    return builder.as_markup()

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
        f"Шаг 3️⃣ — введи время через запятую:\n\n"
        f"Пример: 10:00, 14:30, 18:00\n\n"
        f"Или одно время:\n"
        f"Пример: 14:30"
    )
    await state.set_state(OrderState.entering_times)

@dp.message(OrderState.entering_times)
async def times_entered(message: Message, state: FSMContext):
    slots = parse_times(message.text)

    if not slots:
        await message.answer(
            "⚠️ Неверный формат! Введи время через запятую в формате ЧЧ:ММ\n"
            "Пример: 10:00, 14:30, 18:00"
        )
        return

    # Создаём слоты
    slot_list = [{"time": t, "comment": ""} for t in slots]
    await state.update_data(slots=slot_list)
    data = await state.get_data()

    slots_text = "\n".join([f"  ⏰ {s['time']}" for s in slot_list])

    await message.answer(
        f"📋 Проверь предзаказ:\n\n"
        f"🏪 Магазин: {data['shop']}\n"
        f"📅 Дата: {data['date']}\n"
        f"Временные слоты:\n{slots_text}\n\n"
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
        "slots": data["slots"],
    }
    orders.append(order)

    slots_text = "\n".join([f"  ⏰ {s['time']}" for s in data["slots"]])

    await call.message.edit_text(
        f"🎉 Предзаказ №{order_number} оформлен!\n\n"
        f"🏪 {data['shop']}\n"
        f"📅 {data['date']}\n"
        f"Слоты:\n{slots_text}\n\n"
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

# --- Редактирование слота ---
@dp.callback_query(F.data.startswith("edit_"))
async def edit_order(call: CallbackQuery, state: FSMContext):
    order_number = int(call.data.split("_")[1])
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await call.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    await state.update_data(edit_order_number=order_number)
    await call.message.answer(
        f"✏️ Выбери слот для редактирования в заказе #{order_number}:",
        reply_markup=slots_keyboard(order_number, order["slots"])
    )
    await state.set_state(EditState.choosing_slot)

@dp.callback_query(EditState.choosing_slot, F.data.startswith("slot_"))
async def slot_chosen(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    order_number = int(parts[1])
    slot_index = int(parts[2])

    order = next((o for o in orders if o["number"] == order_number), None)
    slot = order["slots"][slot_index]

    await state.update_data(edit_slot_index=slot_index)
    await call.message.edit_text(
        f"✏️ Редактирование слота ⏰ {slot['time']}\n\n"
        f"Введи новое время и комментарий:\n"
        f"Пример: 16:00 Позвоните за час\n\n"
        f"Или только время:\n"
        f"Пример: 16:00"
    )
    await state.set_state(EditState.entering_new_time)

@dp.message(EditState.entering_new_time)
async def save_edited_slot(message: Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    time_str = parts[0]
    comment = parts[1] if len(parts) > 1 else ""

    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await message.answer(
            "⚠️ Неверный формат! Введи время в формате ЧЧ:ММ\n"
            "Пример: 16:00 или 16:00 Позвоните за час"
        )
        return

    data = await state.get_data()
    order_number = data["edit_order_number"]
    slot_index = data["edit_slot_index"]
    order = next((o for o in orders if o["number"] == order_number), None)

    if not order:
        await message.answer("⚠️ Заказ не найден.")
        await state.clear()
        return

    order["slots"][slot_index]["time"] = time_str
    order["slots"][slot_index]["comment"] = comment

    comment_text = f" — {comment}" if comment else ""
    await message.answer(
        f"✅ Слот обновлён: ⏰ {time_str}{comment_text}"
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