# Introduction to subagents

> Source: https://anthropic.skilljar.com/introduction-to-subagents  
> 정리일: 2026-07-21  
> 출처: Anthropic Academy (Claude Academy)

Claude Code에서 sub-agent를 사용·생성해 컨텍스트를 관리하고, 작업을 위임하며, 메인 대화를 깔끔하게 유지하는 전문화 워크플로를 만드는 법을 배운다.

---

> **섹션: Curriculum**

---

## What are subagents?
[동영상: https://www.youtube.com/embed/jKErNxuxPXg]



Subagents are specialized assistants that Claude Code can delegate tasks to. Think of them as focused helpers: each one runs in its own conversation context window, does its work, and returns a summary to the main thread. The intermediate steps -- all the file reads, searches, and tool calls -- stay isolated and never clutter your main conversation.


## Why Subagents Matter


Every time you chat with Claude Code, you're adding to the main context window. Every tool call, every file read, every search result gets stored there. That space is finite, and once it fills up, Claude starts losing track of earlier parts of the conversation.



Subagents solve this by spinning up a separate context window. The subagent receives two things:

- **A custom system prompt** from your configuration file that defines the subagent's role and behavior
- **A task description** written by the parent agent based on what you asked for

The subagent then works on its own. It reads files, runs searches, edits code -- whatever it needs to do. When it's done, only a summary comes back to your main conversation. The entire subagent conversation is then discarded.


This means your main context stays clean. You get the answer without all the noise of the journey it took to find it. The tradeoff is that you lose visibility into how the subagent reached its conclusions.


## A Practical Example


Say you're exploring an unfamiliar codebase and you want to know which service handles refunds. Without a subagent, Claude might read 15 files, run several searches, and trace through multiple function calls. All of that fills your context window, even though you only needed one fact.


With a subagent, the experience is much cleaner. You ask the question, the Explore subagent spins up, does all that digging in its own context, and hands back a focused answer.


Your main context window only records the question and the summary -- not the 15 files that were read along the way.


## Built-in Subagents


Claude Code ships with several built-in subagents you can use right away:

- **General purpose subagent** -- for multi-step tasks that require both exploration and action
- **Explore** -- for fast searching and navigation of codebases
- **Plan** -- used during plan mode for research and analysis of your codebase before presenting a plan

## Custom Subagents


Beyond the built-in options, you can create your own subagents with custom system prompts and tool access. This lets you define specialized agents tailored to your workflow -- a code reviewer, a test writer, a documentation generator, or anything else you need.


## Key Takeaways


Subagents give you three main benefits:

- They break work into focused pieces, letting each subagent concentrate on a specific task
- They keep your main context window clean by isolating all the intermediate work
- They bring back just the information you need as a concise summary

Whether you're using the built-in subagents or creating your own, they're a practical way to get more out of longer Claude Code sessions. The less noise in your main context, the longer and more effectively you can work.

---

## Creating a subagent
[동영상: https://www.youtube.com/embed/arD6qEWa2Xc]


Claude Code comes with built-in subagents, but you can also create your own. Custom subagents specialize in specific tasks -- like reviewing code, writing tests, or checking documentation. They are defined as markdown files with YAML frontmatter that tell Claude when to use the subagent and how the subagent should behave.


## Creating a Subagent


The easiest way to create a subagent is with the /agents slash command. This opens the main interface for managing your subagents. From there, select **Create new agent**.


You will first be asked to choose the scope of your subagent:

- **Project-level** -- available only in the current project
- **User-level** -- shared across all projects on your machine

Next, you can choose how to create it. You can write the configuration manually, but the recommended approach is to let Claude generate it for you. Just describe what you want the subagent to do, and Claude will produce a name, description, and system prompt based on your input.
  [이미지]


## Customizing Tools


During creation, you get the chance to customize which tools the subagent can access. The tool categories include:

- Read-only tools
- Edit tools
- Execution tools
- MCP tools
- Other tools   [이미지]


Think about what your subagent actually needs. A code reviewer probably does not need edit tools -- it should read and analyze code, not change it. However, you might want to keep execution tools enabled so it can more easily identify pending changes.


## Choosing a Model and Color


After configuring tools, you select which Claude model powers the subagent. The model picker offers four options:

- **Haiku** -- best for fast, lightweight tasks
- **Sonnet** -- a good middle ground between speed and depth
- **Opus** -- best for complex analysis
- **Inherit** -- uses whatever model your main conversation is running

Finally, you pick a color. This shows up in the UI so you can quickly tell which subagent is active. It is a small touch, but it helps when you have multiple subagents running.
  [이미지]


## The Config File


Once creation is complete, the subagent config file is saved into your project (typically at .claude/agents/your-agent-name.md). Here is what a typical subagent config looks like:



```
---
name: code-quality-reviewer
description: Use this agent when you need to review recently written or modified code for quality, security, and best practice compliance.
tools: Bash, Glob, Grep, Read, WebFetch, WebSearch
model: sonnet
color: purple
---

You are an expert code reviewer specializing in quality assurance, security best practices, and
adherence to project standards. Your role is to thoroughly examine recently written or modified code
and identify issues that could impact reliability, security, maintainability, or performance.
```


Let's break down each field:

- **name** -- A unique identifier for the subagent. This is how you reference it, either by asking Claude directly or by typing @agent code-quality-reviewer in your message.
- **description** -- Controls when Claude decides to use the subagent. This must be a single line (use escaped newline characters \n if you need breaks). You can include example conversations here to help Claude understand when delegation is appropriate.
- **tools** -- Lists which tools the subagent can access. This matches whatever you selected during generation, but you can edit the list here at any time.
- **model** -- Specifies which Claude model to use: sonnet, opus, haiku, or inherit.
- **color** -- The UI color for identifying the subagent.

## System Prompts


The body of the markdown file (everything below the YAML frontmatter) is the system prompt. This is where you give the subagent its instructions: what it should focus on, how it should analyze things, and how it should report findings back to the main agent.


A well-written system prompt is the difference between a useful subagent and one that misses the point. Be specific about what the subagent should look for and how it should structure its output.


## Making Claude Use Your Subagent Automatically


If you want Claude to delegate tasks to the subagent without you explicitly asking, include the word **"proactively"** in the description field. For example:


```
description: Proactively suggest running this agent after major code changes...
```


You can also add example conversations to the description to help Claude understand specific scenarios where the subagent should be used. The more concrete your examples, the better Claude gets at knowing when to delegate.


## Testing Your Subagent


After creating your subagent, test it by making some code changes and asking Claude to review them.
  [이미지]


If the subagent is not being used when you expect it to be, go back and check the description. Adding more specific examples and trigger scenarios helps Claude understand when to delegate work to your subagent.

---

## Designing effective subagents
[동영상: https://www.youtube.com/embed/WPxWKT_OaU4]


Now that you know how to create subagents, let's look at the patterns that make them actually effective. A subagent that's poorly configured will wander, run too long, or produce output the main agent can't use. The fixes come down to four things: writing good descriptions, defining an output format, reporting obstacles, and limiting tool access.


## How Subagent Config Data Gets Used


When you send a message to the main context window agent, the name and description of every available subagent are included in the system prompt. This is how the main agent decides which subagent to launch and when. If you want better control over when a subagent gets triggered automatically, the name and description are what you should tweak.


The description also plays a second role. When the main agent launches a subagent, it writes an input prompt to kick off the task. It uses the description as guidance for writing that prompt. So the description doesn't just control *when* a subagent runs -- it shapes *what the subagent is told to do*.
  [이미지]


## Writing Descriptions That Shape Input Prompts


Consider a code review subagent. With a generic description, the main agent might write an input prompt like "use get diff to find the current changes." That's vague. The subagent has to figure out which files matter on its own.


If you update the description to include something like "You must tell the agent precisely which files you want it to review," the main agent will now write a much more specific input prompt that lists the actual files to review.


This same technique works across different types of subagents. For example, adding "return sources that can be cited" to a web search subagent's description causes the main agent to include that instruction when delegating the task.
  [이미지]


## Defining an Output Format


The single most important improvement you can make to a subagent is defining an output format in its system prompt. This does two things:

- It creates natural stopping points -- the subagent knows it's done when it has filled in each section of the format.
- It prevents the subagent from running too long. Without a defined output, subagents struggle to decide when enough research has been done and tend to run much longer than necessary.

Here's an example of a structured output format for a code review subagent:


```
Provide your review in a structured format:

1. Summary: Brief overview of what you reviewed and overall assessment
2. Critical Issues: Any security vulnerabilities, data integrity risks,
   or logic errors that must be fixed immediately
3. Major Issues: Quality problems, architecture misalignment, or
   significant performance concerns
4. Minor Issues: Style inconsistencies, documentation gaps, or
   minor optimizations
5. Recommendations: Suggestions for improvement, refactoring
   opportunities, or best practices to apply
6. Approval Status: Clear statement of whether the code is ready
   to merge/deploy or requires changes
```


This format gives the subagent a clear checklist to work through. Once every section is filled in, the subagent knows it can stop.


## Reporting Obstacles


When a subagent discovers a workaround during its work -- like solving a dependency issue or finding that a certain command needs particular flags -- those details need to appear in the summary it returns. If they don't, the main thread has to rediscover the same solutions on its own, which wastes time and tokens.


The kinds of things you want surfaced include:

- Setup issues or environment quirks
- Workarounds discovered during the task
- Commands that needed special flags or configuration
- Dependencies or imports that caused problems

The way to get this information is to explicitly ask for it in the output format. Adding an "Obstacles Encountered" section to your output template surfaces this information reliably.


```
7. Obstacles Encountered: Report any obstacles encountered during the
   review process. This can be: setup issues, workarounds discovered or
   environment quirks. Report commands that needed a special flag or
   configuration. Report dependencies or imports that caused problems.
```
  [이미지]


## Limiting Tool Access


Not every subagent needs access to every tool. Think about what a subagent actually needs to do, and only give it the tools required for that job. This does two things: it prevents unintended side effects, and it makes each subagent's role clearer when you have several of them.


Here's how to think about tool access for common subagent types:

- **Research / read-only subagent** -- Only needs Glob, Grep, and Read. Cannot accidentally modify files.
- **Code reviewer** -- Needs Bash access to run git diff and see what changed, but still doesn't need Edit or Write.
- **Styling / code modification agent** -- This is where you give Edit and Write access, because the subagent's job is to actually change your code.

## Putting It All Together


Effective subagents share four characteristics:

- **Specific descriptions** -- The description controls when the subagent is launched and what instructions it receives. Write it to steer both.
- **Structured output** -- Define an output format in the system prompt so the subagent knows when it's done and returns information the main thread can use.
- **Obstacle reporting** -- Include a section in the output format for workarounds, quirks, and problems so the main thread doesn't have to rediscover them.
- **Limited tool access** -- Only give a subagent the tools it actually needs. Read-only for research, bash for reviewers, edit/write only for agents that should change code.

Each of these patterns is simple on its own, but together they turn a subagent from something that vaguely tries to help into a focused, predictable worker that finishes on time and reports back clearly.

---

## Using subagents effectively
[동영상: https://www.youtube.com/embed/n5LoKZ8Oa-A]


You know how to create subagents and design them well. Now the question is: when do they actually help, and when do they get in the way? The difference comes down to one thing -- whether the intermediate work matters to your main thread.


## When subagents shine


Subagents work best when the exploration is separate from the execution. If each step in a task depends on what the previous step discovered, you want that work in your main thread. But if you just need an answer and don't care about the journey, delegate it.


Subagents excel at tasks where:

- You need a result, not a play-by-play of how it was found
- The exploratory work would clutter your main thread's context
- The task benefits from a fresh perspective or a custom system prompt

## Research tasks


Research is the classic subagent use case. Consider investigating how authentication works in an unfamiliar codebase. Your main thread needs to know *where* the JWT is validated, but it doesn't need to see every file that was searched along the way.


A research subagent can read dozens of files, trace through function calls, and explore different code paths. All that exploration stays in the subagent's context. Your main thread receives a clean summary like:


```
JWT validation happens in middleware/auth.js line 42,
called from the Express router in route/api.js
```


The subagent did the heavy lifting. Your main thread gets exactly what it needs to move forward.


## Code Reviews


Claude reviews code more effectively when the code is presented as being authored by someone else. If you built a feature over many turns with your main thread, asking that same thread to review it often produces weak feedback. Claude was involved in creating it, so it has trouble seeing it with fresh eyes.


A reviewer subagent sees the changes in a separate context. It runs git diff, reads the modified files, and applies its specialized review criteria without the history of how the code was written. This separation also lets you encode project-specific review standards in the subagent's system prompt, ensuring consistent review criteria across the team.


## Custom System Prompts


Claude Code's default system prompt emphasizes concise, code-focused responses. That works great for coding, but not for everything.


Here are two cases where a custom system prompt makes the subagent genuinely better than the main thread:

- **Copywriting subagent** -- Give it instructions about tone, audience, and style. Claude Code's default prompt tends toward concise technical writing, which really isn't what you want for a landing page or email campaign. A copywriting subagent can have completely different instructions about voice and structure.
- **Styling subagent** -- Point it at your design system files. When the subagent runs, those files load into its context automatically, so it knows your color variables, spacing conventions, and component patterns before it even starts writing any CSS.

## When Subagents Hurt


The overhead of launching a subagent -- losing visibility into its work and compressing its findings into a summary -- only makes sense when the subagent does something the main thread can't. There are three common anti-patterns to watch out for.


### Expert Claims


Subagents that claim expertise rarely help. Prompts like "you are a Python expert" or "you are a Kubernetes specialist" add no value because Claude already has that knowledge. There's nothing a so-called expert subagent can do that your main thread can't do directly.


### Sequential Pipelines


Sequential subagent pipelines create problems. Consider a three-agent flow: one to reproduce a bug, one to debug it, and one to fix it. Pipelines work when tasks are truly independent. They fail when each step depends on discoveries from the previous step -- and bug fixing almost always does. Information gets lost in the handoff between agents.


### Test Runners


Test runner subagents tend to hide information you need. When tests fail, you want the full output to diagnose issues. A subagent that returns "tests failed" forces you to create additional debug scripts to get details that would have been visible in direct output. Testing has shown that the test runner pattern performed worse among all configurations.


## The Decision Rule


When you're deciding whether to use a subagent, ask yourself one question: **does the intermediate work matter?**


If the answer is no -- you just need the final result -- delegate it to a subagent. If the answer is yes -- you need to see and react to what's happening along the way -- keep it in your main thread.


Use subagents for:

- Research and exploration
- Code reviews
- Tasks that need a custom system prompt

Avoid subagents for:

- "Expert" personas that don't add real capability
- Multi-step pipelines where each step depends on the last
- Running tests where you need full output for debugging
