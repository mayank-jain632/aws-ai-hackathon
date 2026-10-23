"""Preview deletion of only the starter resources recorded in backend/resources.json."""

import argparse
import json
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent


def optional(call, **kwargs):
    try:
        return call(**kwargs)
    except ClientError as error:
        if error.response["Error"]["Code"] in {
            "ResourceNotFoundException",
            "NoSuchEntity",
            "NoSuchBucket",
            "404",
        }:
            return None
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Delete these AWS resources"
    )
    args = parser.parse_args()
    path = ROOT / "backend/resources.json"
    manifest = json.loads(path.read_text())
    if manifest.get("cleanup_complete"):
        print("Cloud cleanup was already completed.")
        return
    for key in ("runtime_id", "bucket", "role_name", "log_group"):
        if manifest.get(key):
            print(f"Delete {key}: {manifest[key]}")
    if not args.apply:
        print(
            "Preview only. Use ./workshop-run uv run python scripts/cleanup_cloud.py --apply to delete."
        )
        return
    session = boto3.Session(region_name=manifest["region"])
    if session.client("sts").get_caller_identity()["Account"] != manifest["account"]:
        raise ValueError("Wrong AWS account. Nothing deleted.")
    control = session.client("bedrock-agentcore-control")
    iam = session.client("iam")
    s3 = session.client("s3")
    tags = {"Team": str(manifest["team"]), "Project": "AWS-Hackathon"}
    runtime = optional(control.get_agent_runtime, agentRuntimeId=manifest["runtime_id"])
    if runtime:
        actual = control.list_tags_for_resource(resourceArn=runtime["agentRuntimeArn"])[
            "tags"
        ]
        if any(actual.get(k) != v for k, v in tags.items()):
            raise ValueError("Runtime ownership tags do not match. Nothing deleted.")
    role = optional(iam.get_role, RoleName=manifest["role_name"])
    if role:
        actual = {
            t["Key"]: t["Value"]
            for t in iam.list_role_tags(RoleName=manifest["role_name"])["Tags"]
        }
        if any(actual.get(k) != v for k, v in tags.items()):
            raise ValueError("Role ownership tags do not match. Nothing deleted.")
        policies = iam.list_role_policies(RoleName=manifest["role_name"])["PolicyNames"]
        attached = iam.list_attached_role_policies(RoleName=manifest["role_name"])[
            "AttachedPolicies"
        ]
        if attached or set(policies) - {manifest["inline_policy"]}:
            raise ValueError("Role has unexpected policies. Nothing deleted.")
    bucket = optional(s3.get_bucket_tagging, Bucket=manifest["bucket"])
    if bucket:
        actual = {t["Key"]: t["Value"] for t in bucket["TagSet"]}
        if any(actual.get(k) != v for k, v in tags.items()):
            raise ValueError("Bucket ownership tags do not match. Nothing deleted.")
    expected_log = f"/aws/bedrock-agentcore/runtimes/{manifest['runtime_id']}-DEFAULT"
    if manifest["log_group"] != expected_log:
        raise ValueError("Unexpected log group. Nothing deleted.")
    # Validate all ownership checks before deleting anything. Re-running resumes partial cleanup.
    if runtime:
        if runtime["status"] != "DELETING":
            control.delete_agent_runtime(agentRuntimeId=manifest["runtime_id"])
        for _ in range(120):
            if (
                optional(
                    control.get_agent_runtime, agentRuntimeId=manifest["runtime_id"]
                )
                is None
            ):
                break
            time.sleep(5)
        else:
            raise TimeoutError("Runtime is still deleting. Rerun cleanup later.")
    if bucket:
        # This bucket is dedicated to the baseline. Include all versions and delete markers.
        session.resource("s3").Bucket(manifest["bucket"]).object_versions.delete()
        s3.delete_bucket(Bucket=manifest["bucket"])
    if role:
        for policy in policies:
            iam.delete_role_policy(RoleName=manifest["role_name"], PolicyName=policy)
        iam.delete_role(RoleName=manifest["role_name"])
    optional(session.client("logs").delete_log_group, logGroupName=expected_log)
    manifest["cleanup_complete"] = True
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Starter cloud resources removed. Organizer infrastructure was not changed.")


if __name__ == "__main__":
    main()
