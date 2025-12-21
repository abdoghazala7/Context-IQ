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
        
    def generate_random_string(self, length: int=12):
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))  