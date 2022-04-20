from resotoclient import ResotoClient

# Create a ResotoClient object.
# in case you have psk available, you can use it here so that
# Resoto is able to verify the TLS certificate.
client = ResotoClient(url="https://localhost:8900", psk=None)

# A simple search query that returns an iterator of all resources
instances = client.search_graph("resoto", "is(resource)")

for instance in instances:
    print(instance.get("id"))
