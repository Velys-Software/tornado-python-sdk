"""
Storage configuration examples — S3, Azure Blob, GCS, OSS, and Slack.

Tornado supports multiple cloud storage backends. You can configure
account-level storage (used for all subsequent jobs) or pass inline
credentials per-job.
"""

import asyncio

from tornado_sdk import (
    TornadoClient,
    S3StorageConfig,
    BlobStorageConfig,
    GcsStorageConfig,
    OssStorageConfig,
    InlineStorageConfig,
    SlackWebhookConfig,
)


async def main():
    client = TornadoClient(api_key="your-api-key-here")

    # ── Option 1: Account-level S3 storage (Cloudflare R2 example) ──
    # Once configured, ALL jobs automatically upload to this bucket.
    await client.configure_s3(S3StorageConfig(
        endpoint="https://your-account-id.r2.cloudflarestorage.com",
        bucket="my-videos",
        region="auto",              # Use "auto" for Cloudflare R2
        access_key="your-access-key",
        secret_key="your-secret-key",
        base_folder="downloads",    # Files go to downloads/<filename>
    ))
    print("S3 storage configured!")

    # ── Option 2: Azure Blob Storage ──
    await client.configure_blob(BlobStorageConfig(
        account_name="mystorageaccount",
        container="videos",
        account_key="your-account-key",  # Or use sas_token= instead
    ))

    # ── Option 3: Google Cloud Storage ──
    await client.configure_gcs(GcsStorageConfig(
        project_id="my-gcp-project",
        bucket="my-gcs-bucket",
        service_account_json='{"type": "service_account", ...}',  # Full JSON key
    ))

    # ── Option 4: Alibaba Cloud OSS ──
    await client.configure_oss(OssStorageConfig(
        endpoint="https://oss-cn-hangzhou.aliyuncs.com",
        bucket="my-oss-bucket",
        access_key_id="your-key-id",
        access_key_secret="your-key-secret",
    ))

    # ── Slack notifications for job failures ──
    await client.configure_slack(SlackWebhookConfig(
        webhook_url="https://hooks.slack.com/services/T00000000/B00000000/XXXX",
        notify_level="errors_only",  # "all", "errors_only", or "warnings_only"
    ))

    # ── Inline storage: override per-job (useful for marketplace integrations) ──
    # Credentials are used only for this specific job, not saved to your account.
    job_id = await client.create_job(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        storage=InlineStorageConfig.s3(
            endpoint="https://s3.amazonaws.com",
            bucket="my-bucket",
            region="us-east-1",
            access_key="AKIA...",
            secret_key="secret...",
        ),
    )
    print(f"Job with inline S3: {job_id}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
