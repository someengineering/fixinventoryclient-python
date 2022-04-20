# resoto-client-python
Python client for Resoto

## Installation

```bash
    pip install resoto-client-python
```

## Usage

```python
from resotoclient import ResotoClient

client = ResotoClient(url="https://localhost:8900", psk=None)
instances_csv = client.cli_execute("resoto", "search is(instance) | tail 5 | list --csv")

for instance in instances_csv:
    print(instance)
```

For more examples see the examples directory.