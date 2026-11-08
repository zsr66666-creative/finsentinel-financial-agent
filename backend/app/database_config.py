from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    is_sqlite: bool
    safe_url: str

    @classmethod
    def from_url(cls, url: str) -> "DatabaseConfig":
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"sqlite", "postgresql", "postgresql+psycopg"}:
            raise ValueError(f"Unsupported database URL scheme: {scheme or '<missing>'}")
        safe_netloc = parsed.netloc
        if parsed.password is not None:
            user = parsed.username or ""
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            safe_netloc = f"{user}:***@{host}{port}"
        safe = urlunsplit((parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment))
        return cls(url=url, is_sqlite=scheme == "sqlite", safe_url=safe)
