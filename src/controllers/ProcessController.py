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
    # Rows per serialized table batch (preamble + headers repeated each batch).
    _TABLE_ROWS_PER_BATCH = 25
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
            serialized = self._serialize_table(table, page_index, table_index)
            if not serialized:
                continue
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

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Normalize extracted text: Unicode NFKC, strip control chars,
        dehyphenate across line breaks, and collapse excess whitespace while
        preserving intentional line boundaries.
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
        # Collapse 3+ blank lines into a single blank line
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def _clean_cell(cls, value) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    # ------------------------------------------------------------------
    # Table serialization (hybrid: markdown for regular, rows for irregular)
    # ------------------------------------------------------------------
    def _serialize_table(self, table, page_index: int, table_index: int):
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
        if not columns or not data_rows:
            return None

        # A table is "regular" when every row matches the column count.
        regular = all(len(r) == len(columns) for r in data_rows)
        total = len(data_rows)
        batches = []

        for start in range(0, total, self._TABLE_ROWS_PER_BATCH):
            end = min(start + self._TABLE_ROWS_PER_BATCH, total)
            batch = data_rows[start:end]
            row_range = f"{start + 1}-{end}"

            if regular:
                preamble = (f"[PDF Table | Page: {page_index + 1} | "
                            f"Table: {table_index} | Rows: {row_range} | "
                            f"Columns: {', '.join(columns)}]")
                lines = [
                    preamble,
                    "| " + " | ".join(columns) + " |",
                    "| " + " | ".join(["---"] * len(columns)) + " |",
                ]
                for r in batch:
                    cells = [self._clean_cell(c) for c in r]
                    lines.append("| " + " | ".join(cells) + " |")
                text = "\n".join(lines)
            else:
                preamble = (f"[PDF Table | Page: {page_index + 1} | "
                            f"Table: {table_index} | Rows: {row_range} | "
                            f"Columns: {' | '.join(columns)}]")
                lines = [preamble]
                for offset, r in enumerate(batch, start=start + 1):
                    lines.append(f"Row {offset}:")
                    cells = [f"{h}: {self._clean_cell(c)}"
                             for h, c in zip(columns, r)]
                    lines.append(" | ".join(cells))
                text = "\n".join(lines)

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
                "page": page_index,
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

        text_splitter = RecursiveCharacterTextSplitter( 
                            chunk_size=chunk_size, 
                            chunk_overlap=overlap_size, 
                            length_function=len,
                            is_separator_regex=False
                        )

        file_content_texts = [
            rec.page_content
            for rec in file_content
        ]

        file_content_metadata = [
            rec.metadata
            for rec in file_content
        ]

        chunks = text_splitter.create_documents(
            file_content_texts,
            metadatas=file_content_metadata
        )

        return chunks