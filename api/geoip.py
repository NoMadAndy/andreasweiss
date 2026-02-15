"""GeoIP lookup via local MaxMind GeoLite2-City database."""

import os

GEOIP_PATH = os.environ.get("GEOIP_PATH", "/data/geoip/GeoLite2-City.mmdb")

_reader = None
_init_attempted = False

UNKNOWN = {"city": "unknown", "region": "unknown", "country": "unknown"}


def _get_reader():
    global _reader, _init_attempted
    if _reader is not None:
        return _reader
    if _init_attempted:
        return None
    _init_attempted = True
    try:
        import geoip2.database
        if os.path.exists(GEOIP_PATH):
            _reader = geoip2.database.Reader(GEOIP_PATH)
            return _reader
    except ImportError:
        pass
    return None


def reload_reader():
    """Close existing reader and force re-initialization."""
    global _reader, _init_attempted
    if _reader is not None:
        try:
            _reader.close()
        except Exception:
            pass
    _reader = None
    _init_attempted = False
    return _get_reader() is not None


def status() -> dict:
    """Return status info about the GeoIP database."""
    import os
    reader = _get_reader()
    db_exists = os.path.exists(GEOIP_PATH)
    info = {
        "loaded": reader is not None,
        "db_exists": db_exists,
        "db_path": GEOIP_PATH,
        "db_size_mb": round(os.path.getsize(GEOIP_PATH) / 1048576, 1) if db_exists else 0,
    }
    if reader is not None:
        try:
            meta = reader.metadata()
            from datetime import datetime
            info["db_type"] = meta.database_type
            info["build_date"] = datetime.fromtimestamp(meta.build_epoch).strftime("%Y-%m-%d %H:%M")
            info["node_count"] = meta.node_count
        except Exception:
            pass
    return info


def lookup(ip: str) -> dict:
    """Return {"city", "region", "country"} for the given IP. Never raises."""
    reader = _get_reader()
    if reader is None:
        return dict(UNKNOWN)
    try:
        r = reader.city(ip)
        return {
            "city": r.city.name or "unknown",
            "region": (
                r.subdivisions.most_specific.name
                if r.subdivisions
                else "unknown"
            ),
            "country": r.country.name or "unknown",
        }
    except Exception:
        return dict(UNKNOWN)
