from time import sleep
from resotoclient import ResotoClient


# Create a ResotoClient object.
# in case you have psk available, you can use it here so that
# Resoto is able to verify the TLS certificate.
client = ResotoClient(url="https://localhost:8900", psk=None)

# Get the configuration of the resotocore.
conf = client.config("resoto.core")
print("resotocore config before patch:")
print(conf)
# Now we patch the loglevel in runtime. This will trigger a restart of resotocore.
client.patch_config("resoto.core", {"resotocore": {"runtime": {"log_level": "debug"}}})
# resotocore restarts after config change. Wait for it to be ready.
while True:
    try:
        conf = client.config("resoto.core")
        print("resotocore config after patch:")
        print(conf)
        break
    except Exception as e:
        sleep(0.5)

# reverting the change back to the original config
client.patch_config("resoto.core", {"resotocore": {"runtime": {"log_level": "info"}}})
# Wait for resotocore restart.
while True:
    try:
        conf = client.config("resoto.core")
        print("resotocore config after revert:")
        print(conf)
        break
    except Exception as e:
        sleep(0.5)
