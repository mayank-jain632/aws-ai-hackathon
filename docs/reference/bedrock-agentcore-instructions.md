---
title: "Austin Agentic AI Hackathon 2026"
source: "https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US/workshop/50-how-to-instructions-helpful-resources/53-bedrock-agentcore"
author:
published:
created: 2026-10-23
description: "Discover and participate in AWS workshops and GameDays"
tags:
  - "clippings"
---
## Introduction to Amazon Bedrock AgentCore

Amazon Bedrock AgentCore enables you to deploy and operate highly effective AI agents securely at scale using any framework and model. With AgentCore, developers can accelerate AI agents into production with enterprise-grade scale, reliability, and security. AgentCore provides composable services that work with popular open-source frameworks like LangGraph, CrewAI, and Strands Agents, offering the flexibility of open-source with enterprise security and reliability.

![](https://www.youtube.com/watch?v=usFIb9aEd1U)

## Key Services and Capabilities

### AgentCore Runtime

**Purpose-built serverless runtime** for deploying dynamic AI agents with:

- **Fast cold starts** and extended runtime support for agentic workloads
- **True session isolation** with built-in identity management
- **Multi-modal payload support** for complex agent interactions

### AgentCore Identity

**Secure agent identity and access management** featuring:

- **Existing identity provider compatibility** - no user migration required
- **Secure token vault** to minimize consent fatigue
- **Just-enough access** with secure permission delegation
- **Streamlined AI agent experiences** with proper IAM role configuration

### AgentCore Memory

**Context-aware agent memory management** with:

- **Short-term memory** for multi-turn conversations
- **Long-term memory** shared across agents and sessions
- **Memory scoping namespaces** for organized data management

### AgentCore Code Interpreter

**Secure code execution environment** providing:

- **Isolated sandbox environments** for safe code execution
- **Advanced configuration support** for complex workflows
- **Enterprise security requirements** compliance
- **Seamless framework integration** with popular AI frameworks

### AgentCore Browser

**Cloud-based browser runtime** enabling:

- **Website interaction at scale** for AI agents
- **Enterprise-grade security** with comprehensive observability
- **Automatic scaling** without infrastructure management
- **Session management** with ability to list and monitor active browser sessions

### AgentCore Gateway

**Unified connectivity layer** for agent-tool integration:

**Gateway Workflow:**

1. **Define tools** using OpenAPI specifications or JSON schemas
2. **Create Gateway endpoint** via AWS console or SDK (serves as MCP entry point)
3. **Add targets** to configure request routing to specific tools
4. **Connect agents** to Gateway endpoint for unified MCP interface access

**Key Features:**

- **Model Context Protocol (MCP) support**
- **Inbound/Outbound Authorization** for secure tool access
- **API transformation** - converts APIs, Lambda functions into agent-compatible tools
- **OAuth and IAM credential support** for authentication flows

### AgentCore Observability

**Comprehensive monitoring and debugging** with:

- **OpenTelemetry compatible telemetry** for industry-standard monitoring
- **Unified operational dashboards** for production visibility
- **Detailed workflow visualizations** showing each agent step
- **Performance metrics** including token usage, latency, session duration, error rates

## Getting Started

[From the AWS Management Console](https://console.aws.amazon.com/bedrock/)

## Key Operations and Documentation

- [Host agents with AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [Runtime troubleshooting guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-troubleshooting.html)
- [Set up Gateway connections](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-building.html)
- [Configure VPC connectivity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-vpc.html)
- [Add memory to your AI agent](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory.html)
- [Use built-in tools](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-tools.html)
- [Code examples repository](https://github.com/awslabs/amazon-bedrock-agentcore-samples/)

More comprehensive information can be found in the [Amazon Bedrock AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) .

Amazon Bedrock AgentCore offers flexible, consumption-based pricing with no upfront commitments. For details, see [Amazon Bedrock AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) .