import os

REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: int = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB: int = int(os.getenv('REDIS_DB', 0))
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN')
CBR_URL: str = 'https://cbr.ru/scripts/XML_daily.asp'