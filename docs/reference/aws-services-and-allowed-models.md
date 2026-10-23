---
title: "Austin Agentic AI Hackathon 2026"
source: "https://catalog.us-east-1.prod.workshops.aws/event/dashboard/en-US/workshop/30-aws-services"
author:
published:
created: 2026-10-23
description: "Discover and participate in AWS workshops and GameDays"
tags:
  - "clippings"
---
The following AWS services can be used to accomplish your goals during this event.

## Amazon Bedrock

[Amazon Bedrock](https://aws.amazon.com/bedrock/) is a fully managed service that offers a choice of high-performing foundation models (FMs) from leading AI companies like Anthropic, OpenAI, Cohere, Meta, Mistral AI, and Amazon via a single API, along with a broad set of capabilities you need to build generative AI applications with security, privacy, and responsible AI. Using Amazon Bedrock, you can easily experiment with and evaluate top FMs for your use case, privately customize them with your data using techniques such as fine-tuning and Retrieval Augmented Generation (RAG), and build agents that execute tasks using your enterprise systems and data sources. Since Amazon Bedrock is serverless, you don't have to manage any infrastructure, and you can securely integrate and deploy generative AI capabilities into your applications using the AWS services you are already familiar with.

Important: Only the below models will be available for use in this hackathon.

- Amazon Nova: Micro, Lite, Pro, Nova 2 Lite, Nova 2 Sonic, and Nova Multimodal Embeddings
- Amazon Titan Embeddings
- Anthropic Claude: Sonnet 5, Opus 5, Fable 5, Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, and Haiku 4.5
- Cohere: Embed English, Embed Multilingual, Embed v4, and Rerank 3.5
- DeepSeek-R1
- Meta Llama 3, 3.1, 3.3, and 4 (Llama 3.2 is not available)
- Mistral AI (all models)
- OpenAI: GPT-5.4, GPT-5.5, GPT-5.6 Luna, GPT-5.6 Sol, and GPT-5.6 Terra
- TwelveLabs: Marengo 3.0 and Pegasus 1.2
- Writer: Palmyra X4 and Palmyra X5

**Data retention:** The following models require your account's data retention setting to be **Default**: GPT-5.4, GPT-5.5, GPT-5.6 Luna, GPT-5.6 Sol, GPT-5.6 Terra, and Anthropic Claude Fable 5. If requests to these models fail with a data retention error, open the Amazon Bedrock console, go to **Playground**, select the model, send a test prompt, and set data retention to **Default** when prompted. If the models are still unavailable after this change, please use one of the other models listed above.

[Documentation](https://docs.aws.amazon.com/bedrock/) [Console](https://console.aws.amazon.com/bedrock)

## Amazon Bedrock AgentCore

[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) enables you to deploy and operate highly effective AI agents securely at scale using any framework and model. AgentCore provides composable services that work with popular open-source frameworks like LangGraph, CrewAI, and Strands Agents, offering enterprise-grade security and reliability without sacrificing open-source flexibility.

Key services include:

- **Runtime**: Serverless runtime for deploying dynamic AI agents with fast cold starts and session isolation
- **Identity**: Secure agent identity and access management with existing identity provider compatibility
- **Memory**: Context-aware agents with short-term and long-term memory capabilities
- **Code Interpreter**: Secure code execution in isolated sandbox environments
- **Browser**: Cloud-based browser runtime for agents to interact with websites at scale
- **Gateway**: Secure tool discovery and API transformation for agent-compatible tools
- **Observability**: Unified dashboards for tracing, debugging, and monitoring agent performance

[Documentation](https://docs.aws.amazon.com/bedrock-agentcore/) [Console](https://console.aws.amazon.com/bedrock)

### AWS Security Agent

[AWS Security Agent](https://aws.amazon.com/security-agent/) is an autonomous security analyst that proactively secures applications throughout the development lifecycle. It understands your application architecture, code, and security requirements to continuously scan for violations and conduct on-demand penetration testing without scheduling delays. The agent performs automated security reviews tailored to your organizational requirements and discovers vulnerabilities before applications reach production.

[Documentation](https://docs.aws.amazon.com/securityagent/) [Console](https://console.aws.amazon.com/security-agent)

### AWS DevOps Agent

[AWS DevOps Agent](https://aws.amazon.com/devops-agent/) accelerates incident response and improves system reliability by acting as an always-on virtual operations team member. When alerts fire from CloudWatch, ServiceNow, or PagerDuty, the agent automatically investigates by analyzing logs, traces, and code changes. It identifies probable root causes, recommends mitigations, and coordinates incident response through Slack channels while maintaining detailed investigation timelines.

[Documentation](https://docs.aws.amazon.com/devopsagent/) [Console](https://console.aws.amazon.com/aidevops)

## Additional AWS AI/ML Services

Beyond the services listed above, you have access to the full suite of AWS AI and machine learning services during this hackathon. These include but are not limited to:

- **Amazon Rekognition** - Image and video analysis for object detection, facial analysis, and content moderation
- **Amazon Polly** - Text-to-speech service with lifelike voices
- **Amazon Translate** - Neural machine translation for real-time language translation
- **Amazon Forecast** - Time-series forecasting using machine learning
- **Amazon Macie** - Data security service that discovers and protects sensitive data
- **Amazon HealthLake** - HIPAA-eligible service for storing and analyzing health data
- **AWS HealthScribe** - Automatically generate clinical documentation from patient-clinician conversations

Feel free to explore and integrate any AWS AI/ML service that helps you build your solution. The hackathon environment provides broad access to experiment with these capabilities.

## Amazon SageMaker

[Amazon SageMaker](https://aws.amazon.com/sagemaker/) is a fully managed machine learning service. It is designed to make it easier for developers and data scientists to build, train, and deploy machine learning models at scale. It provides an integrated [Jupyter](https://docs.aws.amazon.com/sagemaker/latest/dg/notebooks.html) authoring notebook instance for easy access to your data sources for exploration and analysis, so you don't have to manage servers. It also provides common [machine learning algorithms](https://sagemaker.readthedocs.io/en/stable/algorithms/index.html) that are optimized to run efficiently against extremely large data in a distributed environment. With native support for bring-your-own-algorithms and frameworks, SageMaker offers flexible distributed training options that adjust to your specific workflows.

- To make it easier to get started, Amazon SageMaker JumpStart provides a set of solutions for the most common use cases that can be deployed readily with just a few clicks.
- Prepare, build, train, and deploy high-quality machine learning models quickly by bringing together a broad set of capabilities purpose-built for machine learning.
- Amazon SageMaker is available for free, for 2 months, as part of the AWS Free Tier program. Users can get access to 250 hours per month of ml.t3.medium notebooks usage with the Free Tier.

[Documentation](https://docs.aws.amazon.com/sagemaker/) [Console](https://console.aws.amazon.com/sagemaker)

## Amazon Simple Storage Service (S3)

[Amazon Simple Storage Service (S3)](https://aws.amazon.com/s3/) is a highly scalable and widely used cloud-based object storage service. It is designed to store and retrieve data, making it a fundamental building block for many cloud-based applications and services.

- Amazon S3 is an object storage service that offers industry-leading scalability, data availability, security, and performance.
- Store and protect any amount of data for a range of use cases, such as data lakes, websites, cloud-native applications, backups, archive, machine learning, and analytics.
- Amazon S3 is designed for 99.999999999% (11 9's) of durability, and stores data for millions of customers all around the world.

[Documentation](https://docs.aws.amazon.com/s3/) [Console](https://console.aws.amazon.com/s3)

## Amazon S3 Tables

[Amazon S3 Tables](https://aws.amazon.com/s3/features/tables/) is a new storage class for Apache Iceberg tables that delivers up to 3x faster query performance and up to 10x higher transactions per second compared to general-purpose S3 storage. S3 Tables provides purpose-built table storage optimized for analytics workloads with automatic optimization, governance, and management capabilities.

[Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables.html) [Console](https://console.aws.amazon.com/s3)

## Amazon S3 Vectors

[Amazon S3 Vectors](https://aws.amazon.com/s3/features/vectors/) is a purpose-built vector storage solution that enables high-performance similarity search and retrieval for AI and machine learning applications. S3 Vectors provides optimized storage and indexing for vector embeddings with seamless integration into generative AI workflows.

[Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors.html) [Console](https://console.aws.amazon.com/s3)

## Amazon CloudFront

[Amazon CloudFront](https://aws.amazon.com/cloudfront) is a content delivery network (CDN) service built for high performance, security, and developer convenience. Together with S3, it enables Storing and Delivering your Content with Speed and Scale. Improve security with traffic encryption and access controls, and use AWS Shield Standard to defend against DDoS attacks at no additional charge.

[Documentation](https://docs.aws.amazon.com/cloudfront/) [Console](https://console.aws.amazon.com/cloudfront)

## Amazon DynamoDB

[Amazon DynamoDB](https://aws.amazon.com/dynamodb/) is a fully managed, serverless NoSQL database service offered by AWS, designed for high-performance applications requiring seamless scalability. It supports key-value and document data models, offering consistent single-digit millisecond latency at any scale. DynamoDB features automatic scaling, high availability across multiple regions, robust security controls, and integration with other AWS services. It's particularly well-suited for serverless architectures, applications with large data volumes and strict latency requirements, and use cases with simple, known access patterns. While its denormalized data model differs from traditional relational databases, DynamoDB's simplicity and performance make it a popular choice for modern, cloud-native applications.

[Documentation](https://docs.aws.amazon.com/dynamodb/) [Console](https://console.aws.amazon.com/dynamodb)

## AWS Step Functions

[AWS Step Functions](https://aws.amazon.com/step-functions/) is a visual workflow service that allows developers to orchestrate distributed applications and microservices using a series of event-driven steps. It enables you to coordinate multiple AWS services into serverless workflows, automating processes, orchestrating microservices, and creating data and machine learning pipelines. Step Functions is based on state machines and tasks, where each step in a workflow is called a state, and tasks represent units of work performed by other AWS services. This service provides built-in controls for examining the state of each step, ensuring that your application runs in order and as expected, while reducing the amount of code you need to write and maintain.

[Documentation](https://docs.aws.amazon.com/step-functions/) [Console](https://console.aws.amazon.com/states)

## Amazon API Gateway

[Amazon API Gateway](https://aws.amazon.com/api-gateway/) is a fully managed service that makes it easy for developers to create, publish, maintain, monitor, and secure APIs at any scale. APIs act as the "front door" for applications to access data, business logic, or functionality from your backend services. Using API Gateway, you can create RESTful APIs and WebSocket APIs that enable real-time two-way communication applications. API Gateway supports containerized and serverless workloads, as well as web applications.

[Documentation](https://docs.aws.amazon.com/apigateway/) [Console](https://console.aws.amazon.com/apigateway)

## AWS Lambda

[AWS Lambda](https://aws.amazon.com/lambda/) lets you run code without provisioning or managing servers. You pay only for the compute time you consume. AWS Lambda is a compute service that runs your code in response to events and automatically manages the compute resources, making it the fastest way to turn an idea into a modern, production, serverless applications.

[Documentation](https://docs.aws.amazon.com/lambda/) [Console](https://console.aws.amazon.com/lambda)

## Amazon Q

[Amazon Q](https://aws.amazon.com/q/) is a generative AI-powered assistant created by Amazon Web Services (AWS) to help customers with their AWS-related tasks and queries.

[Documentation](https://docs.aws.amazon.com/amazonq/) [Console](https://console.aws.amazon.com/amazonq)

## Amazon Opensearch Service

[Amazon Opensearch Service](https://aws.amazon.com/opensearch-service/) Service is a managed service that makes it easy for you to perform interactive log analytics, real-time application monitoring, website search, and more. OpenSearch is an open source, distributed search and analytics suite derived from Elasticsearch. Amazon OpenSearch Service offers the latest versions of OpenSearch, support for 19 versions of Elasticsearch (1.5 to 7.10 versions), as well as visualization capabilities powered by OpenSearch Dashboards and Kibana (1.5 to 7.10 versions).

[Documentation](https://docs.aws.amazon.com/opensearch-service/) [Console](https://console.aws.amazon.com/aos)

## Amazon Textract

[Amazon Textract](https://aws.amazon.com/textract/) is a document analysis service that detects and extracts printed text, handwriting, structured data (such as fields of interest and their values) and tables from images and scans of documents. Amazon Textract's machine learning models have been trained on millions of documents so that virtually any document type you upload is automatically recognized and processed for text extraction.

[Documentation](https://docs.aws.amazon.com/textract/) [Console](https://console.aws.amazon.com/textract)

## Amazon Transcribe

[Amazon Transcribe](https://aws.amazon.com/transcribe/) is a fully managed, automatic speech recognition (ASR) service that makes it easy for developers to add speech to text capabilities to their applications. It is powered by a next-generation, multi-billion parameter speech foundation model that delivers high accuracy transcriptions for streaming and recorded speech.

[Documentation](https://docs.aws.amazon.com/transcribe/) [Console](https://console.aws.amazon.com/transcribe)

## Amazon Kendra

[Amazon Kendra](https://aws.amazon.com/kendra/) is a highly accurate and easy-to-use enterprise search service that’s powered by machine learning (ML). It allows developers to add search capabilities to their applications so their end users can discover information stored within the vast amount of content spread across their company.

[Documentation](https://docs.aws.amazon.com/kendra/) [Console](https://console.aws.amazon.com/kendra)

## Amazon Neptune

[Amazon Neptune](https://aws.amazon.com/neptune/) is a serverless graph database designed for superior scalability and availability. Neptune Database provides built-in security, continuous backups, and integrations with other AWS services.

[Documentation](https://docs.aws.amazon.com/neptune/latest/userguide/intro.html) [Console](https://console.aws.amazon.com/neptune)

## Amazon Comprehend

[Amazon Comprehend](https://aws.amazon.com/comprehend/) is a natural language processing (NLP) service that uses machine learning to find meaning and insights in text.

[Documentation](https://docs.aws.amazon.com/comprehend/) [Console](https://console.aws.amazon.com/comprehend)

## Amazon Personalize

[Amazon Personalize](https://aws.amazon.com/personalize/) is a fully managed machine learning (ML) service that uses your data to generate product and content recommendations for your users. You provide data about your end-users (e.g., age, location, device type), items in your catalog (e.g., genre, price) and interactions between users and items (e.g., clicks, purchases).

[Documentation](https://docs.aws.amazon.com/personalize/) [Console](https://console.aws.amazon.com/personalize/home)

## Amazon Lookout for Metrics

[Amazon Lookout for Metrics](https://aws.amazon.com/lookout-for-metrics/) is an AI service that detects anomalies in business data using machine learning. It identifies outliers, diagnoses root causes, and groups related anomalies, enabling quick issue resolution. The service integrates with AWS databases and third-party applications for easy monitoring and customized alerts.

[Documentation](https://docs.aws.amazon.com/lookoutmetrics/latest/dev/lookoutmetrics-welcome.html) [Console](https://console.aws.amazon.com/lookoutmetrics/home)

## Amazon Relational Database Service

[Amazon RDS](https://aws.amazon.com/rds/) is an easy-to-manage relational database service optimized for total cost of ownership. It is simple to set up, operate, and scale with demand. Amazon RDS automates undifferentiated database management tasks, such as provisioning, configuring, backing up, and patching.

[Documentation](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html) [Console](https://console.aws.amazon.com/rds/home)

## Amazon Glue

[Amazon Glue](https://aws.amazon.com/glue/) is a serverless data integration service that makes it easier to discover, prepare, and combine data for analytics, machine learning (ML), and application development. AWS Glue provides all the capabilities needed for data integration, so you can start analyzing your data and putting it to use in minutes instead of months.

[Documentation](https://docs.aws.amazon.com/glue/) [Console](https://console.aws.amazon.com/glue/home)

## Amazon Kinesis Data Streams

[Amazon Kinesis Data Streams](https://aws.amazon.com/kinesis/data-streams/) build custom applications that process or analyze streaming data for specialized needs. You can add various types of data such as clickstreams, application logs, and social media to a Kinesis data stream from hundreds of thousands of sources.

[Documentation](https://docs.aws.amazon.com/streams/latest/dev/introduction.html) [Console](https://console.aws.amazon.com/kinesis/home)

## Amazon Data Firehose

[Amazon Data Firehose](https://aws.amazon.com/firehose/) is the easiest way to load streaming data into data stores and analytics tools. It can capture, transform, and load streaming data into Amazon S3, Amazon Redshift, Amazon OpenSearch Service, Snowflake, Apache Iceberg tables and Splunk, enabling near real-time analytics with existing business intelligence tools and dashboards you’re already using today.

[Documentation](https://docs.aws.amazon.com/firehose/latest/dev/what-is-this-service.html) [Console](https://console.aws.amazon.com/firehose/home)

## Amazon EventBridge

[Amazon EventBridge](https://aws.amazon.com/eventbridge/) is a service that provides real-time access to changes in data in AWS services, your own applications, and software as a service (SaaS) applications without writing code.

[Documentation](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html) [Console](https://console.aws.amazon.com/events/home)

## Amazon QuickSight

[Amazon QuickSight](https://aws.amazon.com/de/quicksight/) powers data-driven organizations with unified business intelligence (BI) at hyperscale. With QuickSight, all users can meet varying analytic needs from the same source of truth through modern interactive dashboards, pixel-perfect reports, natural language queries and embedded analytics.

[Documentation](https://docs.aws.amazon.com/quicksight/) [Console](https://quicksight.aws.amazon.com/sn/start)

## AWS Amplify

[AWS Amplify](https://aws.amazon.com/amplify/) is a development platform that simplifies building, connecting, and hosting full-stack web and mobile applications. It provides tools for various platforms, including iOS, Android, and web, enabling easy integration of features like authentication and data storage. With its user-friendly interface and scalable infrastructure, Amplify allows developers to focus on app development without needing extensive cloud expertise.

[Documentation](https://docs.amplify.aws/) [Console](https://console.aws.amazon.com/amplify/apps)

## Amazon Athena

[Amazon Athena](https://aws.amazon.com/de/athena/) interactive analytics service that makes it simple to analyze data in Amazon Simple Storage Service (S3) using SQL. Athena is serverless, so there is no infrastructure to set up or manage, and you can start analyzing data immediately.

[Documentation](https://docs.aws.amazon.com/athena/) [Console](https://console.aws.amazon.com/athena/home)

## Amazon Redshift

[Amazon Redshift](https://aws.amazon.com/de/redshift/) uses SQL to analyze structured and semistructured data across data warehouses, operational databases, and data lakes, using hardware and ML designed by AWS to deliver the best price performance at any scale.

[Documentation](https://docs.aws.amazon.com/redshift/) [Console](https://console.aws.amazon.com/redshift/home)

## Amazon Simple Queue Service (SQS)

[Amazon Simple Queue Service (SQS)](https://aws.amazon.com/sqs/) is a fully managed message queuing service that enables you to decouple and scale microservices, distributed systems, and serverless applications. SQS eliminates the complexity and overhead associated with managing and operating message-oriented middleware, and empowers developers to focus on differentiating work. Using SQS, you can send, store, and receive messages between software components at any volume, without losing messages or requiring other services to be available.

[Documentation](https://docs.aws.amazon.com/sqs/) [Console](https://console.aws.amazon.com/sqs)

## Amazon Lex

[Amazon Lex](https://aws.amazon.com/lex/) is a fully managed AI service with advanced natural language models to design, build, test, and deploy conversational interfaces in applications. With Amazon Lex, you can build bots that increase contact center productivity, automate simple tasks, and drive operational efficiencies across the enterprise. As a fully managed service, Amazon Lex scales automatically, so you don't need to worry about managing infrastructure.

[Documentation](https://docs.aws.amazon.com/lex/) [Console](https://console.aws.amazon.com/lex)

## Amazon ElastiCache

[Amazon ElastiCache](https://aws.amazon.com/elasticache/) is a fully managed in-memory caching service supporting flexible, real-time use cases. You can use ElastiCache for caching, which accelerates application and database performance, or as a primary data store for use cases that don't require durability like session stores, gaming leaderboards, streaming, and analytics. ElastiCache is compatible with Redis and Memcached.

[Documentation](https://docs.aws.amazon.com/elasticache/) [Console](https://console.aws.amazon.com/elasticache)

## Amazon MemoryDB for Redis

[Amazon MemoryDB for Redis](https://aws.amazon.com/memorydb/) is a durable, in-memory database service that delivers ultra-fast performance. It is purpose-built for modern applications with microservices architectures. MemoryDB stores the entire dataset in memory, enables microsecond read latency, single-digit millisecond write latency, and offers Multi-AZ durability. It is compatible with Redis, a popular open source data store, enabling you to quickly build applications using the same flexible and friendly Redis data structures, APIs, and commands that they already use today.

[Documentation](https://docs.aws.amazon.com/memorydb/) [Console](https://console.aws.amazon.com/memorydb)