---
title: "awslabs/amazon-bedrock-agent-samples: Example Jupyter notebooks 📓 and code scripts 💻 for using Amazon Bedrock Agents 🤖 and its functionalities"
source: "https://github.com/awslabs/amazon-bedrock-agent-samples"
author:
published:
created: 2026-10-23
description:
tags:
  - "clippings"
---
## Amazon Bedrock Agent Samples

👋 👋 Welcome to the Amazon Bedrock Agent Samples repository 👋 👋

> [!caution] Caution
> The examples provided in this repository are for experimental and educational purposes only. They demonstrate concepts and techniques but are not intended for direct use in production environments. Make sure to have Amazon Bedrock Guardrails in place to protect against [prompt injection](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-injection.html).

This repository provides examples and best practices for working with [Amazon Bedrock Agents](https://aws.amazon.com/bedrock/agents/).

Amazon Bedrock Agents enables you to automate complex workflows, build robust and scalable end-to-end solutions from experimentation to production and quickly adapt to new models and experiments.

With [Amazon Bedrock multi-agent collaboration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agents-collaboration.html) you can plan and execute complex tasks across agents using supervisor mode. You can also have unified conversations across agents with built-in intent classification using the supervisor with routing mode and fallback to supervisor mode when a single intention cannot be detected. Amazon Bedrock Agents provides you with traces to observe your agents' behavior across multi-agent flows and provides guardrails, security and privacy that are standard across Amazon Bedrock features.

![architecture](https://github.com/awslabs/amazon-bedrock-agent-samples/raw/main/images/architecture.gif?raw=true)

architecture

### Demo Video

---

This one-hour video takes you through a deep dive introduction to Amazon Bedrock multi-agent collaboration, including a pair of demos, and a walkthrough of Unifying customer experiences, and Automating complex processes. You’ll also see a customer explain their experience with multi-agent solutions.

[![](https://camo.githubusercontent.com/70fb65536e3e46d1f8d6f23e52d23046dcabac9820e12ecc2c5f4c4eb5511c6a/68747470733a2f2f6d61726b646f776e2d766964656f732d6170692e6a6f7267656e6b682e6e6f2f796f75747562652f37707645594c5731795a773f77696474683d363430266865696768743d3336302666696c65747970653d6a706567)](https://youtu.be/7pvEYLW1yZw)

## �� Table of Contents ��

## Overview

Amazon Bedrock Agents enables you to create AI-powered assistants that can perform complex tasks and interact with various APIs and services.

This repository provides practical examples to help you understand and implement agentic solutions.

The solutions presented here use the [boto3 SDK in Python](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agent.html), however, you can create Bedrock Agents solutions using any of the AWS SDKs for [C++](https://sdk.amazonaws.com/cpp/api/LATEST/aws-cpp-sdk-bedrock-agent/html/annotated.html), [Go](https://docs.aws.amazon.com/sdk-for-go/api/service/bedrockagent/), [Java](https://sdk.amazonaws.com/java/api/latest/software/amazon/awssdk/services/bedrockagent/package-summary.html), [JavaScript](https://docs.aws.amazon.com/AWSJavaScriptSDK/v3/latest/client/bedrock-agent/), [Kotlin](https://sdk.amazonaws.com/kotlin/api/latest/bedrockagent/index.html), [.NET](https://docs.aws.amazon.com/sdkfornet/v3/apidocs/items/BedrockAgent/NBedrockAgent.html), [PHP](https://docs.aws.amazon.com/aws-sdk-php/v3/api/namespace-Aws.BedrockAgent.html), [Ruby](https://docs.aws.amazon.com/sdk-for-ruby/v3/api/Aws/BedrockAgent.html), [Rust](https://docs.rs/aws-sdk-bedrockagent/latest/aws_sdk_bedrockagent/), [SAP ABAP](https://docs.aws.amazon.com/sdk-for-sap-abap/v1/api/latest/bdr/index.html) or [Swift](https://sdk.amazonaws.com/swift/api/awsbedrockruntime/0.34.0/documentation/awsbedrockruntime)

## Repository Structure

```
├── examples/agents/
│   ├── agent_with_code_interpretation/
│   ├── user_confirmation_agents/
│   ├── inline_agent/
|   └── ....
├── examples/multi_agent_collaboration/
│   ├── 00_hello_world_agent/
│   ├── devops_agent/
│   ├── energy_efficiency_management_agent/
|   └── ....
├── src/shared/
│   ├── working_memory/
│   ├── stock_data/
│   ├── web_search/
|   └── ....
├── src/utils/
│   ├── bedrock_agent_helper.py
|   ├── bedrock_agent.py
|   ├── knowledge_base_helper.py
|   └── ....
```
- [examples/agents/](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents): Shows Amazon Bedrock Agents examples.
- [examples/multi\_agent\_collaboration/](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration): Shows Amazon Bedrock multi-agent collaboration examples.
- [src/shared](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src/shared): This module consists of shared tools that can be reused by Amazon Bedrock Agents via Action Groups. They provide functionality like [Web Search](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src/shared/file_store), [Working Memory](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src/shared/working_memory), and [Stock Data Lookup](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src/shared/stock_data).
- [src/utils](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src/utils): This module contains utilities for building and using various Amazon Bedrock features, providing a higher level of abstraction than the underlying APIs.

## Getting Started

1. Navigate to [`src/`](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/src) for more details.
2. To get started, navigate to the example you want to deploy in the [`examples/*`](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples) directory.
3. Follow the deployment steps in the `examples/*/*/README.md` file of the example.

## Agents examples

- [Analyst assistant using Code Interpretation](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/agent_with_code_interpretation)
- [Agent using Amazon Bedrock Guardrails](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/agent_with_guardrails_integration)
- [Agent using Amazon Bedrock Knowledge Bases](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/agent_with_knowledge_base_integration)
- [Agent with long term memory](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/agent_with_long_term_memory)
- [Agent using models not yet optimized for Bedrock Agents](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/agent_with_models_not_yet_optimized_for_bedrock_agents)
- [AWS CDK Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/cdk_agent)
- [Computer use Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/computer_use)
- [Custom orchestration Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/custom_orchestration_agent)
- [Configure an inline agent at runtime](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/inline_agent)
- [Utilize LangChain Tools with Amazon Bedrock Inline Agents](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/langchain_tools_with_inline_agent)
- [Provide conversation history to Amazon Bedrock Agents](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/manage_conversation_history)
- [Agent using OpenAPI schema](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/open_api_schema_agent)
- [Agents with user confirmation before action execution](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/user_confirmation_agents)
- [Agents with access to house security camera in cloudformation](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/connected_house_agent)
- [Agents with metadata filtering](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/metadata_filtering_amazon_bedrock_agents)
- [Agents with human\_in\_the\_loop](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents/human_in_the_loop)

## Multi-agent collaboration examples

- [00\_hello\_world\_agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/00_hello_world_agent)
- [DevOps Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/devops_agent)
- [Energy Efficiency Management Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/energy_efficiency_management_agent)
- [Assistant Agent with metadata filtering](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/metadata_filtering)
- [Mortgage Assistant Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/mortgage_assistant)
- [Portfolio Assistant Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/portfolio_assistant_agent)
- [Real Estate Investment Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/real_estate_investment_agent)
- [Startup Advisor Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/startup_advisor_agent)
- [Support Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/support_agent)
- [Team Poems Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/team_poems_agent)
- [Trip Planner Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/trip_planner_agent)
- [Voyage Virtuso Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/voyage_virtuoso_agent)
- [Contract Assistant Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/contract_assistant_agent)
- [Financial Assitant Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/Financial-Analyst-Agents)
- [Investment Research Agent](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/multi_agent_collaboration/investment_research_agent)

## UX Demos

- [Streamlit Demo UI](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents_ux/streamlit_demo)
- [Data Analyst Assistant for Video Game Sales](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents_ux/video_games_sales_assistant_with_amazon_bedrock_agents)
- [Dynamic AI Assistant Demo using Amazon Bedrock Inline Agents](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/examples/agents_ux/inline-agent-hr-assistant)

## Best Practices

The code samples highlighted in this repository focus on showcasing different Amazon Bedrock Agents capabilities.

Please check out our two-part blog series for best practices around building generative AI applications with Amazon Bedrock Agents:

- [Best practices for building robust generative AI applications with Amazon Bedrock Agents – Part 1](https://aws.amazon.com/blogs/machine-learning/best-practices-for-building-robust-generative-ai-applications-with-amazon-bedrock-agents-part-1/)
- [Best practices for building robust generative AI applications with Amazon Bedrock Agents – Part 2](https://aws.amazon.com/blogs/machine-learning/best-practices-for-building-robust-generative-ai-applications-with-amazon-bedrock-agents-part-2/)

Understand Bedrock Multi-agents Collaboration concepts by reading our [blog post](https://aws.amazon.com/blogs/machine-learning/unlocking-complex-problem-solving-with-multi-agent-collaboration-on-amazon-bedrock/) written by Bedrock Agent's science team

🔗 **Related Links**:

- [Amazon Bedrock Agents Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html)
- [Amazon Bedrock multi-agent collaboration](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-multi-agents-collaboration.html)
- [Boto3 Python SDK Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agent.html)
- [Amazon Bedrock Samples](https://github.com/aws-samples/amazon-bedrock-samples/tree/main)

## Security

See [CONTRIBUTING](https://github.com/awslabs/amazon-bedrock-agent-samples/blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the Apache-2.0 License.

> [!important] Important
> Examples in this repository are for demonstration purposes. Ensure proper security and testing when deploying to production environments.

[![](https://camo.githubusercontent.com/c78979ef13619631ff8879a872c4c62ae19dd937bed740a21621b2a177bfea8f/68747470733a2f2f636f6e747269622e726f636b732f696d6167653f7265706f3d6177736c6162732f616d617a6f6e2d626564726f636b2d6167656e742d73616d706c6573)](https://github.com/awslabs/amazon-bedrock-agent-samples/graphs/contributors)

[![Forkers repo roster for @awslabs/amazon-bedrock-agent-samples](https://camo.githubusercontent.com/845f5c52937e07d676c0a3a61d2c09615600ce65a5662837b4605dc9b665d17e/68747470733a2f2f7265706f726f737465722e636f6d2f666f726b732f6177736c6162732f616d617a6f6e2d626564726f636b2d6167656e742d73616d706c6573)](https://github.com/awslabs/amazon-bedrock-agent-samples/network/members)