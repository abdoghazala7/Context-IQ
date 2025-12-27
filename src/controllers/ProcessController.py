import os
from .BaseController import basecontroller
from .ProjectController import projectController
from models import processingenum
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


class processcontroller(basecontroller):
    """
    Controller responsible for processing uploaded files.
    """

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id
        self.project_path = projectController().get_project_path(project_id=project_id)

    def get_file_path(self, file_id: str) -> str:
        return os.path.join(self.project_path, file_id)
    
    def get_file_extension(self, file_id: str) -> str:
        return os.path.splitext(file_id)[1].lower()

    def load_txt_file(self, file_path: str):
        loader = TextLoader(file_path, encoding="utf-8")
        return loader.load()

    def load_pdf_file(self, file_path: str):
        loader = PyMuPDFLoader(file_path)
        return loader.load()

    def get_file_content(self, file_id: str):
        file_path = self.get_file_path(file_id)
        if not os.path.exists(file_path):
            return None
        
        file_extension = self.get_file_extension(file_id)

        if file_extension == processingenum.TXT.value:
            return self.load_txt_file(file_path)
        elif file_extension == processingenum.PDF.value:
            return self.load_pdf_file(file_path)
        else:
            return None

    def get_file_chunks(self, file_content: list, file_id: str,
                            chunk_size: int=100, overlap_size: int=20):

        text_splitter = RecursiveCharacterTextSplitter( 
                            chunk_size=chunk_size, 
                            chunk_overlap=overlap_size, 
                            length_function=len
                        )

        file_content_texts = [
            rec.page_content
            for rec in file_content
        ]

        file_content_metadata = [
            rec.metadata
            for rec in file_content
        ]

        chunks = text_splitter.create_documents(
            file_content_texts,
            metadatas=file_content_metadata
        )

        return chunks