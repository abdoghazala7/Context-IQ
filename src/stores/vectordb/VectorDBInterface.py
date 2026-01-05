from abc import ABC, abstractmethod
from typing import List, Optional, Union, Dict, Any

class VectorDBInterface(ABC):

    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def disconnect(self) -> None:
        pass

    @abstractmethod
    def is_collection_existed(self, collection_name: str) -> bool:
        pass

    @abstractmethod
    def list_all_collections(self) -> List:
        pass

    @abstractmethod
    def get_collection_info(self, collection_name: str) -> dict:
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str):
        pass

    @abstractmethod
    def create_collection(self, collection_name: str, 
                                embedding_size: int,
                                do_reset: bool = False):
        pass

    @abstractmethod
    def insert_one(self, collection_name: str, text: str, vector: List[float],
                          metadata: Optional[Dict[str, Any]] = None, 
                          record_id: Optional[Union[str, int]] = None) -> bool:
        pass

    @abstractmethod
    def insert_many(self, collection_name: str, texts: List[str], 
                          vectors: List[List[float]], 
                          metadata: Optional[List[Optional[Dict[str, Any]]]] = None, 
                          record_ids: Optional[List[Optional[Union[str, int]]]] = None, 
                          batch_size: int = 50) -> bool:
        pass

    @abstractmethod
    def search_by_vector(self, collection_name: str, vector: List[float], 
                               limit: int = 5, score_threshold: Optional[float] = None) -> List:
        pass