from .BaseController import basecontroller
from models.db_schemes import Project, DataChunk
from stores.llm.LLMEnums import DocumentTypeEnum
from typing import List, Optional, Union
import json

class NLPController(basecontroller):

    def __init__(self, vectordb_client, generation_client, template_parser,
                 embedding_client= None):
        super().__init__()

        self.vectordb_client = vectordb_client
        self.generation_client = generation_client
        self.template_parser = template_parser
        self.embedding_client = embedding_client

    def create_collection_name(self, project_id: str):
        return f"collection_{self.vectordb_client.default_vector_size}_{project_id}".strip()
    
    async def reset_vector_db_collection(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        return await self.vectordb_client.delete_collection(collection_name=collection_name)
    
    async def get_vector_db_collection_info(self, project: Project):
        collection_name = self.create_collection_name(project_id=project.project_id)
        collection_info = await self.vectordb_client.get_collection_info(collection_name=collection_name)
        # Convert CollectionInfo object to dictionary for JSON serialization
        if isinstance(collection_info, dict):
            return collection_info
        return collection_info.model_dump() if hasattr(collection_info, 'model_dump') else collection_info.dict()
    
    async def index_into_vector_db(self, project: Project, chunks: List[DataChunk],
                                   chunks_ids: Optional[List[Union[str, int]]]= None, 
                                   do_reset: bool = False):
        
        # step1: get collection name
        collection_name = self.create_collection_name(project_id=project.project_id)

        # step2: manage items
        texts = [ self.generation_client.process_text(c.chunk_text) for c in chunks ]
        metadata = [ c.chunk_metadata for c in  chunks]
        vectors = self.generation_client.embed_text(text=texts, 
                                                  document_type=DocumentTypeEnum.DOCUMENT.value)

        # step3: create collection if not exists
        _ = await self.vectordb_client.create_collection(
            collection_name=collection_name,
            embedding_size=self.config.EMBEDDING_MODEL_SIZE,
            do_reset=do_reset,
        )

        # step4: insert into vector db
        inserttion_success = await self.vectordb_client.insert_many(
            collection_name=collection_name,
            texts=texts,
            metadata=metadata,
            vectors=vectors,
            record_ids= chunks_ids,
            )
        
        if not inserttion_success:
            return False
        
        return True

    async def search_vector_db_collection(self, project: Project, text: str, limit: int = 10, score_threshold: Optional[float] = None):
        query_vector = None

        # step1: get collection name
        collection_name = self.create_collection_name(project_id=project.project_id)

        # step2: get text embedding vector
        processed_text = self.generation_client.process_text(text)
        vectors = self.generation_client.embed_text(text=processed_text, 
                                                 document_type=DocumentTypeEnum.QUERY.value)

        if not vectors or len(vectors) == 0:
            return False
        
        if isinstance(vectors, list) and len(vectors) > 0:
            query_vector = vectors[0]

        if not query_vector:
            return False    

        # step3: do semantic search
        results = await self.vectordb_client.search_by_vector(
            collection_name=collection_name,
            vector=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        if not results:
            return False

        return results
    
    async def answer_rag_question(self, project: Project, query: str, limit: int = 10, score_threshold: Optional[float] = None):
        
        answer, full_prompt, chat_history = None, None, None

        # step1: retrieve related documents
        retrieved_documents = await self.search_vector_db_collection(
            project=project,
            text=query,
            limit=limit,
            score_threshold=score_threshold
        )

        if not retrieved_documents or len(retrieved_documents) == 0:
            return answer, full_prompt, chat_history
        
        # step2: Construct LLM prompt
        system_prompt = self.template_parser.get("rag", "system_prompt")

        documents_prompts = "\n".join([
            self.template_parser.get("rag", "document_prompt", {
                    "doc_num": idx + 1,
                    "chunk_text": self.generation_client.process_text(doc.text),
            })
            for idx, doc in enumerate(retrieved_documents)
        ])

        footer_prompt = self.template_parser.get("rag", "footer_prompt", {
            "query": self.generation_client.process_text(query)
        })

        # step3: Construct Generation Client Prompts
        chat_history = [
            self.generation_client.construct_prompt(
                prompt=system_prompt,
                role=self.generation_client.enums.SYSTEM.value,
            )
        ]

        full_prompt = "\n\n".join([ documents_prompts,  footer_prompt])

        # step4: Retrieve the Answer
        answer = self.generation_client.generate_text(
            prompt=full_prompt,
            chat_history=chat_history
        )

        return answer, full_prompt, chat_history
    