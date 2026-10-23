---
title: "Track 3: Financial Portfolio Management | Austin Agentic AI Hackathon"
source: "https://atx.rahman.dev/track-3.html"
author:
published:
created: 2026-10-23
description: "Track 3: Financial Portfolio Management background and instructions."
tags:
  - "clippings"
---
## Track 3:Financial Portfolio Management

Build agents that analyze historical price patterns, company financials, macroeconomic indicators, market sentiment, and geopolitical factors to construct investment portfolios. Use open-source SEC data and past market data — portfolios will be evaluated against actual performance.

**How to join the event**

Use a fresh browser window or private window, sign in to Workshop Studio, enter the 12-digit event access code from the event operator, and open the temporary AWS account provided for the event. [Watch the login walkthrough video ↗](https://atx.rahman.dev/hackathon-login.mp4)

[Open Workshop Studio join page ↗](https://catalog.us-east-1.prod.workshops.aws/join?access-code=a52a-010f17-28)

![Workshop Studio sign-in screen with email one-time password, Login with Amazon, and Amazon employee options](https://atx.rahman.dev/workshop-studio-step-1.svg)

1\. Sign in Choose the sign-in method that applies to you.

![Workshop Studio event page showing event details and AWS account access](https://atx.rahman.dev/workshop-studio-step-2.svg)

2\. Join the event Enter the event code, review the terms, and open AWS account access.

![AWS Management Console showing the WSParticipantRole participant role and selected region](https://atx.rahman.dev/workshop-studio-step-3.svg)

3\. Verify access Open the console and confirm you are using WSParticipantRole in the workshop region.

**Optional CLI access:** Workshop Studio can provide temporary AWS CLI credentials. They expire after 60 minutes, so copy a fresh set if needed. When you are ready, click this header again to collapse the walkthrough.

**Choose your build environment**

After joining the event, return to the Event dashboard and scroll to `Event outputs`. Choose the browser-based VS Code experience or the Linux UI-based Kiro alternative.

[Open Event dashboard ↗](https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US)

### VS Code web experience

- In `Event outputs`, find `VScodeIdeURL`, described as the Code Editor URL.
- Open the value in a new browser tab. It opens the shared `/workshop` folder for the event.
- Use the integrated terminal and editor to build, run, and share your track prototype.

### Kiro on Ubuntu Desktop

- In `Event outputs`, find `KiroRDPConnectionURL`, the one-click URL for the Kiro Ubuntu Desktop.
- Paste it into a new browser tab. The one-click URL normally signs you in automatically.
- If the desktop prompts for credentials, use the username and password from `KiroRDPCredentials`. Do not copy those values into workshop notes or chat.

**Which should I choose?** Use `VScodeIdeURL` for the fastest web-based path. Choose Kiro when you want a full Linux desktop UI and prefer working inside an Ubuntu environment.

### Want Positron?

If your idea benefits from a notebook-first workflow, run the optional bootstrap from the workshop VS Code terminal. It will create or reuse the Positron workspace and print a Studio URL. Setup can take 20-30 minutes.

Download the script

`curl -fsSL https://atx.rahman.dev/setup_positron_sagemaker_from_private_ecr.py -o positron.py`

Run the script

`uv run positron.py`

**Set up Bedrock + AgentCore**

Use this shared starter kit as a working baseline before adapting your agent to this track. It checks direct Amazon Bedrock access, creates an AgentCore execution role, deploys a minimal runtime, and gives you a small project to extend.

[Download the hackathon kit (.zip) ↗](https://atx.rahman.dev/hackathon-kit.zip)

- `infer.py` runs a direct Bedrock Converse smoke test with the workshop AWS role.
- `setup_agentcore_role.py` creates the execution role used by the deployed runtime.
- `agent.py` is a minimal AgentCore handler that you can replace with your track workflow.
- `README.md` contains the full setup, deployment, invocation, and troubleshooting steps.

- Run the direct inference check to confirm your workshop terminal can call Bedrock.
- Deploy the sample runtime to verify the separate AgentCore execution role path.
- Keep the working baseline, then adapt the handler and tools to your portfolio-management workflow.

Download and unpack the starter kit

`curl -fsSL https://atx.rahman.dev/hackathon-kit.zip -o hackathon-kit.zip && unzip -qo hackathon-kit.zip`

**Before you run it:** use the AWS credentials from your workshop environment. The role setup requires the participant account to allow `iam:CreateRole`, `iam:PutRolePolicy`, and `iam:PassRole`. AgentCore runtimes can incur charges, so follow the README cleanup steps when you finish.

## Make a portfolio you can test.

Combine different kinds of evidence, turn the evidence into an explicit investment thesis, and then evaluate the result against what actually happened in the market.

### Markets are multi-signal problems

Price history is only one input. Company financials, macroeconomic indicators, sentiment, and geopolitical factors can change the story around an asset. Your agents should make those connections legible.

### Make the thesis inspectable

Show which sources influenced the portfolio, how the agents weighed them, and what would cause the system to change its position or confidence.

- Pick a small universe, such as 5–15 tickers, and make the historical evaluation cutoff explicit.
- Use specialist analyst agents for price and technical signals, fundamentals, macro conditions, sentiment, and geopolitical events.
- Feed those perspectives into a portfolio-manager agent that reconciles them into explicit target weights and a rationale for each position.
- Backtest the portfolio from the cutoff forward and report return, maximum drawdown, and performance versus a simple baseline.

- State the asset universe, cutoff date, and baseline.
- Show the agents' reasoning for at least one allocation decision.
- Compare the equity curve and key metrics with the baseline.

Avoid look-ahead bias by using only data available on or before the cutoff. Keep the experiment reproducible, explain the benchmark, and separate historical evaluation from any suggestion of live financial advice or trading.

## Start with data.Borrow patterns.

Use one dataset to establish a baseline, then borrow ideas from the sample architectures when you extend the prototype into a multi-agent or RAG-backed workflow.

[**SEC Financial Statement Data Sets** Official XBRL financial statement data in quarterly ZIP files. Add a descriptive User-Agent header when downloading.](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) [**Stooq historical prices** Daily historical prices for US stocks, ETFs, and indices without an API key.](https://stooq.com/db/h/) [**FRED macro indicators** Macroeconomic series such as CPI, GDP, unemployment, interest rates, and the yield curve.](https://fred.stlouisfed.org/docs/api/fred/) [**Huge Stock Market Dataset** Daily OHLCV data for US stocks and ETFs, available through Kaggle.](https://www.kaggle.com/datasets/borismarjanovic/price-volume-data-for-all-us-stocks-etfs) [**S&P 500 Stock Data** Daily prices for S&P 500 companies, available through Kaggle.](https://www.kaggle.com/datasets/camnugent/sandp500) [**GDELT** Global events and media-tone data that can support geopolitical and sentiment signals.](https://www.gdeltproject.org/)

[**Guidance for Investment Analysis** Financial statement summarization, 10-K and 10-Q RAG, and news-sentiment analysis on Amazon Bedrock.](https://github.com/aws-solutions-library-samples/guidance-for-investment-analysis-using-amazon-bedrock) [**Hedge Fund Analyst Multi-Agent** Fundamental, technical, and market analyst agents coordinated by a supervisor on Bedrock.](https://github.com/aws-samples/hedge-fund-analyst-multi-agent-collaboration) [**Amazon Bedrock Agent Samples** Example notebooks and multi-agent patterns, including portfolio-assistant examples.](https://github.com/awslabs/amazon-bedrock-agent-samples) [**Sample Wealth Advisor Demo Platform** AWS-native wealth-advisor patterns combining AI/ML, a data lake, and a graph database.](https://github.com/aws-samples/sample-wealth-advisor-demo-platform)

- Use only information that would have been available on or before the selected cutoff date.
- Document the universe, data window, assumptions, and rebalancing rules.
- Compare against a simple baseline, such as equal weighting or a broad-market index.
- Present results as a historical experiment, not as live financial advice or a trading recommendation.

**Good demo question**

Can your agents explain not only what the portfolio holds, but also how the thesis performed when tested against actual market outcomes?