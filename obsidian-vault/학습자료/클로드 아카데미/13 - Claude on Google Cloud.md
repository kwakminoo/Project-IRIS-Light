# Claude on Google Cloud

> Source: https://anthropic.skilljar.com/claude-with-google-vertex  
> 정리일: 2026-07-22  
> 출처: Anthropic Academy (Claude Academy)

Google Cloud(Vertex AI)에서 Anthropic 모델을 다루는 종합 강좌. **대부분 플랫폼 내장 동영상**이라 외부 URL/자막은 없음 → Skilljar에서 시청. 아래는 전체 커리큘럼 + 텍스트 레슨 원문.

---

## 섹션 1. Accessing Claude on Vertex AI

- Welcome to the course
- Overview of Claude models
- Accessing the API
- **Vertex AI Setup (텍스트 — 아래 전문)**
- Making a request
- Multi-turn conversations
- Chat exercise
- System prompts
- System prompts exercise
- Temperature
- Course satisfaction survey
- Response streaming
- Controlling model output
- Structured data
- Structured data exercise
- Quiz on accessing Claude with the API

### 📄 Vertex AI Setup (텍스트 레슨 전문)

다음 영상에서 Vertex AI로 Claude 모델을 호출한다. 이를 위해 아래 설정이 필요하다.

**Step One: Vertex에서 Anthropic 모델 활성화**

1. [https://console.cloud.google.com/vertex-ai/dashboard](https://console.cloud.google.com/vertex-ai/dashboard) 로 이동
2. 왼쪽 내비에서 **Model Garden** 클릭
3. **Search models**에 `Anthropic` 입력
4. 사용할 모델 클릭

**Step Two: 모델 Enable**

- 모델 정보 페이지에서 **Enable** 버튼 클릭
- Enable 버튼이 없으면 이미 접근 권한이 있는 것

**Step Three: gcloud CLI 설치**

- 미설치 시: [https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)

**Step Four: gcloud CLI 로그인·인증**

```bash
gcloud init
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default login
```

Anthropic SDK는 Vertex 접근 시 이 자격 증명을 자동으로 사용한다.

---

## 섹션 2. Prompt evaluation

- Prompt evaluation
- A typical eval workflow
- Generating test datasets
- Running the eval
- Model based grading
- Code based grading
- Exercise on prompt evals
- Quiz on prompt evaluation

## 섹션 3. Prompt engineering

- Prompt engineering
- Being clear and direct
- Being specific
- Structure with XML tags
- Providing examples
- Exercise on prompting
- Quiz on prompt engineering techniques

## 섹션 4. Tool use

- Introducing tool use
- Project overview
- Tool functions
- Tool schemas
- Handling message blocks
- Sending tool results
- Multi-turn conversations with tools
- Implementing multiple turns
- Using multiple tools
- The batch tool
- Tools for structured data
- The text edit tool
- The web search tool
- Quiz on tool use with Claude

## 섹션 5. RAG

- Introducing Retrieval Augmented Generation
- Text chunking strategies
- Text embeddings
- The full RAG flow
- Implementing the RAG flow
- BM25 lexical search
- A Multi-index RAG pipeline
- Reranking results
- Contextual retrieval
- Quiz on Retrieval Augmented Generation

## 섹션 6. Features of Claude

- Extended thinking
- Image support
- PDF support
- Citations
- Prompt caching
- Rules of prompt caching
- Prompt caching in action
- Quiz on features of Claude

## 섹션 7. MCP

- Introducing MCP
- MCP clients
- Project setup
- Defining tools with MCP
- The server inspector
- Implementing a client
- Defining resources
- Accessing resources
- Defining prompts
- Prompts in the client
- MCP review
- Quiz on Model Context Protocol

## 섹션 8. Agents, Claude Code & Computer Use

- Anthropic apps
- Claude Code setup
- Claude Code in action
- Enhancements with MCP servers
- Parallelizing Claude Code
- Automated debugging
- Computer use
- How computer use works
- Agents and workflows
- Parallelization workflows
- Chaining workflows
- Routing workflows
- Agents and tools
- Environment inspection
- Workflows vs agents
- Quiz on agents and workflows
- Final assessment quiz
- Course Wrap Up

관련: [[07 - Building with the Claude API]] · [[12 - Claude with Amazon Bedrock]]
