import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, SHOPS

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

orders = []
active_user = None  # кто сейчас оформляет заказ

# --- Состояния ---
class OrderState(StatesGroup):
    choosing_shop = State()
    choosing_date = State()
    choosing_hour = State()
    choosing_minute_tens = State()
    choosing_minute_units = State()
    confirming = State()

# --- Вспомогательные функции ---
def get_next_days(n=7):
    days = []
    for i in range(n):
        date = datetime.now() + timedelta(days=i)
        days.append(date.strftime("%d.%m.%Y"))
    return days

def shops_keyboard():
    builder = InlineKeyboardBuilder()
    for i, shop in enumerate(SHOPS):
        builder.button(text=shop, callback_data=f"shop_{i}")
    builder.adjust(1)
    return builder.as_markup()

def dates_keyboard():
    builder = InlineKeyboardBuilder()
    for date in get_next_days():
        builder.button(text=date, callback_data=f"date_{date}")
    builder.adjust(2)
    return builder.as_markup()

def hours_keyboard():
    builder = InlineKeyboardBuilder()
    for hour in range(9, 22):
        builder.button(text=f"{hour:02d}:__", callback_data=f"hour_{hour}")
    builder.adjust(3)
    return builder.as_markup()

def minute_tens_keyboard():
    builder = InlineKeyboardBuilder()
    for tens in range(0, 6):
        builder.button(text=f"{tens}_", callback_data=f"tens_{tens}")
    builder.adjust(3)
    return builder.as_markup()

def minute_units_keyboard(tens):
    builder = InlineKeyboardBuilder()
    for unit in range(0, 10):
        builder.button(text=f":{tens}{unit}", callback_data=f"unit_{unit}")
    builder.adjust(5)
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
            f"{'─' * 25}\n"
        )
        builder.button(
            text=f"🗑 Удалить #{o['number']}",
            callback_data=f"delete_{o['number']}"
        )

    builder.adjust(1)
    return text, builder.as_markup()

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

@dp.callback_query(OrderState.choosing_shop, F.data.startswith("shop_"))
async def shop_chosen(call: CallbackQuery, state: FSMContext):
    index = int(call.data.split("_")[1])
    shop = SHOPS[index]
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
        f"✅ Дата: {date}\n\nШаг 3️⃣ — выбери час:",
        reply_markup=hours_keyboard()
    )
    await state.set_state(OrderState.choosing_hour)

@dp.callback_query(OrderState.choosing_hour, F.data.startswith("hour_"))
async def hour_chosen(call: CallbackQuery, state: FSMContext):
    hour = int(call.data.split("_")[1])
    await state.update_data(hour=hour)
    await call.message.edit_text(
        f"✅ Час: {hour:02d}:__\n\nШаг 4️⃣ — выбери десятки минут:",
        reply_markup=minute_tens_keyboard()
    )
    await state.set_state(OrderState.choosing_minute_tens)

@dp.callback_query(OrderState.choosing_minute_tens, F.data.startswith("tens_"))
async def minute_tens_chosen(call: CallbackQuery, state: FSMContext):
    tens = int(call.data.split("_")[1])
    await state.update_data(tens=tens)
    data = await state.get_data()
    await call.message.edit_text(
        f"✅ Час: {data['hour']:02d}:{tens}_\n\nШаг 5️⃣ — выбери единицы минут:",
        reply_markup=minute_units_keyboard(tens)
    )
    await state.set_state(OrderState.choosing_minute_units)

@dp.callback_query(OrderState.choosing_minute_units, F.data.startswith("unit_"))
async def minute_units_chosen(call: CallbackQuery, state: FSMContext):
    unit = int(call.data.split("_")[1])
    data = await state.get_data()
    minute = data["tens"] * 10 + unit
    time = f"{data['hour']:02d}:{minute:02d}"
    await state.update_data(time=time)
    await call.message.edit_text(
        f"📋 Проверь предзаказ:\n\n"
        f"🏪 Магазин: {data['shop']}\n"
        f"📅 Дата: {data['date']}\n"
        f"🕐 Время: {time}\n\n"
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
    }
    orders.append(order)

    await call.message.edit_text(
        f"🎉 Предзаказ №{order_number} оформлен!\n\n"
        f"🏪 {data['shop']}\n"
        f"📅 {data['date']} в {data['time']}\n\n"
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

  @dp.message(Command("getid"))
async def get_id(message: Message):
    await message.answer(f"ID этого чата: `{message.chat.id}`")

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())