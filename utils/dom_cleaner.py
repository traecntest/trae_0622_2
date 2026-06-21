from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

_STRIP_TAGS = {"script", "style", "noscript", "iframe", "object", "embed",
               "svg", "canvas", "link", "meta", "head", "button", "form",
               "input", "select", "textarea", "nav", "footer", "aside"}

_INLINE_NOISE_TAGS = {"span", "font", "u", "center", "marquee"}

_BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul",
               "ol", "blockquote", "pre", "table", "tr", "td", "th", "br", "hr",
               "section", "article", "main", "header", "figure", "figcaption"}

_KEEP_ATTRS = {"href", "src", "alt", "colspan", "rowspan"}


@dataclass
class CleanResult:
    text: str
    html: str
    title: str = ""
    source_url: str = ""
    images: list = field(default_factory=list)
    tables: int = 0
    paragraphs: int = 0


class DOMCleaner:
    def __init__(self, keep_images: bool = True):
        self.keep_images = keep_images

    def clean(self, raw_html: str, source_url: str = "") -> CleanResult:
        if not raw_html or not raw_html.strip():
            return CleanResult(text="", html="")
        soup = BeautifulSoup(raw_html, "lxml")

        title = self._extract_title(soup)

        for tag in soup(list(_STRIP_TAGS)):
            tag.decompose()

        self._unwrap_inline_noise(soup)
        self._strip_attrs(soup)
        self._clean_empty(soup)
        self._normalize_links(soup, source_url)
        if not self.keep_images:
            for img in soup.find_all("img"):
                img.decompose()

        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                images.append(src)

        tables = len(soup.find_all("table"))
        paragraphs = len(soup.find_all("p"))

        body = soup.body or soup
        html = body.decode_contents()
        text = body.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return CleanResult(
            text=text,
            html=html,
            title=title,
            source_url=source_url,
            images=images,
            tables=tables,
            paragraphs=paragraphs,
        )

    def to_plain_text(self, raw_html: str) -> str:
        return self.clean(raw_html).text

    def _extract_title(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""

    def _unwrap_inline_noise(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(_INLINE_NOISE_TAGS):
            tag.unwrap()

    def _strip_attrs(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(True):
            kept = {k: v for k, v in tag.attrs.items() if k.lower() in _KEEP_ATTRS}
            tag.attrs = kept

    def _normalize_links(self, soup: BeautifulSoup, source_url: str) -> None:
        from urllib.parse import urljoin
        for a in soup.find_all("a"):
            href = a.get("href", "")
            if href and source_url:
                try:
                    a["href"] = urljoin(source_url, href)
                except Exception:
                    pass
            if not a.get_text(strip=True):
                a.decompose()

    def _clean_empty(self, soup: BeautifulSoup) -> None:
        changed = True
        while changed:
            changed = False
            for tag in soup.find_all(_BLOCK_TAGS - {"br", "hr"}):
                if tag.name in ("ul", "ol", "table"):
                    continue
                has_text = any(
                    isinstance(c, NavigableString) and str(c).strip()
                    for c in tag.children
                )
                has_child = any(isinstance(c, Tag) for c in tag.children)
                if not has_text and not has_child:
                    tag.decompose()
                    changed = True


dom_cleaner = DOMCleaner()
