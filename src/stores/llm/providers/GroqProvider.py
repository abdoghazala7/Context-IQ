from ..LLMInterface import LLMInterface
from ..LLMEnums import GroqEnums, DocumentTypeEnum
from groq import Groq
from langchain_huggingface import HuggingFaceEmbeddings
import logging
import torch   

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

        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int = None):
        self.embedding_model_id = model_id
        if embedding_size:
            self.embedding_size = embedding_size

        try:  
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            self.embedding_client = HuggingFaceEmbeddings(
                model_name=model_id,
                model_kwargs={
                    'device': device, 
                    'trust_remote_code': True 
                },
                encode_kwargs={
                    'normalize_embeddings': True
                },
                show_progress=False 
            )
            
        except Exception as e:
            self.logger.error(f"Failed to load embedding model: {str(e)}")

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
    
    def embed_text(self, text: str, document_type: str = None):
        """
        Embeds a single text string into a vector using the HuggingFace model.

        Args:
            text (str): The content to embed (e.g., `chunk.page_content`).
            document_type (str, optional): If `DocumentTypeEnum.QUERY`, uses `embed_query`.
                                           Otherwise, uses `embed_documents` (for chunks).

        Returns:
            list[float] | None: A single list of floats representing the vector, or None if failed.
        """

        if not self.embedding_client:
            self.logger.error("Embedding model was not initialized")
            return None
        
        if not self.embedding_model_id:
            self.logger.error("Embedding model for Groq was not set")
            return None

        try:
            processed_text = self.process_text(text)

            if "e5" in self.embedding_model_id:
                if document_type == DocumentTypeEnum.QUERY.value:
                    processed_text = f"query: {processed_text}"
                else:
                    processed_text = f"passage: {processed_text}"

            if document_type == DocumentTypeEnum.QUERY.value:
                return self.embedding_client.embed_query(processed_text)
            else:
                return self.embedding_client.embed_documents([processed_text])[0]

        except Exception as e:
            self.logger.error(f"Error while embedding text with HuggingFace: {str(e)}")
            return None

    def construct_prompt(self, prompt: str, role: str):
        return {
            "role": role,
            "content": self.process_text(prompt)
        }
