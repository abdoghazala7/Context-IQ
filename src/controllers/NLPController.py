from .BaseController import basecontroller
from models.db_schemes import Project, DataChunk
from stores.llm.LLMEnums import DocumentTypeEnum
from typing import List, Optional, Union
import json

class NLPController(basecontroller):

    def __init__(self, vectordb_client, generation_client, 
                 embedding_client= None):
        super().__init__()

        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.embedding_client = embedding_client

    def create_collection_name(self, project_id: str):
        return f"collection_{project_id}".strip()
    
    def reset_vector_db_collection(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        return self.vectordb_client.delete_collection(collection_name=collection_name)
    
    def get_vector_db_collection_info(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        collection_info = self.vectordb_client.get_collection_info(collection_name=collection_name)
        # Convert CollectionInfo object to dictionary for JSON serialization
        return collection_info.model_dump() if hasattr(collection_info, 'model_dump') else collection_info.dict()
    
    def index_into_vector_db(self, project: Project, chunks: List[DataChunk],
                                   chunks_ids: Optional[List[Union[str, int]]]= None, 
                                   do_reset: bool = False):
        
        # step1: get collection name
        collection_name = self.create_collection_name(project_id=project.project_id)

        # step2: manage items
        texts = [ c.chunk_text for c in chunks ]
        metadata = [ c.chunk_metadata for c in  chunks]
        vectors = [
            self.generation_client.embed_text(text=text, 
                                             document_type=DocumentTypeEnum.DOCUMENT.value)
            for text in texts
        ]

        # step3: create collection if not exists
        _ = self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.config.EMBEDDING_MODEL_SIZE,
            do_reset=do_reset,
        )

        # step4: insert into vector db
        inserttion_success = self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors
            )
        
        if not inserttion_success:
            return False
        
        return True

    def search_vector_db_collection(self, project: Project, text: str, limit: int = 10, score_threshold: Optional[float] = None):

        # step1: get collection name
        collection_name = self.create_collection_name(project_id=project.project_id)

        # step2: get text embedding vector
        vector = self.generation_client.embed_text(text=text, 
                                                 document_type=DocumentTypeEnum.QUERY.value)

        if not vector or len(vector) == 0:
            return False

        # step3: do semantic search
        results = self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=vector,
            limit=limit,
            score_threshold=score_threshold
        )

        if not results:
            return False

        return results
    
    