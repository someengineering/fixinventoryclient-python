from resotoclient import ResotoClient
import os

# Create a ResotoClient object.
# in case you configured psk, use it here so that
# Resoto is able to verify the TLS certificate.
psk = os.environ.get("PSK", "changeme")
client = ResotoClient(url="https://localhost:8900", psk=psk)

# Search for all instances and return a markdown formatted table.
for line in client.cli_execute("search is(instance) | list --markdown"):
    print(line)
