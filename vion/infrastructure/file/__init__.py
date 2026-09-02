"""
File I/O module initialization.

Instantiates and exports global File I/O handlers for text, JSON, and YAML formats,
as well as path creation helpers.
"""

from typing import cast

from .base import CreatePath
from .service import (
	JSON,
	YAML,
	TEXT,
	HAS_ORJSON,
	HAS_YAML
)


_DEFAULT_CACHE_CONFIG = (
	1800,  # cache_ttl_seconds
	500    # cache_maxsize
)

text_file = TEXT(*_DEFAULT_CACHE_CONFIG)
json_file = cast(JSON, JSON(*_DEFAULT_CACHE_CONFIG) if HAS_ORJSON else None)
yaml_file = cast(YAML, YAML(*_DEFAULT_CACHE_CONFIG) if HAS_YAML and HAS_ORJSON else None)

create_path = CreatePath()


__all__ = (
	'text_file',
	'json_file',
	'yaml_file',
	'create_path'
)
