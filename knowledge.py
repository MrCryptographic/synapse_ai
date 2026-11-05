import hashlib
import http.client
import ipaddress
import math
import re
import socket
import sqlite3
import ssl
import uuid
from collections import Counter
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from pypdf.errors import PdfReadError
from urllib.parse import urljoin, urlsplit, urlunsplit

from pypdf import PdfReader


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PAGE_BYTES = 1 * 1024 * 1024
MAX_PAGES_PER_SITE = 8
MAX_SITE_TEXT = 200_000
MAX_FILE_TEXT = 200_000
MAX_CHUNKS_PER_SOURCE = 350
MAX_CHUNKS_PER_USER = 10_000
CHUNK_SIZE = 900
CHUNK_OVERLAP = 140
MAX_CONTEXT_CHARS = 12_000
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf"}
BLOCKED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


class PageTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self._blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in BLOCKED_TAGS:
            self._blocked_depth += 1
        if tag == "a" and attributes.get("href") and len(self.links) < 2000:
            self.links.append(attributes["href"])
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in BLOCKED_TAGS and self._blocked_depth:
            self._blocked_depth -= 1
        if tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._blocked_depth:
            self.parts.append(data)


def _normalized_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Enter a website URL under 2,048 characters.")
    if any(character in value for character in "\r\n\x00"):
        raise ValueError("The website URL contains invalid characters.")
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use a complete public http:// or https:// website URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Website URLs cannot include embedded credentials.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("The website URL has an invalid port.") from error
    expected_port = 443 if parsed.scheme == "https" else 80
    if port not in (None, expected_port):
        raise ValueError("Only standard HTTP and HTTPS website ports are allowed.")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Local and private-network websites cannot be fetched.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Local and private-network websites cannot be fetched.")
    netloc = f"[{host}]" if ":" in host else host
    path = parsed.path or "/"
    normalized = urlunsplit((parsed.scheme, netloc, path, parsed.query, ""))
    return normalized, host


def _validate_public_host(host):
    try:
        addresses = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ValueError(f"Could not resolve website host: {error}") from error
    if not addresses:
        raise ValueError("Could not resolve the website host.")
    public_addresses = []
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("The website resolves to a local or non-public network address.")
        if ip not in public_addresses:
            public_addresses.append(ip)
    return public_addresses


def _pinned_connection(scheme, host, address, timeout):
    port = 443 if scheme == "https" else 80
    raw_socket = socket.create_connection((str(address), port), timeout=timeout)
    if scheme == "https":
        try:
            return ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
        except Exception:
            raw_socket.close()
            raise
    return raw_socket


def _fetch_page(url, expected_host, expected_scheme):
    current_url = url
    for _ in range(4):
        current_url, host = _normalized_url(current_url)
        if host != expected_host:
            raise ValueError("Website redirects must stay on the original hostname.")
        parsed = urlsplit(current_url)
        if parsed.scheme != expected_scheme:
            raise ValueError("Website redirects must keep the original HTTP or HTTPS scheme.")
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        host_header = f"[{host}]" if ":" in host else host
        last_error = None
        for address in _validate_public_host(host):
            connection = None
            try:
                connection = _pinned_connection(parsed.scheme, host, address, timeout=8)
                connection.settimeout(8)
                request = http.client.HTTPConnection(host)
                request.sock = connection
                request.request(
                    "GET",
                    target,
                    headers={
                        "Host": host_header,
                        "User-Agent": "SynapseKnowledgeBot/1.0",
                        "Accept": "text/html, application/xhtml+xml, text/plain",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                )
                response = request.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    response.read(1024)
                    if not location:
                        raise ValueError("The website returned an invalid redirect.")
                    current_url = urljoin(current_url, location)
                    break
                if response.status < 200 or response.status >= 300:
                    raise ValueError(f"The website returned HTTP {response.status}.")
                content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    raise ValueError(f"Unsupported website content type: {content_type or 'unknown'}.")
                if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
                    raise ValueError("Compressed website responses are not supported.")
                body = response.read(MAX_PAGE_BYTES + 1)
                if len(body) > MAX_PAGE_BYTES:
                    raise ValueError("A website page exceeded the 1 MB download limit.")
                content_type_header = Message()
                content_type_header["content-type"] = response.getheader("Content-Type", "")
                encoding = content_type_header.get_content_charset() or "utf-8"
                try:
                    return body.decode(encoding, errors="replace"), content_type, current_url
                except LookupError:
                    return body.decode("utf-8", errors="replace"), content_type, current_url
            except ValueError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException) as error:
                last_error = error
            finally:
                if connection is not None:
                    connection.close()
        else:
            raise ValueError(f"Could not fetch {current_url}: {last_error or 'connection failed'}.")
    raise ValueError("The website redirected too many times.")


def _extract_page_text(body, content_type):
    if content_type == "text/plain":
        return body, []
    parser = PageTextParser()
    parser.feed(body)
    parser.close()
    text = re.sub(r"[ \t]+\n", "\n", "".join(parser.parts))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), parser.links


def crawl_website(url):
    start_url, host = _normalized_url(url)
    scheme = urlsplit(start_url).scheme
    pages = []
    visited = set()
    queue = [start_url]
    while queue and len(pages) < MAX_PAGES_PER_SITE:
        current_url = queue.pop(0)
        current_url, current_host = _normalized_url(current_url)
        if current_host != host or current_url in visited:
            continue
        visited.add(current_url)
        body, content_type, final_url = _fetch_page(current_url, host, scheme)
        visited.add(final_url)
        text, links = _extract_page_text(body, content_type)
        if text:
            pages.append((final_url, text))
        for link in links:
            if len(queue) >= MAX_PAGES_PER_SITE * 10:
                break
            try:
                candidate, candidate_host = _normalized_url(urljoin(final_url, link))
            except (ValueError, UnicodeError):
                continue
            if (
                candidate_host == host
                and urlsplit(candidate).scheme == scheme
                and candidate not in visited
                and candidate not in queue
            ):
                queue.append(candidate)
    if not pages:
        raise ValueError("No readable text was found on that website.")
    total = sum(len(text) for _, text in pages)
    if total > MAX_SITE_TEXT:
        raise ValueError("Website text exceeded the 200,000 character import limit.")
    return pages


def extract_uploaded_text(filename, content):
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_TEXT_EXTENSIONS:
        raise ValueError("Supported knowledge files are TXT, Markdown, HTML, and PDF.")
    if not content:
        raise ValueError("The selected file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("Knowledge files must be 10 MB or smaller.")
    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError("The file contents are not a valid PDF.")
        try:
            import io
            reader = PdfReader(io.BytesIO(content))
        except (PdfReadError, OSError, ValueError, TypeError) as error:
            raise ValueError(f"Could not extract PDF text: {error}") from error
        if len(reader.pages) > 100:
            raise ValueError("PDF knowledge files are limited to 100 pages.")
        try:
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except (PdfReadError, OSError, ValueError, TypeError, KeyError) as error:
            raise ValueError(f"Could not extract PDF text: {error}") from error
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Text and HTML files must use UTF-8 encoding.") from error
        if extension in {".html", ".htm"}:
            text, _ = _extract_page_text(text, "text/html")
    text = text.strip()
    if not text:
        raise ValueError("No readable text was found in that file.")
    if len(text) > MAX_FILE_TEXT:
        raise ValueError("Extracted document text exceeded the 200,000 character limit.")
    return text


def split_into_chunks(text):
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > CHUNK_SIZE:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:CHUNK_SIZE])
            paragraph = paragraph[CHUNK_SIZE - CHUNK_OVERLAP:]
        if current and len(current) + len(paragraph) + 2 > CHUNK_SIZE:
            chunks.append(current)
            current = current[-CHUNK_OVERLAP:] + "\n\n" + paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks[:MAX_CHUNKS_PER_SOURCE]


def database_path(root, user_id):
    owner_key = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return Path(root) / f"{owner_key}.sqlite3"


def _connect(root, user_id):
    path = database_path(root, user_id)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            origin TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            origin TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL
        )"""
    )
    chunk_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()
    }
    if "origin" not in chunk_columns:
        connection.execute("ALTER TABLE chunks ADD COLUMN origin TEXT NOT NULL DEFAULT ''")
    connection.commit()
    return connection


def add_source(root, user_id, title, source_type, origin, documents):
    documents = list(documents)
    combined_text = "\n\n".join(text for _, text in documents).strip()
    if not combined_text:
        raise ValueError("No readable text was found in the selected source.")
    if len(combined_text) > MAX_SITE_TEXT:
        raise ValueError("Source text exceeded the 200,000 character limit.")
    chunks = []
    for document_origin, text in documents:
        chunks.extend(
            (document_origin[:2048], chunk)
            for chunk in split_into_chunks(text)
        )
    if len(chunks) > MAX_CHUNKS_PER_SOURCE:
        chunks = chunks[:MAX_CHUNKS_PER_SOURCE]
    if not chunks:
        raise ValueError("No searchable text chunks could be created.")
    source_id = str(uuid.uuid4())
    with _connect(root, user_id) as connection:
        source_count, chunk_count = connection.execute(
            "SELECT (SELECT COUNT(*) FROM sources), (SELECT COUNT(*) FROM chunks)"
        ).fetchone()
        if source_count >= 500 or chunk_count + len(chunks) > MAX_CHUNKS_PER_USER:
            raise ValueError("Your knowledge library has reached its storage limit.")
        connection.execute(
            "INSERT INTO sources (id, title, source_type, origin, created_at) VALUES (?, ?, ?, ?, ?)",
            (source_id, title[:160], source_type, origin[:2048], datetime.now(timezone.utc).isoformat()),
        )
        connection.executemany(
            "INSERT INTO chunks (source_id, ordinal, origin, content) VALUES (?, ?, ?, ?)",
            [
                (source_id, ordinal, origin, content)
                for ordinal, (origin, content) in enumerate(chunks)
            ],
        )
    return {"id": source_id, "title": title[:160], "type": source_type, "origin": origin[:2048], "chunks": len(chunks)}


def list_sources(root, user_id):
    with _connect(root, user_id) as connection:
        rows = connection.execute(
            """SELECT sources.id, sources.title, sources.source_type, sources.origin,
                      sources.created_at, COUNT(chunks.id) AS chunks
               FROM sources LEFT JOIN chunks ON chunks.source_id = sources.id
               GROUP BY sources.id ORDER BY sources.created_at DESC"""
        ).fetchall()
    return [
        {
            "id": row["id"], "title": row["title"], "type": row["source_type"],
            "origin": row["origin"], "created_at": row["created_at"], "chunks": row["chunks"],
        }
        for row in rows
    ]


def delete_source(root, user_id, source_id):
    with _connect(root, user_id) as connection:
        cursor = connection.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        return cursor.rowcount > 0


def retrieve_context(root, user_id, query):
    query_terms = [term.casefold() for term in TOKEN_PATTERN.findall(query)]
    if not query_terms:
        return ""
    term_counts = Counter(query_terms)
    with _connect(root, user_id) as connection:
        rows = connection.execute(
            """SELECT chunks.content, sources.title, sources.origin, chunks.origin AS chunk_origin
               FROM chunks JOIN sources ON sources.id = chunks.source_id"""
        ).fetchall()
    if not rows:
        return ""
    document_frequency = Counter()
    tokenized = []
    for row in rows:
        counts = Counter(token.casefold() for token in TOKEN_PATTERN.findall(row["content"]))
        document_frequency.update(counts.keys())
        tokenized.append((row, counts))
    scored = []
    for row, counts in tokenized:
        score = sum(
            frequency * math.log(1 + len(rows) / (1 + document_frequency[term]))
            * (1 + math.log(counts[term]))
            for term, frequency in term_counts.items()
            if counts[term]
        )
        if score:
            scored.append((score, row))
    scored.sort(key=lambda result: result[0], reverse=True)
    excerpts = []
    total_length = 0
    for _, row in scored[:8]:
        origin = row["chunk_origin"] or row["origin"]
        excerpt = f"[{row['title']} — {origin}]\n{row['content']}"
        if total_length + len(excerpt) > MAX_CONTEXT_CHARS:
            excerpt = excerpt[:MAX_CONTEXT_CHARS - total_length]
        if not excerpt:
            break
        excerpts.append(excerpt)
        total_length += len(excerpt)
        if total_length >= MAX_CONTEXT_CHARS:
            break
    return "\n\n---\n\n".join(excerpts)
