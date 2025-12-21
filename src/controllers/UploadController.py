
import os
import re
from .ProjectController import projectController
from .BaseController import basecontroller
from fastapi import UploadFile
from models import responsesignal


class uploadcontroller(basecontroller):
    def __init__(self):
        super().__init__()

        self.allowed_extensions = self.config.ALLOWED_EXTENSIONS
        self.max_file_size = self.config.MAX_FILE_SIZE

    def validate_uploaded_file(self, file: UploadFile):
        """
        Validate the uploaded file based on allowed extensions and size.
        """
        if file.content_type not in self.allowed_extensions:
            return False, responsesignal.FILE_TYPE_NOT_SUPPORTED.value

        if file.size > self.max_file_size:
            return False, responsesignal.FILE_SIZE_EXCEEDED.value

        return True, responsesignal.FILE_VALIDATED_SUCCESS.value
    
    
    def generate_unique_filepath(self, orig_file_name: str, project_id: str):

        """
            Generate a unique file path for the uploaded file within the project directory.
            Ensures no filename collisions by appending a random string if necessary.

            Returns:
                - new_file_path (str): The unique file path for the uploaded file.
                - new_file_name (str): The unique file name for the uploaded file.
        """

        random_key = self.generate_random_string()
        project_path = projectController().get_project_path(project_id=project_id)

        cleaned_file_name = self.get_clean_file_name(
            orig_file_name=orig_file_name
        )

        new_file_path = os.path.join(
            project_path,
            random_key + "_" + cleaned_file_name
        )

        while os.path.exists(new_file_path):
            random_key = self.generate_random_string()
            new_file_path = os.path.join(
                project_path,
                random_key + "_" + cleaned_file_name
            )

        return new_file_path, random_key + "_" + cleaned_file_name
    


    def get_clean_file_name(self, orig_file_name: str):

        # remove any special characters, except underscore and .
        cleaned_file_name = re.sub(r'[^\w.]', '', orig_file_name.strip())

        # replace spaces with underscore
        cleaned_file_name = cleaned_file_name.replace(" ", "_")

        return cleaned_file_name
    
        

    
