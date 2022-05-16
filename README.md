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

## Test


The tests expect a ResotoCore on localhost with the default PSK `changeme`.
You can start it locally via:

```bash
$> resotocore --graphdb-database resotoclient_test --psk changeme
```

A local test environment is required. See the [contribution guide](https://resoto.com/docs/contributing/components) for instructions.
When the virtual environment is available, use those commands to set up the project and run the tests:

```bash
$> pip install --upgrade pip poetry nox nox-poetry
$> nox
```

For more examples see the examples directory.

## Publish

- bump the version number in pyproject.toml
- `poetry build`
- `poetry publish`
