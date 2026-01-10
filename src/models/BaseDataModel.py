from helpers.config import get_config

class BaseDataModel:
    def __init__(self, db_client):
        self.db_client = db_client
        self.config = get_config()
        