from resotoclient import ResotoClient
import os

# Create a ResotoClient object.
# in case you configured psk, use it here so that
# Resoto is able to verify the TLS certificate.
psk = os.environ.get("PSK", "changeme")
with ResotoClient(url="https://localhost:8900", psk=psk) as client:

    # echo command returns the input string.
    ping = client.cli_execute("echo ping")
    # since cli_execute returns an iterator, convert it to a list befor printing.
    print(list(ping))

    # find all instances and return a csv list with them.
    instances_csv = client.cli_execute("search is(instance) | tail 5 | list --csv")

    for instance in instances_csv:
        print(instance)
