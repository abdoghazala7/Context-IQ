import os
import io
import re
import unicodedata
import logging
from .BaseController import basecontroller
from .ProjectController import projectController
from models import processingenum
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import markdown
from bs4 import BeautifulSoup
import pandas as pd

logger = logging.getLogger(__name__)



class processcontroller(basecontroller):
    """
    Controller responsible for processing uploaded files.
    """

    # Separator used when serializing structured-data rows into text.
    _STRUCTURED_COL_SEP = " | "
    # Maximum number of rows grouped into a single Document before chunking.
    _STRUCTURED_ROWS_PER_DOC = 50

    # ---------------------- PDF multimodal tuning ----------------------
    # Hard upper bound on rows per serialized table batch. Batches are also
    # capped by ``_TABLE_BATCH_CHAR_BUDGET`` so that a batch reliably fits into
    # a single downstream chunk — otherwise the ``Rows: X-Y`` header on the
    # first sub-chunk would mislead about what the sub-chunk actually contains.
    _TABLE_ROWS_PER_BATCH = 25
    # Soft character budget (excluding preamble) for one serialized table
    # batch. Sized so that ``preamble + budget`` typically fits within the
    # chunker's default chunk_size (see ``get_file_chunks``).
    _TABLE_BATCH_CHAR_BUDGET = 650
    # A text block is considered "inside" a table when this fraction of its
    # area overlaps the table bbox (intersection-over-area).
    _TABLE_TEXT_IOA_THRESHOLD = 0.60

    # Elements wider than this fraction of the page act as band separators
    # (headings / wide tables read before the columns beneath them).
    _FULL_WIDTH_RATIO = 0.65
    # Below this many meaningful characters a page is a scanned-page candidate.
    _SCANNED_TEXT_CHAR_THRESHOLD = 50
    # A single image covering at least this fraction of the page => scanned page.
    _SCANNED_IMAGE_COVERAGE = 0.50
    # DPI used when rasterizing a full page for OCR.
    _PAGE_SCAN_DPI = 150

    # Vision prompts.
    _IMAGE_PROMPT = (
        "Describe the visual content for retrieval. Include visible text, chart "
        "axes/labels, entities, and concise semantic meaning. Do not hallucinate "
        "unseen details."
    )
    _PAGE_PROMPT = (
        "Extract all readable text in natural reading order. Preserve headings, "
        "lists, tables, and labels."
    )


    def __init__(self, project_id: str, vision_client=None):
        super().__init__()
        self.project_id = project_id
        self.project_path = projectController().get_project_path(project_id=project_id)
        # Optional multimodal vision client. May be None or a NullVisionProvider;
        # PDF text/table processing must work regardless of its availability.
        self.vision_client = vision_client
        # Per-parse cache: the last real (non-generic) column set observed
        # while walking pages of the CURRENT PDF, keyed by table index. Lets a
        # multi-page table continue to carry its original column names on the
        # next page when the extractor picks up header-less rows (Issue 6).
        # Reset on every call to ``load_pdf_file`` so it never leaks across
        # files handled by the same controller instance.
        self._last_pdf_columns: dict[int, list[str]] | None = None



    def get_file_path(self, file_id: str) -> str:
        return os.path.join(self.project_path, file_id)
    
    def get_file_extension(self, file_id: str) -> str:
        return os.path.splitext(file_id)[1].lower()

    def load_txt_file(self, file_path: str):
        loader = TextLoader(file_path, encoding="utf-8")
        return loader.load()

    # ------------------------------------------------------------------
    # PDF multimodal parser (raw PyMuPDF + optional vision enrichment)
    # ------------------------------------------------------------------

    def load_pdf_file(self, file_path: str) -> list[Document]:
        """
        Multimodal PDF loader built directly on PyMuPDF (``fitz``).

        Flow per page:
          1. Extract tables (find_tables) and serialize them.
          2. Extract text blocks, skipping text that overlaps table regions.
          3. Detect scanned pages -> single full-page OCR via ``describe_page``.
          4. Otherwise extract + optimize meaningful images -> ``describe_image``.
          5. Order every element with a recursive XY-cut layout algorithm.
          6. Emit LangChain Documents with rich, citation-ready metadata.

        Vision is strictly optional: if no provider is configured, image /
        page-scan enrichment is skipped and text/table processing still works.
        Any unexpected fatal error degrades gracefully to the legacy loader so
        a single problematic PDF never breaks ingestion.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF (fitz) unavailable; using legacy PyMuPDFLoader")
            return PyMuPDFLoader(file_path).load()

        # Reset per-file column carryover so a previous file cannot leak
        # its columns into this one (Issue 6, multi-page table continuation).
        self._last_pdf_columns = {}

        try:
            doc = fitz.open(file_path)

        except Exception as e:  # unreadable PDF is a genuine fatal condition
            logger.error(f"Failed to open PDF {file_path}: {e}")
            raise

        vision_ready = self._vision_ready()
        documents: list[Document] = []

        try:
            for page_index in range(doc.page_count):
                try:
                    page = doc.load_page(page_index)
                    page_elements = self._process_pdf_page(
                        page, page_index, file_path, vision_ready
                    )
                    documents.extend(page_elements)
                except Exception as page_err:  # never let one page kill the file
                    logger.error(f"Error processing page {page_index} of "
                                 f"{file_path}: {page_err}")
                    continue
        finally:
            doc.close()

        # Fallback: if the rich parser produced nothing (e.g. exotic PDF),
        # fall back to the legacy loader so we never silently drop content.
        if not documents:
            logger.warning(f"Multimodal parser produced no elements for "
                           f"{file_path}; falling back to legacy loader")
            return PyMuPDFLoader(file_path).load()

        return documents

    def _process_pdf_page(self, page, page_index: int, file_path: str,
                          vision_ready: bool) -> list[Document]:
        """Build the ordered list of Documents for a single PDF page."""
        page_rect = page.rect
        page_width = float(page_rect.width) or 1.0
        page_height = float(page_rect.height) or 1.0

        elements: list[dict] = []
        table_bboxes: list[list[float]] = []

        # --- 1. Tables first -------------------------------------------------
        table_index = 0
        try:
            table_finder = page.find_tables()
            tables = getattr(table_finder, "tables", []) or []
        except Exception as e:
            logger.debug(f"find_tables failed on page {page_index}: {e}")
            tables = []

        for table in tables:
            bbox = self._normalize_bbox(getattr(table, "bbox", None), page_rect)
            if bbox is None:
                continue
            table_index += 1
            # Multi-page tables — some PDF authoring tools (Word included)
            # emit a continuation table on the next page with no meaningful
            # header row, causing find_tables to fall back to generic
            # ``col_1, col_2…`` names (Issue 6, third bullet). If we saw a
            # real header for the same table index on a previous page of
            # THIS file, reuse it. The heuristic is intentionally strict —
            # only the *first* table on each page inherits, and only when
            # the current column names are all generic.
            carry_columns = None
            if (table_index == 1 and self._last_pdf_columns
                    and self._last_pdf_columns.get(1)):
                carry_columns = self._last_pdf_columns[1]

            serialized = self._serialize_table(
                table, page_index, table_index, carry_columns=carry_columns
            )
            if not serialized:
                continue
            # Record real (non-generic) columns for continuation lookup on
            # the next page.
            cols = serialized["columns"]
            if cols and not all(c.startswith("col_") for c in cols):
                if self._last_pdf_columns is None:
                    self._last_pdf_columns = {}
                self._last_pdf_columns[table_index] = list(cols)

            table_bboxes.append(bbox)
            elements.append({
                "content_type": "table",
                "bbox": bbox,
                "batches": serialized["batches"],
                "columns": serialized["columns"],
                "table_index": table_index,
            })


        # --- 2. Text blocks (skip those inside tables) -----------------------
        text_char_count = 0
        try:
            page_dict = page.get_text("dict")
        except Exception as e:
            logger.debug(f"get_text(dict) failed on page {page_index}: {e}")
            page_dict = {"blocks": []}

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 == text block
                continue
            raw_text = self._extract_block_text(block)
            cleaned = self._clean_text(raw_text)
            if not cleaned:
                continue
            bbox = self._normalize_bbox(block.get("bbox"), page_rect)
            if bbox is None:
                continue
            # Drop text that visually belongs to a table region.
            if any(self._ioa(bbox, tb) > self._TABLE_TEXT_IOA_THRESHOLD
                   for tb in table_bboxes):
                continue
            text_char_count += len(cleaned)
            elements.append({
                "content_type": "text",
                "bbox": bbox,
                "text": cleaned,
            })

        # --- 3. Collect candidate images ------------------------------------
        images = self._extract_page_images(page, page_index, page_rect) if vision_ready else []

        # --- 4. Scanned-page detection --------------------------------------
        is_scanned = self._is_scanned_page(
            text_char_count, table_bboxes, images, page_width, page_height
        )

        if vision_ready and is_scanned:
            scan_element = self._run_page_scan(page, page_index, page_rect)
            if scan_element is not None:
                # A scanned page is atomic: the OCR result is the only element.
                return self._elements_to_documents(
                    [scan_element], page_index, file_path, page_rect
                )
            # If OCR yielded nothing, fall through to whatever text we have.

        # --- 5. Per-image vision enrichment ---------------------------------
        if vision_ready and not is_scanned:
            self._enrich_with_images(images, page_index, elements)

        # --- 6. Order + convert ---------------------------------------------
        return self._elements_to_documents(elements, page_index, file_path, page_rect)

    # ------------------------------------------------------------------
    # Vision availability
    # ------------------------------------------------------------------
    def _vision_ready(self) -> bool:
        """True only when a real, configured vision provider is attached."""
        client = self.vision_client
        if client is None:
            return False
        try:
            return bool(client.is_configured())
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_bbox(bbox, page_rect) -> list[float] | None:
        """Clamp a bbox to page bounds and reject empty/invalid boxes."""
        if bbox is None:
            return None
        try:
            x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]),
                              float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError, IndexError):
            return None
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        x0 = max(x0, float(page_rect.x0))
        y0 = max(y0, float(page_rect.y0))
        x1 = min(x1, float(page_rect.x1))
        y1 = min(y1, float(page_rect.y1))
        if (x1 - x0) <= 1.0 or (y1 - y0) <= 1.0:
            return None
        return [x0, y0, x1, y1]

    @staticmethod
    def _bbox_area(bbox) -> float:
        return max(0.0, (bbox[2] - bbox[0])) * max(0.0, (bbox[3] - bbox[1]))

    @classmethod
    def _intersection_area(cls, a, b) -> float:
        ix0 = max(a[0], b[0])
        iy0 = max(a[1], b[1])
        ix1 = min(a[2], b[2])
        iy1 = min(a[3], b[3])
        if ix1 <= ix0 or iy1 <= iy0:
            return 0.0
        return (ix1 - ix0) * (iy1 - iy0)

    @classmethod
    def _ioa(cls, inner, outer) -> float:
        """Intersection-over-(inner)-area: how much of ``inner`` sits in ``outer``."""
        inner_area = cls._bbox_area(inner)
        if inner_area <= 0:
            return 0.0
        return cls._intersection_area(inner, outer) / inner_area

    # ------------------------------------------------------------------
    # Text extraction / cleanup
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_block_text(block) -> str:
        lines = []
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = "".join(span.get("text", "") for span in spans)
            lines.append(line_text)
        return "\n".join(lines)

    # Regex used to identify lines that behave as paragraph-level separators
    # even when they are visually flush with adjacent lines inside a single
    # PyMuPDF block (headings, numbered list items, etc.).
    _PARAGRAPH_LEAD_PATTERN = re.compile(
        r"^\s*("
        r"\d+(\.\d+)*\.?\s+"                   # 1.  2.3  4.1.2  etc.
        r"|Chapter\s+\d+"                       # Chapter 4
        r"|Figure\s+\d+"                        # Figure 4.1
        r"|Table\s+\d+"                         # Table 4.1
        r"|Step\s+\d+"                          # Step 1
        r"|Phase\s+\d+"                         # Phase 1
        r"|[•\-\u2022]\s+"                     # bullets
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """
        Normalize extracted text.

        PyMuPDF returns one ``\\n`` per *visual line* inside a block. A single
        printed paragraph therefore arrives as many short lines, and if we
        keep those newlines the downstream RecursiveCharacterTextSplitter
        treats each one as a preferred split boundary — which is exactly how
        we end up with one-word/one-sentence chunks (Issue 1) and mid-sentence
        splits like ``"…driver's facial\\ncues to identify…"`` (Issue 3).

        The fix: collapse *soft* intra-paragraph line wraps into spaces while
        preserving genuine paragraph boundaries (blank lines) and leading
        markers that indicate a new logical line (headings, numbered lists,
        bullets, ``Figure``/``Table`` captions, etc.).
        """
        if not text:
            return ""
        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)
        # Dehyphenate words split across line breaks: "exam-\nple" -> "example"
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        # Remove control characters (keep \n and \t)
        text = "".join(
            ch for ch in text
            if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
        )
        # Collapse runs of spaces/tabs
        text = re.sub(r"[ \t]+", " ", text)
        # Trim spaces around newlines
        text = re.sub(r" *\n *", "\n", text)

        # Collapse soft wraps. Iterate line pairs: keep a hard break only if
        # (a) the next line is blank (paragraph boundary), or
        # (b) the next line starts with a structural lead (heading, bullet…),
        # or (c) the current line ends with terminal punctuation AND the next
        # line's first character is uppercase / digit (sentence boundary).
        lines = text.split("\n")
        merged: list[str] = []
        for i, ln in enumerate(lines):
            if not merged:
                merged.append(ln)
                continue
            prev = merged[-1]
            if prev == "" or ln == "":
                # keep the boundary
                merged.append(ln)
                continue
            if cls._PARAGRAPH_LEAD_PATTERN.match(ln):
                merged.append(ln)
                continue
            # Sentence-terminated on previous line + capitalized/digit start
            # on this line => keep as a paragraph boundary too.
            if prev[-1:] in ".!?:" and ln[:1].isalnum() and (ln[:1].isupper() or ln[:1].isdigit()):
                merged.append(ln)
                continue
            # Otherwise this is a soft line wrap: merge with a space.
            sep = "" if prev.endswith("-") else " "
            merged[-1] = prev + sep + ln

        text = "\n".join(merged)
        # Collapse 3+ blank lines into a single blank line
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Whitespace cleanup after merging
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


    @classmethod
    def _clean_cell(cls, value) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    # ------------------------------------------------------------------
    # Table serialization (hybrid: markdown for regular, rows for irregular)
    # ------------------------------------------------------------------
    def _serialize_table(self, table, page_index: int, table_index: int,
                         carry_columns: list[str] | None = None):
        """
        Serialize a PyMuPDF table into one Document per batch of rows.

        Two fixes here address Issue 6:

        (a) **Batching is character-budgeted**, not just row-count-capped.
            Before, a single batch could easily exceed the downstream chunk
            budget (chunk_size=800 in the reported scenario). The splitter
            would then cut it, leaving only the *first* sub-chunk with the
            ``[PDF Table … Rows: X-Y]`` preamble while the continuation rows
            landed in header-less follower chunks — and the ``Rows`` label on
            the first sub-chunk lied about the rows actually inside it. We
            now cap each batch's serialized *body* size to
            ``_TABLE_BATCH_CHAR_BUDGET`` so it fits comfortably in one chunk,
            and each batch always emits its own preamble.

        (b) **Multi-page column carry-over.** When the caller passes
            ``carry_columns`` (i.e. this is the first table on a continuation
            page and the previous page ended with a real header row), the
            first data row is inspected: if it looks like body (not a
            plausible re-emitted header), we substitute the carried column
            names in place of the generic ``col_1, col_2…`` that
            ``find_tables`` produces on continuation pages.
        """
        try:
            rows = table.extract()
        except Exception as e:
            logger.debug(f"table.extract failed (page {page_index}): {e}")
            return None
        if not rows:
            return None

        # Determine header row.
        header = None
        try:
            names = getattr(getattr(table, "header", None), "names", None)
            if names:
                header = [self._clean_cell(n) for n in names]
        except Exception:
            header = None

        if header and any(header):
            data_rows = rows
        else:
            header = [self._clean_cell(c) for c in rows[0]]
            data_rows = rows[1:]

        columns = [h if h else f"col_{i+1}" for i, h in enumerate(header)]

        # Multi-page column carry-over. Applied only when
        # (i) the caller says the previous page ended with the same table
        #     (``carry_columns`` supplied),
        # (ii) column counts match, and
        # (iii) the current header row looks degenerate — meaning **any**
        #      column is generic (``col_N``) or empty, or a large fraction of
        #      the headers exceed a plausible header length (Word-generated
        #      continuation pages tend to promote the first body row into a
        #      pseudo-header, so real headers are short but pseudo-headers
        #      are full sentences).
        _HEADER_MAX_LEN = 60
        if carry_columns and len(carry_columns) == len(columns):
            any_generic = any(
                (not c) or c.startswith("col_") for c in columns
            )
            mostly_long = (
                sum(1 for c in columns if len(c) > _HEADER_MAX_LEN)
                >= max(1, len(columns) // 2)
            )
            if any_generic or mostly_long:
                # Push the mis-classified header row back into the data if it
                # actually contained content (was not pure ``col_N`` fillers).
                if any(c and not c.startswith("col_") for c in columns):
                    data_rows = [list(header)] + list(data_rows)
                columns = list(carry_columns)


        if not columns or not data_rows:
            return None

        # A table is "regular" when every row matches the column count.
        regular = all(len(r) == len(columns) for r in data_rows)
        total = len(data_rows)

        def _preamble(regular_flag: bool, row_range: str) -> str:
            col_sep = ", " if regular_flag else " | "
            return (f"[PDF Table | Page: {page_index + 1} | "
                    f"Table: {table_index} | Rows: {row_range} | "
                    f"Columns: {col_sep.join(columns)}]")

        def _format_regular_row(r) -> str:
            cells = [self._clean_cell(c) for c in r]
            return "| " + " | ".join(cells) + " |"

        def _format_irregular_row(r, absolute_row_num: int) -> str:
            cells = [f"{h}: {self._clean_cell(c)}"
                     for h, c in zip(columns, r)]
            return f"Row {absolute_row_num}:\n" + " | ".join(cells)

        # Header + separator lines shared by every regular batch. They count
        # toward the char budget so a wide table still fits.
        header_line = "| " + " | ".join(columns) + " |"
        sep_line = "| " + " | ".join(["---"] * len(columns)) + " |"

        batches: list[dict] = []
        i = 0
        while i < total:
            body_lines: list[str] = []
            body_chars = 0
            start = i
            # Grow the batch row-by-row until it hits either the char budget
            # or the hard row cap.
            while i < total and (i - start) < self._TABLE_ROWS_PER_BATCH:
                r = data_rows[i]
                if regular:
                    line = _format_regular_row(r)
                else:
                    line = _format_irregular_row(r, absolute_row_num=i + 1)
                # +1 accounts for the newline joining this line to the batch.
                cost = len(line) + 1
                # Always accept the first row of a batch — even if a single
                # row exceeds the budget on its own, splitting it further
                # would lose the ``Row N`` labelling and violate the promise
                # that ``Rows: X-Y`` matches what's inside.
                if body_lines and body_chars + cost > self._TABLE_BATCH_CHAR_BUDGET:
                    break
                body_lines.append(line)
                body_chars += cost
                i += 1
            end = i
            row_range = f"{start + 1}-{end}"
            if regular:
                text = "\n".join([_preamble(True, row_range),
                                  header_line, sep_line, *body_lines])
            else:
                text = "\n".join([_preamble(False, row_range), *body_lines])
            batches.append({"text": text, "row_range": row_range})

        return {"columns": columns, "batches": batches}


    # ------------------------------------------------------------------
    # Image extraction + optimization
    # ------------------------------------------------------------------
    def _extract_page_images(self, page, page_index: int, page_rect) -> list[dict]:
        """Return candidate images as dicts: {bytes, ext, bbox}."""
        images = []
        page_area = self._bbox_area([page_rect.x0, page_rect.y0,
                                     page_rect.x1, page_rect.y1]) or 1.0
        min_ratio = float(self.config.VISION_MIN_IMAGE_AREA_RATIO)
        max_images = int(self.config.VISION_MAX_IMAGES_PER_PAGE)

        try:
            raw_images = page.get_images(full=True)
        except Exception as e:
            logger.debug(f"get_images failed on page {page_index}: {e}")
            return []

        seen_xrefs = set()
        for img in raw_images:
            if len(images) >= max_images:
                break
            xref = img[0]
            if xref in seen_xrefs:  # skip repeated logos/watermarks
                continue
            seen_xrefs.add(xref)

            # Locate the image on the page.
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            if not rects:
                continue
            bbox = self._normalize_bbox(
                [rects[0].x0, rects[0].y0, rects[0].x1, rects[0].y1], page_rect
            )
            if bbox is None:
                continue
            # Skip decorative / tiny images.
            if self._bbox_area(bbox) / page_area < min_ratio:
                continue

            try:
                base = page.parent.extract_image(xref)
            except Exception:
                continue
            img_bytes = base.get("image")
            if not img_bytes:
                continue

            images.append({
                "bytes": img_bytes,
                "ext": base.get("ext", "png"),
                "bbox": bbox,
            })

        return images

    def _optimize_image(self, image_bytes: bytes) -> tuple[bytes, str] | None:
        """
        Deterministically resize + compress an image to a JPEG payload that
        respects VISION_IMAGE_MAX_WIDTH / JPEG_QUALITY / MAX_IMAGE_BYTES.
        Returns (jpeg_bytes, "image/jpeg") or None when it can't be shrunk.
        """
        try:
            from PIL import Image
        except ImportError:
            logger.debug("Pillow unavailable; sending raw image bytes")
            if len(image_bytes) <= int(self.config.VISION_MAX_IMAGE_BYTES):
                return image_bytes, "image/jpeg"
            return None

        max_width = int(self.config.VISION_IMAGE_MAX_WIDTH)
        quality = int(self.config.VISION_IMAGE_JPEG_QUALITY)
        max_bytes = int(self.config.VISION_MAX_IMAGE_BYTES)

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = img.convert("RGB")
        except Exception as e:
            logger.debug(f"Pillow failed to open image: {e}")
            return None

        # Resize longest edge down to max_width.
        longest = max(img.width, img.height)
        if longest > max_width:
            scale = max_width / float(longest)
            new_size = (max(1, int(img.width * scale)),
                        max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        # Progressive quality reduction until under the byte budget.
        for q in (quality, 70, 55, 40, 30):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return data, "image/jpeg"

        # Last resort: halve dimensions once more.
        try:
            img = img.resize((max(1, img.width // 2), max(1, img.height // 2)),
                             Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=40, optimize=True)
            data = buf.getvalue()
            if len(data) <= max_bytes:
                return data, "image/jpeg"
        except Exception:
            pass

        logger.debug("Image still exceeds VISION_MAX_IMAGE_BYTES; skipping")
        return None

    def _enrich_with_images(self, images: list[dict], page_index: int,
                            elements: list[dict]) -> None:
        """Call the vision provider per image and append image elements."""
        image_index = 0
        for image in images:
            image_index += 1
            optimized = self._optimize_image(image["bytes"])
            if optimized is None:
                continue
            payload, mime = optimized
            try:
                result = self.vision_client.describe_image(
                    image_bytes=payload,
                    mime_type=mime,
                    prompt=self._IMAGE_PROMPT,
                    metadata={"page": page_index, "image_index": image_index},
                )
            except Exception as e:  # image-level failure must not kill the page
                logger.warning(f"Vision describe_image failed "
                               f"(page {page_index}, image {image_index}): {e}")
                continue
            if result is None or not result.text:
                continue

            body = (f"[Image Description | Page: {page_index + 1} | "
                    f"Image: {image_index}]\n{result.text.strip()}")
            elements.append({
                "content_type": "image",
                "bbox": image["bbox"],
                "text": body,
                "image_index": image_index,
                "vision_provider": result.provider,
                "vision_model": result.model,
            })

    # ------------------------------------------------------------------
    # Full-page scan detection + OCR
    # ------------------------------------------------------------------
    def _is_scanned_page(self, text_char_count: int, table_bboxes: list,
                         images: list, page_width: float,
                         page_height: float) -> bool:
        if text_char_count >= self._SCANNED_TEXT_CHAR_THRESHOLD:
            return False
        if table_bboxes:
            return False
        if not images:
            return False
        page_area = page_width * page_height or 1.0
        largest = max((self._bbox_area(im["bbox"]) for im in images), default=0.0)
        return (largest / page_area) >= self._SCANNED_IMAGE_COVERAGE

    def _run_page_scan(self, page, page_index: int, page_rect):
        """Render the whole page once and OCR it via ``describe_page``."""
        try:
            import fitz
            matrix = fitz.Matrix(self._PAGE_SCAN_DPI / 72.0,
                                 self._PAGE_SCAN_DPI / 72.0)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
        except Exception as e:
            logger.warning(f"Failed to render page {page_index} for OCR: {e}")
            return None

        optimized = self._optimize_image(png_bytes)
        if optimized is None:
            return None
        payload, mime = optimized

        try:
            result = self.vision_client.describe_page(
                image_bytes=payload,
                mime_type=mime,
                prompt=self._PAGE_PROMPT,
                metadata={"page": page_index},
            )
        except Exception as e:
            logger.warning(f"Vision describe_page failed (page {page_index}): {e}")
            return None
        if result is None or not result.text:
            return None

        body = (f"[Page Scan | Page: {page_index + 1}]\n"
                f"{self._clean_text(result.text)}")
        return {
            "content_type": "page_scan",
            "bbox": [page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1],
            "text": body,
            "vision_provider": result.provider,
            "vision_model": result.model,
        }

    # ------------------------------------------------------------------
    # Spatial ordering (recursive XY-cut) + Document conversion
    # ------------------------------------------------------------------
    def _elements_to_documents(self, elements: list[dict], page_index: int,
                               file_path: str, page_rect) -> list[Document]:
        if not elements:
            return []

        rtl = str(getattr(self.config, "PRIMARY_LANG", "en")).lower().startswith("ar")
        page_width = float(page_rect.width) or 1.0
        page_height = float(page_rect.height) or 1.0

        ordered = self._xy_cut_order(elements, page_width, page_height, rtl)

        documents: list[Document] = []
        for order_index, element in enumerate(ordered):
            base_meta = {
                "source": file_path,
                "format": "pdf",
                # Store 1-indexed page numbers so metadata always agrees with
                # the ``Page: N`` label written inside serialized tables /
                # image descriptions / page scans (Issue 5). Downstream
                # citation code (NLPController._build_source_label) matches
                # this convention.
                "page": page_index + 1,
                "content_type": element["content_type"],
                "bbox": element["bbox"],
                "reading_order": order_index,
            }

            if element.get("vision_provider"):
                base_meta["vision_provider"] = element["vision_provider"]
            if element.get("vision_model"):
                base_meta["vision_model"] = element["vision_model"]
            if element.get("image_index"):
                base_meta["image_index"] = element["image_index"]

            if element["content_type"] == "table":
                columns = element.get("columns")
                for batch in element["batches"]:
                    meta = dict(base_meta)
                    meta["table_index"] = element["table_index"]
                    meta["row_range"] = batch["row_range"]
                    if columns:
                        meta["columns"] = columns
                    documents.append(
                        Document(page_content=batch["text"], metadata=meta)
                    )
            else:
                documents.append(
                    Document(page_content=element["text"], metadata=base_meta)
                )

        return documents

    def _xy_cut_order(self, elements: list[dict], page_width: float,
                      page_height: float, rtl: bool) -> list[dict]:
        """
        Recursive XY-cut ordering based on whitespace gaps.

        Alternates horizontal band cuts (top->bottom) and vertical column cuts
        (left->right, or right->left for RTL). Full-width elements act as band
        separators. Falls back to (y, x) sorting when no reliable gap exists.
        """
        line_tol = max(2.0, 0.01 * page_height)   # visually-shared-line tolerance
        band_gap = max(4.0, 0.015 * page_height)  # min vertical whitespace gap
        gutter = max(6.0, 0.02 * page_width)      # min horizontal gutter
        full_width = self._FULL_WIDTH_RATIO * page_width

        def fallback_sort(items):
            return sorted(items, key=lambda e: (round(e["bbox"][1] / max(line_tol, 1e-6)),
                                                e["bbox"][0]))

        def split_gaps(items, axis, tol):
            lo, hi = (1, 3) if axis == "y" else (0, 2)
            ordered_items = sorted(items, key=lambda e: e["bbox"][lo])
            groups = [[ordered_items[0]]]
            current_max = ordered_items[0]["bbox"][hi]
            for it in ordered_items[1:]:
                if it["bbox"][lo] > current_max + tol:
                    groups.append([it])
                    current_max = it["bbox"][hi]
                else:
                    groups[-1].append(it)
                    current_max = max(current_max, it["bbox"][hi])
            return groups

        def recurse_bands(items):
            if len(items) <= 1:
                return items
            bands = split_gaps(items, "y", band_gap)
            if len(bands) > 1:
                result = []
                for band in bands:  # already top -> bottom
                    result.extend(recurse_cols(band))
                return result
            return recurse_cols(items)

        def recurse_cols(items):
            if len(items) <= 1:
                return items
            # A full-width element (heading / wide table) blocks column splitting.
            if any((it["bbox"][2] - it["bbox"][0]) >= full_width for it in items):
                return fallback_sort(items)
            cols = split_gaps(items, "x", gutter)
            if len(cols) > 1:
                cols.sort(key=lambda col: min(c["bbox"][0] for c in col),
                          reverse=rtl)
                result = []
                for col in cols:
                    result.extend(recurse_bands(col))
                return result
            return fallback_sort(items)

        try:
            return recurse_bands(list(elements))
        except Exception as e:
            logger.debug(f"XY-cut ordering failed; using fallback sort: {e}")
            return fallback_sort(list(elements))


    def load_docx_file(self, file_path: str):
        loader = Docx2txtLoader(file_path)
        return loader.load()

    def load_md_file(self, file_path: str):
        """
        Load a Markdown file, converting it to structured plain text
        while preserving semantic sections (headings, lists, code blocks).
        """
        with open(file_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        # Convert Markdown to HTML with common extensions
        html = markdown.markdown(
            md_content,
            extensions=["extra", "codehilite", "toc", "tables", "sane_lists"]
        )

        # Extract clean text from HTML, preserving structural whitespace
        soup = BeautifulSoup(html, "lxml")
        clean_text = soup.get_text(separator="\n", strip=True)

        doc = Document(
            page_content=clean_text,
            metadata={"source": file_path, "format": "markdown"}
        )
        return [doc]

    # ------------------------------------------------------------------
    # Structured data helpers (CSV / Excel)
    # ------------------------------------------------------------------

    def _dataframe_to_documents(self, df: pd.DataFrame, file_path: str,
                                sheet_name: str = None) -> list[Document]:
        """
        Convert a pandas DataFrame into a list of LangChain Documents.

        Strategy — **Row-with-Headers**:
        Each row is serialized as ``Header1: Value1 | Header2: Value2 | …``
        so every chunk is self-contained and meaningful for RAG retrieval.
        Rows are batched into groups of ``_STRUCTURED_ROWS_PER_DOC`` to avoid
        creating an excessive number of micro-documents while still keeping
        each Document small enough for the downstream text splitter.
        """
        if df.empty:
            logger.warning(f"Empty DataFrame from {file_path}"
                           + (f" sheet={sheet_name}" if sheet_name else ""))
            return []

        # Clean column names: strip whitespace, replace NaN headers
        df.columns = [
            str(col).strip() if pd.notna(col) else f"column_{i}"
            for i, col in enumerate(df.columns)
        ]

        # Drop rows that are entirely empty
        df = df.dropna(how="all").reset_index(drop=True)

        if df.empty:
            return []

        headers = list(df.columns)
        documents: list[Document] = []

        for batch_start in range(0, len(df), self._STRUCTURED_ROWS_PER_DOC):
            batch_end = min(batch_start + self._STRUCTURED_ROWS_PER_DOC, len(df))
            batch = df.iloc[batch_start:batch_end]

            rows_text_parts: list[str] = []
            for row_idx, (_, row) in enumerate(batch.iterrows(), start=batch_start + 1):
                cells = [
                    f"{h}: {str(v).strip()}" if pd.notna(v) else f"{h}: N/A"
                    for h, v in zip(headers, row)
                ]
                rows_text_parts.append(
                    f"Row {row_idx}:\n{self._STRUCTURED_COL_SEP.join(cells)}"
                )

            page_content = "\n\n".join(rows_text_parts)

            metadata = {
                "source": file_path,
                "format": "structured_data",
                "row_range": f"{batch_start + 1}-{batch_end}",
                "total_rows": len(df),
                "columns": headers,
            }
            if sheet_name is not None:
                metadata["sheet_name"] = sheet_name

            documents.append(
                Document(page_content=page_content, metadata=metadata)
            )

        return documents

    def load_csv_file(self, file_path: str) -> list[Document]:
        """
        Load a CSV file and convert it into LangChain Documents
        using the row-with-headers serialization strategy.
        """
        try:
            df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="latin-1", on_bad_lines="skip")

        logger.info(f"CSV loaded: {file_path} — {len(df)} rows, {len(df.columns)} columns")
        return self._dataframe_to_documents(df, file_path)

    def load_excel_file(self, file_path: str) -> list[Document]:
        """
        Load an Excel file (.xlsx / .xls) and convert every sheet
        into LangChain Documents using the row-with-headers strategy.
        Multiple sheets are handled individually with sheet-name metadata.
        """
        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            logger.error(f"Failed to open Excel file {file_path}: {e}")
            return None

        all_documents: list[Document] = []

        for sheet_name in xls.sheet_names:
            df = xls.parse(sheet_name)
            logger.info(f"Excel sheet '{sheet_name}' loaded: "
                        f"{len(df)} rows, {len(df.columns)} columns")
            sheet_docs = self._dataframe_to_documents(
                df, file_path, sheet_name=sheet_name
            )
            all_documents.extend(sheet_docs)

        return all_documents if all_documents else None

    def get_file_content(self, file_id: str):
        file_path = self.get_file_path(file_id)
        if not os.path.exists(file_path):
            return None
        
        file_extension = self.get_file_extension(file_id)

        if file_extension == processingenum.TXT.value:
            return self.load_txt_file(file_path)
        elif file_extension == processingenum.PDF.value:
            return self.load_pdf_file(file_path)
        elif file_extension == processingenum.DOCX.value:
            return self.load_docx_file(file_path)
        elif file_extension == processingenum.MD.value:
            return self.load_md_file(file_path)
        elif file_extension == processingenum.CSV.value:
            return self.load_csv_file(file_path)
        elif file_extension in (processingenum.XLSX.value, processingenum.XLS.value):
            return self.load_excel_file(file_path)
        else:
            return None

    def get_file_chunks(self, file_content: list, file_id: str,
                            chunk_size: int=1000, overlap_size: int=200):
        """
        Chunk parsed Documents for embedding.

        For non-PDF sources the behaviour is unchanged: hand every Document to
        the RecursiveCharacterTextSplitter as-is (the CSV / Excel / Markdown
        loaders already produce reasonably-sized, self-describing Documents).

        For PDFs the naive "pass every element through the splitter" strategy
        is what causes Issues 1-4:

        * PyMuPDF emits one Document per *text block*, so a paragraph split
          across visual lines / columns arrives as several tiny Documents.
          The splitter never joins them, so most chunks end up far below the
          configured ``chunk_size`` (Issue 1) and section headings become
          isolated micro-chunks (Issue 2).
        * A paragraph broken across two adjacent text blocks becomes two
          chunks with mid-sentence cuts, because the splitter has no way to
          bridge Documents (Issue 3).
        * Serialized table batches and image / page-scan descriptions carry
          a self-locating header on their first line. If the splitter cuts
          them, every continuation chunk loses that header and its citation
          identity (Issue 4).

        The routing here fixes all four in one place:

          1. **Group** PDF text elements per page and join them with paragraph
             separators. The splitter is then free to merge small text blocks
             up to ``chunk_size`` — exactly the behaviour the caller expects
             — and to break on paragraph / sentence boundaries.
          2. **Passthrough** PDF ``table`` / ``image`` / ``page_scan`` elements
             atomically. ``_serialize_table`` already batches by character
             budget so each batch fits comfortably in one chunk; image and
             page-scan bodies are short single passages that must stay whole.
             Only when a single atomic body is larger than ``2 * chunk_size``
             do we fall back to splitting it — and in that case we re-prepend
             its ``[... | Page: N | ...]`` header line to every continuation
             so the citation identifier survives (Issue 4 safety net).
        """
        if not file_content:
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap_size,
            length_function=len,
            is_separator_regex=False,
        )

        pdf_docs = [d for d in file_content if d.metadata.get("format") == "pdf"]
        other_docs = [d for d in file_content if d.metadata.get("format") != "pdf"]

        chunks: list[Document] = []

        if pdf_docs:
            chunks.extend(
                self._chunk_pdf_documents(pdf_docs, text_splitter,
                                          chunk_size, overlap_size)
            )

        if other_docs:
            texts = [d.page_content for d in other_docs]
            metas = [d.metadata for d in other_docs]
            chunks.extend(text_splitter.create_documents(texts, metadatas=metas))

        return chunks

    # --- PDF chunk routing ---------------------------------------------------
    _ATOMIC_PDF_TYPES = frozenset({"table", "image", "page_scan"})

    def _chunk_pdf_documents(self, pdf_docs: list[Document],
                             text_splitter: RecursiveCharacterTextSplitter,
                             chunk_size: int,
                             overlap_size: int) -> list[Document]:
        """See ``get_file_chunks`` docstring for rationale."""
        # Group by page. Missing ``page`` (should not happen with the current
        # loader) is bucketed together and processed last.
        by_page: dict[int, list[Document]] = {}
        for d in pdf_docs:
            by_page.setdefault(d.metadata.get("page", -1), []).append(d)

        out: list[Document] = []

        for page in sorted(by_page.keys()):
            # Preserve reading order within the page.
            page_elements = sorted(
                by_page[page],
                key=lambda d: d.metadata.get("reading_order", 0),
            )

            text_buffer: list[Document] = []

            def _flush_text_buffer():
                if not text_buffer:
                    return
                # Merge adjacent text blocks with a paragraph separator so the
                # splitter can find real paragraph / sentence boundaries.
                joined = "\n\n".join(d.page_content for d in text_buffer)
                # Base metadata: keep page/source/format; drop per-block
                # coordinates that no longer apply to the merged chunk.
                base = dict(text_buffer[0].metadata)
                for k in ("bbox", "reading_order"):
                    base.pop(k, None)
                base["content_type"] = "text"
                out.extend(
                    text_splitter.create_documents([joined], metadatas=[base])
                )
                text_buffer.clear()

            for d in page_elements:
                if d.metadata.get("content_type") in self._ATOMIC_PDF_TYPES:
                    # An atomic element interrupts the text stream. Flush any
                    # pending text FIRST so reading order is preserved, then
                    # pass the atomic element through.
                    _flush_text_buffer()
                    out.extend(
                        self._split_atomic_pdf_element(
                            d, text_splitter, chunk_size, overlap_size
                        )
                    )
                else:
                    text_buffer.append(d)

            _flush_text_buffer()

        return out

    @staticmethod
    def _split_atomic_pdf_element(doc: Document,
                                  text_splitter: RecursiveCharacterTextSplitter,
                                  chunk_size: int,
                                  overlap_size: int) -> list[Document]:
        """
        Emit an atomic PDF element (table batch / image description / page
        scan) as a single Document when it fits, or as multiple header-
        preserving Documents when it truly exceeds ``2 * chunk_size``.
        """
        body = doc.page_content
        if len(body) <= chunk_size * 2:
            return [doc]

        # Isolate the "[... | Page: N | ...]" header line so we can re-prepend
        # it to every continuation, preserving the citation identifier.
        header_line = ""
        rest = body
        if body.startswith("["):
            newline_pos = body.find("\n")
            close_pos = body.find("]")
            if 0 <= close_pos < (newline_pos if newline_pos != -1 else len(body)):
                # Header ends at either the closing ']' or the first newline,
                # whichever comes first.
                split_at = newline_pos if newline_pos != -1 else close_pos + 1
                header_line = body[:split_at].rstrip()
                rest = body[split_at:].lstrip("\n")

        if not header_line:
            # No recognizable header: fall back to a plain split.
            return text_splitter.create_documents([body], metadatas=[doc.metadata])

        # Leave headroom in each sub-chunk for the re-prepended header.
        inner_size = max(200, chunk_size - len(header_line) - 2)
        inner_splitter = RecursiveCharacterTextSplitter(
            chunk_size=inner_size,
            chunk_overlap=min(overlap_size, inner_size // 2),
            length_function=len,
            is_separator_regex=False,
        )
        parts = inner_splitter.split_text(rest)
        results: list[Document] = []
        for idx, part in enumerate(parts):
            meta = dict(doc.metadata)
            if idx > 0:
                meta["continuation"] = True
            results.append(
                Document(page_content=f"{header_line}\n{part}", metadata=meta)
            )
        return results



