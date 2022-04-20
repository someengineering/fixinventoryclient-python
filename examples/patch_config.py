from time import sleep
from resotoclient import ResotoClient
import os

# Create a ResotoClient object.
# in case you configured psk, use it here so that
# Resoto is able to verify the TLS certificate.
psk = os.environ.get("PSK", "changeme")
client = ResotoClient(url="https://localhost:8900", psk=psk)

def wait_for_resotocore(client: ResotoClient):
    while True:
        try:
            client.ready()
            break
        except Exception:
            sleep(0.5)


# Get the configuration of the resotocore.
conf = client.config("resoto.core")
print("resotocore config before patch:")
print(conf)
# Now we patch the loglevel in runtime. This will trigger a hot-reload of the config.
client.patch_config("resoto.core", {"resotocore": {"runtime": {"log_level": "debug"}}})
# resotocore might restart after the config was changed. Let's wait for it to be ready.
wait_for_resotocore(client)
print("resotocore config after patch:")
print(client.config("resoto.core"))

# reverting the change back to the original config
client.patch_config("resoto.core", {"resotocore": {"runtime": {"log_level": "info"}}})
# Wait for resotocore readiness.
wait_for_resotocore(client)
print("resotocore config after revert:")
print(client.config("resoto.core"))
