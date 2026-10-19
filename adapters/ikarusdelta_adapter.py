import base64
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from urllib.parse import quote
import boto3
from botocore.exceptions import ClientError
from .base_adapter import BaseAdapter
from canonical_model import Contact

class IkarusDeltaAdapter(BaseAdapter):
    """
    Adapter that dumps leads into the Ikarus Delta analytics S3 bucket,
    partitioned as year/month/day/<org_id>/leads/data.json.
    Records the payload as-is (no field mapping) plus an auto 'day' stamp.
    """
    DEFAULT_BUCKET = "ikarus-delta-analytics-storage-dev"
    FILES_BUCKET = "ikarus-delta"
    FILES_CLOUDFRONT_DOMAIN = "d1pfj9if6nezm0.cloudfront.net"
    NON_RECORD_FIELDS = {"id", "created_at", "updated_at", "raw_data", "custom_fields", "files"}

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.bucket = config.get("bucket_name", self.DEFAULT_BUCKET)
        self.files_bucket = config.get("files_bucket_name", self.FILES_BUCKET)
        self.files_cloudfront_domain = config.get("files_cloudfront_domain", self.FILES_CLOUDFRONT_DOMAIN)
        self.s3 = boto3.client("s3")

    def authenticate(self) -> bool:
        return True

    def push_contact(self, contact: Contact, target: str = None) -> str:
        flat = contact.dict()
        flat.update(contact.custom_fields)

        org_id = flat.get("organization_id") or flat.get("org_id")
        if not org_id:
            raise ValueError("organization_id not provided in payload.")

        now = datetime.now(timezone.utc)
        prefix = f"{now.year}/{now.month:02d}/{now.day:02d}/{org_id}/leads"

        file_refs = []
        if contact.files:
            product_id = flat.get("product_id")
            if not product_id:
                raise ValueError("product_id not provided in payload (required to store quote PDFs).")
            file_refs = self._upload_files(contact, product_id)

        record = {k: v for k, v in flat.items() if k not in self.NON_RECORD_FIELDS and v is not None}
        record["day"] = now.strftime("%Y-%m-%d")
        if file_refs:
            record["files"] = file_refs

        data_key = f"{prefix}/data.json"

        try:
            existing = json.loads(self.s3.get_object(Bucket=self.bucket, Key=data_key)["Body"].read())
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                raise
            existing = []

        existing.append(record)

        self.s3.put_object(
            Bucket=self.bucket,
            Key=data_key,
            Body=json.dumps(existing, default=str).encode("utf-8"),
            ContentType="application/json",
        )

        return data_key

    def _upload_files(self, contact: Contact, product_id: str) -> List[str]:
        file_refs = []
        for f in contact.files:
            file_key = f"CRM PDF/{product_id}/quote_pdfs/{f.filename}"
            self.s3.put_object(
                Bucket=self.files_bucket,
                Key=file_key,
                Body=base64.b64decode(f.content_base64),
                ContentType=f.mime_type or "application/octet-stream",
            )
            file_refs.append(f"https://{self.files_cloudfront_domain}/{quote(file_key)}")
        return file_refs

    def get_model_schema(self, target: str) -> List[Dict[str, str]]:
        return [
            {"label": "Name", "value": "name", "type": "varchar"},
            {"label": "Email", "value": "email", "type": "varchar"},
            {"label": "Phone", "value": "phone", "type": "varchar"},
            {"label": "Product Name", "value": "product_name", "type": "varchar"},
            {"label": "Product Id", "value": "product_id", "type": "varchar"},
            {"label": "Organization Id", "value": "organization_id", "type": "varchar"},
        ]
