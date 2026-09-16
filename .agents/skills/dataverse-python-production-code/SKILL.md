---
name: dataverse-python-production-code
description: 'Write Python code for the Dataverse SDK with error handling, retries, logging, and efficient OData queries.'
---

# Instructions

Write Python for the PowerPlatform-Dataverse-Client SDK. The code must:

- Handle errors through the `DataverseError` hierarchy.
- Reuse one client connection.
- Retry HTTP 429 responses and timeouts with exponential backoff.
- Filter on the server and select only the required OData columns.
- Log enough information to audit and debug requests.
- Include type hints and docstrings.
- Follow the patterns in Microsoft's official examples.

# Code rules

## Error handling
```python
from PowerPlatform.Dataverse.core.errors import (
    DataverseError,
    ValidationError,
    MetadataError,
    HttpError,
)
import logging
import time

logger = logging.getLogger(__name__)


def operation_with_retry(max_retries=3):
    """Function with retry logic."""
    for attempt in range(max_retries):
        try:
            # Operation code
            pass
        except HttpError as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed after {max_retries} attempts: {e}")
                raise
            backoff = 2**attempt
            logger.warning(f"Attempt {attempt + 1} failed. Retrying in {backoff}s")
            time.sleep(backoff)
```

## Client management
```python
class DataverseService:
    _instance = None
    _client = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, org_url, credential):
        if self._client is None:
            self._client = DataverseClient(org_url, credential)
    
    @property
    def client(self):
        return self._client
```

## Logging
```python
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logger.info(f"Created {count} records")
logger.warning(f"Record {id} not found")
logger.error(f"Operation failed: {error}")
```

## OData queries
- Always include `select` parameter to limit columns
- Use `filter` on server (lowercase logical names)
- Use `orderby`, `top` for pagination
- Use `expand` for related records when available

## Code structure
1. Imports (stdlib, then third-party, then local)
2. Constants and enums
3. Logging configuration
4. Helper functions
5. Main service classes
6. Error handling classes
7. Usage examples

# Response contents

When the user asks for code, include the required imports, configuration,
implementation, error handling, logging, type hints, and docstrings. Include a
usage example and show how expected errors are handled.

# Checks

- Write valid Python 3.10 or newer.
- Wrap API calls in `try` and `except` blocks.
- Type every function parameter and return value.
- Add a docstring to every function.
- Retry transient failures.
- Use a logger instead of `print()`.
- Keep secrets and URLs in configuration.
- Follow PEP 8.
- Include a usage example.
