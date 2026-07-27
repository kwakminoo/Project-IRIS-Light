# Building with the Claude API

> Source: https://anthropic.skilljar.com/claude-with-the-anthropic-api  
> 정리일: 2026-07-21  
> 출처: Anthropic Academy (Claude Academy)

Claude API로 Anthropic 모델을 다루는 전 범위를 다루는 종합 강좌. **동영상 강의 85개**로 구성(플랫폼 내장 동영상이라 외부 링크/자막은 제공되지 않음 → 사이트에서 시청). 아래는 전체 커리큘럼(학습 순서)과 텍스트 레슨 원문이다.

---

## 섹션 1. Accessing the API (API 접근)

- Welcome to the course (동영상)
- Overview of Claude models (동영상)
- Accessing the API (동영상)
- **Getting an API key (텍스트 — 아래 전문 참고)**
- Making a request (동영상)
- Multi-Turn conversations (동영상)
- Chat exercise (동영상)
- System prompts (동영상)
- System prompts exercise (동영상)
- Temperature (동영상)
- Course satisfaction survey (설문)
- Response streaming (동영상)
- Structured data (동영상)
- Structured data exercise (동영상)
- Quiz on accessing Claude with the API (퀴즈)

### 📄 Getting an API key (텍스트 레슨 전문)

다음 영상에서 Anthropic API에 요청을 보낼 것이다. 이를 위해 비밀 API 키가 필요하다. 아래 절차로 API 키를 생성한다.

**Step One: Anthropic API 콘솔로 이동**  
브라우저에서 [https://console.anthropic.com/](https://console.anthropic.com/) 로 이동해 Anthropic 계정으로 로그인한다.

**Step Two: 'Get API Keys' 버튼 클릭**  
메인 대시보드 페이지 오른쪽 상단에 있다.

**Step Three: 'Create Key' 버튼 클릭**  
페이지 오른쪽 상단의 'Create Key' 버튼을 클릭한다.

**Step Four: 워크스페이스와 키 이름 입력**  
워크스페이스 'Default'에서 키를 생성하고 키 이름을 입력한다(식별용). 예: 'Anthropic Course'.

**Step Five: 키 복사**  
팝업 창에 API 키가 표시된다. 이 키를 복사해 보관한다(다음 영상에서 사용). **이 키는 한 번만 표시**되므로 반드시 복사한다. 실수로 창을 닫으면 기존 키를 삭제하고 다시 생성한다.

---

## 섹션 2. Prompt evaluation (프롬프트 평가)

- Prompt evaluation (동영상)
- A typical eval workflow (동영상)
- Generating test datasets (동영상)
- Running the eval (동영상)
- Model based grading (동영상)
- Code based grading (동영상)
- Exercise on prompt evals (동영상)
- Quiz on prompt evaluation (퀴즈)

---

## 섹션 3. Prompt engineering (프롬프트 엔지니어링)

- Prompt engineering (동영상)
- Being clear and direct (동영상)
- Being specific (동영상)
- Structure with XML tags (동영상)
- Providing examples (동영상)
- Exercise on prompting (동영상)
- Quiz on prompt engineering techniques (퀴즈)

---

## 섹션 4. Tool use (도구 사용)

- Introducing tool use (동영상)
- Project overview (동영상)
- Tool functions (동영상)
- Tool schemas (동영상)
- Handling message blocks (동영상)
- Sending tool results (동영상)
- Multi-turn conversations with tools (동영상)
- Implementing multiple turns (동영상)
- Using multiple tools (동영상)
- Fine grained tool calling (동영상)
- The text edit tool (동영상)
- The web search tool (동영상)
- Quiz on tool use with Claude (퀴즈)

---

## 섹션 5. Features of Claude & RAG (기능과 RAG)

- Introducing Retrieval Augmented Generation (동영상)
- Text chunking strategies (동영상)
- Text embeddings (동영상)
- The full RAG flow (동영상)
- Implementing the RAG flow (동영상)
- BM25 lexical search (동영상)
- A Multi-Index RAG pipeline (동영상)
- Extended thinking (동영상)
- Image support (동영상)
- PDF support (동영상)
- Citations (동영상)
- Prompt caching (동영상)
- Rules of prompt caching (동영상)
- Prompt caching in action (동영상)
- Code execution and the Files API (동영상)
- Quiz on features of Claude (퀴즈)

---

## 섹션 6. MCP (Model Context Protocol)

- Introducing MCP (동영상)
- MCP clients (동영상)
- Project setup (동영상)
- Defining tools with MCP (동영상)
- The server inspector (동영상)
- Implementing a client (동영상)
- Defining resources (동영상)
- Accessing resources (동영상)
- Defining prompts (동영상)
- Prompts in the client (동영상)
- MCP review (동영상)
- Quiz on Model Context Protocol (퀴즈)

---

## 섹션 7. Agents and Workflows (에이전트와 워크플로)

- Anthropic apps (동영상)
- Claude Code setup (동영상)
- Claude Code in action (동영상)
- Enhancements with MCP servers (동영상)
- Agents and workflows (동영상)
- Parallelization workflows (동영상)
- Chaining workflows (동영상)
- Routing workflows (동영상)
- Agents and tools (동영상)
- Environment inspection (동영상)
- Workflows vs agents (동영상)
- Quiz on Agents and Workflows (퀴즈)

---

## 섹션 8. 마무리

- Final Assessment (최종 평가)
- Course Wrap Up (동영상)
