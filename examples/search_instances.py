from resotoclient import ResotoClient
import os

# Create a ResotoClient object.
# in case you configured psk, use it here so that
# Resoto is able to verify the TLS certificate.
psk = os.environ.get("PSK", "changeme")
client = ResotoClient(url="https://localhost:8900", psk=psk)

# A simple search query that returns an iterator of all resources wihtout edges
instances = client.search_list("resoto", "is(resource)")

for instance in instances:
    print(instance.get("id"))


# find all instandes, all their successors and the edges, and print them
instance_graph = client.search_graph("resoto", "is(instance) <-[0:]->")
for elem in instance_graph:
    print(elem)
