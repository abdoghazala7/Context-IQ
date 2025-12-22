from enum import Enum

class responsesignal(Enum):

    WELCOME_AND_HEALTH_CHECK_MESSAGE="Welcome to Context IQ! The service is up and running. ✅"
    FILE_TYPE_NOT_SUPPORTED = "File type not supported. ❌"
    FILE_SIZE_EXCEEDED = "File size exceeded the maximum limit. ❌"
    FILE_VALIDATED_SUCCESS = "File validated successfully. ✔️"
    FILE_UPLOAD_SUCCESS = "File uploaded successfully. ✅"
    FILE_UPLOAD_FAILED = "File upload failed. ❗"
    FILE_NOT_FOUND = "File not found. Please upload the file first. ❌"
    FILE_PROCESS_SUCCESS = "File processed successfully. ✅"
    FILE_PROCESS_FAILED = "File processing failed. ❗"
