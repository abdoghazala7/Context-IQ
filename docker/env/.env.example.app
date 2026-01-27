APP_NAME="Context-IQ"

ALLOWED_EXTENSIONS = ["text/plain", "application/pdf"]
MAX_FILE_SIZE = 10485760  # 10MB
FILE_DEFAULT_CHUNK_SIZE = 512000 # 512KB

# ========================= DB Config =========================
POSTGRES_USERNAME="postgres"
POSTGRES_PASSWORD="password"
POSTGRES_HOST="pgvector"
POSTGRES_PORT=5432
POSTGRES_MAIN_DATABASE="minirag"

# ========================= LLM Config =========================
GENERATION_BACKEND = "GROQ"
EMBEDDING_BACKEND = "COHERE"

OPENAI_API_KEY=
OPENAI_API_URL=
COHERE_API_KEY=
GROQ_API_KEY=

GENERATION_MODEL_ID= "llama-3.3-70b-versatile"
EMBEDDING_MODEL_ID= "embed-multilingual-v3.0"
EMBEDDING_MODEL_SIZE=1024

INPUT_DEFAULT_MAX_CHARACTERS = 1200
GENERATION_DEFAULT_MAX_TOKENS = 1024
GENERATION_DEFAULT_TEMPERATURE = 0.1

# ========================= Vector DB Config =========================
VECTOR_DB_BACKEND_LITERAL = ["QDRANT", "PGVECTOR"]
VECTOR_DB_BACKEND="PGVECTOR"
VECTOR_DB_NAME="pgvector_db"
VECTOR_DB_DISTANCE_METHOD="cosine"
VECTOR_DB_PGVEC_INDEX_THRESHOLD = 1000

# ========================= Template Configs =========================
PRIMARY_LANG = "ar"
DEFAULT_LANG = "en"
