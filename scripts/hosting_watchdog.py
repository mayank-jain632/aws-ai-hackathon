"""Provision only the hosted watchdog Guardrail and Memory; preview by default.

Run through ./workshop-run. Inventory is private in .local/hosting/watchdog.json.
Cleanup removes only IDs created by this script, never resources merely discovered.
"""

import argparse
import json
from pathlib import Path

import boto3
import watchdog_aws as watchdog_setup
from watchdog_aws import find_guardrail, find_memory

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
    parser.add_argument("--scope-memory", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(region_name="us-east-1")
    account = session.client("sts").get_caller_identity()["Account"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"account": account}
    if state["account"] != account:
        raise ValueError("Inventory belongs to another account")
    bedrock = session.client("bedrock")
    control = session.client("bedrock-agentcore-control")
    if args.scope_memory:
        item = state.get("memory")
        if not item or not item.get("created_here"):
            raise ValueError("Refusing to update a Memory not created by this setup")
        memory = control.get_memory(memoryId=item["id"])["memory"]
        if memory["arn"] != item["arn"]:
            raise ValueError("Memory ARN does not match private inventory")
        desired = watchdog_setup.aws.LESSONS_NAMESPACE
        if "{actorId}" not in desired:
            raise ValueError(
                "Fund-private namespace patch must land before this update"
            )
        changes = [
            {"memoryStrategyId": strategy["strategyId"], "namespaces": [desired]}
            for strategy in memory.get("strategies", [])
            if strategy["name"] == "watchdogLessons"
            and strategy.get("namespaces") != [desired]
        ]
        print("Memory namespace:", desired, "updates:", len(changes))
        if args.apply and changes:
            control.update_memory(
                memoryId=item["id"],
                memoryStrategies={"modifyMemoryStrategies": changes},
            )
            item["namespace_template"] = desired
            save(state)
        return
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
    # Reuse the lane owner's exact provisioning/configuration implementation.
    # A separate inventory prevents cleanup touching that owner's other account.
    watchdog_setup.STATE = STATE
    watchdog_setup.TAGS = TAGS
    created = watchdog_setup.apply(session, account, core_only=True)
    created["account"] = account
    for key, existing in [("guardrail", guard), ("memory", memory)]:
        created[key]["created_here"] = state.get(key, {}).get(
            "created_here", existing is None
        )
    save(created)
    state = created

    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
