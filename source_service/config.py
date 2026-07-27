import jsonschema
from typing import Dict, Any
from .exceptions import InvalidConfigurationError


def validate_config(config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    try:
        jsonschema.validate(instance=config, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        raise InvalidConfigurationError(f"Configuration validation error: {e}")
