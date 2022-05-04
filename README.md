# resotoclient-python
Python client for Resoto

## Installation

```bash
pip install resotoclient
```

## Usage

```python
from resotoclient import ResotoClient

client = ResotoClient(url="https://localhost:8900", psk="changeme")
instances_csv = client.cli_execute("search is(instance) | tail 5 | list --csv")

for instance in instances_csv:
    print(instance)
```

For more examples see the examples directory.

## Publish

- bump the version number in pyproject.toml
- `poetry build`
- `poetry publish`
