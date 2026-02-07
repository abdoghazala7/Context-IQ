from helpers.config import get_config
config = get_config()

# Flower configuration
port = 5555
max_tasks = 10000
# db = 'flower.db'  # SQLite database for persistent storage
auto_refresh = True

# Authentication (optional)
basic_auth = [f'admin:{config.CELERY_FLOWER_PASSWORD}']