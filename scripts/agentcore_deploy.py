"""Deploy the watchdog second-opinion agent to Amazon Bedrock AgentCore Runtime (D28).

Preview by default; --apply creates or updates only the resources below, each named after its
owner and tagged per D25. Inventory goes to ignored .local/agentcore/resources.json, which
scripts/agentcore_cleanup.py reads to remove exactly these resources.

  IAM role     aaron-agentcore-watchdog-runtime  (Luna inference, runtime logs, X-Ray)
  S3 bucket    aaron-agentcore-watchdog-<account> (code package)
  Runtime      aaron_watchdog_opinion             (backend/app/agentcore/remote/opinion_agent.py)
  Account      CloudWatch Transaction Search, so runtime spans reach GenAI Observability

Every ARN, the bucket name and the log group come from the signed-in account, so the same
command works in Aaron's participant account or the hosting account. --account is an optional
guard that stops unless the credentials are in that account.

  uv run python scripts/agentcore_deploy.py                # preview
  uv run python scripts/agentcore_deploy.py --apply        # deploy or update
  uv run python scripts/agentcore_deploy.py --policy       # hosted-role IAM statement for this runtime
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "backend/app/agentcore/remote/opinion_agent.py"
STATE = ROOT / ".local/agentcore"
INVENTORY = STATE / "resources.json"
OWNER = "aaron"
ROLE = "aaron-agentcore-watchdog-runtime"
POLICY = "watchdog-opinion-runtime"
RUNTIME = "aaron_watchdog_opinion"
MODEL = "us.openai.gpt-5.6-luna"
PACKAGES = ["bedrock-agentcore", "aws-opentelemetry-distro", "boto3"]
TAGS = {"Project": "AWS-Hackathon", "Owner": OWNER, "Team": "4", "Component": "agentcore-watchdog-opinion"}


def missing(error: ClientError) -> bool:
    return error.response["Error"]["Code"] in {"ResourceNotFoundException", "NoSuchEntity", "404", "NoSuchBucket"}


def portable_launchers(bin_dir: Path) -> None:
    """`uv pip install --target` writes this laptop's Python path into console scripts such as
    opentelemetry-instrument; point them at the runtime's python3 instead."""
    for script in bin_dir.glob("*"):
        lines = script.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("#!") and "python" in lines[0]:
            lines[0] = "#!/usr/bin/env python3\n"
        if len(lines) > 1 and lines[1].startswith("'''exec'"):
            lines[1] = "'''exec' python3 \"$0\" \"$@\"\n"
        script.write_text("".join(lines))


def build_package() -> Path:
    """Linux arm64 wheels for Python 3.12 plus the agent file, zipped at the archive root."""
    build = STATE / "build"
    shutil.rmtree(build, ignore_errors=True)
    target = build / "package"
    subprocess.run(
        [
            "uv", "pip", "install", "--quiet", "--target", str(target),
            "--python-platform", "aarch64-manylinux2014", "--python-version", "3.12",
            "--only-binary=:all:", *PACKAGES,
        ],
        check=True,
    )
    portable_launchers(target / "bin")
    shutil.copy(AGENT, target / "opinion_agent.py")
    archive = build / "opinion_agent.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(target.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                handle.write(path, path.relative_to(target).as_posix())
    return archive


def ensure_bucket(s3, bucket: str, region: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
            raise
        kwargs = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
        s3.create_bucket(Bucket=bucket, **kwargs)
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={k: True for k in ["BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets"]},
        )
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})


def role_policy(session, account: str, region: str, bucket: str) -> dict:
    profile = session.client("bedrock").get_inference_profile(inferenceProfileIdentifier=MODEL)
    models = [profile["inferenceProfileArn"], *(m["modelArn"] for m in profile["models"])]
    runtime_logs = f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/*"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "LunaInference", "Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], "Resource": models},
            {"Sid": "RuntimeLogs", "Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], "Resource": [runtime_logs, runtime_logs + ":*"]},
            {"Sid": "DescribeLogGroups", "Effect": "Allow", "Action": ["logs:DescribeLogGroups"], "Resource": "*"},
            {"Sid": "Traces", "Effect": "Allow", "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"], "Resource": "*"},
            {"Sid": "RuntimeMetrics", "Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*", "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}}},
            {"Sid": "CodePackage", "Effect": "Allow", "Action": ["s3:GetObject", "s3:GetObjectVersion"], "Resource": f"arn:aws:s3:::{bucket}/*"},
        ],
    }


def ensure_role(iam, account: str, region: str, policy: dict) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account}:*"},
                },
            }
        ],
    }
    try:
        arn = iam.get_role(RoleName=ROLE)["Role"]["Arn"]
        iam.update_assume_role_policy(RoleName=ROLE, PolicyDocument=json.dumps(trust))
    except ClientError as error:
        if not missing(error):
            raise
        arn = iam.create_role(
            RoleName=ROLE,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="AgentCore Runtime role for the Team 4 watchdog second opinion (Owner aaron, D28)",
            Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
        )["Role"]["Arn"]
        time.sleep(10)  # IAM propagation before AgentCore assumes the new role
    iam.put_role_policy(RoleName=ROLE, PolicyName=POLICY, PolicyDocument=json.dumps(policy))
    return arn


def enable_transaction_search(session, account: str, region: str) -> str:
    """Route X-Ray spans to CloudWatch Logs (aws/spans). Returns the previous destination."""
    xray = session.client("xray")
    previous = xray.get_trace_segment_destination()["Destination"]
    if previous != "CloudWatchLogs":
        session.client("logs").put_resource_policy(
            policyName="TransactionSearchXRayAccess",
            policyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "TransactionSearchXRayAccess",
                            "Effect": "Allow",
                            "Principal": {"Service": "xray.amazonaws.com"},
                            "Action": "logs:PutLogEvents",
                            "Resource": [
                                f"arn:aws:logs:{region}:{account}:log-group:aws/spans:*",
                                f"arn:aws:logs:{region}:{account}:log-group:/aws/application-signals/data:*",
                            ],
                            "Condition": {"ArnLike": {"aws:SourceArn": f"arn:aws:xray:{region}:{account}:*"}, "StringEquals": {"aws:SourceAccount": account}},
                        }
                    ],
                }
            ),
        )
        xray.update_trace_segment_destination(Destination="CloudWatchLogs")
    return previous


def index_every_trace(session) -> float:
    """Index all spans as trace summaries so each invocation opens on the X-Ray trace page
    (the default indexes 1%). Returns the previous percentage."""
    xray = session.client("xray")
    rule = next(r for r in xray.get_indexing_rules()["IndexingRules"] if r["Name"] == "Default")
    previous = rule["Rule"]["Probabilistic"]["DesiredSamplingPercentage"]
    if previous < 100:
        xray.update_indexing_rule(Name="Default", Rule={"Probabilistic": {"DesiredSamplingPercentage": 100}})
    return previous


def find_runtime(control) -> dict | None:
    for page in control.get_paginator("list_agent_runtimes").paginate():
        for runtime in page.get("agentRuntimes", []):
            if runtime["agentRuntimeName"] == RUNTIME:
                return runtime
    return None


def deploy_runtime(control, role_arn: str, bucket: str, key: str, region: str) -> dict:
    artifact = {
        "codeConfiguration": {
            "code": {"s3": {"bucket": bucket, "prefix": key}},
            "runtime": "PYTHON_3_12",
            "entryPoint": ["opentelemetry-instrument", "opinion_agent.py"],
        }
    }
    settings = {
        "agentRuntimeArtifact": artifact,
        "roleArn": role_arn,
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "environmentVariables": {"MODEL_ID": MODEL, "AWS_REGION": region},
        "description": "Team 4 watchdog second opinion on flagged paper orders (Owner aaron, D28)",
    }
    existing = find_runtime(control)
    if existing:
        control.update_agent_runtime(agentRuntimeId=existing["agentRuntimeId"], **settings)
        runtime_id = existing["agentRuntimeId"]
    else:
        runtime_id = control.create_agent_runtime(agentRuntimeName=RUNTIME, tags=TAGS, **settings)["agentRuntimeId"]
    for _ in range(90):
        runtime = control.get_agent_runtime(agentRuntimeId=runtime_id)
        if runtime["status"] in {"READY", "CREATE_FAILED", "UPDATE_FAILED"}:
            break
        time.sleep(5)
    if runtime["status"] != "READY":
        raise RuntimeError(f"Runtime {runtime_id} ended {runtime['status']}: {runtime.get('failureReason', '')}")
    return runtime


def hosted_role_statement(runtime_arn: str) -> dict:
    """What the hosted app's role needs to call this runtime (D25: the deployment owner adds it)."""
    return {
        "Sid": "InvokeWatchdogOpinionRuntime",
        "Effect": "Allow",
        "Action": "bedrock-agentcore:InvokeAgentRuntime",
        "Resource": [runtime_arn, f"{runtime_arn}/runtime-endpoint/*"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", help="Optional guard: stop unless the credentials are in this account")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--apply", action="store_true", help="Create or update the resources")
    parser.add_argument("--policy", action="store_true", help="Print the hosted-role IAM statement for the deployed runtime")
    args = parser.parse_args()
    if args.policy:
        print(json.dumps(hosted_role_statement(json.loads(INVENTORY.read_text())["runtime_arn"]), indent=2))
        return
    session = boto3.Session(region_name=args.region)
    identity = session.client("sts").get_caller_identity()
    account = identity["Account"]
    if args.account and account != args.account:
        sys.exit(f"Signed in to {account}, expected {args.account}. Nothing changed.")
    args.account = account
    bucket = f"aaron-agentcore-watchdog-{account}"
    print(f"Account {account} as {identity['Arn'].split('/')[-2]}, region {args.region}")
    for line in [f"IAM role {ROLE}", f"S3 bucket {bucket}", f"AgentCore Runtime {RUNTIME} ({MODEL})", "CloudWatch Transaction Search on, 100% trace indexing"]:
        print(f"  create or update: {line}")
    if not args.apply:
        print("Preview only. Add --apply to deploy.")
        return
    STATE.mkdir(parents=True, exist_ok=True)
    inventory = json.loads(INVENTORY.read_text()) if INVENTORY.exists() else {}
    archive = build_package()
    print(f"Package {archive.stat().st_size / 1e6:.1f} MB")
    s3 = session.client("s3")
    ensure_bucket(s3, bucket, args.region)
    key = f"opinion_agent/{datetime.now(UTC):%Y%m%dT%H%M%S}.zip"
    s3.upload_file(str(archive), bucket, key)
    role_arn = ensure_role(session.client("iam"), args.account, args.region, role_policy(session, args.account, args.region, bucket))
    previous = enable_transaction_search(session, args.account, args.region)
    indexing = index_every_trace(session)
    runtime = deploy_runtime(session.client("bedrock-agentcore-control"), role_arn, bucket, key, args.region)
    inventory.update(
        {
            "account": args.account,
            "region": args.region,
            "owner": OWNER,
            "tags": TAGS,
            "role_name": ROLE,
            "inline_policy": POLICY,
            "bucket": bucket,
            "package_key": key,
            "runtime_id": runtime["agentRuntimeId"],
            "runtime_arn": runtime["agentRuntimeArn"],
            "runtime_version": runtime.get("agentRuntimeVersion"),
            "log_group": f"/aws/bedrock-agentcore/runtimes/{runtime['agentRuntimeId']}-DEFAULT",
            "transaction_search_previous": inventory.get("transaction_search_previous", previous),
            "trace_indexing_previous": inventory.get("trace_indexing_previous", indexing),
            "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        }
    )
    INVENTORY.write_text(json.dumps(inventory, indent=2) + "\n")
    print(f"Runtime READY: {runtime['agentRuntimeArn']}")
    print(f"Inventory: {INVENTORY.relative_to(ROOT)}")
    print(f"Enable it in the backend: AGENTCORE_OPINION_ARN={runtime['agentRuntimeArn']}")
    print("Hosted-role statement (D25, for the deployment owner):")
    print(json.dumps(hosted_role_statement(runtime["agentRuntimeArn"]), indent=2))


if __name__ == "__main__":
    main()
