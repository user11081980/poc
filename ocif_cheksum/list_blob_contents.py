"""List all blobs in a specific container using a container-level SAS URL.

Usage:
    python list_blob_contents.py

Before running, install the Azure Storage Blob SDK:
    python -m pip install azure-storage-blob

Set CONTAINER_SAS_URL to the full SAS URL for the container.
Example:
    https://<account>.blob.core.windows.net/<container>?sv=...&sig=...
"""
from azure.storage.blob import ContainerClient

# Replace this with your container-level SAS URL.
CONTAINER_SAS_URL = "https://stlejbubzk5gqf2.blob.core.windows.net/documents?sp=racwdli&st=2026-05-15T21:18:30Z&se=2026-05-16T05:33:30Z&spr=https&sv=2026-02-06&sr=c&sig=K9Zlp%2BeFdTMbgr8mYzRqUNU7wX5MKak%2B3OXukecmNts%3D"


def list_container_blobs(container_sas_url: str) -> None:
    if not container_sas_url or not container_sas_url.strip():
        raise SystemExit("Please set CONTAINER_SAS_URL to your container-level SAS URL.")

    container_client = ContainerClient.from_container_url(container_sas_url)
    print(f"Listing blobs in container: {container_client.container_name}")

    blob_list = container_client.list_blobs()
    count = 0
    for blob in blob_list:
        count += 1
        print(blob.name)

    if count == 0:
        print("No blobs found in this container.")
    else:
        print(f"Total blobs: {count}")


if __name__ == "__main__":
    list_container_blobs(CONTAINER_SAS_URL)
