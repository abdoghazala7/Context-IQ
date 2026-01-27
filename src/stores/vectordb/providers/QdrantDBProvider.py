from qdrant_client import models, QdrantClient
from models.db_schemes import RetrievedDocument
from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import DistanceMethodEnums
import logging
import uuid
from typing import List, Optional, Union, Dict, Any

class QdrantDBProvider(VectorDBInterface):

    def __init__(self, db_client: str, default_vector_size: int = 1024,
                       distance_method: Optional[str] = None, index_threshold: int = 1000):
   
        self.client: Optional[QdrantClient] = None
        self.db_client = db_client
        self.distance_method: Optional[models.Distance] = None
        self.default_vector_size = default_vector_size
        self.index_threshold = index_threshold

        if distance_method == DistanceMethodEnums.COSINE.value:
            self.distance_method = models.Distance.COSINE
        elif distance_method == DistanceMethodEnums.DOT.value:
            self.distance_method = models.Distance.DOT
        else:
            raise ValueError(f"Unsupported distance method: {distance_method}")

        self.logger = logging.getLogger("uvicorn")

    async def connect(self) -> None:
        try:
            self.client = QdrantClient(path=self.db_client)
            self.logger.info(f"Successfully connected to Qdrant at {self.db_client}")
        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise

    async def disconnect(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            except Exception as e:
                self.logger.warning(f"Error during disconnect: {e}")
            finally:
                self.client = None

    def _ensure_client_connected(self) -> None:
        if self.client is None:
            raise RuntimeError("Client not connected. Call connect() method first.")
    
    async def is_collection_existed(self, collection_name: str) -> bool:
        self._ensure_client_connected()
        return self.client.collection_exists(collection_name=collection_name)
    
    async def list_all_collections(self) -> List:
        self._ensure_client_connected()
        return self.client.get_collections()
    
    async def get_collection_info(self, collection_name: str) -> dict:
        self._ensure_client_connected()
        return self.client.get_collection(collection_name=collection_name)
    
    async def delete_collection(self, collection_name: str):
        self._ensure_client_connected()
        if await self.is_collection_existed(collection_name):
            self.logger.info(f"Deleting Qdrant collection: {collection_name}")
            return self.client.delete_collection(collection_name=collection_name)
        
    async def create_collection(self, collection_name: str, 
                                embedding_size: int,
                                do_reset: bool = False):
        self._ensure_client_connected()

        if do_reset:
            _ = await self.delete_collection(collection_name=collection_name)
        
        if not await self.is_collection_existed(collection_name):
            self.logger.info(f"Creating new Qdrant collection: {collection_name}")
            _ = self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=self.distance_method
                )
            )

            return True
        
        return False
    
    async def insert_one(self, collection_name: str, text: str, vector: List[float],
                         metadata: Optional[Dict[str, Any]] = None, 
                         record_id: Optional[Union[str, int]] = None) -> bool:
        """Insert a single point into the collection.
        
        Args:
            collection_name: Name of the collection
            text: Text content to store
            vector: Embedding vector
            metadata: Optional metadata dictionary
            record_id: Optional point ID (auto-generated if None)
            
        Returns:
            True if successful, False otherwise
        """
        self._ensure_client_connected()
        
        if not await self.is_collection_existed(collection_name):
            self.logger.error(f"Cannot insert record to non-existent collection: {collection_name}")
            return False
        
        # Validate vector is not empty
        if not vector:
            self.logger.error("Vector cannot be empty")
            return False
        
        # Generate UUID if record_id is None
        if record_id is None:
            record_id = str(uuid.uuid4())
        
        try:
            self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(
                        id=record_id,
                        vector=vector,
                        payload={
                            "text": text, 
                            "metadata": metadata
                        }
                    )
                ]
            )
            return True
        except Exception as e:
            self.logger.error(f"Error while inserting point: {e}")
            return False
    
    async def insert_many(self, collection_name: str, texts: List[str], 
                          vectors: List[List[float]], metadata: Optional[List[Optional[Dict[str, Any]]]] = None, 
                          record_ids: Optional[List[Optional[Union[str, int]]]] = None, 
                          batch_size: int = 50) -> bool:
        
        self._ensure_client_connected()
        
        # Input validation
        if not texts or not vectors:
            self.logger.error("Texts and vectors cannot be empty")
            return False
        
        if len(texts) != len(vectors):
            self.logger.error(f"Length mismatch: {len(texts)} texts vs {len(vectors)} vectors")
            return False
        
        if not await self.is_collection_existed(collection_name):
            self.logger.error(f"Cannot insert records to non-existent collection: {collection_name}")
            return False
        
        # Prepare metadata and IDs
        if metadata is None:
            metadata = [None] * len(texts)
        elif len(metadata) != len(texts):
            self.logger.error(f"Metadata length mismatch: {len(metadata)} vs {len(texts)}")
            return False

        if record_ids is None:
            record_ids = [None] * len(texts)
        elif len(record_ids) != len(texts):
            self.logger.error(f"Record IDs length mismatch: {len(record_ids)} vs {len(texts)}")
            return False
        
        record_ids = [str(uuid.uuid4()) if rid is None else rid for rid in record_ids]
        
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(texts), batch_size), 1):
            batch_end = min(i + batch_size, len(texts))

            batch_texts = texts[i:batch_end]
            batch_vectors = vectors[i:batch_end]
            batch_metadata = metadata[i:batch_end]
            batch_ids = record_ids[i:batch_end]

            batch_points = [
                models.PointStruct(
                    id=batch_ids[idx],
                    vector=batch_vectors[idx],
                    payload={
                        "text": batch_texts[idx], 
                        "metadata": batch_metadata[idx]
                    }
                )
                for idx in range(len(batch_texts))
            ]

            try:
                self.client.upsert(
                    collection_name=collection_name,
                    points=batch_points,
                )
            except Exception as e:
                self.logger.error(f"Error while inserting batch {batch_num}/{total_batches}: {e}")
                return False

        self.logger.info(f"Successfully inserted all {len(texts)} points")
        return True
        

    async def search_by_vector(self, collection_name: str, vector: List[float], 
                               limit: int = 5, score_threshold: Optional[float] = None) -> List[RetrievedDocument]:
        self._ensure_client_connected()
        
        if not await self.is_collection_existed(collection_name):
            self.logger.error(f"Cannot search in non-existent collection: {collection_name}")
            return []
        
        if not vector:
            self.logger.error("Query vector cannot be empty")
            return []
        
        if limit <= 0:
            self.logger.error(f"Limit must be positive: {limit}")
            return []
        
        try:
            response = self.client.query_points(
                collection_name=collection_name,
                query=vector,                 
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,           
                with_vectors=False          
            )
            
            results = response.points
            
            self.logger.debug(f"Search returned {len(results)} results")

            return [
            RetrievedDocument(**{
                "score": result.score,
                "text": result.payload["text"],
            })
            for result in results
        ]

        except Exception as e:
            self.logger.error(f"Error during search: {e}")
            return []