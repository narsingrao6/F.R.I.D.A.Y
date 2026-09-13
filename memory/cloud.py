import json
import os
from datetime import datetime, timezone


class CloudMemoryStore:
    def __init__(self):
        self.bucket_name = os.environ.get("FRIDAY_GCS_BUCKET")
        self.object_name = os.environ.get(
            "FRIDAY_GCS_MEMORY_OBJECT",
            "friday/memory.json",
        )

        self._client = None
        self._bucket = None

    @property
    def enabled(self):
        return bool(self.bucket_name)

    def _ensure_client(self):
        if not self.enabled:
            return False

        if self._bucket is not None:
            return True

        try:
            from google.cloud import storage

            self._client = storage.Client()
            self._bucket = self._client.bucket(self.bucket_name)

            return True

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Cloud memory unavailable "
                f"({type(error).__name__})."
            )

            return False

    def upload(self, memories):
        if not self._ensure_client():
            return False

        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "memories": memories,
        }

        try:
            blob = self._bucket.blob(self.object_name)

            blob.upload_from_string(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                content_type="application/json",
            )

            return True

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Cloud memory upload failed "
                f"({type(error).__name__})."
            )

            return False

    def download(self):
        if not self._ensure_client():
            return None

        try:
            blob = self._bucket.blob(self.object_name)

            if not blob.exists():
                return None

            payload = json.loads(
                blob.download_as_text()
            )

            return payload.get("memories", [])

        except Exception as error:
            print(
                "F.R.I.D.A.Y.: Cloud memory download failed "
                f"({type(error).__name__})."
            )

            return None