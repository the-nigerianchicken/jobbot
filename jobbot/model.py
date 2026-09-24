"""Core data types. One Posting shape regardless of which ATS it came from."""
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional
import hashlib


@dataclass
class Posting:
    source: str                 # greenhouse | lever | ashby | aggregate
    org: str                    # board slug on that source
    company: str
    title: str
    location: str
    url: str
    apply_url: str
    posted_at: Optional[datetime]   # the EMPLOYER's own timestamp, never a scraper's
    description: str = ""
    deadline: Optional[datetime] = None
    remote: bool = False
    raw_id: str = ""

    @property
    def uid(self) -> str:
        """Stable identity. Novelty is decided on this, not on any date."""
        basis = f"{self.source}:{self.org}:{self.raw_id or self.url}"
        return hashlib.sha1(basis.encode()).hexdigest()[:16]

    @property
    def age_hours(self) -> Optional[float]:
        if not self.posted_at:
            return None
        return (datetime.now(timezone.utc) - self.posted_at).total_seconds() / 3600

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        for k in ("posted_at", "deadline"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        d["description"] = d["description"][:400]
        return d


@dataclass
class Match:
    posting: Posting
    tier: int
    reasons: list = field(default_factory=list)
