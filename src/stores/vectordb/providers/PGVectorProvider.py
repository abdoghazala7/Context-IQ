from ..VectorDBInterface import VectorDBInterface
from ..VectorDBEnums import (DistanceMethodEnums, PgVectorTableSchemeEnums, 
                             PgVectorDistanceMethodEnums, PgVectorIndexTypeEnums)
import logging
from typing import List, Optional, Union, Dict, Any
from models.db_schemes import RetrievedDocument
from sqlalchemy.sql import text as sql_text
import json

class PGVectorProvider(VectorDBInterface):

    def __init__(self, db_client, default_vector_size: int = 1024,
                       distance_method: Optional[str] = None, index_threshold: int = 1000):
        
        self.db_client = db_client
        self.default_vector_size = default_vector_size
        self.index_threshold = index_threshold

        if distance_method == DistanceMethodEnums.COSINE.value:
            self.distance_method = PgVectorDistanceMethodEnums.COSINE.value
        elif distance_method == DistanceMethodEnums.DOT.value:
            self.distance_method = PgVectorDistanceMethodEnums.DOT.value
        else:
            # Default to cosine similarity
            self.distance_method = PgVectorDistanceMethodEnums.COSINE.value

        self.pgvector_table_prefix = PgVectorTableSchemeEnums._PREFIX.value

        self.default_index_name = lambda collection_name: f"{collection_name}_vector_idx"

        self.logger = logging.getLogger("uvicorn")

    async def connect(self) -> None:
        """
        Establish connection and ensure pgvector extension is installed.
        """
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(sql_text(
                    "CREATE EXTENSION IF NOT EXISTS vector"
                ))
                await session.commit()

    async def disconnect(self):
        pass

    async def is_collection_existed(self, collection_name: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                list_tbl = sql_text('SELECT 1 FROM pg_tables WHERE tablename = :collection_name LIMIT 1')
                results = await session.execute(list_tbl, {"collection_name": collection_name})
                record = results.scalar_one_or_none()

        return record is not None
    
    async def list_all_collections(self) -> List:
        records = []
        async with self.db_client() as session:
            async with session.begin():
                list_tbl = sql_text('SELECT tablename FROM pg_tables WHERE tablename LIKE :prefix')
                results = await session.execute(list_tbl, {"prefix": self.pgvector_table_prefix})
                records = list(results.scalars().all())
        
        return records
    
    async def get_collection_info(self, collection_name: str) -> dict:
        async with self.db_client() as session:
            async with session.begin():
                
                table_info_sql = sql_text('''
                    SELECT schemaname, tablename, tableowner, tablespace, hasindexes 
                    FROM pg_tables 
                    WHERE tablename = :collection_name
                ''')

                table_info = await session.execute(table_info_sql, {"collection_name": collection_name})
                table_data = table_info.fetchone()
                
                if not table_data:
                    return {}

                # Use identifier quoting for the count query to prevent SQL injection
                count_sql = sql_text(f'SELECT COUNT(*) FROM "{collection_name}"')
                record_count = await session.execute(count_sql)
                
                return {
                    "table_info": {
                        "schemaname": table_data[0],
                        "tablename": table_data[1],
                        "tableowner": table_data[2],
                        "tablespace": table_data[3],
                        "hasindexes": table_data[4],
                    },
                    "record_count": record_count.scalar_one(),
                }
            
    async def delete_collection(self, collection_name: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                self.logger.info(f"Deleting collection: {collection_name}")
                # Use identifier quoting to prevent SQL injection
                delete_sql = sql_text(f'DROP TABLE IF EXISTS "{collection_name}" CASCADE')
                await session.execute(delete_sql)
                await session.commit()
        
        return True

    async def create_collection(self, collection_name: str,
                                      embedding_size: int,
                                      do_reset: bool = False) -> bool:
        """
        Create a new vector collection (table) with the specified embedding size.
        
        Args:
            collection_name: Name for the new collection.
            embedding_size: Dimension of the embedding vectors.
            do_reset: If True, drop existing collection before creating.
            
        Returns:
            True if collection was created, False if it already existed.
        """
        if do_reset:
            await self.delete_collection(collection_name=collection_name)

        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.info(f"Creating new PGVector collection: {collection_name}")
            async with self.db_client() as session:
                async with session.begin():
                    # Build table creation SQL with proper column definitions
                    create_sql = sql_text(
                        f'CREATE TABLE "{collection_name}" ('
                            f'{PgVectorTableSchemeEnums.ID.value} bigserial PRIMARY KEY, '
                            f'{PgVectorTableSchemeEnums.TEXT.value} text, '
                            f'{PgVectorTableSchemeEnums.VECTOR.value} vector({embedding_size}), '
                            f'{PgVectorTableSchemeEnums.METADATA.value} jsonb DEFAULT \'{{}}\', '
                            f'{PgVectorTableSchemeEnums.CHUNK_ID.value} integer, '
                            f'FOREIGN KEY ({PgVectorTableSchemeEnums.CHUNK_ID.value}) REFERENCES chunks(chunk_id)'
                        ')'
                    )
                    await session.execute(create_sql)
                    await session.commit()
            
            return True

        return False
    

    
    async def is_index_existed(self, collection_name: str) -> bool:
        index_name = self.default_index_name(collection_name)
        async with self.db_client() as session:
            async with session.begin():
                check_sql = sql_text("""
                    SELECT 1 
                    FROM pg_indexes 
                    WHERE tablename = :collection_name
                    AND indexname = :index_name
                    LIMIT 1
                """)
                results = await session.execute(check_sql, {
                    "index_name": index_name, 
                    "collection_name": collection_name
                })
                
                return results.scalar_one_or_none() is not None
            
    async def create_vector_index(self, collection_name: str,
                                        index_type: str = PgVectorIndexTypeEnums.HNSW.value) -> bool:
        """
        Create a vector index on the collection for efficient similarity search.
        Index is only created if record count exceeds threshold.
        
        Args:
            collection_name: Name of the collection.
            index_type: Type of index (HNSW or IVFFLAT).
            
        Returns:
            True if index was created, False otherwise.
        """
        is_index_existed = await self.is_index_existed(collection_name=collection_name)
        if is_index_existed:
            return False
        
        async with self.db_client() as session:
            async with session.begin():
                count_sql = sql_text(f'SELECT COUNT(*) FROM "{collection_name}"')
                result = await session.execute(count_sql)
                records_count = result.scalar_one()

                if records_count < self.index_threshold:
                    return False
                
                self.logger.info(f"START: Creating vector index for collection: {collection_name}")
                
                index_name = self.default_index_name(collection_name)
                create_idx_sql = sql_text(
                    f'CREATE INDEX "{index_name}" ON "{collection_name}" '
                    f'USING {index_type} ({PgVectorTableSchemeEnums.VECTOR.value} {self.distance_method})'
                )

                await session.execute(create_idx_sql)
                await session.commit()

                self.logger.info(f"END: Created vector index for collection: {collection_name}")
                
        return True

    async def reset_vector_index(self, collection_name: str, 
                                       index_type: str = PgVectorIndexTypeEnums.HNSW.value) -> bool:
        
        index_name = self.default_index_name(collection_name)
        async with self.db_client() as session:
            async with session.begin():
                drop_sql = sql_text(f'DROP INDEX IF EXISTS "{index_name}"')
                await session.execute(drop_sql)
                await session.commit()
        
        return await self.create_vector_index(collection_name=collection_name, index_type=index_type)

    def _format_vector(self, vector: List[float]) -> str:
        """
        Convert a Python list of floats to pgvector string format.
        
        Args:
            vector: List of float values.
            
        Returns:
            String formatted as "[v1,v2,v3,...]" for pgvector.
        """
        return "[" + ",".join(str(v) for v in vector) + "]"
    
    async def insert_one(self, collection_name: str, text: str, vector: List[float],
                         metadata: Optional[Dict[str, Any]] = None,
                         record_id: Optional[Union[str, int]] = None) -> bool:
        """
        Insert a single document with its embedding vector into a collection.
        
        Args:
            collection_name: Target collection name.
            text: The text content to store.
            vector: The embedding vector.
            metadata: Optional metadata dictionary.
            record_id: Optional chunk ID for foreign key reference.
            
        Returns:
            True if insertion successful, False otherwise.
        """
        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.error(f"Cannot insert new record to non-existent collection: {collection_name}")
            return False
        
        if record_id is None:
            self.logger.error(f"Cannot insert new record without chunk_id: {collection_name}")
            return False
        
        async with self.db_client() as session:
            async with session.begin():
                insert_sql = sql_text(
                    f'INSERT INTO "{collection_name}" '
                    f'({PgVectorTableSchemeEnums.TEXT.value}, '
                    f'{PgVectorTableSchemeEnums.VECTOR.value}, '
                    f'{PgVectorTableSchemeEnums.METADATA.value}, '
                    f'{PgVectorTableSchemeEnums.CHUNK_ID.value}) '
                    'VALUES (:text, :vector, :metadata, :chunk_id)'
                )
                
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata is not None else "{}"
                await session.execute(insert_sql, {
                    'text': text,
                    'vector': self._format_vector(vector),
                    'metadata': metadata_json,
                    'chunk_id': record_id
                })
                await session.commit()

        await self.create_vector_index(collection_name=collection_name)
        
        return True
    

    async def insert_many(self, collection_name: str, texts: List[str],
                         vectors: List[List[float]], 
                         metadata: Optional[List[Optional[Dict[str, Any]]]] = None,
                         record_ids: Optional[List[Optional[Union[str, int]]]] = None, 
                         batch_size: int = 50) -> bool:
        """
        Insert multiple documents with their embedding vectors in batches.
        
        Args:
            collection_name: Target collection name.
            texts: List of text contents to store.
            vectors: List of embedding vectors.
            metadata: Optional list of metadata dictionaries (one per document).
            record_ids: Optional list of chunk IDs for foreign key references.
            batch_size: Number of records to insert per batch.
            
        Returns:
            True if all insertions successful, False otherwise.
        """
        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.error(f"Cannot insert new records to non-existent collection: {collection_name}")
            return False
        
        # Validate input lengths
        if len(texts) != len(vectors):
            self.logger.error(f"Mismatch between texts ({len(texts)}) and vectors ({len(vectors)}) count")
            return False
        
        if record_ids is not None and len(vectors) != len(record_ids):
            self.logger.error(f"Mismatch between vectors ({len(vectors)}) and record_ids ({len(record_ids)}) count")
            return False
        
        # Initialize metadata list if not provided
        if metadata is None or len(metadata) == 0:
            metadata = [None] * len(texts)
        
        # Initialize record_ids list if not provided
        if record_ids is None:
            record_ids = [None] * len(texts)
        
        async with self.db_client() as session:
            async with session.begin():
                for i in range(0, len(texts), batch_size):
                    batch_texts = texts[i:i + batch_size]
                    batch_vectors = vectors[i:i + batch_size]
                    batch_metadata = metadata[i:i + batch_size]
                    batch_record_ids = record_ids[i:i + batch_size]

                    values = []

                    for _text, _vector, _metadata, _record_id in zip(
                        batch_texts, batch_vectors, batch_metadata, batch_record_ids
                    ):
                        metadata_json = json.dumps(_metadata, ensure_ascii=False) if _metadata is not None else "{}"
                        values.append({
                            'text': _text,
                            'vector': self._format_vector(_vector),
                            'metadata': metadata_json,
                            'chunk_id': _record_id
                        })
                    
                    batch_insert_sql = sql_text(
                        f'INSERT INTO "{collection_name}" '
                        f'({PgVectorTableSchemeEnums.TEXT.value}, '
                        f'{PgVectorTableSchemeEnums.VECTOR.value}, '
                        f'{PgVectorTableSchemeEnums.METADATA.value}, '
                        f'{PgVectorTableSchemeEnums.CHUNK_ID.value}) '
                        f'VALUES (:text, :vector, :metadata, :chunk_id)'
                    )
                    
                    await session.execute(batch_insert_sql, values)
                
                await session.commit()

        await self.create_vector_index(collection_name=collection_name)

        return True
    
    async def search_by_vector(self, collection_name: str, vector: List[float], 
                               limit: int = 5, 
                               score_threshold: Optional[float] = None) -> List[RetrievedDocument]:
        """
        Search for similar documents using vector similarity.
        
        Uses cosine similarity (1 - cosine_distance) for scoring.
        
        Args:
            collection_name: Collection to search in.
            vector: Query embedding vector.
            limit: Maximum number of results to return.
            score_threshold: Optional minimum score threshold for filtering results.
            
        Returns:
            List of RetrievedDocument objects with text and similarity score.
            Returns empty list if collection doesn't exist or on error.
        """
        is_collection_existed = await self.is_collection_existed(collection_name=collection_name)
        if not is_collection_existed:
            self.logger.error(f"Cannot search for records in a non-existent collection: {collection_name}")
            return []
        
        formatted_vector = self._format_vector(vector)
        
        async with self.db_client() as session:
            async with session.begin():
                # Build search query with optional score threshold
                # Using cosine similarity: 1 - cosine_distance
                base_query = (
                    f'SELECT {PgVectorTableSchemeEnums.TEXT.value} as text, '
                    f'1 - ({PgVectorTableSchemeEnums.VECTOR.value} <=> :vector) as score, '
                    f'{PgVectorTableSchemeEnums.METADATA.value} as metadata '
                    f'FROM "{collection_name}"'
                )
                
                if score_threshold is not None:
                    search_sql = sql_text(
                        f'{base_query} '
                        f'WHERE 1 - ({PgVectorTableSchemeEnums.VECTOR.value} <=> :vector) >= :threshold '
                        f'ORDER BY score DESC '
                        f'LIMIT :limit'
                    )
                    result = await session.execute(search_sql, {
                        "vector": formatted_vector,
                        "threshold": score_threshold,
                        "limit": limit
                    })
                else:
                    search_sql = sql_text(
                        f'{base_query} '
                        f'ORDER BY score DESC '
                        f'LIMIT :limit'
                    )
                    result = await session.execute(search_sql, {
                        "vector": formatted_vector,
                        "limit": limit
                    })

                records = result.fetchall()

                return [
                    RetrievedDocument(
                        text=record.text,
                        score=float(record.score),
                        metadata=record.metadata if record.metadata else {}
                    )
                    for record in records
                ]