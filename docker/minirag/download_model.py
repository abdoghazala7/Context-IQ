#!/usr/bin/env python3
"""
Script to pre-download HuggingFace models during Docker build.
This ensures the model is cached and doesn't need internet at runtime.
"""
import os
import sys
import torch

def download_model(model_name):
    """Download the HuggingFace model to cache."""
    print(f"Downloading model: {model_name}")
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        
        # Detect device
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"Using device: {device}")
        
        # Download the model using HuggingFaceEmbeddings - it will be cached
        model = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={
                'device': device, 
                'trust_remote_code': True 
            },
            encode_kwargs={
                'normalize_embeddings': False
            },
            show_progress=True 
        )
        
        # Test embedding to ensure model is fully loaded
        test_embedding = model.embed_query("test")
        print(f"Model dimension: {len(test_embedding)}")
        
        print(f"✓ Successfully downloaded model: {model_name}")
        return True
    except Exception as e:
        print(f"✗ Failed to download model {model_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Default model from env or hardcoded
    model_name = os.getenv("EMBEDDING_MODEL_ID", "intfloat/multilingual-e5-base")
    
    success = download_model(model_name)
    sys.exit(0 if success else 1)
