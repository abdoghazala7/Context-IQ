import os
import re
import httpx
import aiofiles
from bs4 import BeautifulSoup
from langchain_core.documents import Document
from .BaseController import basecontroller
from .ProjectController import projectController
from models import responsesignal

import logging

logger = logging.getLogger(__name__)


class urlcontroller(basecontroller):
    """
    Controller responsible for ingesting content from web URLs.
    Downloads the page, extracts clean text, and saves it as
    a local text file so it can be processed by the existing pipeline.
    """

    # Tags that carry meaningful page content
    CONTENT_TAGS = [
        "article", "main", "section",
        "p", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "td", "th", "blockquote", "pre", "code",
        "figcaption", "summary", "details",
    ]

    # Tags whose entire subtree should be stripped
    STRIP_TAGS = [
        "script", "style", "nav", "footer", "header",
        "aside", "form", "noscript", "svg", "iframe",
    ]

    def __init__(self):
        super().__init__()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def validate_url(self, url: str) -> bool:
        """Basic URL format validation."""
        pattern = re.compile(
            r"^https?://"
            r"(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}"
            r"(?::\d+)?"
            r"(?:/[^\s]*)?$"
        )
        return bool(pattern.match(url))

    async def fetch_url_content(self, url: str) -> str | None:
        """
        Fetch the raw HTML content of a URL using httpx (async).
        Returns None on failure.
        """
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; Context-IQ/1.0; "
                        "+https://github.com/abdoghazala7/Context-IQ)"
                    )
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.error(f"Failed to fetch URL {url}: {e}")
            return None

    def extract_clean_text(self, html: str, source_url: str) -> Document | None:
        """
        Parse raw HTML and return a LangChain Document with clean,
        semantically-meaningful text content.
        """
        soup = BeautifulSoup(html, "lxml")

        # Remove noisy elements
        for tag in soup.find_all(self.STRIP_TAGS):
            tag.decompose()

        # Try to find the main content area first
        content_root = (
            soup.find("article")
            or soup.find("main")
            or soup.find("div", {"role": "main"})
            or soup.body
            or soup
        )

        # Extract text from content-bearing tags
        paragraphs: list[str] = []
        for element in content_root.find_all(self.CONTENT_TAGS):
            text = element.get_text(separator=" ", strip=True)
            if text and len(text) > 20:
                paragraphs.append(text)

        if not paragraphs:
            return None

        clean_text = "\n\n".join(paragraphs)

        # Extract page title for metadata
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        doc = Document(
            page_content=clean_text,
            metadata={
                "source": source_url,
                "format": "url",
                "title": title,
            },
        )
        return doc

    async def save_url_content_as_file(
        self, text: str, url: str, project_id: int
    ) -> tuple[str, str]:
        """
        Persist the extracted text to disk as a .txt file within the
        project directory, following the existing file-naming conventions.

        Returns:
            (file_path, file_id)
        """
        # Derive a human-readable slug from the URL
        slug = re.sub(r"https?://", "", url)
        slug = re.sub(r"[^\w]", "_", slug)[:80]
        file_name = f"{slug}.txt"

        random_key = self.generate_random_string()
        project_path = projectController().get_project_path(project_id=project_id)

        file_id = f"{random_key}_{file_name}"
        file_path = os.path.join(project_path, file_id)

        while os.path.exists(file_path):
            random_key = self.generate_random_string()
            file_id = f"{random_key}_{file_name}"
            file_path = os.path.join(project_path, file_id)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(text)

        return file_path, file_id
