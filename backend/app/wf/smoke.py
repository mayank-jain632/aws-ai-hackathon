"""One real-model decision on a clean date. Run: AWS_PROFILE=default AWS_REGION=us-east-1 python -m backend.app.wf.smoke"""

from __future__ import annotations

import logging

from backend.app.wf.config import WfConfig
from backend.app.wf.llm import Llm
from backend.app.wf.pipeline import run_decision

AS_OF = "2025-10-03"


def main() -> None:
    from backend.app.wf.pit import PitData  # owned by the data lane

    logging.basicConfig(level=logging.INFO)
    cfg = WfConfig()
    llm = Llm(cfg.model_id, temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    rec = run_decision(PitData(), llm, cfg, AS_OF, list(cfg.universe))
    out = [f"abstained: {rec.abstained_analysts}"]
    out += [f"{m.analyst}: {m.headline}" for m in rec.memos]
    out += [rec.plan.model_dump_json(indent=1), rec.orders.model_dump_json(indent=1), str(llm.stats())]
    logging.getLogger("wf.smoke").info("\n".join(out))


if __name__ == "__main__":
    main()
