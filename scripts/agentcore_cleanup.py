"""Preview, then remove, only the AgentCore resources in .local/agentcore/resources.json (D28).

Checks the account and every Owner/Project tag before deleting anything; re-running resumes a
partial cleanup. Removes the runtime, its log group, the code bucket and the execution role.
CloudWatch Transaction Search is left on unless --restore-transaction-search is given, since
other agents in the same account may emit spans; with it, the destination returns to what it
was before the deploy.

  uv run python scripts/agentcore_cleanup.py
  uv run python scripts/agentcore_cleanup.py --apply
"""

import argparse
import json
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / ".local/agentcore/resources.json"
OWNED = ("Project", "Owner")


def optional(call, **kwargs):
    try:
        return call(**kwargs)
    except ClientError as error:
        if error.response["Error"]["Code"] in {"ResourceNotFoundException", "NoSuchEntity", "NoSuchBucket", "NoSuchTagSet", "404"}:
            return None
        raise


def owned(actual: dict, expected: dict, what: str) -> None:
    if any(actual.get(key) != expected[key] for key in OWNED):
        raise SystemExit(f"{what} ownership tags do not match. Nothing deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Delete these AWS resources")
    parser.add_argument("--restore-transaction-search", action="store_true", help="Also return X-Ray to its previous span destination")
    args = parser.parse_args()
    if not INVENTORY.exists():
        raise SystemExit("No .local/agentcore/resources.json; nothing was deployed from this checkout.")
    inv = json.loads(INVENTORY.read_text())
    if inv.get("cleanup_complete"):
        print("AgentCore cleanup was already completed.")
        return
    for key in ("runtime_arn", "log_group", "bucket", "role_name"):
        print(f"Delete {key}: {inv[key]}")
    if args.restore_transaction_search:
        print(f"Restore X-Ray destination: {inv['transaction_search_previous']}")
    if not args.apply:
        print("Preview only. Add --apply to delete.")
        return
    session = boto3.Session(region_name=inv["region"])
    if session.client("sts").get_caller_identity()["Account"] != inv["account"]:
        raise SystemExit("Wrong AWS account. Nothing deleted.")
    control, iam, s3 = session.client("bedrock-agentcore-control"), session.client("iam"), session.client("s3")

    runtime = optional(control.get_agent_runtime, agentRuntimeId=inv["runtime_id"])
    if runtime:
        owned(control.list_tags_for_resource(resourceArn=runtime["agentRuntimeArn"])["tags"], inv["tags"], "Runtime")
    role = optional(iam.get_role, RoleName=inv["role_name"])
    if role:
        owned({t["Key"]: t["Value"] for t in iam.list_role_tags(RoleName=inv["role_name"])["Tags"]}, inv["tags"], "Role")
        policies = iam.list_role_policies(RoleName=inv["role_name"])["PolicyNames"]
        if iam.list_attached_role_policies(RoleName=inv["role_name"])["AttachedPolicies"] or set(policies) - {inv["inline_policy"]}:
            raise SystemExit("Role has unexpected policies. Nothing deleted.")
    bucket = optional(s3.get_bucket_tagging, Bucket=inv["bucket"])
    if bucket:
        owned({t["Key"]: t["Value"] for t in bucket["TagSet"]}, inv["tags"], "Bucket")
    if inv["log_group"] != f"/aws/bedrock-agentcore/runtimes/{inv['runtime_id']}-DEFAULT":
        raise SystemExit("Unexpected log group. Nothing deleted.")

    # Every ownership check passed; delete in dependency order.
    if runtime:
        if runtime["status"] != "DELETING":
            control.delete_agent_runtime(agentRuntimeId=inv["runtime_id"])
        for _ in range(120):
            if optional(control.get_agent_runtime, agentRuntimeId=inv["runtime_id"]) is None:
                break
            time.sleep(5)
        else:
            raise SystemExit("Runtime is still deleting. Rerun cleanup later.")
    optional(session.client("logs").delete_log_group, logGroupName=inv["log_group"])
    if bucket:
        session.resource("s3").Bucket(inv["bucket"]).object_versions.delete()
        s3.delete_bucket(Bucket=inv["bucket"])
    if role:
        for policy in policies:
            iam.delete_role_policy(RoleName=inv["role_name"], PolicyName=policy)
        iam.delete_role(RoleName=inv["role_name"])
    if args.restore_transaction_search and inv["transaction_search_previous"] != "CloudWatchLogs":
        session.client("xray").update_trace_segment_destination(Destination=inv["transaction_search_previous"])
    inv["cleanup_complete"] = True
    INVENTORY.write_text(json.dumps(inv, indent=2) + "\n")
    print("AgentCore watchdog resources removed. Nothing else in the account was changed.")


if __name__ == "__main__":
    main()
