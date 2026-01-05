from helpers.config import Config, get_config
import os
import random
import string

class basecontroller:
    def __init__(self):
        self.config: Config = get_config()

        self.base_dir = os.path.dirname( os.path.dirname(__file__) )
        self.files_dir = os.path.join(
            self.base_dir,
            "assets/files"
        )

        self.database_dir = os.path.join(
            self.base_dir,
            "assets/database"
        )
        
    def generate_random_string(self, length: int=12):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))  

    def get_database_path(self, db_name: str):

        database_path = os.path.join(
            self.database_dir, db_name
        )

        if not os.path.exists(database_path):
            os.makedirs(database_path)

        return database_path