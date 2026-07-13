<div align="center">

# 🧠 Context-IQ

### Enterprise-Grade Multi-RAG Platform · Multimodal PDF Pipeline · Polymorphic Vision Providers · Async Processing · Granular Citations · Full Observability

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
[![Gemini](https://img.shields.io/badge/Gemini-Vision-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Mistral](https://img.shields.io/badge/Mistral-OCR-FF7000?style=for-the-badge)](https://mistral.ai)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_4_Scout-F55036?style=for-the-badge)](https://groq.com)
[![PyMuPDF](https://img.shields.io/badge/PyMuPDF-Multimodal-1B72BE?style=for-the-badge)](https://pymupdf.readthedocs.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

---

**A production-ready _Multi-RAG_ platform built as a distributed microservices architecture. Context-IQ ingests corporate documents through a purpose-built _Multimodal PDF Pipeline_ — extracting text, tables, embedded images, and full page-scans through a _polymorphic vision provider layer_ (Gemini / Mistral / Groq) — then processes them asynchronously, stores embeddings in hybrid vector databases, and answers natural-language queries with page-level, row-level, and figure-level source citations — all monitored through a real-time observability stack.**

[Getting Started](#-getting-started) •
[Architecture](#-system-architecture) •
[Multimodal Pipeline](#-the-multimodal-pdf-pipeline) •
[Vision Providers](#-polymorphic-vision-provider-architecture) •
[API Docs](#-api-documentation) •
[Features](#-key-features)

</div>

---

## 🎯 The Engineering Story

Context-IQ started life as a conventional, text-only RAG. It worked — until it hit real corporate documents.

> **The problem with "just chunk everything":**
> Naive RAG pipelines pass every PDF through a plain text loader and a character-based splitter. The result is a system that:
> * **Silently drops every image, chart, diagram and scanned page** — half the information in a modern report is thrown away before retrieval even begins.
> * **Shreds tables mid-row.** A character-agnostic splitter has no idea what a `Rows: 51-70` header means, so it happily severs table batches from their column signatures, leaving header-less continuation chunks that the LLM can never reconstruct.
> * **Fragments paragraphs into micro-chunks** whenever PyMuPDF emits multiple text blocks for the same paragraph, producing one-line "ghost" chunks with broken sentence boundaries and orphaned section headings.
> * **Pollutes citations with off-by-one page numbers** because the extractor uses 0-indexed pages internally while the LLM cites 1-indexed pages to the user.

Context-IQ was re-engineered around a fundamentally different premise: **structure is content**. Tables, images, page-scans, and reading order carry meaning that must survive the entire pipeline — from parsing all the way to the final `[3]` citation the user sees. What follows is that re-engineered platform.

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
│         REST API · Auth (API Key) · Request Validation · Routing            │
│                                                                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────────────┐   │
│  │  Upload  │  │  Process &   │  │    NLP     │  │   Task Status        │   │
│  │  Routes  │  │  Push Routes │  │   Routes   │  │   Routes             │   │
│  └─────┬────┘  └──────┬───────┘  └─────┬──────┘  └──────────────────────┘   │
└────────┼──────────────┼────────────────┼────────────────────────────────────┘
         │              │                │
         │              ▼                │
         │    ┌─────────────────────┐    │
         │    │    RabbitMQ         │    │
         │    │  (Message Broker)   │    │
         │    └─────────┬───────────┘    │
         │              │                │
         │              ▼                │
         │    ┌─────────────────────────────────────────┐
         │    │           Celery Workers                │
         │    │                                         │
         │    │  ┌───────────────────────────────────┐  │
         │    │  │  File Processing Task             │  │
         │    │  │  ┌─────────────────────────────┐  │  │
         │    │  │  │ Multimodal PDF Pipeline     │  │  │
         │    │  │  │  · Text / Table / Image     │  │  │
         │    │  │  │  · XY-cut Reading Order     │  │  │
         │    │  │  │  · Vision Enrichment ──────┼──┼──┼──► Polymorphic Vision Layer
         │    │  │  └─────────────────────────────┘  │  │   ┌─────────┬─────────┬─────────┐
         │    │  │  Content-Type-Aware Chunk Router  │  │   │ Gemini  │ Mistral │  Groq   │
         │    │  └───────────────┬───────────────────┘  │   │ 3.5-Flash│OCR-Latest│Llama-4 │
         │    │                  │                      │   └─────────┴─────────┴─────────┘
         │    │  ┌───────────────▼───────────────────┐  │
         │    │  │  Data Indexing Task               │  │
         │    │  └───────────────┬───────────────────┘  │
         │    │                  │                      │
         │    │  ┌───────────────▼───────────────────┐  │
         │    │  │  Maintenance Task (Beat)          │  │
         │    │  └───────────────────────────────────┘  │
         │    └────────────────┬────────────────────────┘
         │                     │
         ▼                     ▼                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                │
│                                                                    │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   PostgreSQL +   │  │    Qdrant    │  │       Redis          │  │
│  │    pgvector      │  │  Vector DB   │  │  (Result Backend)    │  │
│  │                  │  │              │  │                      │  │
│  │ • Users          │  │ • Vectors    │  │ • Task Results       │  │
│  │ • Projects       │  │ • Similarity │  │ • Celery State       │  │
│  │ • Assets         │  │   Search     │  │                      │  │
│  │ • Chunks         │  │              │  │                      │  │
│  │ • Vector Cols    │  │              │  │                      │  │
│  │ • Task Exec      │  │              │  │                      │  │
│  └──────────────────┘  └──────────────┘  └──────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
         │                                           │
         ▼                                           ▼
┌────────────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY STACK                             │
│                                                                    │
│  ┌──────────────┐  ┌────────────┐  ┌───────────┐  ┌────────────┐   │
│  │  Prometheus  │  │  Grafana   │  │   Node    │  │  Postgres  │   │
│  │  (Scraper)   │  │ (Dashbord) │  │  Exporter │  │  Exporter  │   │
│  └──────────────┘  └────────────┘  └───────────┘  └────────────┘   │
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
| **Celery Workers** | Async task execution | Offloads CPU/IO-intensive work (multimodal PDF parsing, vision-provider calls, embedding generation, vector indexing) from the API thread. Supports chained workflows and automatic retries. |
| **Celery Beat** | Periodic task scheduler | Runs scheduled maintenance tasks (e.g., `clean_celery_executions_table`) to prevent stale task records from accumulating. |
| **Redis** | Result backend | Stores Celery task results for status polling. Faster than DB-backed results for high-frequency status checks. |
| **Vision Layer** | Polymorphic multimodal provider | Decoupled, factory-created client (`Gemini` / `Mistral` / `Groq`) that turns embedded images and scanned pages into retrieval-ready text — with per-image retry/backoff and a `NullVisionProvider` fallback so ingestion never fails on a missing SDK. |
| **PostgreSQL + pgvector** | Primary relational DB + vector storage | Stores all structured data (users, projects, assets, chunks). With the `pgvector` extension, also serves as one of two interchangeable vector database backends. |
| **Qdrant** | Dedicated vector database | Purpose-built for high-performance similarity search. Interchangeable with pgvector via the Provider Factory pattern. |
| **Prometheus** | Metrics collection | Scrapes HTTP request metrics (count, latency, status codes) from FastAPI and system metrics from exporters. |
| **Grafana** | Visualization | Dashboards for API performance, database health, system resources, and task queue depth. |
| **Node Exporter** | System metrics | Exposes host-level CPU, memory, disk, and network metrics to Prometheus. |
| **Postgres Exporter** | Database metrics | Exposes PostgreSQL-specific metrics (connections, query performance, replication lag). |
| **Flower** | Task monitoring UI | Real-time web dashboard for Celery task inspection, worker status, and queue depth. |

---

## 🧬 The Multimodal PDF Pipeline

The centerpiece of the Context-IQ platform is a purpose-built, structure-aware PDF pipeline that replaces LangChain's naive `PyPDFLoader → RecursiveCharacterTextSplitter` chain with a per-page, per-element ingestion flow. It runs directly on **PyMuPDF (`fitz`)** and treats every PDF as what it really is: a mixed medium of text blocks, tables, embedded images, and — when a page is a pure scan — a rasterized bitmap that needs OCR.

```
                       ┌──────────────────────────────────────┐
                       │           PDF Document Input         │
                       └──────────────────┬───────────────────┘
                                          │
                        ┌─────────────────▼──────────────────┐
                        │  Per-page walk (PyMuPDF `fitz`)    │
                        └─────────────────┬──────────────────┘
                                          │
   ┌──────────────────────────┬───────────┴───────────┬──────────────────────────┐
   ▼                          ▼                       ▼                          ▼
┌─────────┐            ┌────────────┐          ┌────────────┐             ┌─────────────┐
│ Tables  │            │ Text Blocks│          │  Images    │             │ Scanned Page│
│         │            │ (IoA-filter│          │  (area-    │             │ (heuristic  │
│ · find_ │            │  vs tables)│          │  filtered) │             │  detection) │
│  tables │            │            │          │            │             │             │
│ · char- │            │ · Unicode  │          │ · Pillow   │             │ · Full-page │
│  budget │            │   NFKC     │          │   resize + │             │  raster @   │
│  batches│            │ · Soft-wrap│          │   JPEG re- │             │  150 DPI    │
│ · column│            │   collapse │          │   quantize │             │ · describe_ │
│  carry- │            │ · Sentence-│          │ · Vision   │             │  page() OCR │
│  over   │            │  aware join│          │  describe_ │             │             │
│         │            │            │          │  image()   │             │             │
└────┬────┘            └──────┬─────┘          └──────┬─────┘             └──────┬──────┘
     │                        │                       │                          │
     └────────────────────────┴───────────┬───────────┴──────────────────────────┘
                                          │
                        ┌─────────────────▼─────────────────┐
                        │   Recursive XY-Cut Reading Order  │
                        │   (RTL-aware for Arabic layouts)  │
                        └─────────────────┬─────────────────┘
                                          │
                        ┌─────────────────▼─────────────────┐
                        │  Content-Type-Aware Chunk Router  │
                        │  · Text → merged + splitter       │
                        │  · Atomic (table/image/scan)      │
                        │    → passthrough or header-safe   │
                        │      surgical split               │
                        └─────────────────┬─────────────────┘
                                          │
                                          ▼
                              ┌──────────────────────┐
                              │ Citation-Ready Chunks│
                              │  page · bbox · order │
                              │  content_type · rows │
                              └──────────────────────┘
```

### The Six Engineering Pillars

#### 1. Structure-First Extraction
Every PDF page is decomposed into typed elements — `text`, `table`, `image`, `page_scan` — each carrying its own bounding box, page number, and content-type tag. Text blocks that visually overlap a detected table region (measured by **intersection-over-area** ≥ `0.60`) are dropped from the text stream so table cells are never double-counted. Nothing about the pipeline is "just extract text" — it is a first-class layout parser.

#### 2. Character-Budgeted Table Serialization
Legacy systems batch tables by row count (e.g. "50 rows per document"). The problem: a single wide table can blow past the downstream chunk budget in three rows, at which point the RecursiveCharacterTextSplitter chops the batch in half — and only the **first** sub-chunk carries the `[PDF Table | Page: 4 | Rows: 51-70 | Columns: …]` preamble. The follower is a header-less orphan.

Context-IQ batches rows against a **soft character budget** (`_TABLE_BATCH_CHAR_BUDGET = 650`) *including* header/separator overhead, with a hard row cap of `25`. Each batch is guaranteed to fit inside a single downstream chunk, so **every batch keeps its own preamble**, and the `Rows: X-Y` label never lies about what's inside.

#### 3. Multi-Page Column Inheritance Fallback
Word- and LibreOffice-generated PDFs frequently split a long table across pages, and PyMuPDF's `find_tables()` returns the continuation with either a degenerate `col_1, col_2, …` header or the first body row mis-promoted into the header slot.

The controller maintains a **per-file running layout state cache** (`self._last_pdf_columns`) keyed by table index. When the first table on a continuation page arrives with either (a) any generic `col_N` column or (b) plausibly-body-length pseudo-headers, the cache's real column signature is **surgically re-applied** and the pseudo-header row is pushed back into the data. This transforms unstructured multi-page layout noise back into a coherent structured stream — automatically.

#### 4. Content-Type-Aware Chunking Router
The chunker no longer treats every Document identically. `get_file_chunks()` performs **format-based routing**:

| Element Type | Routing Strategy |
|---|---|
| Non-PDF (`csv`, `xlsx`, `md`, `docx`, `txt`) | Standard `RecursiveCharacterTextSplitter`. |
| PDF `text` | Grouped **per page**, joined with `\n\n` paragraph separators, then splitter merges small blocks up to `chunk_size` on paragraph/sentence boundaries. |
| PDF `table` / `image` / `page_scan` | **Atomic passthrough** — kept whole so the citation header on the first line is never severed from its body. |

The router flushes buffered text **before** each atomic element and **again after**, preserving reading order across mixed pages.

#### 5. Fail-Safe Header Injection
For the pathological case where a single atomic body legitimately exceeds `2 × chunk_size` (rare — usually only for OCR results on dense scanned pages), the pipeline degrades gracefully via a **header-preserving surgical splitter**:

1. Isolate the leading `[PDF Table | ...]` / `[Image Description | ...]` / `[Page Scan | ...]` bracket header.
2. Compute an `inner_size = chunk_size - len(header) - 2` to reserve headroom.
3. Split the body only, then **re-prepend the header line** to every sub-chunk, marking continuations with `metadata["continuation"] = True`.

Result: even in the fallback case, **every** chunk retains a full citation identifier — so the UI's `[3] report.pdf (Page: 12)` link always works, no matter how the underlying atomic element had to be cut.

#### 6. Normalized 1-Based Citation Storage
The parser and the RAG layer now speak exactly the same page indices. Internally PyMuPDF uses 0-indexed pages, but metadata written to Postgres, metadata embedded in the table/image/scan header lines, and the labels emitted by `NLPController._build_source_label()` all use **1-based** page numbers. This eliminates the off-by-one pollution that used to make citations point one page before the actual source.

### Soft-Wrap Collapse & Sentence-Aware Joining
`_clean_text()` runs Unicode NFKC normalization, dehyphenates words split across line breaks (`"exam-\nple"` → `"example"`), and then collapses **soft** intra-paragraph line wraps produced by PyMuPDF while preserving genuine paragraph boundaries. A line break is kept only when:

* the next line is blank (real paragraph break),
* the next line begins with a **structural lead** (`Chapter N`, `Figure N`, `Table N`, `Step N`, numbered lists `1.2.3.`, bullets `•/-/·`),
* **or** the previous line ends with terminal punctuation *and* the next line starts with a capital letter or digit (sentence boundary).

The regex `_PARAGRAPH_LEAD_PATTERN` is a compiled multi-alternative that recognises numbered outlines, headings, and common captions.

### Recursive XY-Cut Reading Order
Elements are ordered with a proper **recursive XY-cut** algorithm: alternate horizontal band cuts and vertical column cuts based on whitespace gaps sized to the page (`band_gap ≈ 1.5 %` of page height, `gutter ≈ 2 %` of page width). Full-width elements — anything wider than `_FULL_WIDTH_RATIO = 0.65` of the page — act as **band separators**, correctly reading a wide heading or full-width table *before* the two-column body beneath it. When `PRIMARY_LANG` starts with `ar`, column ordering is inverted for **RTL Arabic reading order**.

### Scanned-Page Detection Heuristic
A page is classified as a scanned page — and routed to `describe_page()` for full-page OCR — only when **all** of the following hold:

* Meaningful character count < `_SCANNED_TEXT_CHAR_THRESHOLD = 50`,
* No detected tables,
* At least one embedded image covers ≥ `_SCANNED_IMAGE_COVERAGE = 0.50` of the page area.

The page is then rasterized once at `_PAGE_SCAN_DPI = 150`, run through the Pillow optimizer, and OCR'd atomically. Successful OCR produces a single `page_scan` element that owns the entire page — no per-image work is duplicated.

### Deterministic Image Optimization
Every image sent to a vision provider is first run through a **deterministic Pillow pipeline**:

1. Convert to RGB.
2. Resize longest edge down to `VISION_IMAGE_MAX_WIDTH`.
3. Progressive JPEG quality reduction (`q ∈ {configured, 70, 55, 40, 30}`) until the payload is ≤ `VISION_MAX_IMAGE_BYTES`.
4. If still too large, halve dimensions once more.

This makes vision calls **cost-predictable** and immune to the "one 20 MB screenshot broke the budget" failure mode.

---

## 🎨 Polymorphic Vision Provider Architecture

Vision providers are treated as **hot-swappable, decoupled dependencies** via a strict abstract interface and a factory. Switching from Gemini to Mistral to Groq is a single environment-variable change — no code paths are hardcoded to any SDK.

```
                    ┌──────────────────────────────────┐
                    │        VisionInterface (ABC)     │
                    │                                  │
                    │  is_configured()                 │
                    │  set_vision_model(model_id)      │
                    │  describe_image(bytes, mime, …)  │
                    │  describe_page(bytes, mime, …)   │
                    └──────────────────┬───────────────┘
                                       │
             ┌─────────────────────────┼──────────────────────────┐
             │                         │                          │
   ┌─────────▼─────────┐    ┌──────────▼────────┐    ┌────────────▼──────────┐
   │  BaseVisionProvider│   │ NullVisionProvider │   │   VisionProviderFactory│
   │  (retry/backoff)   │   │  (safe no-op)      │   │   .create()            │
   └─────────┬──────────┘   └────────────────────┘   └────────────┬───────────┘
             │                                                    │
   ┌─────────┼───────────────────┬──────────────────────┐         │
   ▼         ▼                   ▼                      ▼         │
┌───────┐ ┌──────────┐    ┌────────────┐         ┌────────────┐   │
│Gemini │ │ Mistral  │    │    Groq    │         │   …future  │◄──┘
│Provider│ │Provider  │    │  Provider  │         │  providers │
│       │ │          │    │(Llama-4    │         │            │
│gemini-│ │mistral-  │    │ Scout / Qwen)         │            │
│3.5-   │ │ocr-latest│    │            │         │            │
│flash  │ │          │    │            │         │            │
└───────┘ └──────────┘    └────────────┘         └────────────┘
```

### The `VisionInterface` Contract

Every provider — including the no-op `NullVisionProvider` — implements the same four methods and returns the same normalized dataclass:

```python
@dataclass(slots=True)
class VisionResult:
    text: str                    # extracted / described text
    provider: str                # "GEMINI" | "MISTRAL" | "GROQ_LLAMA_SCOUT" | ...
    model: str | None            # concrete model id used
    metadata: dict[str, Any]     # free-form: usage, timing, retries
```

The contract mandates that **any misconfiguration, SDK error, rate limit or oversized payload returns `None`** — never an exception. This is what allows the multimodal pipeline to treat vision as **strictly optional**: text/table processing runs identically whether vision is Gemini-backed, Groq-backed, or entirely absent.

### The Factory: Never Raises, Never Returns None

`VisionProviderFactory.create()` is the single entry point for provider construction, and it is deliberately **paranoid**:

| Failure Mode | Factory Behaviour |
|---|---|
| `VISION_PROVIDER` unset | → `NullVisionProvider("VISION_PROVIDER not set")` |
| Invalid selector value | → `NullVisionProvider("invalid VISION_PROVIDER …")` |
| API key missing for chosen provider | → `NullVisionProvider("GEMINI_API_KEY missing")` etc. |
| Optional SDK not installed (`ImportError`) | → `NullVisionProvider("SDK import failed for …")` |
| Provider constructor throws | → `NullVisionProvider("construction failed for …")` |
| Constructed but `is_configured()` returns False | → `NullVisionProvider(f"{provider} not configured")` |

Provider modules are imported **lazily inside `create()`** so that a deployment that doesn't use Gemini never has to install `google-genai`, and a container missing `mistralai` won't crash worker startup. This is a critical operational property for a distributed system.

### The Retry Engine

All concrete providers inherit `BaseVisionProvider`, which supplies:

* A **retry classifier** for HTTP 408/409/429/500/502/503/504 and connection errors.
* **Exponential backoff with full jitter** (`base × 2^attempt`, capped at 30 s), honouring `Retry-After` headers when the API supplies them.
* A **`RetryableError` → transient / any other exception → fatal-for-this-item** dispatch, so **rate limits never poison an entire Celery task** — the offending image is skipped, and processing continues.
* A `max_image_bytes` guardrail that rejects oversized payloads before they hit the wire.

### Supported Providers

| Provider Selector | Default Model | Best For |
|---|---|---|
| `GEMINI` | `gemini-3.5-flash` | Rich chart/diagram understanding, multilingual OCR, generous free-tier throughput. Uses the modern `google-genai` SDK with inline `types.Part.from_bytes` payloads. |
| `MISTRAL` | `mistral-ocr-latest` | Purpose-built OCR — highest fidelity on dense scanned documents (invoices, receipts, forms). |
| `GROQ_LLAMA_SCOUT` | `meta-llama/llama-4-scout-17b-16e-instruct` | Low-latency inference for high-volume figure-caption workloads. |
| `GROQ_QWEN` | `qwen/qwen3.6-27b` | Alternative Groq-hosted multilingual vision model for A/B comparisons. |

Switching between them is a **one-line change**:

```env
# Any provider — no code changes required
VISION_PROVIDER=GEMINI              # or MISTRAL / GROQ_LLAMA_SCOUT / GROQ_QWEN
VISION_MODEL_ID=                    # optional override; blank = provider default
GEMINI_API_KEY=...
# MISTRAL_API_KEY=...
# GROQ_API_KEY=...
```

### Operational Tuning Knobs

Every knob that affects vision cost or latency is exposed as a plain env var and read defensively by the factory:

| Setting | Purpose |
|---|---|
| `VISION_TIMEOUT_SECONDS` | Per-request timeout (default: 60 s). |
| `VISION_MAX_RETRIES` | Retries per image (default: 3). |
| `VISION_RETRY_BASE_SECONDS` | Backoff base (default: 1.0 s). |
| `VISION_MAX_IMAGE_BYTES` | Hard payload cap (default: 4 MB). |
| `VISION_IMAGE_MAX_WIDTH` | Pillow resize target (longest edge). |
| `VISION_IMAGE_JPEG_QUALITY` | Starting JPEG quality for re-compression. |
| `VISION_MIN_IMAGE_AREA_RATIO` | Ignore decorative micro-icons below this page-area fraction. |
| `VISION_MAX_IMAGES_PER_PAGE` | Vision call budget per page. |

---

## ✨ Key Features

### 1. 🧬 Multimodal Multi-RAG Pipeline

Text, tables, embedded figures, and scanned pages are all first-class retrieval sources — each with distinct citation shapes, distinct chunk-routing rules, and independent failure modes. See the [Multimodal Pipeline](#-the-multimodal-pdf-pipeline) and [Vision Providers](#-polymorphic-vision-provider-architecture) sections for the deep dive.

### 2. 🔄 Asynchronous Processing Pipeline

The system never blocks the API thread for heavy operations. Document processing follows a **chained workflow pattern**:

```
API Request → Celery Task 1 (Parse & Chunk) → Celery Task 2 (Embed & Index) → Result
```

- **File Processing** (`process_project_files`): Runs the multimodal pipeline, coordinates vision enrichment, and produces citation-ready chunks.
- **Data Indexing** (`index_data_content`): Generates embedding vectors (via OpenAI, Cohere, or Groq), creates vector collections, performs batched insertions, and stores them in PostgreSQL.
- **Workflow Orchestration** (`process_and_push_workflow`): Chains both tasks using Celery's `chain()` primitive, ensuring indexing only begins after successful processing.

All tasks feature **automatic retries** (3 attempts, 60 s backoff) and **progress tracking** via `tqdm`.

### 3. 🛡️ Idempotency & Stability

A custom `IdempotencyManager` prevents duplicate processing of identical requests — critical in distributed systems where network retries, user double-clicks, or broker redeliveries can trigger the same task multiple times.

**How it works:**
1. Each task computes a deterministic hash of its arguments (`project_id`, `file_id`, `chunk_size`, etc.).
2. Before execution, the manager checks the `celery_task_executions` table for an existing record with the same hash.
3. If a task with the same arguments is already `PENDING` or `STARTED` (within the time limit), execution is **skipped** and the existing result is returned.
4. Stale tasks (past `CELERY_TASK_TIME_LIMIT`) are eligible for re-execution.
5. A scheduled Celery Beat task periodically cleans up old execution records.

### 4. 📄 Granular Multimodal Source Citations

Context-IQ doesn't just cite filenames — it provides **page-level**, **row-level**, **figure-level**, and **scan-level** citations, produced in lockstep with the multimodal pipeline's normalized 1-based indices:

| Source Type | Citation Format | Example |
|---|---|---|
| PDF Text | `filename.pdf (Page: N)` | `report.pdf (Page: 12)` |
| PDF Table | `filename.pdf (Page: N \| Table: T \| Rows: X-Y)` | `report.pdf (Page: 4 \| Table: 1 \| Rows: 51-70)` |
| PDF Image | `filename.pdf (Page: N \| Image: I)` | `report.pdf (Page: 8 \| Image: 2)` |
| PDF Page Scan | `filename.pdf (Page: N \| Scanned)` | `invoice.pdf (Page: 1 \| Scanned)` |
| Excel | `filename.xlsx (Sheet: Sales \| Rows: 10-20)` | `data.xlsx (Sheet: Q4 \| Rows: 51-100)` |
| CSV | `filename.csv (Rows: 1-25)` | `metrics.csv (Rows: 101-150)` |
| TXT / MD / DOCX | `filename.ext` | `notes.txt` |

The RAG prompt template instructs the LLM to use inline citations (`[1]`, `[2]`) and generate a `Sources:` section at the end of every answer.

### 5. 📊 Full Observability Stack

Every layer of the system is monitored:

- **Application Layer**: Custom Prometheus middleware tracks `http_requests_total` and `http_request_duration_seconds` per endpoint.
- **Infrastructure Layer**: Node Exporter provides CPU, memory, disk, and network metrics.
- **Database Layer**: Postgres Exporter monitors connection pools, query performance, and replication.
- **Task Layer**: Flower provides real-time Celery worker status, task history, and queue depth.
- **Visualization**: Pre-configured Grafana dashboards aggregate all metrics into actionable views.

### 6. 🗄️ Hybrid Vector Database Architecture

The system implements a **Provider Factory Pattern** allowing runtime selection between two vector database backends:

| Feature | pgvector | Qdrant |
|---|---|---|
| **Deployment** | Embedded in PostgreSQL | Dedicated service |
| **Index Types** | HNSW, IVFFlat | HNSW |
| **Foreign Keys** | ✅ Direct FK to `chunks` table | ❌ Standalone |
| **Best For** | Transactional consistency | High-throughput search |
| **Auto-Indexing** | After threshold (configurable) | Built-in |

Switching backends requires only changing the `VECTOR_DB_BACKEND` environment variable.

### 7. 🔐 API Key Authentication & Multi-Tenant Isolation

All endpoints (except health check) require an `X-API-Key` header. Users are registered via a dedicated endpoint, each user is issued a `uuid4` API key, and every project is bound to its owner via a `User (1) — (N) Project` relationship enforced in SQLAlchemy — you can only access projects you own.

### 8. 🌍 Multi-Language RAG Prompts

RAG system prompts are fully localized. The system ships with **English** and **Arabic** prompt templates, and the language is configurable per-request via the `primary_lang` parameter. The multimodal reading-order algorithm is **RTL-aware** and reverses column order when `PRIMARY_LANG` starts with `ar`.

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
| **PyMuPDF (`fitz`)** | Low-level PDF layout, table extraction, image extraction, page rasterization |
| **Pillow** | Deterministic image resize / re-quantization pipeline |
| **OpenAI / Cohere / Groq** | Embedding generation & text generation (pluggable) |
| **Google Gemini (`google-genai`)** | Vision provider — chart/diagram description & OCR |
| **Mistral (`mistralai`)** | Vision provider — dedicated OCR (`mistral-ocr-latest`) |
| **Groq (Llama-4 Scout / Qwen)** | Vision provider — low-latency figure captioning |
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
  -d '{"username": "ghazala"}'

# 2. Upload a document (PDF with images and tables works out of the box)
curl -X POST http://localhost:8000/api/v1/upload/1 \
  -H "X-API-Key: your-api-key" \
  -F "file=@report.pdf"

# 3. Process and index in one step (multimodal pipeline runs automatically)
curl -X POST http://localhost:8000/api/v1/process-and-push/1 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"chunk_size": 1000, "overlap_size": 200, "do_reset": 0}'

# 4. Check task status
curl http://localhost:8000/api/v1/task/status/{task_id} \
  -H "X-API-Key: your-api-key"

# 5. Ask a question with citations — answers may cite text, tables, or figures
curl -X POST http://localhost:8000/api/v1/nlp/index/answer/1 \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "What were the Q4 revenue figures and how do they compare to the chart on page 8?", "limit": 10}'
```

### ⚠️ Important Limitations

> **Structured Data (CSV/Excel):** The system processes structured data through **semantic chunking**, not SQL-style aggregation. Each chunk contains rows serialized as `Header: Value` pairs. This means:
> - ✅ "What does the data say about customer X?" → Works well (semantic retrieval)
> - ❌ "What is the average of column Y?" → Will not produce accurate results (requires SQL aggregation, not RAG)

> **Vision Enrichment:** Image and page-scan enrichment is **optional and provider-gated**. When `VISION_PROVIDER` is unset or the configured SDK/API key is unavailable, the factory silently falls back to `NullVisionProvider` and the pipeline processes text + tables normally. Image/page-scan chunks are simply omitted from the index.

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
# ─── Required: At least one LLM provider for text generation / embeddings ───
OPENAI_API_KEY=sk-...
# or
COHERE_API_KEY=...
# or
GROQ_API_KEY=...

# ─── Vector DB backend: "PGVECTOR" or "QDRANT" ───
VECTOR_DB_BACKEND=PGVECTOR

# ─── Optional: Vision provider for the multimodal PDF pipeline ───
# Leave blank to disable vision (text + tables still work fully).
VISION_PROVIDER=GEMINI              # GEMINI | MISTRAL | GROQ_LLAMA_SCOUT | GROQ_QWEN
VISION_MODEL_ID=                    # optional override; blank = provider default
GEMINI_API_KEY=...                  # required if VISION_PROVIDER=GEMINI
# MISTRAL_API_KEY=...               # required if VISION_PROVIDER=MISTRAL
# GROQ_API_KEY already set above    # required if VISION_PROVIDER=GROQ_*

# ─── Optional: Vision cost / latency tuning ───
VISION_TIMEOUT_SECONDS=60
VISION_MAX_RETRIES=3
VISION_MAX_IMAGE_BYTES=4000000
VISION_IMAGE_MAX_WIDTH=1600
VISION_IMAGE_JPEG_QUALITY=85
VISION_MIN_IMAGE_AREA_RATIO=0.02
VISION_MAX_IMAGES_PER_PAGE=6
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
│   │   ├── NLPController.py       # RAG, embedding, search, citation labelling
│   │   ├── ProcessController.py   # Multimodal PDF pipeline & content-type-aware chunk router
│   │   ├── UploadController.py    # File validation
│   │   ├── UrlController.py       # URL content fetching
│   │   └── ProjectController.py   # Project directory management
│   ├── models/
│   │   ├── db_schemes/            # SQLAlchemy models & Alembic migrations
│   │   ├── enums/                 # Response signals, asset types, processing types
│   │   ├── UserModel.py           # User CRUD & API key issuance
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
│   │   ├── llm/                   # LLM provider factory (OpenAI / Cohere / Groq)
│   │   ├── vectordb/              # Vector DB factory (pgvector / Qdrant)
│   │   └── vision/                # Polymorphic vision provider layer
│   │       ├── VisionInterface.py     # ABC + VisionResult + NullVisionProvider
│   │       ├── VisionEnums.py         # Provider selectors + default model ids
│   │       ├── VisionProviderFactory.py  # Safe, lazy factory
│   │       └── providers/
│   │           ├── _base.py           # Retry / backoff / Retry-After parsing
│   │           ├── GeminiProvider.py  # google-genai (gemini-3.5-flash)
│   │           ├── MistralProvider.py # mistralai (mistral-ocr-latest)
│   │           └── GroqProvider.py    # groq (Llama-4 Scout / Qwen)
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

Every project is owned by a `User` (1:N), and every project owns its assets (1:N), which in turn own their chunks (1:N). API-key authentication resolves the caller to a `User` row, and all project queries are scoped to that owner — providing multi-tenant isolation at the ORM layer.

```
┌────────────┐
│   users    │
│            │
│ user_id    │
│ user_api_  │
│   key (uuid)│
│ user_name  │
│ is_active  │
│ created_at │
│ updated_at │
└─────┬──────┘
      │ 1:N (owner → projects)
      ▼
┌────────────┐       ┌────────────┐       ┌──────────────────────┐
│  projects  │──1:N──│   assets   │       │  celery_task_        │
│            │       │            │       │  executions          │
│ project_id │       │ asset_id   │       │                      │
│ project_uuid│      │ asset_type │       │ execution_id         │
│ owner_id ──┼──FK──►│ asset_name │       │ task_name            │
│ created_at │       │ asset_size │       │ task_args_hash       │
│ updated_at │       │ asset_config│      │ celery_task_id       │
└─────┬──────┘       │ asset_proj │       │ status               │
      │              └─────┬──────┘       │ task_args            │
      │                    │              │ result               │
      └──────1:N───────────┤              │ started_at           │
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

### Table Overview

| Table | Purpose |
|---|---|
| **`users`** | Identity & authentication. Each row owns a unique `user_api_key` (`uuid4`, indexed) used for API-key auth. `is_active` supports soft-disable. `projects = relationship("Project", back_populates="owner")` yields the 1:N ownership graph. |
| **`projects`** | Logical isolation boundary. `owner_id` FKs to `users.user_id` so every project is bound to the user who created it. |
| **`assets`** | Uploaded files metadata (name, size, type, per-asset config). One asset per uploaded file. |
| **`chunks`** | Post-multimodal-pipeline output. `chunk_meta` stores content-type, page, bbox, table index, row range, image index, vision provider/model — the full citation payload. |
| **`celery_task_executions`** | Idempotency ledger. Keyed by `task_args_hash` so identical requests are deduplicated across retries and broker redeliveries. |
| **`collection_{size}_{proj_id}`** | Dynamically-created pgvector table, one per (embedding-size, project) combination. Contains vectors + FK back to `chunks`. Excluded from Alembic autogenerate. |

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
