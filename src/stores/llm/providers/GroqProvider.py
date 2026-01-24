from ..LLMInterface import LLMInterface
from ..LLMEnums import GroqEnums, DocumentTypeEnum
from groq import Groq
from langchain_huggingface import HuggingFaceEmbeddings
import logging
import torch   
from typing import List, Union

class GroqProvider(LLMInterface):

    def __init__(self, api_key: str,
                 default_input_max_characters: int=2000,
                 default_generation_max_output_tokens: int=1024,
                 default_generation_temperature: float=0.1):
        
        self.api_key = api_key

        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        
        self.embedding_model_id = None
        self.embedding_size = None
        self.embedding_client = None 

        self.client = Groq(
            api_key=self.api_key
        )

        self.enums = GroqEnums

        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int = None):
        self.embedding_model_id = model_id
        if embedding_size:
            self.embedding_size = embedding_size

        try:  
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            self.logger.info(f"Loading embedding model: {model_id} on device: {device}")
            
            self.embedding_client = HuggingFaceEmbeddings(
                model_name=model_id,
                model_kwargs={
                    'device': device, 
                    'trust_remote_code': True 
                },
                encode_kwargs={
                    'normalize_embeddings': False
                },
                show_progress=False 
            )
            
            self.logger.info(f"Successfully loaded embedding model: {model_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {str(e)}")
            raise

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def generate_text(self, prompt: str, chat_history: list=[], max_output_tokens: int=None,
                            temperature: float = None):
        
        if not self.client:
            self.logger.error("Groq client was not set")
            return None

        if not self.generation_model_id:
            self.logger.error("Generation model for Groq was not set")
            return None
        
        max_output_tokens = max_output_tokens if max_output_tokens else self.default_generation_max_output_tokens
        temperature = temperature if temperature else self.default_generation_temperature

        messages = chat_history.copy()
        messages.append(
            self.construct_prompt(prompt=prompt, role=GroqEnums.USER.value)
        )
    
        try:
            response = self.client.chat.completions.create(
                messages=messages,
                model=self.generation_model_id,
                temperature=temperature,
                max_completion_tokens=max_output_tokens, 
            )

            if not response or not response.choices or len(response.choices) == 0 or not response.choices[0].message:
                self.logger.error("Error: Empty response from Groq")
                return None
            
            return response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Error while generating text with Groq: {str(e)}")
            return None
    
    def embed_text(self, text: Union[str, List[str]], document_type: str = None):
        """ Embeds text(s) using the HuggingFace embedding model. 
            returns a list of embeddings.
            """
        if not self.embedding_client:
            self.logger.error("Embedding model was not initialized")
            return None
        
        if not self.embedding_model_id:
            self.logger.error("Embedding model for Groq was not set")
            return None
        
        is_single_text = isinstance(text, str)
        
        texts_to_process = [text] if is_single_text else text

        try:
            processed_texts = []
            for single_text in texts_to_process:
                processed = single_text
                
                if "e5" in self.embedding_model_id.lower():
                    if document_type == DocumentTypeEnum.QUERY.value:
                        processed = f"query: {processed}"
                    else:
                        processed = f"passage: {processed}"
                
                processed_texts.append(processed)

            if is_single_text:
                embedding = self.embedding_client.embed_query(processed_texts[0])
                if not embedding:
                    self.logger.error("Error while embedding text with HuggingFace")
                    return None
                return [embedding]
            else:
                embeddings = self.embedding_client.embed_documents(processed_texts)
                if not embeddings or len(embeddings) == 0:
                    self.logger.error("Error while embedding texts with HuggingFace")
                    return None
                return embeddings

        except Exception as e:
            self.logger.error(f"Error while embedding text with HuggingFace: {str(e)}")
            return None

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": prompt
        }
