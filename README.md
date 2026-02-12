<div align="center">

# 🧠 Context-IQ

### Enterprise-Grade RAG System with Async Processing, Granular Citations & Full Observability

<br />
<img src="src/assets/architecture_diagram.png" alt="Context-IQ Architecture" width="100%" style="border-radius: 10px;">
<br />

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![PostgreSQL](https://img.shields.io/badge/pgvector-PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-Broker-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)](https://rabbitmq.com)
[![Redis](https://img.shields.io/badge/Redis-Backend-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Prometheus](https://img.shields.io/badge/Prometheus-Metrics-E6522C?style=for-the-badge&logo=prometheus&logoColor=white)](https://prometheus.io)
[![Grafana](https://img.shields.io/badge/Grafana-Dashboards-F46800?style=for-the-badge&logo=grafana&logoColor=white)](https://grafana.com)
[![Nginx](https://img.shields.io/badge/Nginx-Gateway-009639?style=for-the-badge&logo=nginx&logoColor=white)](https://nginx.org)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-DC244C?style=for-the-badge)](https://qdrant.tech)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

---

**A production-ready Retrieval-Augmented Generation (RAG) platform built as a distributed microservices architecture. It processes documents asynchronously, stores embeddings in hybrid vector databases, and answers natural-language queries with page-level and row-level source citations — all monitored through a real-time observability stack.**

[Getting Started](#-getting-started) •
[Architecture](#-system-architecture) •
[API Docs](#-api-documentation) •
[Features](#-key-features)

</div>

---

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT / USER                                  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTPS
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NGINX (Reverse Proxy)                               │
│              Rate Limiting · Security Headers · SSL Termination             │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Application (Uvicorn)                           │
│         REST API · Auth (API Key) · Request Validation · Routing           │
│                                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────────┐  │
│  │  Upload   │  │  Process &   │  │    NLP     │  │   Task Status        │  │
│  │  Routes   │  │  Push Routes │  │   Routes   │  │   Routes             │  │
│  └─────┬────┘  └──────┬───────┘  └─────┬──────┘  └──────────────────────┘  │
└────────┼───────────────┼───────────────┼───────────────────────────────────┘
         │               │               │
         │               ▼               │
         │    ┌─────────────────────┐     │
         │    │    RabbitMQ         │     │
         │    │  (Message Broker)   │     │
         │    └─────────┬──────────┘     │
         │              │                │
         │              ▼                │
         │    ┌─────────────────────┐    │
         │    │   Celery Workers    │    │
         │    │                     │    │
         │    │  ┌───────────────┐  │    │
         │    │  │ File Process  │  │    │
         │    │  │    Task       │  │    │
         │    │  └───────┬───────┘  │    │
         │    │          │          │    │
         │    │  ┌───────▼───────┐  │    │
         │    │  │ Data Indexing │  │    │
         │    │  │    Task       │  │    │
         │    │  └───────┬───────┘  │    │
         │    │          │          │    │
         │    │  ┌───────▼───────┐  │    │
         │    │  │ Maintenance   │  │    │
         │    │  │    Task       │  │    │
         │    │  └───────────────┘  │    │
         │    └─────────────────────┘    │
         │              │                │
         ▼              ▼                ▼
┌────────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                                  │
│                                                                    │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   PostgreSQL +   │  │    Qdrant    │  │       Redis          │ │
│  │    pgvector      │  │  Vector DB   │  │  (Result Backend)    │ │
│  │                  │  │              │  │                      │ │
│  │ • Projects       │  │ • Vectors    │  │ • Task Results       │ │
│  │ • Assets         │  │ • Similarity │  │ • Celery State       │ │
│  │ • Chunks         │  │   Search     │  │                      │ │
│  │ • Users          │  │              │  │                      │ │
│  │ • Vector Cols    │  │              │  │                      │ │
│  │ • Task Exec      │  │              │  │                      │ │
│  └──────────────────┘  └──────────────┘  └──────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
         │                                           │
         ▼                                           ▼
┌────────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY STACK                              │
│                                                                    │
│  ┌──────────────┐  ┌────────────┐  ┌───────────┐  ┌────────────┐ │
│  │  Prometheus   │  │  Grafana   │  │   Node    │  │  Postgres  │ │
│  │  (Scraper)    │  │ (Dashbord) │  │  Exporter │  │  Exporter  │ │
│  └──────────────┘  └────────────┘  └───────────┘  └────────────┘ │
│                                                                    │
│  ┌──────────────┐                                                  │
│  │   Flower     │  (Celery Task Monitoring UI)                     │
│  └──────────────┘                                                  │
└────────────────────────────────────────────────────────────────────┘
```

### Service Interaction Flow

| Service | Role | Why It Exists |
|---|---|---|
| **Nginx** | Reverse proxy & API gateway | Rate limiting, security headers (`X-Frame-Options`, `X-Content-Type-Options`), SSL termination, static asset serving. Decouples the public interface from the application server. |
| **FastAPI** | Core REST API | Async request handling via Uvicorn. Manages authentication, validation, and delegates heavy work to Celery. |
| **RabbitMQ** | Message broker | Durable message queue ensuring tasks survive worker restarts. Chosen over Redis-as-broker for production reliability (`task_acks_late`, `task_reject_on_worker_lost`). |
| **Celery Workers** | Async task execution | Offloads CPU/IO-intensive work (PDF parsing, embedding generation, vector indexing) from the API thread. Supports chained workflows and automatic retries. |
| **Celery Beat** | Periodic task scheduler | Runs scheduled maintenance tasks (e.g., `clean_celery_executions_table`) to prevent stale task records from accumulating. |
| **Redis** | Result backend | Stores Celery task results for status polling. Faster than DB-backed results for high-frequency status checks. |
| **PostgreSQL + pgvector** | Primary relational DB + vector storage | Stores all structured data (projects, users, assets, chunks). With the `pgvector` extension, also serves as one of two interchangeable vector database backends. |
| **Qdrant** | Dedicated vector database | Purpose-built for high-performance similarity search. Interchangeable with pgvector via the Provider Factory pattern. |
| **Prometheus** | Metrics collection | Scrapes HTTP request metrics (count, latency, status codes) from FastAPI and system metrics from exporters. |
| **Grafana** | Visualization | Dashboards for API performance, database health, system resources, and task queue depth. |
| **Node Exporter** | System metrics | Exposes host-level CPU, memory, disk, and network metrics to Prometheus. |
| **Postgres Exporter** | Database metrics | Exposes PostgreSQL-specific metrics (connections, query performance, replication lag). |
| **Flower** | Task monitoring UI | Real-time web dashboard for Celery task inspection, worker status, and queue depth. |

---

## ✨ Key Features

### 1. 🔄 Asynchronous Processing Pipeline

The system never blocks the API thread for heavy operations. Document processing follows a **chained workflow pattern**:

```
API Request → Celery Task 1 (Parse & Chunk) → Celery Task 2 (Embed & Index) → Result
```

- **File Processing** (`process_project_files`): Parses uploaded files (PDF, DOCX, TXT, MD, CSV, XLSX), splits content into semantically meaningful chunks.
- **Data Indexing** (`index_data_content`): Generates embedding vectors (via OpenAI, Cohere, or Groq), creates vector collections, performs batched insertions, and stores them in PostgreSQL.
- **Workflow Orchestration** (`process_and_push_workflow`): Chains both tasks using Celery's `chain()` primitive, ensuring indexing only begins after successful processing.

All tasks feature **automatic retries** (3 attempts, 60s backoff) and **progress tracking** via `tqdm`.

### 2. 🛡️ Idempotency & Stability

A custom `IdempotencyManager` prevents duplicate processing of identical requests — critical in distributed systems where network retries, user double-clicks, or broker redeliveries can trigger the same task multiple times.

**How it works:**
1. Each task computes a deterministic hash of its arguments (`project_id`, `file_id`, `chunk_size`, etc.).
2. Before execution, the manager checks the `celery_task_executions` table for an existing record with the same hash.
3. If a task with the same arguments is already `PENDING` or `STARTED` (within the time limit), execution is **skipped** and the existing result is returned.
4. Stale tasks (past `CELERY_TASK_TIME_LIMIT`) are eligible for re-execution.
5. A scheduled Celery Beat task periodically cleans up old execution records.

### 3. 📄 Granular Source Citations

Context-IQ doesn't just cite filenames — it provides **page-level** and **row-level** citations:

| Document Type | Citation Format | Example |
|---|---|---|
| PDF | `filename.pdf (Page: 5)` | `report.pdf (Page: 12)` |
| Excel | `filename.xlsx (Sheet: Sales \| Rows: 10-20)` | `data.xlsx (Sheet: Q4 \| Rows: 51-100)` |
| CSV | `filename.csv (Rows: 1-25)` | `metrics.csv (Rows: 101-150)` |
| TXT / MD / DOCX | `filename.ext` | `notes.txt` |

The RAG prompt template instructs the LLM to use inline citations (`[1]`, `[2]`) and generate a `Sources:` section at the end of every answer.

### 4. 📊 Full Observability Stack

Every layer of the system is monitored:

- **Application Layer**: Custom Prometheus middleware tracks `http_requests_total` and `http_request_duration_seconds` per endpoint.
- **Infrastructure Layer**: Node Exporter provides CPU, memory, disk, and network metrics.
- **Database Layer**: Postgres Exporter monitors connection pools, query performance, and replication.
- **Task Layer**: Flower provides real-time Celery worker status, task history, and queue depth.
- **Visualization**: Pre-configured Grafana dashboards aggregate all metrics into actionable views.

### 5. 🗄️ Hybrid Vector Database Architecture

The system implements a **Provider Factory Pattern** allowing runtime selection between two vector database backends:

| Feature | pgvector | Qdrant |
|---|---|---|
| **Deployment** | Embedded in PostgreSQL | Dedicated service |
| **Index Types** | HNSW, IVFFlat | HNSW |
| **Foreign Keys** | ✅ Direct FK to `chunks` table | ❌ Standalone |
| **Best For** | Transactional consistency | High-throughput search |
| **Auto-Indexing** | After threshold (configurable) | Built-in |

Switching backends requires only changing the `VECTOR_DB_BACKEND` environment variable.

### 6. 🔐 API Key Authentication

All endpoints (except health check) require an `X-API-Key` header. Users are registered via a dedicated endpoint, and each user's projects are isolated — you can only access projects you own.

### 7. 🌍 Multi-Language RAG Prompts

RAG system prompts are fully localized. The system ships with **English** and **Arabic** prompt templates, and the language is configurable per-request via the `primary_lang` parameter.

---

## ☁️ Live Demo Access

Want to see **Context-IQ** in action without setting up the full Docker infrastructure locally?

I maintain a fully configured **GitHub Codespace** environment for this project. Since this is a resource-intensive microservices architecture, the live environment is spun up on demand.

> **Interested in a test drive?**
> Please **[Contact Me via LinkedIn](https://www.linkedin.com/in/abdo-ghazala/)**, and I will provision a temporary public URL for you to explore the API, dashboards, and RAG pipeline interactively.

---

## 🛠️ Tech Stack

### Core Application
| Technology | Purpose |
|---|---|
| **Python 3.11** | Runtime |
| **FastAPI** | Async REST API framework |
| **Uvicorn** | ASGI server |
| **Pydantic v2** | Request/response validation |
| **SQLAlchemy 2.0** | Async ORM (AsyncSession) |
| **Alembic** | Database migrations |

### Processing & AI
| Technology | Purpose |
|---|---|
| **LangChain** | Document loading & text splitting |
| **OpenAI / Cohere / Groq** | Embedding generation & text generation (pluggable) |
| **PyPDF** | PDF parsing |
| **python-docx** | Word document parsing |
| **BeautifulSoup + lxml** | HTML/Markdown cleaning |
| **pandas + openpyxl** | CSV/Excel structured data processing |
| **httpx** | Async URL content fetching |

### Infrastructure
| Technology | Purpose |
|---|---|
| **Docker Compose** | Container orchestration (12+ services) |
| **Nginx** | Reverse proxy, rate limiting, security headers |
| **PostgreSQL 16 + pgvector** | Relational DB + vector storage |
| **Qdrant** | Dedicated vector similarity search |
| **RabbitMQ** | Message broker for Celery |
| **Redis** | Task result backend |
| **Celery 5.4** | Distributed task queue |
| **Celery Beat** | Periodic task scheduling |
| **Flower** | Task monitoring dashboard |

### Observability
| Technology | Purpose |
|---|---|
| **Prometheus** | Metrics collection & alerting |
| **Grafana** | Metrics visualization & dashboards |
| **Node Exporter** | System-level metrics |
| **Postgres Exporter** | Database-specific metrics |

---

## 📡 API Documentation

### Authentication

All endpoints require the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/
```

### Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/` | Health check |
| `POST` | `/api/v1/user/register` | Register a new user & get API key |
| `POST` | `/api/v1/upload/{project_id}` | Upload a file (PDF, DOCX, TXT, MD, CSV, XLSX) |
| `POST` | `/api/v1/upload/ingest-url/{project_id}` | Ingest content from a web URL |
| `POST` | `/api/v1/process/{project_id}` | Process uploaded files into chunks (async) |
| `POST` | `/api/v1/process-and-push/{project_id}` | Process + index in one workflow (async) |
| `POST` | `/api/v1/nlp/index/push/{project_id}` | Index chunks into vector DB (async) |
| `GET` | `/api/v1/nlp/index/info/{project_id}` | Get vector collection info |
| `POST` | `/api/v1/nlp/index/search/{project_id}` | Semantic search across indexed documents |
| `POST` | `/api/v1/nlp/index/answer/{project_id}` | RAG-powered Q&A with citations |
| `GET` | `/api/v1/task/status/{task_id}` | Check async task status |

### Full Workflow Example

```bash
# 1. Register a user
curl -X POST http://localhost:8000/api/v1/user/register \
  -H "Content-Type: application/json" \
  -d '{"username": "ghazala"}.'

# 2. Upload a document
curl -X POST http://localhost:8000/api/v1/upload/1 \
  -H "X-API-Key: your-api-key" \
  -F "file=@report.pdf"

# 3. Process and index in one step
curl -X POST http://localhost:8000/api/v1/process-and-push/1 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"chunk_size": 1000, "overlap_size": 200, "do_reset": 0}'

# 4. Check task status
curl http://localhost:8000/api/v1/task/status/{task_id} \
  -H "X-API-Key: your-api-key"

# 5. Ask a question with citations
curl -X POST http://localhost:8000/api/v1/nlp/index/answer/1 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "What were the Q4 revenue figures?", "limit": 10}'
```

### ⚠️ Important Limitations

> **Structured Data (CSV/Excel):** The system processes structured data through **semantic chunking**, not SQL-style aggregation. Each chunk contains rows serialized as `Header: Value` pairs. This means:
> - ✅ "What does the data say about customer X?" → Works well (semantic retrieval)
> - ❌ "What is the average of column Y?" → Will not produce accurate results (requires SQL aggregation, not RAG)

---

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose v2+
- 4GB+ available RAM (for all services)

### 1. Clone the Repository

```bash
git clone https://github.com/abdoghazala7/Context-IQ.git
cd Context-IQ
```

### 2. Configure Environment Variables

```bash
cd docker/env

# Create all required .env files from examples
cp .env.example.app .env.app
cp .env.example.postgres .env.postgres
cp .env.example.grafana .env.grafana
cp .env.example.postgres-exporter .env.postgres-exporter
cp .env.example.rabbitmq .env.rabbitmq
cp .env.example.redis .env.redis

# Configure Alembic for database migrations
cd ../minirag
cp alembic.example.ini alembic.ini
```

Edit `.env.app` with your API keys and configuration:

```env
# Required: At least one LLM provider
OPENAI_API_KEY=sk-...
# or
COHERE_API_KEY=...
# or
GROQ_API_KEY=...

# Vector DB backend: "PGVECTOR" or "QDRANT"
VECTOR_DB_BACKEND=PGVECTOR
```

### 3. Launch the Platform

```bash
cd docker

# Start databases first (recommended)
docker compose up -d pgvector qdrant rabbitmq redis
sleep 30

# Start application + monitoring
docker compose up --build -d
```

### 4. Access Services

| Service | URL |
|---|---|
| **API Documentation (Swagger)** | http://localhost:8000/docs |
| **API via Nginx** | http://localhost |
| **Flower (Task Monitor)** | http://localhost:5555 |
| **Grafana** | http://localhost:3000 |
| **Prometheus** | http://localhost:9090 |
| **Qdrant Dashboard** | http://localhost:6333/dashboard |

### 5. Verify Health

```bash
curl http://localhost:8000/api/v1/
# → {"message": "Welcome to Context IQ APP! The service is up and running ✅"}
```

---

## 📁 Project Structure

```
Context-IQ/
├── src/
│   ├── main.py                    # FastAPI app entrypoint & lifespan
│   ├── celery_app.py              # Celery configuration & factory
│   ├── flowerconfig.py            # Flower monitoring config
│   ├── controllers/
│   │   ├── BaseController.py      # Shared controller logic
│   │   ├── NLPController.py       # RAG, embedding, search logic
│   │   ├── ProcessController.py   # File parsing & chunking
│   │   ├── UploadController.py    # File validation
│   │   ├── UrlController.py       # URL content fetching
│   │   └── ProjectController.py   # Project directory management
│   ├── models/
│   │   ├── db_schemes/            # SQLAlchemy models & Alembic migrations
│   │   ├── enums/                 # Response signals, asset types
│   │   ├── ProjectModel.py        # Project CRUD operations
│   │   ├── ChunkModel.py          # Chunk CRUD & pagination
│   │   └── AssetModel.py          # Asset CRUD operations
│   ├── routes/
│   │   ├── base.py                # Health check
│   │   ├── upload.py              # File upload & processing endpoints
│   │   ├── nlp.py                 # Search, index, RAG endpoints
│   │   ├── status.py              # Task status polling
│   │   ├── user.py                # User registration
│   │   └── auth.py                # API key authentication
│   ├── stores/
│   │   ├── llm/                   # LLM provider factory (OpenAI/Cohere/Groq)
│   │   └── vectordb/              # Vector DB factory (pgvector/Qdrant)
│   ├── tasks/
│   │   ├── file_processing.py     # Async file processing task
│   │   ├── data_indexing.py       # Async vector indexing task
│   │   ├── process_workflow.py    # Chained workflow orchestration
│   │   └── maintenance.py         # Scheduled cleanup tasks
│   ├── utils/
│   │   ├── idempotency_manager.py # Duplicate task prevention
│   │   └── metrics.py             # Prometheus middleware
│   └── helpers/
│       └── config.py              # Pydantic Settings configuration
├── docker/
│   ├── docker-compose.yml         # 12+ service orchestration
│   ├── minirag/                   # App Dockerfile & entrypoint
│   ├── nginx/                     # Nginx configuration
│   ├── prometheus/                # Prometheus scrape config
│   ├── rabbitmq/                  # RabbitMQ configuration
│   └── env/                       # Environment file templates
└── README.md
```

---

## 🗄️ Database Schema

Managed via Alembic migrations. The schema automatically excludes dynamically-created pgvector collection tables from migration tracking.

```
┌────────────┐       ┌────────────┐       ┌──────────────────────┐
│  projects   │──1:N──│   assets   │       │  celery_task_        │
│             │       │            │       │  executions           │
│ project_id  │       │ asset_id   │       │                      │
│ project_uuid│       │ asset_type │       │ execution_id         │
│ created_at  │       │ asset_name │       │ task_name            │
│ updated_at  │       │ asset_size │       │ task_args_hash       │
└─────┬──────┘       │ asset_config│      │ celery_task_id       │
      │               │ asset_proj │       │ status               │
      │               └─────┬──────┘       │ task_args            │
      │                     │              │ result               │
      └──────1:N────────────┤              │ started_at           │
                            │              │ completed_at         │
                     ┌──────▼──────┐       └──────────────────────┘
                     │   chunks    │
                     │             │       ┌──────────────────────┐
                     │ chunk_id    │       │ collection_{size}_   │
                     │ chunk_text  │       │          {proj_id}   │
                     │ chunk_meta  │       │ (Dynamic pgvector)   │
                     │ chunk_order │◄──FK──│                      │
                     │ chunk_proj  │       │ id, text, vector,    │
                     │ chunk_asset │       │ metadata, chunk_id   │
                     └─────────────┘       └──────────────────────┘
```

---

## 🧪 Development

### Running Locally (without Docker)

```bash
cd src
pip install -r requirements.txt

# Start the API server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start a Celery worker (separate terminal)
celery -A celery_app worker --loglevel=info

# Start Celery Beat (separate terminal)
celery -A celery_app beat --loglevel=info

# Start Flower (separate terminal)
celery -A celery_app flower --conf=flowerconfig.py
```

### Database Migrations

```bash
cd src/models/db_schemes/minirag

# Generate a new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with precision by [Abdo Ghazala](https://github.com/abdoghazala7)**


</div>
