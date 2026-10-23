"""Create a GPT AgentCore execution role in the caller's AWS account."""

import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def main():
    region = os.getenv("AWS_REGION", "us-east-1")
    profile_id = os.getenv("BEDROCK_MODEL_ID", "us.openai.gpt-5.6-luna")
    role_name = os.getenv(
        "AGENTCORE_ROLE_NAME", "hackathon-gpt-agentcore-execution-role"
    )
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    expected_account = os.environ["EXPECTED_AWS_ACCOUNT"]
    if account_id != expected_account:
        raise ValueError(
            "Selected account is not the workshop account verified during setup"
        )
    profile = boto3.client("bedrock", region_name=region).get_inference_profile(
        inferenceProfileIdentifier=profile_id
    )
    resources = [profile["inferenceProfileArn"]]
    resources.extend(model["modelArn"] for model in profile["models"])
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
            }
        ],
    }
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": resources,
            }
        ],
    }
    iam = boto3.client("iam")
    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust),
        Description=f"Hackathon AgentCore access to {profile_id}",
        Tags=[
            {"Key": "Team", "Value": "4"},
            {"Key": "Project", "Value": "AWS-Hackathon"},
        ],
    )["Role"]
    Path(__file__).with_name("resources.json").write_text(
        json.dumps(
            {
                "account": account_id,
                "region": region,
                "team": 4,
                "role_name": role_name,
                "role_arn": role["Arn"],
                "inline_policy": "gpt-inference-profile",
                "model": profile_id,
            },
            indent=2,
        )
        + "\n"
    )
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="gpt-inference-profile",
        PolicyDocument=json.dumps(policy),
    )
    print(role["Arn"])


if __name__ == "__main__":
    try:
        main()
    except ClientError as exc:
        print(f"Role setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
