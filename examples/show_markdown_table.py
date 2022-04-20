from resotoclient import ResotoClient


# Create a ResotoClient object.
# in case you have psk available, you can use it here so that
# Resoto is able to verify the TLS certificate.
client = ResotoClient(url="https://localhost:8900", psk=None)

# Search for all instances and return a markdown formatted table.
for line in client.cli_execute("resoto", "search is(instance) | list --markdown"):
    print(line)
