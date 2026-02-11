import os
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

    def __init__(self, project_id: str):
        super().__init__()
        self.project_id = project_id
        self.project_path = projectController().get_project_path(project_id=project_id)

    def get_file_path(self, file_id: str) -> str:
        return os.path.join(self.project_path, file_id)
    
    def get_file_extension(self, file_id: str) -> str:
        return os.path.splitext(file_id)[1].lower()

    def load_txt_file(self, file_path: str):
        loader = TextLoader(file_path, encoding="utf-8")
        return loader.load()

    def load_pdf_file(self, file_path: str):
        loader = PyMuPDFLoader(file_path)
        return loader.load()

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