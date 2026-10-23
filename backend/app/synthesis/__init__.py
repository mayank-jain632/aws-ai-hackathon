"""Synthesis layer: research memos -> frozen strategy -> significance -> order plan.

Sits on top of the desk gates in `backend.app.desk` and the paper adapter in
`backend.app.paper`. Nothing here can approve a strategy, change a verdict or submit an
order; it prepares inputs for those existing, backend-enforced steps.
"""
