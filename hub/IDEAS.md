# Ideas parking lot

Append-only, one line per idea: `- HH:MM · who · idea · why it might matter`. Nothing here gets built until it becomes an accepted decision in `hub/DECISIONS.md`.

- 12:00 · Aaron · Open desk: people and outside agents take seats through the same contract (UI for people, MCP through AgentCore Gateway for agents), and the PM weighs every seat · makes the human plus agent idea concrete and scores on AWS usage
- 12:00 · Aaron · Seat scorecard: rerun the PM with each seat left out and show which seats helped or hurt against equal weight · makes "show the reasoning" measurable
- 12:00 · Aaron · Leakage check: run the same cutoff with tickers masked as "Company 3, semiconductors" and show the gap · answers the first question a finance judge will ask
- 12:00 · Aaron · Walk-forward: run every slider cutoff and report how often the book beat equal weight · one date is an anecdote, thirty are evidence
- 12:00 · Aaron · Debate round: the PM sends the two most opposed analysts back to rebut each other before it sets weights · turns a fan-out of calls into agents actually talking
- 12:00 · Aaron · AgentCore Memory for the PM: it remembers its "changes my mind" triggers across cutoffs and says when one fired · gives the cutoff drag a storyline
- 12:15 · Aaron · Join the two halves: expose `backend/app/data.py` loaders and `backend/app/backtest.py` as canvas agent tools, so canvas agents reason over cutoff-safe data and every book they propose gets backtested · uses Chaithu's pipeline instead of stranding it, and is the fastest route to "breadth of data inputs"
