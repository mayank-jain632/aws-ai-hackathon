"""Lane C: five analyst agents and one PM agent on Bedrock (Converse API).

Each analyst module exposes `run(universe, cutoff) -> (Memo, list[Source])`.
`pm.run(memos, universe, cutoff) -> list[Weight]`.

Set MOCK_AGENTS=1 to serve the fixture memos and weights without calling Bedrock.
"""
