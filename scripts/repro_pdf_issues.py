"""
Reproduce (and later verify fixes for) the reported PDF pipeline issues
against the real 31-page production PDF.

Runs the parser end-to-end (without vision, since no API key is configured
in this local box), then the chunker, and prints a compact structured
report keyed to Issues 1-6 from the investigation.

This script imports ``processcontroller`` directly (like the tasks do) and
does not touch the DB, vector store or API layer.
"""
from __future__ import annotations

import os
import sys
import json
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, SRC)

# Minimal env so ``helpers.config.get_config()`` can construct without a real .env.
# NOTE: field names come directly from src/helpers/config.py.
os.environ.setdefault("APP_NAME", "context-iq")
os.environ.setdefault("ALLOWED_EXTENSIONS", '["text/plain","application/pdf"]')
os.environ.setdefault("FILE_DEFAULT_CHUNK_SIZE", "800")
os.environ.setdefault("MAX_FILE_SIZE", "50000000")
os.environ.setdefault("POSTGRES_USERNAME", "u")
os.environ.setdefault("POSTGRES_PASSWORD", "p")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_MAIN_DATABASE", "d")
os.environ.setdefault("GENERATION_BACKEND", "OPENAI")
os.environ.setdefault("EMBEDDING_BACKEND", "COHERE")
os.environ.setdefault("VECTOR_DB_BACKEND_LITERAL", '["QDRANT","PGVECTOR"]')
os.environ.setdefault("VECTOR_DB_BACKEND", "QDRANT")
os.environ.setdefault("VECTOR_DB_NAME", "context_iq")
os.environ.setdefault("VECTOR_DB_DISTANCE_METHOD", "COSINE")
os.environ.setdefault("PRIMARY_LANG", "en")
os.environ.setdefault("DEFAULT_LANG", "en")
os.environ.setdefault("CELERY_FLOWER_PASSWORD", "x")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

# Vision — off. The PDF pipeline must work with no provider configured.
os.environ.setdefault("VISION_PROVIDER", "")



def _import_processcontroller():
    """Import ProcessController without triggering ``controllers/__init__.py``
    which cascades into LLM/vector-store SDKs we don't need here."""
    import importlib.util

    def load(mod_name, rel_path):
        spec = importlib.util.spec_from_file_location(
            mod_name, os.path.join(SRC, rel_path)
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod

    # Bootstrap the exact chain ProcessController depends on.
    load("helpers", "helpers/__init__.py")
    load("helpers.config", "helpers/config.py")
    # ``models`` is used only for the processingenum enum in ProcessController.
    load("models", "models/__init__.py")
    # BaseController + ProjectController must be loaded as submodules of a
    # synthetic ``controllers`` package so relative imports work.
    import types
    controllers_pkg = types.ModuleType("controllers")
    controllers_pkg.__path__ = [os.path.join(SRC, "controllers")]
    sys.modules["controllers"] = controllers_pkg
    load("controllers.BaseController", "controllers/BaseController.py")
    load("controllers.ProjectController", "controllers/ProjectController.py")
    pcmod = load("controllers.ProcessController", "controllers/ProcessController.py")
    return pcmod.processcontroller


def main(pdf_path: str) -> int:
    print(f"\n=== Repro run against: {pdf_path} ===\n")

    processcontroller = _import_processcontroller()

    class DummyVision:
        def is_configured(self):
            return False

    pc = processcontroller.__new__(processcontroller)
    pc.project_id = "reprro"
    pc.project_path = os.path.dirname(pdf_path)
    pc.vision_client = DummyVision()
    from helpers.config import get_config
    pc.config = get_config()



    file_content = pc.load_pdf_file(pdf_path)
    print(f"Loaded documents (elements): {len(file_content)}")

    per_page = defaultdict(Counter)
    for d in file_content:
        per_page[d.metadata.get("page")][d.metadata.get("content_type")] += 1
    print("\nElements per page (content_type histogram):")
    for page in sorted(per_page):
        print(f"  page={page}: {dict(per_page[page])}")

    chunks = pc.get_file_chunks(file_content, "chapter4.pdf",
                                chunk_size=800, overlap_size=200)
    print(f"\nTotal chunks: {len(chunks)}")

    sizes = [len(c.page_content) for c in chunks]
    tiny  = [i for i, s in enumerate(sizes) if s < 100]
    small = [i for i, s in enumerate(sizes) if 100 <= s < 300]
    print(f"  size min={min(sizes)}, max={max(sizes)}, avg={sum(sizes)//len(sizes)}")
    print(f"  tiny (<100 chars): {len(tiny)}, small (100-299): {len(small)}")
    print(f"  first 10 tiny chunk indices: {tiny[:10]}")
    for i in tiny[:6]:
        print(f"    [{i}] ({sizes[i]}c) {chunks[i].page_content!r}")

    heading_only = []
    for i, c in enumerate(chunks):
        t = c.page_content.strip()
        if len(t) < 120 and (t.lower().startswith("chapter") or
                             (len(t) >= 3 and t[0].isdigit() and "." in t[:5])):
            heading_only.append((i, t))
    print(f"\nIssue 2 heading-only chunks: {len(heading_only)}")
    for i, t in heading_only[:8]:
        print(f"  [{i}] {t!r}")

    mid_sentence = []
    for i, c in enumerate(chunks):
        t = c.page_content.strip()
        if not t: continue
        if t.startswith("[PDF Table") or t.startswith("[Image Description") or t.startswith("[Page Scan"):
            continue
        toks = t.split()
        if not toks: continue
        last = toks[-1]
        if last and last[-1].isalpha() and last[-1].islower():
            mid_sentence.append((i, t[-80:]))
    print(f"\nIssue 3 mid-sentence tail chunks: {len(mid_sentence)}")
    for i, tail in mid_sentence[:5]:
        print(f"  [{i}] ...{tail!r}")

    image_chunks = [c for c in chunks if c.metadata.get("content_type") == "image"]
    image_missing_header = [
        c for c in image_chunks
        if not c.page_content.lstrip().startswith("[Image Description")
    ]
    print(f"\nIssue 4 image chunks: total={len(image_chunks)}, "
          f"missing header={len(image_missing_header)}")

    import re as _re
    pat = _re.compile(r"\[(?:PDF Table|Image Description|Page Scan) \| Page: (\d+)")
    mismatches = []
    aligned_offset = Counter()
    for c in chunks:
        m = pat.search(c.page_content)
        if not m: continue
        body_page = int(m.group(1))
        meta_page = c.metadata.get("page")
        if meta_page is None: continue
        diff = body_page - int(meta_page)
        aligned_offset[diff] += 1
        # Under the current code the diff is expected to be +1. Anything else
        # (including 0 after our fix) is what we want to see.
        if diff != 1:
            mismatches.append((meta_page, body_page, c.page_content[:80]))
    print(f"\nIssue 5 body_page - meta_page distribution: {dict(aligned_offset)}")
    print(f"  chunks NOT matching the current +1 offset: {len(mismatches)}")

    table_chunks = [c for c in chunks if c.metadata.get("content_type") == "table"]
    print(f"\nIssue 6 table chunks: {len(table_chunks)}")
    for i, c in enumerate(table_chunks[:8]):
        t = c.page_content
        head_line = t.split("\n", 1)[0] if t else ""
        md_rows = sum(1 for line in t.splitlines()
                      if line.startswith("|") and "---" not in line)
        # subtract 1 for the header row itself when regular-format
        data_rows_in_body = max(0, md_rows - 1) if md_rows else t.count("\nRow ")
        generic = "col_" in head_line
        print(f"  [{i}] meta.page={c.metadata.get('page')}, "
              f"row_range={c.metadata.get('row_range')}, "
              f"len={len(t)}, data_rows_in_body={data_rows_in_body}, "
              f"generic_cols={generic}")
        print(f"      head: {head_line[:160]}")

    dump_path = os.path.join(HERE, "chunks_dump.json")
    with open(dump_path, "w", encoding="utf-8") as f:
        json.dump([{
            "i": i,
            "len": len(c.page_content),
            "content_type": c.metadata.get("content_type"),
            "page": c.metadata.get("page"),
            "reading_order": c.metadata.get("reading_order"),
            "row_range": c.metadata.get("row_range"),
            "table_index": c.metadata.get("table_index"),
            "image_index": c.metadata.get("image_index"),
            "columns": c.metadata.get("columns"),
            "head": c.page_content[:200],
            "tail": c.page_content[-200:],
        } for i, c in enumerate(chunks)], f, ensure_ascii=False, indent=2)
    print(f"\nDump written to: {dump_path}")

    return 0


if __name__ == "__main__":
    default_pdf = r"d:\gHaZaLa\Graduation Project\Chapter 4 AI-Based Driver Monitoring.pdf"
    path = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    sys.exit(main(path))
