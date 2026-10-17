"""Board sources. Each module exposes fetch(client, slug, company) and is_open(client, slug, job_id)."""
from __future__ import annotations

from . import ashby, greenhouse, lever

MODULES = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
