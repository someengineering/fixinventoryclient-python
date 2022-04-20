from resotoclient import ResotoClient


# Create a ResotoClient object.
# in case you have psk available, you can use it here so that
# Resoto is able to verify the TLS certificate.
client = ResotoClient(url="https://localhost:8900", psk=None)

# echo command returns the input string.
ping = client.cli_execute("resoto", "echo ping")
# since cli_execute returns an iterator, convert it to a list befor printing.
print(list(ping))

# find all instances and return a csv list with them.
instances_csv = client.cli_execute(
    "resoto", "search is(instance) | tail 5 | list --csv"
)

for instance in instances_csv:
    print(instance)
