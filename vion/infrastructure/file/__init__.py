from typing import cast

from .base import CreatePath
from .services import (
	JSON,
	YAML,
	TEXT,
	orjson,
	yaml
)


_default = (
	1800, # cache_ttl_seconds
	500   # cache_maxsize
)

text_file = TEXT(*_default)
json_file = cast(JSON, JSON(*_default) if orjson else None)
yaml_file = cast(YAML, YAML(*_default) if yaml and orjson else None)

create_path = CreatePath()


__all__ = (
	'text_file',
	'json_file',
	'yaml_file',
	'create_path'
)
