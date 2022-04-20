from resotoclient import ResotoClient

# Create a ResotoClient object.
# in case you have psk available, you can use it here so that
# Resoto is able to verify the TLS certificate.
client = ResotoClient(url="https://localhost:8900", psk=None)

# A simple search query that returns an iterator of all resources wihtout edges
instances = client.search_list("resoto", "is(resource)")

for instance in instances:
    print(instance.get("id"))


# find all instandes, all their successors and the edges, and print them
instance_graph = client.search_graph("resoto", "is(instance) <-[0:]->")
for elem in instance_graph:
    print(elem)
