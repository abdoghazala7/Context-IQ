from enum import Enum

class responsesignal(Enum):

    WELCOME_AND_HEALTH_CHECK_MESSAGE="Welcome to Context IQ APP! The service is up and running ✅"
    FILE_TYPE_NOT_SUPPORTED = "File type not supported ❌"
    FILE_SIZE_EXCEEDED = "File size exceeded the maximum limit ❌"
    FILE_VALIDATED_SUCCESS = "File validated successfully ✔️"
    FILE_UPLOAD_SUCCESS = "File uploaded successfully ✅"
    FILE_UPLOAD_FAILED = "File upload failed ❗"
    FILE_NOT_FOUND = "File not found. Please upload the file first ❌"
    PROCESSING_SUCCESS = "processed successfully ✅"
    PROCESSING_FAILED = "processing failed ❗"
    NO_FILES_ERROR = "not_found_files ❗"
    FILE_ID_ERROR = "no_file_found_with_this_id ❗"
    PROJECT_NOT_FOUND_ERROR = "project_not_found ❗"
    INSERT_INTO_VECTORDB_ERROR = "insert_into_vectordb_error ❗"
    INSERT_INTO_VECTORDB_SUCCESS = "insert_into_vectordb_success ✅"
    VECTORDB_COLLECTION_RETRIEVED = "vectordb_collection_retrieved ✅"
    VECTORDB_SEARCH_ERROR = "vectordb_search_error ❗"
    VECTORDB_SEARCH_SUCCESS = "vectordb_search_success ✅"

