"""Deploy the single app image to a dedicated EC2 host behind CloudFront HTTPS.

Run through ./workshop-run. Inventory and access details stay in .local/hosting/.
This does not modify or copy local agent conversations or workspace files.
"""

import argparse
import base64
import json
import secrets
import subprocess
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local/hosting"
NAME = "team4-agent-canvas"
REGION = "us-east-1"
TAGS = [
    {"Key": "Project", "Value": "AWS-Hackathon"},
    {"Key": "Team", "Value": "4"},
    {"Key": "Name", "Value": NAME},
]


def cleanup(session, state, save, apply):
    """Preview removal, then remove recorded app resources in dependency order."""
    print("Hosting resources:", json.dumps(state, indent=2))
    print("Removal deletes the hosted workspace and conversations with its disk.")
    if not apply:
        print("Preview only. Add --apply to remove these resources.")
        return
    if state.get("distribution_id"):
        cf = session.client("cloudfront")
        result = cf.get_distribution_config(Id=state["distribution_id"])
        config = result["DistributionConfig"]
        if config["Enabled"]:
            config["Enabled"] = False
            cf.update_distribution(
                Id=state["distribution_id"],
                IfMatch=result["ETag"],
                DistributionConfig=config,
            )
            print(
                "CloudFront is disabling. Rerun cleanup after its status is Deployed."
            )
            return
        if (
            cf.get_distribution(Id=state["distribution_id"])["Distribution"]["Status"]
            != "Deployed"
        ):
            print("CloudFront is still disabling. Rerun cleanup after it finishes.")
            return
        cf.delete_distribution(Id=state["distribution_id"], IfMatch=result["ETag"])
        save(distribution_id=None)
    ec2 = session.client("ec2")
    if state.get("instance_id"):
        ec2.terminate_instances(InstanceIds=[state["instance_id"]])
        status = ec2.describe_instances(InstanceIds=[state["instance_id"]])[
            "Reservations"
        ][0]["Instances"][0]["State"]["Name"]
        if status != "terminated":
            print(
                "Instance is terminating. Rerun cleanup to finish removing dependencies."
            )
            return
        save(instance_id=None)
    if state.get("security_group"):
        ec2.delete_security_group(GroupId=state["security_group"])
        save(security_group=None)
    iam = session.client("iam")
    if state.get("instance_profile"):
        iam.remove_role_from_instance_profile(InstanceProfileName=NAME, RoleName=NAME)
        iam.delete_instance_profile(InstanceProfileName=NAME)
        save(instance_profile=None)
    if state.get("role"):
        iam.detach_role_policy(
            RoleName=NAME,
            PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
        )
        iam.delete_role_policy(RoleName=NAME, PolicyName="app")
        iam.delete_role(RoleName=NAME)
        save(role=None)
    if state.get("repository"):
        session.client("ecr").delete_repository(repositoryName=NAME, force=True)
        save(repository=None)
    if state.get("secret_arn"):
        session.client("secretsmanager").delete_secret(
            SecretId=state["secret_arn"], RecoveryWindowInDays=7
        )
        save(secret_arn=None)
    save(cleanup_complete=True)
    print("Hosted app removed. The secret has a seven-day recovery window.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    inventory = STATE / "resources.json"
    state = json.loads(inventory.read_text()) if inventory.exists() else {}

    def save(**changes):
        state.update(changes)
        inventory.write_text(json.dumps(state, indent=2) + "\n")
        inventory.chmod(0o600)

    session = boto3.Session(region_name=REGION)
    account = session.client("sts").get_caller_identity()["Account"]
    if state.get("account", account) != account:
        raise ValueError("Deployment inventory belongs to a different account")
    save(account=account, region=REGION)
    ec2, iam, ecr = (session.client(service) for service in ("ec2", "iam", "ecr"))
    cloudfront = session.client("cloudfront")
    if args.cleanup:
        cleanup(session, state, save, args.apply)
        return
    if state.get("cleanup_complete"):
        raise ValueError(
            "This deployment was removed. Archive its inventory before creating another."
        )
    if args.status:
        print(json.dumps(state, indent=2))
        return

    access_file = STATE / "access.json"
    access = (
        json.loads(access_file.read_text())
        if access_file.exists()
        else {
            "password": secrets.token_urlsafe(24),
            "origin_token": secrets.token_urlsafe(32),
        }
    )
    if "accounts" not in access:
        access["accounts"] = {
            email: secrets.token_urlsafe(16)
            for email in (
                "kush@example.com",
                "mayank@example.com",
                "gerson@example.com",
            )
        }
    access_file.write_text(json.dumps(access, indent=2) + "\n")
    access_file.chmod(0o600)
    demo_file = STATE / "demo-accounts.json"
    demo_file.write_text(json.dumps(access["accounts"], indent=2) + "\n")
    demo_file.chmod(0o600)
    env = {
        key: value
        for key, value in dotenv_values(ROOT / ".env").items()
        if value
        and (
            key.endswith("_API_KEY")
            or key
            in {
                "X_BEARER_TOKEN",
                "MAIN_AGENT_MODEL",
                "ALPACA_SECRET_KEY",
                "APCA_API_KEY_ID",
                "APCA_API_SECRET_KEY",
                "APIFY_TOKEN",
                "APIFY_API_TOKEN",
            }
        )
    }
    env.update(
        AWS_REGION=REGION,
        AWS_CREDENTIAL_MODE="role",
        APP_ACCESS_PASSWORD=access["password"],
        APP_DEMO_ACCOUNTS=json.dumps(access["accounts"]),
        APP_ORIGIN_TOKEN=access["origin_token"],
    )
    watchdog_file = STATE / "watchdog.json"
    watchdog = json.loads(watchdog_file.read_text()) if watchdog_file.exists() else {}
    if watchdog and watchdog.get("account") != account:
        raise ValueError("Watchdog inventory belongs to a different account")
    if watchdog.get("guardrail"):
        env.update(
            WATCHDOG_GUARDRAIL_ID=watchdog["guardrail"]["id"],
            WATCHDOG_GUARDRAIL_VERSION="1",
        )
    if watchdog.get("memory"):
        env["WATCHDOG_MEMORY_ID"] = watchdog["memory"]["id"]
    sm = session.client("secretsmanager")
    if not state.get("secret_arn"):
        result = sm.create_secret(
            Name=f"{NAME}-environment", SecretString=json.dumps(env), Tags=TAGS
        )
        save(secret_arn=result["ARN"])
    else:
        previous = json.loads(
            sm.get_secret_value(SecretId=state["secret_arn"])["SecretString"]
        )
        # A teammate's blank local template must not erase deployed credentials.
        sm.put_secret_value(
            SecretId=state["secret_arn"], SecretString=json.dumps({**previous, **env})
        )
    if not state.get("repository"):
        try:
            repo = ecr.create_repository(
                repositoryName=NAME,
                imageScanningConfiguration={"scanOnPush": True},
                tags=[{"Key": t["Key"], "Value": t["Value"]} for t in TAGS],
            )["repository"]
        except ecr.exceptions.RepositoryAlreadyExistsException:
            repo = ecr.describe_repositories(repositoryNames=[NAME])["repositories"][0]
        save(repository=repo["repositoryUri"])
    auth = ecr.get_authorization_token()["authorizationData"][0]
    username, password = (
        base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    )
    subprocess.run(
        [
            "docker",
            "login",
            "--username",
            username,
            "--password-stdin",
            auth["proxyEndpoint"],
        ],
        input=password.encode(),
        check=True,
        stdout=subprocess.DEVNULL,
    )
    previous_image = state.get("image")
    existing_instance = state.get("instance_id")
    image = state["repository"] + ":" + str(int(time.time()))
    subprocess.run(["docker", "tag", "aws-hackathon-sandbox:hosted", image], check=True)
    subprocess.run(["docker", "push", image], check=True)
    save(image=image)

    if not state.get("role"):
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        iam.create_role(
            RoleName=NAME, AssumeRolePolicyDocument=json.dumps(trust), Tags=TAGS
        )
        save(role=NAME)
    catalog = json.loads((ROOT / "backend/model-catalog.json").read_text())
    # Keep Luna for the existing moderator second-opinion path.
    profile_ids = [item["id"] for item in catalog["main"]] + [
        catalog["backtester"],
        "us.openai.gpt-5.6-luna",
    ]
    models = [
        session.client("bedrock").get_inference_profile(
            inferenceProfileIdentifier=model_id
        )
        for model_id in profile_ids
    ]
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": sorted(
                    {
                        arn
                        for model in models
                        for arn in [
                            model["inferenceProfileArn"],
                            *[m["modelArn"] for m in model["models"]],
                        ]
                    }
                ),
            },
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": state["secret_arn"],
            },
            {"Effect": "Allow", "Action": "ecr:GetAuthorizationToken", "Resource": "*"},
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability",
                ],
                "Resource": f"arn:aws:ecr:{REGION}:{account}:repository/{NAME}",
            },
        ],
    }
    if watchdog.get("guardrail") and watchdog.get("memory"):
        policy["Statement"].extend(
            [
                {
                    "Effect": "Allow",
                    "Action": "bedrock:ApplyGuardrail",
                    "Resource": watchdog["guardrail"]["arn"],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "bedrock-agentcore:CreateEvent",
                        "bedrock-agentcore:ListEvents",
                        "bedrock-agentcore:RetrieveMemoryRecords",
                    ],
                    "Resource": watchdog["memory"]["arn"],
                },
                {
                    "Effect": "Allow",
                    "Action": "cloudwatch:PutMetricData",
                    "Resource": "*",
                    "Condition": {
                        "StringEquals": {"cloudwatch:namespace": "Team4/Watchdog"}
                    },
                },
                {
                    "Effect": "Allow",
                    "Action": "events:PutEvents",
                    "Resource": f"arn:aws:events:{REGION}:{account}:event-bus/default",
                },
            ]
        )
    iam.put_role_policy(
        RoleName=NAME, PolicyName="app", PolicyDocument=json.dumps(policy)
    )
    iam.attach_role_policy(
        RoleName=NAME, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    )
    if not state.get("instance_profile"):
        iam.create_instance_profile(InstanceProfileName=NAME, Tags=TAGS)
        iam.add_role_to_instance_profile(InstanceProfileName=NAME, RoleName=NAME)
        save(instance_profile=NAME)
    if not state.get("security_group"):
        vpc = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])[
            "Vpcs"
        ][0]
        group = ec2.create_security_group(
            GroupName=NAME,
            Description="Agent canvas origin, CloudFront only",
            VpcId=vpc["VpcId"],
            TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}],
        )["GroupId"]
        save(security_group=group, vpc=vpc["VpcId"])
        prefix = ec2.describe_managed_prefix_lists(
            Filters=[
                {
                    "Name": "prefix-list-name",
                    "Values": ["com.amazonaws.global.cloudfront.origin-facing"],
                }
            ]
        )["PrefixLists"][0]["PrefixListId"]
        ec2.authorize_security_group_ingress(
            GroupId=group,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "PrefixListIds": [{"PrefixListId": prefix}],
                }
            ],
        )
    if not state.get("instance_id"):
        ami = session.client("ssm").get_parameter(
            Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
        )["Parameter"]["Value"]
        subnet = ec2.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [state["vpc"]]}]
        )["Subnets"][0]["SubnetId"]
        user_data = f"""#!/bin/bash
set -eu
umask 077
dnf install -y docker
systemctl enable --now docker
install -d -m 700 /opt/agent-canvas
install -d -m 700 -o 1000 -g 1000 /opt/agent-canvas/state
cat > /opt/agent-canvas/start.sh <<'START'
#!/bin/bash
set -eu
umask 077
aws secretsmanager get-secret-value --region {REGION} --secret-id {state["secret_arn"]} --query SecretString --output text > /opt/agent-canvas/env.json
python3 - <<'ENV'
import json
with open('/opt/agent-canvas/env.json') as f: env=json.load(f)
with open('/opt/agent-canvas/.env', 'w') as f:
 for key,value in env.items():
  if '\\n' in value or '\\r' in value: raise ValueError('Environment values must be single line')
  f.write(key+'='+value+'\\n')
ENV
rm -f /opt/agent-canvas/env.json
aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {state["repository"].split("/")[0]}
docker pull {image}
docker rm -f agent-canvas || true
exec docker run --name agent-canvas --init --user 1000:1000 --read-only --tmpfs /tmp:mode=1777,size=256m --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 5g --cpus 2 --log-opt max-size=10m --log-opt max-file=3 --env-file /opt/agent-canvas/.env -p 80:8000 -v /opt/agent-canvas/state:/app/.local {image}
START
chmod 700 /opt/agent-canvas/start.sh
cat > /etc/systemd/system/agent-canvas.service <<'UNIT'
[Unit]
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service
[Service]
ExecStart=/opt/agent-canvas/start.sh
ExecStop=/usr/bin/docker stop -t 8 agent-canvas
Restart=always
RestartSec=10
TimeoutStartSec=600
TimeoutStopSec=15
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now agent-canvas
"""
        for attempt in range(6):
            try:
                instance = ec2.run_instances(
                    ImageId=ami,
                    InstanceType="t4g.large",
                    MinCount=1,
                    MaxCount=1,
                    ClientToken=f"{NAME}-{account}",
                    IamInstanceProfile={"Name": NAME},
                    NetworkInterfaces=[
                        {
                            "DeviceIndex": 0,
                            "SubnetId": subnet,
                            "AssociatePublicIpAddress": True,
                            "Groups": [state["security_group"]],
                        }
                    ],
                    MetadataOptions={
                        "HttpTokens": "required",
                        "HttpPutResponseHopLimit": 2,
                    },
                    BlockDeviceMappings=[
                        {
                            "DeviceName": "/dev/xvda",
                            "Ebs": {
                                "VolumeSize": 40,
                                "VolumeType": "gp3",
                                "Encrypted": True,
                                "DeleteOnTermination": True,
                            },
                        }
                    ],
                    TagSpecifications=[
                        {"ResourceType": "instance", "Tags": TAGS},
                        {"ResourceType": "volume", "Tags": TAGS},
                    ],
                    UserData=user_data,
                )["Instances"][0]
                save(instance_id=instance["InstanceId"])
                break
            except ClientError as error:
                if (
                    attempt == 5
                    or error.response["Error"]["Code"] != "InvalidParameterValue"
                ):
                    raise
                time.sleep(10)
    print("Instance:", state["instance_id"], flush=True)
    # A bounded invocation can be rerun; AWS startup continues independently.
    ec2.get_waiter("instance_running").wait(
        InstanceIds=[state["instance_id"]], WaiterConfig={"Delay": 5, "MaxAttempts": 10}
    )
    instance = ec2.describe_instances(InstanceIds=[state["instance_id"]])[
        "Reservations"
    ][0]["Instances"][0]
    save(origin=instance["PublicDnsName"])
    if existing_instance:
        command = session.client("ssm").send_command(
            InstanceIds=[existing_instance],
            DocumentName="AWS-RunShellScript",
            Parameters={
                "commands": [
                    "set -eu",
                    f"aws ecr get-login-password --region {REGION} | docker login --username AWS --password-stdin {state['repository'].split('/')[0]}",
                    f"docker pull {image}",
                    f"sed -i 's|{previous_image}|{image}|g' /opt/agent-canvas/start.sh",
                    "systemctl restart agent-canvas",
                ]
            },
        )["Command"]["CommandId"]
        save(update_command=command)
    if not state.get("distribution_id"):
        config = {
            "CallerReference": NAME + "-" + account,
            "Comment": "Team 4 agent canvas",
            "Enabled": True,
            "PriceClass": "PriceClass_100",
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": "app",
                        "DomainName": state["origin"],
                        "CustomHeaders": {
                            "Quantity": 1,
                            "Items": [
                                {
                                    "HeaderName": "X-Origin-Token",
                                    "HeaderValue": access["origin_token"],
                                }
                            ],
                        },
                        "CustomOriginConfig": {
                            "HTTPPort": 80,
                            "HTTPSPort": 443,
                            "OriginProtocolPolicy": "http-only",
                            "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
                            "OriginReadTimeout": 60,
                            "OriginKeepaliveTimeout": 5,
                        },
                    }
                ],
            },
            "DefaultCacheBehavior": {
                "TargetOriginId": "app",
                "ViewerProtocolPolicy": "redirect-to-https",
                "TrustedSigners": {"Enabled": False, "Quantity": 0},
                "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
                "AllowedMethods": {
                    "Quantity": 7,
                    "Items": [
                        "GET",
                        "HEAD",
                        "OPTIONS",
                        "PUT",
                        "PATCH",
                        "POST",
                        "DELETE",
                    ],
                    "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
                },
                "Compress": False,
            },
            "ViewerCertificate": {"CloudFrontDefaultCertificate": True},
            "HttpVersion": "http2",
            "IsIPV6Enabled": True,
        }
        result = cloudfront.create_distribution_with_tags(
            DistributionConfigWithTags={
                "DistributionConfig": config,
                "Tags": {"Items": TAGS},
            }
        )["Distribution"]
        save(distribution_id=result["Id"], url="https://" + result["DomainName"])
    if existing_instance:
        result = cloudfront.get_distribution_config(Id=state["distribution_id"])
        config = result["DistributionConfig"]
        if config["Origins"]["Items"][0]["DomainName"] != state["origin"]:
            config["Origins"]["Items"][0]["DomainName"] = state["origin"]
            cloudfront.update_distribution(
                Id=state["distribution_id"],
                IfMatch=result["ETag"],
                DistributionConfig=config,
            )
    print("URL:", state["url"], flush=True)
    print("Demo account passwords are in", demo_file, flush=True)


if __name__ == "__main__":
    main()
