
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

        # MIME types that browsers/clients may send for structured data files.
        # These vary across OS and client, so we accept them via extension fallback.
        self._structured_data_mime_map = {
            ".csv": [
                "text/csv",
                "application/csv",
                "application/vnd.ms-excel",   # Windows sometimes sends this for CSV
                "text/plain",
                "application/octet-stream",
            ],
            ".xlsx": [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/octet-stream",
            ],
            ".xls": [
                "application/vnd.ms-excel",
                "application/octet-stream",
            ],
        }

    def validate_uploaded_file(self, file: UploadFile):
        
        if file.size > self.max_file_size:
            return False, responsesignal.FILE_SIZE_EXCEEDED.value

        if file.content_type in self.allowed_extensions:
            return True, responsesignal.FILE_VALIDATED_SUCCESS.value

        file_ext = os.path.splitext(file.filename)[1].lower()

        # Markdown fallback (existing behaviour)
        if file_ext == ".md" and file.content_type in ["application/octet-stream", "text/plain"]:
            return True, responsesignal.FILE_VALIDATED_SUCCESS.value

        # Structured data (CSV / Excel) fallback: accept if the extension is
        # known AND the reported MIME type is one of the common variants.
        if file_ext in self._structured_data_mime_map:
            accepted_mimes = self._structured_data_mime_map[file_ext]
            if file.content_type in accepted_mimes:
                return True, responsesignal.FILE_VALIDATED_SUCCESS.value

        return False, responsesignal.FILE_TYPE_NOT_SUPPORTED.value
    
    
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
    
        

    
