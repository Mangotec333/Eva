# EVA Deal Scout — scrapers package
from .flippa import fetch_flippa_listing
from .empire_flippers import fetch_ef_listing

__all__ = ["fetch_flippa_listing", "fetch_ef_listing"]
