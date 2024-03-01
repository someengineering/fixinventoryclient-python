# fixinventoryclient-python
Python client for Fix Inventory

## Installation
```bash
pip install fixinventoryclient
```

For GraphVis and Pandas support:

```bash
pip install fixinventoryclient[extras]
```

## Usage

```python
from fixclient import FixInventoryClient

client = FixInventoryClient(url="https://localhost:8900", psk="changeme")
instances_csv = client.cli_execute("search is(instance) | tail 5 | list --csv")

for instance in instances_csv:
    print(instance)
```

### Pandas Dataframes
```python
df = client.dataframe("is(instance)")
```

### GraphViz Digraph
```python
graph = client.graphviz("is(graph_root) -->")
```

## Test
The tests expect a FixCore on localhost with the default PSK `changeme`.
You can start it locally via:

```bash
$> fixcore --graphdb-database fixclient_test --psk changeme
```

A local test environment is required. See the [contribution guide](https://fix.com/docs/contributing/components) for instructions.
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
