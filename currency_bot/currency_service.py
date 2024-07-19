import aiohttp
import redis.asyncio as redis
import xml.etree.ElementTree as ET
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, CBR_URL


async def fetch_exchange_rates() -> str:
    """
    Асинхронно загружает XML файл с курсами валют с сайта ЦБ РФ.

    :return: Строка с содержимым XML файла.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(CBR_URL) as response:
            response_text = await response.text()
            if response.status != 200:
                raise ValueError(f"Ошибка загрузки данных: {response.status}")
            return response_text


def parse_exchange_rates(xml_data: str) -> dict[str, float]:
    """
    Парсит XML данные и извлекает курсы валют.

    :param xml_data: Строка с XML данными.
    :return: Словарь с курсами валют, где ключ - код валюты, значение - курс.
    """
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"Ошибка парсинга XML: {e}")
        print(f"Содержимое ответа: {xml_data}")
        raise

    rates = {'RUB': 1.0}  # Добавляем курс рубля, равный 1
    for valute in root.findall('Valute'):
        char_code = valute.find('CharCode').text
        value = float(valute.find('Value').text.replace(',', '.'))
        nominal = int(valute.find('Nominal').text)
        rates[char_code] = value / nominal
    return rates


async def save_exchange_rates(rates: dict[str, float]) -> None:
    """
    Сохраняет курсы валют в Redis.

    :param rates: Словарь с курсами валют.
    """
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    for char_code, value in rates.items():
        await r.set(char_code, value)


async def update_exchange_rates() -> None:
    """
    Обновляет курсы валют: загружает, парсит и сохраняет их в Redis.
    """
    xml_data = await fetch_exchange_rates()
    rates = parse_exchange_rates(xml_data)
    await save_exchange_rates(rates)


async def start_scheduler() -> None:
    """
    Запускает планировщик задач для обновления курсов валют каждый день в 12:00 ночи.
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_exchange_rates, 'cron', hour=0, minute=0)
    scheduler.start()


async def main() -> None:
    await update_exchange_rates()
    await start_scheduler()


if __name__ == '__main__':
    asyncio.run(main())