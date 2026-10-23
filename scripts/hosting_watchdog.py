"""Provision only the hosted watchdog Guardrail and Memory; preview by default.

Run through ./workshop-run. Inventory is private in .local/hosting/watchdog.json.
Cleanup removes only IDs created by this script, never resources merely discovered.
"""

import argparse
import json
from pathlib import Path

import boto3
from watchdog_aws import TOPIC, find_guardrail, find_memory

from backend.app.watchdog import aws

STATE = Path(__file__).resolve().parents[1] / ".local/hosting/watchdog.json"
TAGS = {"Project": "AWS-Hackathon", "Team": "4", "Owner": "Kushagra"}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    STATE.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(region_name="us-east-1")
    account = session.client("sts").get_caller_identity()["Account"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"account": account}
    if state["account"] != account:
        raise ValueError("Inventory belongs to another account")
    bedrock = session.client("bedrock")
    control = session.client("bedrock-agentcore-control")
    if args.cleanup:
        print(json.dumps(state, indent=2))
        if args.apply:
            for key, client, method, arg in [
                ("memory", control, "delete_memory", "memoryId"),
                ("guardrail", bedrock, "delete_guardrail", "guardrailIdentifier"),
            ]:
                item = state.get(key)
                if item and item.get("created_here"):
                    getattr(client, method)(**{arg: item["id"]})
                    del state[key]
                    save(state)
        return
    guard = find_guardrail(bedrock)
    memory = find_memory(control)
    print("Existing Guardrail:", guard["id"] if guard else "absent")
    print("Existing Memory:", memory["id"] if memory else "absent")
    if not args.apply:
        print("Preview only; --apply creates only these two missing resources.")
        return
    if not guard:
        result = bedrock.create_guardrail(
            name=aws.GUARDRAIL_NAME,
            description="Team 4 hosted watchdog: prompt injection and trading limit evasion.",
            contentPolicyConfig={
                "filtersConfig": [
                    {
                        "type": "PROMPT_ATTACK",
                        "inputStrength": "HIGH",
                        "outputStrength": "NONE",
                    }
                ]
            },
            topicPolicyConfig={"topicsConfig": [TOPIC]},
            blockedInputMessaging="Blocked by the Team 4 watchdog guardrail.",
            blockedOutputsMessaging="Blocked by the Team 4 watchdog guardrail.",
            tags=[{"key": k, "value": v} for k, v in TAGS.items()],
        )
        guard = {"id": result["guardrailId"], "arn": result["guardrailArn"]}
        state["guardrail"] = {**guard, "created_here": True}
        save(state)
        bedrock.create_guardrail_version(
            guardrailIdentifier=guard["id"], description="Hosted watchdog v1"
        )
    state.setdefault("guardrail", {**guard, "created_here": False})
    save(state)
    if not memory:
        memory = control.create_memory(
            name=aws.MEMORY_NAME,
            description="Team 4 hosted watchdog lessons.",
            eventExpiryDuration=30,
            memoryStrategies=[
                {
                    "semanticMemoryStrategy": {
                        "name": "watchdogLessons",
                        "namespaces": [aws.LESSONS_NAMESPACE],
                    }
                }
            ],
            tags=TAGS,
        )["memory"]
        state["memory"] = {
            "id": memory["id"],
            "arn": memory["arn"],
            "created_here": True,
        }
    state.setdefault(
        "memory", {"id": memory["id"], "arn": memory["arn"], "created_here": False}
    )
    save(state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
