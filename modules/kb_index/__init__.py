"""Shared KB → Master Index writer.

A tiny, FastAPI-free helper that any Eva agent can import to append a titled
link/summary row to the Eva Master Index Google Doc. See ``index_writer``.
"""

from .index_writer import (  # noqa: F401
    IndexWriter,
    StubIndexTransport,
    GoogleDocsIndexTransport,
    append_to_index,
    make_index_transport,
)
