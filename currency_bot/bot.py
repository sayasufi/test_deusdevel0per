import redis.asyncio as redis
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import Command
from aiogram import Router
import asyncio
from config import TELEGRAM_TOKEN, REDIS_HOST, REDIS_PORT, REDIS_DB
from currency_service import start_scheduler, update_exchange_rates
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

router = Router()


class ConversionState(StatesGroup):
    waiting_for_to_currency = State()
    waiting_for_amount = State()


async def get_currency_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с валютами из Redis.
    """
    keys = await r.keys()
    keys.sort()  # Сортируем валюты для удобства
    buttons = [InlineKeyboardButton(text=key, callback_data=f"{prefix}:{key}") for key in keys]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 3] for i in range(0, len(buttons), 3)])
    return keyboard


@router.message(Command("start"))
async def send_welcome(message: Message) -> None:
    """
    Отправляет приветственное сообщение при старте бота.

    :param message: Сообщение от пользователя.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Конвертировать валюту", callback_data="convert_currency")],
        [InlineKeyboardButton(text="Показать курсы валют", callback_data="show_rates")],
    ])
    await message.answer("Добро пожаловать! Выберите опцию ниже:", reply_markup=keyboard)


@router.message(Command("help"))
async def send_help(message: Message) -> None:
    """
    Отправляет сообщение с инструкциями по использованию команд.

    :param message: Сообщение от пользователя.
    """
    help_text = (
        "Команды:\n"
        "/start - Запуск бота и отображение меню\n"
        "/help - Помощь по командам\n"
        "/exchange <from_currency> <to_currency> <amount> - Конвертация валюты\n"
        "/rates - Показать курсы валют\n\n"
        "Пример:\n"
        "/exchange USD RUB 10 - Конвертировать 10 долларов в рубли"
    )
    await message.answer(help_text)


@router.message(Command("exchange"))
async def exchange(message: Message) -> None:
    """
    Обрабатывает команду /exchange для конвертации валют.

    :param message: Сообщение от пользователя.
    """
    try:
        _, from_currency, to_currency, amount = message.text.split()
        amount = float(amount)
        from_rate = await r.get(from_currency)
        to_rate = await r.get(to_currency)

        if from_rate is None or to_rate is None:
            await message.answer(f"Ошибка: Не удалось найти курс для {from_currency} или {to_currency}.")
            return

        from_rate = float(from_rate)
        to_rate = float(to_rate)
        result = (amount * from_rate) / to_rate
        await message.answer(f"{amount} {from_currency} = {result:.2f} {to_currency}")
    except Exception as e:
        await message.answer(f"Ошибка: {str(e)}")


@router.message(Command("rates"))
async def send_rates(message: Message) -> None:
    """
    Обрабатывает команду /rates для отображения текущих курсов валют.

    :param message: Сообщение от пользователя.
    """
    keys = await r.keys()
    if not keys:
        await message.answer("Курсы валют не найдены.")
        return

    rates = {key: await r.get(key) for key in keys}
    rates_message = "\n".join([f"{key}: {float(value):.2f}" for key, value in rates.items()])
    await message.answer(rates_message)


@router.callback_query(lambda callback_query: callback_query.data == "convert_currency")
async def convert_currency(callback_query: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает запрос на конвертацию валют.
    """
    keyboard = await get_currency_keyboard(prefix="from_currency")
    await callback_query.message.answer("Выберите валюту, которую хотите конвертировать:", reply_markup=keyboard)
    await state.set_state(ConversionState.waiting_for_to_currency)


@router.callback_query(lambda callback_query: callback_query.data == "show_rates")
async def show_rates(callback_query: CallbackQuery) -> None:
    """
    Обрабатывает запрос на показ курсов валют.
    """
    keys = await r.keys()
    if not keys:
        await callback_query.message.answer("Курсы валют не найдены.")
        return

    rates = {key: await r.get(key) for key in keys}
    rates_message = "\n".join([f"{key}: {float(value):.2f}" for key, value in rates.items()])
    await callback_query.message.answer(rates_message)


@router.callback_query(lambda callback_query: callback_query.data.startswith("from_currency:"))
async def select_from_currency(callback_query: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает выбор первой валюты.
    """
    from_currency = callback_query.data.replace("from_currency:", "")
    await state.update_data(from_currency=from_currency)
    keyboard = await get_currency_keyboard(prefix="to_currency")
    await callback_query.message.answer(f"Вы выбрали {from_currency}. Теперь выберите валюту для конвертации:",
                                        reply_markup=keyboard)
    await state.set_state(ConversionState.waiting_for_amount)


@router.callback_query(lambda callback_query: callback_query.data.startswith("to_currency:"))
async def select_to_currency(callback_query: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает выбор второй валюты.
    """
    to_currency = callback_query.data.replace("to_currency:", "")
    await state.update_data(to_currency=to_currency)
    data = await state.get_data()
    from_currency = data['from_currency']
    await callback_query.message.answer(
        f"Вы выбрали {to_currency}. Введите количество {from_currency} для конвертации в {to_currency}:")
    await state.set_state(ConversionState.waiting_for_amount)


@router.message(ConversionState.waiting_for_amount)
async def handle_amount(message: Message, state: FSMContext) -> None:
    """
    Обрабатывает ввод количества валюты для конвертации.
    """
    data = await state.get_data()
    from_currency = data['from_currency']
    to_currency = data['to_currency']
    amount = float(message.text)
    from_rate = await r.get(from_currency)
    to_rate = await r.get(to_currency)

    if from_rate is None or to_rate is None:
        await message.answer(f"Ошибка: Не удалось найти курс для {from_currency} или {to_currency}.")
        return

    from_rate = float(from_rate)
    to_rate = float(to_rate)
    result = (amount * from_rate) / to_rate
    await message.answer(f"{amount} {from_currency} = {result:.2f} {to_currency}")
    await state.clear()


async def main() -> None:
    dp.include_router(router)
    await update_exchange_rates()  # Обновляем курсы валют при запуске
    await start_scheduler()  # Запускаем планировщик

    # Устанавливаем команды для меню
    await bot.set_my_commands([
        types.BotCommand(command="/start", description="Запустить бота"),
        types.BotCommand(command="/help", description="Помощь"),
        types.BotCommand(command="/exchange", description="Конвертировать валюту"),
        types.BotCommand(command="/rates", description="Показать курсы валют"),
    ])

    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
