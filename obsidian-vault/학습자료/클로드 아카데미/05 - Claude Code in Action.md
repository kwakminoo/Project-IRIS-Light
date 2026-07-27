# Claude Code in Action

> Source: https://anthropic.skilljar.com/claude-code-in-action  
> 정리일: 2026-07-21  
> 출처: Anthropic Academy (Claude Academy)

신뢰할 수 있는 장시간·무인 Claude Code 세션을 운영하는 법: 조종(steer), 설정(configure), 자동화(automate), 검증(verify).

---

> **섹션: Curriculum**

---

## Steering Long Sessions
[동영상: https://www.youtube.com/embed/l_4ZYAiyP7U]

Prompting Claude to knock out a quick task is easy. You ask, it works, you check the result. But long tasks are a different game. Refactoring across a dozen files or building out a new feature can take hours. And the more you have to steer Claude along the way, the longer it drags on.


The good news is that you have a lot of tools to help Claude during these long sessions. It really comes down to two habits: scope the work before Claude starts, and steer it while it runs. Let's walk through both.


## Scope the work first with plan mode


Before Claude writes a single line, get it to lay out a plan. In plan mode, Claude does its research in read-only mode. It reads the code, figures out what needs to change, and hands you a plan to review.


When you get that plan, actually read it. Don't skim it. The more thorough the plan, the fewer surprises you'll hit once Claude starts executing. If something's off or missing, just ask Claude to add it where you want. Iterating on a plan is much faster than letting Claude run and hoping for the best, then cleaning up the mess.


## Steer while Claude works


Once Claude is running, you have a few ways to keep it pointed in the right direction. The first is compaction.


### Compact


Compact summarizes your conversation, uses that summary as the new context, and deletes the old messages. This frees up your context window so Claude can keep going. The risk is that something important gets dropped in the summary, and Claude drifts off course.


So don't just run /compact on its own. Add instructions after the command to tell Claude how to summarize. For example, if you finished debugging a while back and now you only care about some API changes, say so:


```
/compact Focus on the --version flag implementation

```


Anything you write after the command shapes what the summary keeps. That's your steering wheel for context.


### Rewind


When Claude heads down the wrong path, you don't have to prompt your way back out. Rewind takes you to your last checkpoint. Every user prompt creates a checkpoint you can revert to. To open the menu, double tap escape on an empty prompt.


From the rewind menu you get a few options:

- **Restore code and conversation** - roll back both together.
- **Restore conversation** - roll back just the chat.
- **Restore code** - roll back just the files.
- **Summarize from here** - summarizes everything after the checkpoint. Great if you had a side conversation and just want to free up some space.
- **Summarize up to here** - summarizes everything before the checkpoint. Great when you had a long setup phase you want to compress, but you want to keep the implementation parts intact.

## Let Claude run more autonomously


Everything so far assumes you're hands-on, watching and correcting. If you want something more autonomous, there's goal and loop.


### Goal


Goal sets a completion condition. You describe what "done" looks like, and Claude keeps working across turns until a fast evaluator confirms those conditions are met. It won't just stop the first time it thinks it's finished.


For example:


```
/goal all tests in src/billing pass, and the type checker reports zero errors

```


To cancel it, run /goal clear. One important constraint: the evaluator only reads the transcript. So your condition has to be checkable from the output Claude actually produces, like the results of a test run.


### Loop


Loop runs a prompt on an interval between turns, either fixed or self-paced. Use it to pull something external, like a CI run or a deploy, and act when the state changes.


To stop a loop, just press escape.


## Run parallel work with worktrees


The steering metaphor so far assumes one steering wheel in one car. But when you're running multiple agents on the same codebase, you don't want two steering wheels in one car. That's unsafe. Two Claude sessions fighting over the same files leads to conflicts.


That's where worktrees come in. Instead of sessions stepping on each other, each one gets its own independent file tree.


Because each agent has its own tree, they can't clobber each other's changes. When a session exits, a clean worktree is automatically removed.


There's one helpful file to know about. A .worktreeinclude file at the repo root lists git-ignored files to copy into each worktree. This is useful for things like an environment variable file or a local config that you need in every worktree but don't want to commit to version control.


## Putting it together


Handling long Claude Code sessions comes down to a handful of habits:

- Scope your work first, then steer.
- Direct your compaction so the summary keeps what matters.
- Use the rewind menu to course correct when Claude drifts.
- Set a goal when you can describe "done" better than you can describe the steps.
- Run parallel work in worktrees.

Do that, and you can trust a long run without babysitting every step of it.

---

## A CLAUDE.md That Follows
[동영상: https://www.youtube.com/embed/sfE5UQEumdM]

Here's a trap that catches almost everyone: your CLAUDE.md file keeps growing. You hit a problem, you add a rule. You hit another, you add another rule. Before long you've got one giant file, and Claude starts ignoring parts of it. That's not a bug in Claude. It's how the file works.


The key thing to understand is that CLAUDE.md is not enforced configuration. It's guidance. Every line competes with every other line for Claude's attention. The longer the file gets, the more it competes with itself, and the less reliably Claude follows any single rule. So the goal isn't to write down everything. The goal is to keep the file tight. The leaner the file, the more of it Claude actually follows.


## First, ask if CLAUDE.md is even the right tool


Before you write a rule, ask whether it belongs in CLAUDE.md at all. Some rules are guidance, and some rules are hard lines that must never be crossed. Those are two different jobs.


Take a rule like "never push to main." If you put that in CLAUDE.md, you're hoping Claude reads it and respects it. Most of the time it will. But "most of the time" isn't good enough for something that dangerous. A hard rule like that belongs in a pre-tool-use hook instead.


The difference matters. A hook is code that runs before Claude takes an action, and it can actually block the action. So even if Claude does try to push to main, the hook stops it. That's real enforcement, not a polite request. Move your hard rules to hooks and let CLAUDE.md handle the softer conventions.


## The four locations


CLAUDE.md isn't just one file sitting in your project. There are four places it can live, and Claude loads all of them together at launch. Nothing gets dropped, and they stack.


Here's what each one is for:

- **Managed policy** — the org-level file your platform team controls. You can't exclude it, so org policy is always in play.
- **User** — your personal preferences that follow you across every project on your machine.
- **Project** — the file shared with your team, checked into the repo.
- **Local** — ignored by git. Your personal notes for this one repository only.

That last one, local, is easy to overlook but really handy. Say you're refactoring off in your own branch and you want Claude to hold some architectural decisions in mind while you work. That doesn't belong in the shared project file where it'd affect your whole team. It goes in local, where it's just yours for this repo.


## Split up a big file with imports


When your project file starts getting long, you can break it into pieces using the path-to-file import syntax. Instead of one wall of text, you point to other files:


```
@.claude/conventions/code-style.md
@.claude/conventions/testing.md
@.claude/conventions/workflow.md

```


This is great for organizing. But know exactly what it buys you, because it's easy to get the wrong idea. When Claude launches, it expands those imported files inline, right where you referenced them. So imports help you keep things tidy, but everything still loads up front. They do not reduce the amount of context Claude has to read. Use imports to organize, not to shrink the load.


## Phrasing is what makes rules stick


Once you've decided a rule belongs in CLAUDE.md, whether Claude actually obeys it comes down to how you phrase it. Most rules fail because they're vague. Here's how to fix that.


### Be specific and checkable


Don't write "follow best practices." Do you even know exactly what that means? If you can't check whether it was followed, neither can Claude. Compare these two:

- Vague: *"Follow best practices for API routes."*
- Specific: *"Put new API routes in src/api/handlers, one per file."*

The second one is explicit. You can look at the result and immediately tell if it was done right. That's the bar every rule should clear.


### Name the replacement, don't just ban something


When you tell Claude not to do something, say what to do instead. Otherwise you've left the door open.

- Leaves it open: *"Don't use default exports."* Okay, but then what?
- Closes it: *"Use named exports, not default exports."*

The second version names the replacement, so there's nothing left to misinterpret.


### Emphasis is a budget


Words like "IMPORTANT" and "YOU MUST" do raise a rule's priority. But only relative to everything quieter around it. If every rule shouts, then nothing stands out and the emphasis means nothing. So treat emphasis like a budget. Spend it on the two or three rules that really hurt when they get broken, and let the rest sit at normal volume.


## Keep the file under revision


Your CLAUDE.md file is never finished. Treat it like living code that keeps getting edited.


When Claude does the wrong thing, don't just sigh and fix it by hand. Treat it as a bug report against your CLAUDE.md file. You can even tell Claude directly: "add that to the CLAUDE.md file," and it'll write the rule for you. That way the file gets better every time something goes wrong.


## The bottom line


Treat your CLAUDE.md like production code. If you can't justify a line, delete it. To keep the file lean and followable:

- Move hard rules to hooks, where they're actually enforced.
- Organize long files with imports (just remember they don't reduce context).
- Make every rule specific and checkable, and name the replacement.
- Spend your emphasis budget on the few rules that matter most.
- Keep revising the file whenever Claude gets something wrong.

The whole idea is simple. The leaner the file, the more of it Claude follows.

---

## Verification Skills
[동영상: https://www.youtube.com/embed/soLPOXXAc1w]

As your project grows, you start noticing the same work happening over and over. You already know skills are a good way to automate repeated work. In this lesson we look at one specific job that skills are great for: verifying your own work. If there's one skill worth building first, this is it.


## Why a verification skill is the one to build first


Think about how you normally check Claude's work. You ask it to refactor something, it finishes, and then you have to remember to double-check it. Maybe you ask it to run the tests. Maybe you read the diff yourself. The problem is that the checking depends on you remembering to ask for it. Skip that step once and bad code slips through.


A verification skill removes that dependency. Here's the shape of it. You ask Claude to refactor something. When it finishes, the change matches the skill's description, so the skill fires on its own. From there it:

- Runs the test suite.
- Reads the diff.
- Checks that no test was weakened just to make things pass.
- Reports pass or fail, with the evidence attached.

The whole flow runs without you asking. The description on the skill is what triggers it, and once triggered it walks the same steps every time.


Notice the last check in that chain. It's not enough to run the tests and see green. A test can be quietly loosened so it passes no matter what. So the skill reads the diff and confirms tests weren't weakened. "Done" isn't "the code looks right" from reading the diff alone. Done is the gates being run and observed, with the results stated explicitly.


This same shape carries any procedure your team repeats. A release checklist. A migration recipe. A pre-PR check. The rule of thumb: if you've typed the same multi-step instruction twice, that's a skill.


## A skill folder can hold more than instructions


A skill isn't just a single skill.md file. The folder around it can carry other things, and this is what makes skills powerful for verification.

- Drop a reference.md next to the skill for detailed material, then link to it from skill.md. Claude only reads it when it actually needs that depth. Your main file stays short.
- Put scripts in the folder too. Claude executes them rather than loading their contents into context. That means a skill can carry its own tooling, like a check.sh that runs all the gates.

The takeaway: keep skill.md itself lean. Push the heavy material, the long explanations and the executable scripts, into side files. The lean file describes what to do; the side files hold the depth and the tools.


## Which instruction surface owns which rule


By now you've got three places to put instructions, and it's easy to mix them up. Here's a quick way to keep them straight.


Conventions that apply all the time, things like naming rules or where files go, belong in your CLAUDE.md file. Procedures and reference material tied to a particular kind of task belong in a skill.


There's a third case. A rule that Claude must not be able to skip belongs in a hook, not in either of the above. That's because CLAUDE.md and skills are both instructions that Claude follows, while a hook is code that actually runs. If skipping the rule isn't acceptable, don't leave it up to instruction-following.


## The recap


A skill is a folder with a skill.md inside it: a name, a description that triggers it, and the procedure itself. Only the descriptions load into context until a skill is actually needed, so there's no cost to packaging every procedure you repeat.


Start with verification. Build the skill, check it into your project's .claude/skills, and now the whole team inherits the same move. Everyone's work gets checked the same way, automatically, without anyone having to remember to ask.

---

## Permission Modes
[동영상: https://www.youtube.com/embed/Fjg4O-ZcRSU]

Permission modes let you decide once what Claude is allowed to run without stopping to ask you. Instead of approving every action one prompt at a time, you pick a mode that matches the job and let Claude work at the level of trust you're comfortable with.


You've already met a few of these modes. Every time you hit shift-tab, you cycle through them: manual, accept edits, and plan. Those cover the everyday, hands-on work. The rest of the modes are where hands-off Claude Code really lives, and the one to reach for there is auto.


## The six permission modes


Here's the full set. Each mode draws a different line between what runs freely and what needs your sign-off.

- **Manual** reads only, without prompting. Everything else asks first.
- **Accept edits** runs reads, file edits, and common file system bash commands without asking. This is for iterating on code that you review after the fact.
- **Plan** reads only. It researches and proposes changes without editing anything.
- **Auto** accepts everything, with a separate classifier model reviewing each action before it runs.
- **Don't ask** allows only pre-approved tools. Everything else is auto-denied with no prompt.
- **Bypass permissions** skips all checks. This is the equivalent of the dangerously-skip-permissions flag. Only run it inside an isolated container or virtual machine.

## Cycling with shift-tab


You don't need to memorize a command for each mode. Press shift-tab to cycle through the everyday ones: manual, accept edits, plan, and auto. The status bar at the bottom always shows which mode you're currently in, so you can glance down and know exactly what Claude is allowed to do.


## How auto mode works


Auto is the hands-off mode. Claude runs on its own, but before each action executes, a separate classifier model reviews it. The classifier guards intent. It's watching for moves that escalate beyond what you actually asked for.


Here's the kind of thing it's designed to block:

- Production deploys and migrations
- Force pushing, or piping downloaded code straight into a shell
- Sending sensitive data to external endpoints
- Destroying files that exist for the session

And it waves through the everyday work: local edits in your project, installing dependencies from your lock file, read-only requests, and pushing to your own branch.


## What the classifier can't do


The classifier checks intent, not correctness. It won't catch whether the code actually works. So if you ask Claude to refactor authentication and it writes broken authentication, the classifier waves it through, because broken isn't dangerous.


That's why you pair auto mode with a stop hook that runs your tests. The two work together:

- Auto mode watches what Claude is *trying* to do while it runs.
- The stop hook confirms the code actually runs once Claude finishes.

One guards intent before each action, the other guards correctness after. Auto mode's guardrails are still evolving, so check the docs for the current block and allow lists.


## Don't ask, for unattended runs


Don't ask is the right move whenever no human is around to approve prompts: CI pipelines, scheduled jobs, overnight batches. Only pre-approved tools are allowed, and anything off that list gets auto-denied with no prompt. That's the whole point. Your pipeline keeps moving instead of hanging on an approval no one is there to give.


## Match the mode to the job


There are several permission modes, and you reach the everyday ones by cycling shift-tab. To sum it up:

- **Auto** is the hands-off mode. The classifier checks intent before each action, and a stop hook checks correctness after.
- **Don't ask** covers unattended pipelines where no one is there to approve.
- **Bypass permissions** belongs only inside isolated containers and VMs.

Pick the mode that fits what you're doing, and let Claude run at that level.

---

## Hooks
[동영상: https://www.youtube.com/embed/8ALu1dk681s]

Here's the problem with telling Claude to do something in a CLAUDE.md file: it's a request, not a guarantee. You can write "always format after editing" and Claude will usually listen. Usually. But on a long run you're not watching, "usually" isn't good enough. A hook fixes that. A hook is deterministic code that runs at a fixed point in the loop, so it can guarantee behavior instead of hoping for it. It turns a rule from "Claude usually listens" into "Claude can't skip it."


That's the whole pitch. Now let's look at how it actually works.


## The hook events


Claude Code fires around 30 hook events over the course of a session. You don't need to know all of them. There's a small handful you'll reach for again and again, and they line up with points in the agentic loop where you'd want to step in.


Here's how they sit in the loop. A session starts, prompts come in, tools get called, and the turn eventually ends. Each of those moments has a hook you can hang code on.


The ones worth knowing:

- **PreToolUse** fires before a tool call. This is your enforcement primitive. It's the one that can stop something before it happens.
- **PostToolUse** fires after a successful tool call. This is usually where auto-formatting or an auto-lint goes.
- **Stop** fires when Claude wants to end its turn. You can refuse and say "no, you're not done yet" if some condition isn't met. There's a matching **SubagentStop** for when a sub-agent finishes.
- **PreCompact** and **PostCompact** fire before and after compaction.
- **InstructionsLoaded** fires when a CLAUDE.md or rule file loads. Handy for auditing what actually made it into context.
- **SessionStart** fires at the start and primes the environment. Use the startup source if you only want it on fresh starts.

One thing that trips people up: to re-inject context after compaction, don't use PostCompact. Use SessionStart with the compact matcher. That's the one that actually gets its output back into the conversation.


## PreToolUse: returning a decision as JSON


PreToolUse is where the real power is, because it can block a tool call before it runs. The way you talk back to Claude is by printing JSON and exiting zero. The key field is permissionDecision, and it takes one of three values:

- allow — let the call through
- deny — stop the call
- ask — hand it back to the user to decide

There's technically a fourth value, defer, but it only applies to non-interactive -p runs where a calling process pauses the tool and resumes it later. You'll rarely reach for it.


The shape looks like this:


```
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "...",
    "updatedInput": {
      "command": "..."
    }
  }
}

```


Notice updatedInput. Instead of blocking a call, you can rewrite it. That's how you'd redact a secret out of a bash command and still let it run. One catch: updatedInput replaces the *whole* input object, so you have to echo back the fields you aren't changing, or you'll lose them.


## Exit codes, for hooks that don't return JSON


Not every hook needs to speak JSON. For simpler hooks, exit codes do the job. There are three numbers that matter.

- **0 is success.** If standard out is JSON, Claude parses it. Plain text is ignored on most events, but on SessionStart, UserPromptSubmit, and UserPromptExpansion, plain text gets added to context. That's exactly what makes a state-preserver hook work.
- **2 is a blocking error.** Standard error gets fed back to Claude as context. This is the blocking exit code almost everywhere.
- **Anything else** is non-blocking. Standard error gets logged, and Claude carries on.

The one that catches people out is exit code 1. It *feels* like an error, but it does not block. Claude runs the command anyway. So if you meant to stop something, exit 2, not 1.


A couple more wrinkles. Exit 2 can even block Stop, which is how you tell Claude it's not done. But PostToolUse fires after the tool already ran, so blocking there is too late to stop the call, though it can still feed text back to Claude. And a few events ignore blocking entirely, like Notification and SessionStart. They'll show your standard error and carry on regardless.


## A real guardrail: redact instead of block


Let's tie it together with something practical. Say you want a PreToolUse guardrail on the Bash tool. The matcher picks the tool to watch, and an optional if clause can narrow it to a specific command.


The obvious move is to return deny and stop a dangerous call. That's good. But the lesser-known and more interesting move is to return updatedInput to rewrite the call. That's how you strip a secret out of a command and still let it run, instead of just refusing.


Here's what that looks like in practice. Claude is asked to run a command that includes a live-looking secret. The hook intercepts it, spots the sk_live_ pattern, and swaps it for a placeholder before the command ever executes.


The command still ran. The work still got done. But the secret never made it through. That's the difference between blocking and redacting, and it's the kind of thing a hook can enforce every single time.


## Preserving state across a compact


One more pattern worth setting up. When Claude compacts a long conversation, it drops a lot of detail. A SessionStart hook with the compact matcher runs right after compaction. Have it print a short summary of the files you've been working on. That summary goes back into context, so Claude picks up where it left off instead of starting cold.


## Wrapping up


Hooks turn a rule Claude usually follows into one it always follows. Reach past auto-formatting: guard tools with PreToolUse, gate the turn with Stop, and preserve state across a compact. The setup takes a little effort up front, but it pays back the first time it catches something on a run you weren't even watching.

---

## Routines and Headless
[동영상: https://www.youtube.com/embed/b9TCW-pdzDA]

Once you trust Claude to do a task, the next move is to stop doing it by hand. If it's the same prompt on a recurring trigger, you shouldn't have to sit there and kick it off yourself every time. This lesson covers two ways to hand that work off: routines, where you build nothing, and headless mode, where you get full control from your own scripts.


Think of it as a spectrum. On one end you have routines that run on Anthropic's managed infrastructure. On the other end you have headless mode and the Agent SDK, which run Claude Code from your own code. Let's start with the end where you build the least.


## Routines: a saved prompt that runs in the cloud


A routine is the most direct way to automate a task. There's no script and no server. It bundles three things: a prompt, the repository it works on, and any connectors it needs. Then it runs that bundle in the cloud whenever it's triggered.


The key part is that the infrastructure is Anthropic's. There's no machine of yours staying on overnight, and there's no workflow file for you to maintain. You describe the job once and it just runs.


A routine can fire on a few kinds of triggers:

- A cron schedule, like every morning at 9am.
- An HTTP POST to its API endpoint, so your own code can kick it off.
- A GitHub event, like a new pull request landing.

Anything that's the same prompt on a recurring trigger is a good fit. A morning dependency audit. A PR triager that fires when a new pull request comes in. A daily scan of your Sentry tickets to figure out what's most urgent.


Here's the mental model for what a routine ties together: a prompt, the repo, connectors, and a schedule.


## Two ways to create one


You can create a routine from the web at claude.ai/code/routines. You give it a name, write the instructions describing what Claude should do in each session, pick a repository, and choose a trigger.


You can also create one from inside Claude Code without leaving your terminal. Just run the /schedule command and describe what you want in plain language, for example:


```
/schedule daily dependency audit at 9am

```


Same idea, either entry point. Pick whichever fits your flow.


## Three things to know before you rely on routines


Before you lean on routines for anything important, keep these three limits in mind.

- **Routines are a research preview.** Behavior and limits will keep moving, so don't be surprised if things change.
- **A recurring schedule runs at most hourly.** If you need something more frequent, routines aren't the tool.
- **Each run starts from a fresh clone of your default branch and can only push to claude/ prefixed branches** unless you loosen that per repo. This is the guardrail that keeps an autonomous run from rewriting main.

## Headless mode: when you need your own environment


Routines are great when the work fits in the cloud. But sometimes the job needs your environment, or logic wrapped around the run. That's when you drop to headless mode.


The core of headless mode is the -p flag (short for --print). It runs Claude Code as a one-shot command with no interactive UI. It reads standard in and writes standard out, so it pipes like any other shell tool:


```
claude -p "summarize the changes in this diff"

```


One thing worth knowing: -p skips auto-discovery of hooks, skills, plugins, MCP servers, and the CLAUDE.md file. You get Claude plus the tools you allow explicitly, and nothing the local environment happens to load. The upside is that startup is much faster this way.


## Getting structured output back


Because headless mode pipes like any shell tool, you'll often want structured data back instead of prose. You can pair a JSON schema with the JSON output format, and Claude will constrain its output to match your schema.


The object that matches your schema lands in the structured_output field of the JSON response. So you can pull it out with a jq command and pipe it into a database or another script:


```
claude -p "Extract the exported function names from src/core/style.js" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}' \
  | jq '.structured_output.functions'

```


That gives you a clean array you can hand to whatever comes next.


## Multi-step automation with sessions


For work that happens across multiple steps, you don't have to cram everything into one command. Capture the session's ID from the JSON output and resume it later:


```
claude --resume "$(jq -r .session_id /tmp/plan.json)"

```


One script kicks off the work. Another resumes it later with full context. This is handy when the first pass produces a plan and a second pass carries it out.


## Deterministic runs for CI


When CI needs the same results every single run, there's a mode built for that.


The --bare flag gives you deterministic mode. It's the right choice when you're running Claude Code inside a pipeline and you want repeatable, predictable output rather than anything that varies run to run.


## The Agent SDK: Claude Code inside your own app


The last step on the spectrum is the Agent SDK. This gets you a library that embeds Claude Code inside your own TypeScript or Python applications.


Both languages expose a query function and the same primitives as the CLI. You pass a prompt plus options, like:

- allowedTools to control what Claude can do,
- a system prompt,
- and a permission mode.

Then you iterate over the messages Claude streams back and handle them however your app needs. It's the same engine as the CLI, just callable from inside your product.


## Which one should you reach for?


Here's the quick decision guide:

- **Routines** are the default for repeat work. They run on Anthropic's infrastructure with nothing for you to host.
- **Headless mode with -p** is for when the job needs your pipeline and you want to pipe data through a script.
- **--bare** is for when CI needs the same results every single run.
- **The Agent SDK** is for when the work belongs inside your own product.

Start with routines. Drop down the spectrum only when the job actually needs the extra control.

---

## GitHub Actions and Code Review
[동영상: https://www.youtube.com/embed/gIVt_iqmACw]

The best place to hand off repetitive work is the pull request. It's where review happens, where changes land, and where a lot of your busywork lives. There are two ways to put Claude to work here, and they solve different problems. One is a managed service you turn on. The other is a GitHub Action you wire up yourself. Let's walk through both and figure out when to reach for each.


## The managed path: Code Review


The simplest option is Code Review. It's an Anthropic-hosted service that reviews your pull requests through the Claude GitHub app. There's nothing for you to build or host. You turn it on, and it starts posting findings as inline comments right on the lines that matter.


An organization admin enables it from the Claude Code admin settings. You'll find a Code review section with a Configure button that hooks it up to your repositories.


From there the admin installs the Claude GitHub app, picks which repos it watches, and decides when it runs. You have a few choices for timing:

- Once when a PR opens
- On every push to the PR
- Only when someone comments @claude review

Once it's on, everything runs on Anthropic's infrastructure. A set of review agents analyzes the diff against your full codebase, not just the changed lines in isolation. Then it posts findings as inline comments on the specific lines, tagged by severity, with a summary table in the check run.


Here's what one of those findings looks like. It lands as a comment from Claude, right on the line, with a clear explanation and a suggested fix.


The nice part is it deduplicates and ranks the findings. So instead of a wall of nitpicks, you read a handful of real issues worth your attention.


## What Code Review will and won't do


A couple of things to keep in mind about the boundaries here:

- It never approves or blocks the PR. The judgment call stays with a human. Claude flags things; you decide.
- There's no managed autofix. The service posts findings only.
- It's a research preview right now, available on team and enterprise plans, so expect the behavior to keep moving.

Since there's no autofix in the service, applying a finding is a local move. From your own terminal, the /code-review command reviews a diff, and its --fix flag applies the findings to your working tree. So the flow is: Claude finds it in the PR, you pull it down and fix it locally.


## The do-it-yourself path: the GitHub Action


Code Review handles review. When the job goes beyond review, you reach for the GitHub Action. This is for custom CI: implementing changes from a comment, running scheduled reports, anything you'd normally write a workflow for. It runs the agent on PR comments, scheduled jobs, and any GitHub event.


Setup starts inside Claude Code. Run the /install-github-app command. You'll need repo admin to do this. The slash command walks you through installing the GitHub app and setting the Anthropic API key secret on the repo.


The action itself is anthropics/claude-code-action@v1. Here are the inputs you'll actually use:

- anthropic_api_key — optional.
- github_token — defaults to secrets.GITHUB_TOKEN.
- trigger_phrase — what the action listens for in comments. Defaults to @claude.
- use_bedrock / use_vertex — switch to those providers if you're on Bedrock or Vertex.
- prompt — the instruction for the run.
- claude_args — a string of CLI arguments passed straight through to Claude Code.

## A workflow that responds to @claude


Drop a workflow into .github/workflows/claude.yaml and it listens for @claude on PR comments and issue comments. The core step looks like this:


```
- uses: anthropics/claude-code-action@v1
  with:
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
    github_token: ${{ secrets.GITHUB_TOKEN }}
    trigger_phrase: "@claude"
    prompt: "Your instructions here"
    claude_args: "--max-turns 5 --model claude-sonnet-5"

```


Now someone writes @claude implement the spec in the linked Linear issue on a pull request, and the action picks it up. Claude pushes commits and posts comments describing what it did.


## A workflow that runs on a schedule


The same action works for a daily rollup. A cron trigger fires at, say, 9:00 UTC, the action runs, and Claude posts the results. You can also add a workflow_dispatch trigger so you can kick it off manually from the Actions tab.


When the action runs, you can watch it work through the steps in the Actions tab, just like any other GitHub workflow.


## Tuning the run with claude_args


The claude_args line is where the fine-tuning happens. A few knobs worth knowing:

- --max-turns 5 puts a hard cap on the agent loop, so it can't run forever.
- Permission mode. For an unattended job you'll want it to not stop and ask, since there's no one there to answer.
- Allowed tools. Give the job exactly what it needs and nothing more. For a report, that means read-only.

## Which one should you use?


Here's the short version:

- For PR reviews, take the managed path. Enable Code Review, let the GitHub app post inline findings, and apply fixes locally with /code-review --fix.
- Reach for the action when the job is more than review. Use /install-github-app for setup, one workflow for @claude mentions, one for cron, and all the tuning lives in claude_args.

Start with the managed service. Move to the action the moment you need Claude to actually do something in CI, not just comment on it.

---

## Trust It: Verifying Unsupervised Runs
[동영상: https://www.youtube.com/embed/lalGZSNhm8E]

You handed Claude a task and let it run without watching every step. Now it says it's done. Before you ship that work, you need a way to check something you didn't even supervise. That check is what makes hands-off Claude Code safe to rely on.


The idea here is simple: verify in proportion to how much rope you gave the run. If you watched the messages scroll by in a short session, a quick glance is enough. But an unattended run, or a job that fired in continuous integration with nobody in the loop, needs a real check. No one saw what happened, so you have to reconstruct it after the fact.


Here's a way to picture it. The less you watched, the more you verify.


## Keep unattended runs in auto mode


When a run goes unattended at work, keep it in auto mode rather than bypass permissions. In auto mode, the classifier still reviews each action for danger. That's a safety net worth keeping.


But be clear about what that net does and doesn't do. The classifier never judges whether the code is actually correct. It only flags dangerous actions. So your verification bar stays exactly where it was. Set that bar based on how unsupervised the run was.


## Start with the diff, not the summary


Don't start with Claude's summary of what it did. Start with the diff itself.

- Run /code-review to walk the changes and flag issues.
- Then put your own eyes on git diff.

The trap is a tidy summary that reads perfectly fine, while the actual diff touched a file you honestly didn't expect it to touch. The summary won't tell you that. The diff will.


So read what changed. Read the files that were part of the plan first, then look for anything outside it. A clean write-up is not proof of clean code.


## Turn tests into a gate, not a promise


The real gate on an unsupervised run is whether the tests passed, and whether Claude actually ran them or only claimed that it did. Don't leave that to trust. Wire it as a hook so Claude can't skip it.


A couple of hooks do the job:

- A **stop hook** that runs your tests and refuses to end the turn on a failure.
- A **post-tool-use hook** that lints and type checks after every edit.

The key detail is the exit code. A hook that exits with exit 2 feeds the failure straight back to Claude. Claude reads that failure and fixes it without you asking. Best of all, the check fires on every run, whether or not you remember to ask for it.


## Get a cold second opinion


The sub-agent code review you'd run before a pull request works here too. Point it at an unsupervised run.


Open a fresh session or sub-agent and have it review the changed code with no memory of how the code was built. Because it has no stake in the approach, it catches the things the original run talked itself past. A second reviewer with fresh eyes finds what the author rationalized away.


## Putting it together


Make the check as serious as the run was unsupervised:

- Read the diff yourself.
- Turn the tests into a hook that gates the turn.
- Verify headless runs by their JSON result and exit code.
- Get a cold second opinion on anything that matters.

Do that, and "Claude did it while I wasn't looking" no longer takes faith.

---

## Plugins
[동영상: https://www.youtube.com/embed/k4kZwJ0FtX0]

A setup you trust is worth a lot more once your whole team is running it. The problem is moving it around. You build a great .claude directory with skills, subagents, and hooks, and then what? Everyone copies and pastes files between machines and hopes they stay in sync. Plugins fix that. A plugin is how Claude Code packages a setup and moves it from one person to the next.


There are two sides to this, and we'll cover both. First, using plugins that other people publish. Second, packaging your own once you've built something worth sharing.


## What a plugin is


A plugin is one installable unit. It bundles everything you'd otherwise share by hand: skills, subagents, hooks, and MCP server configs, plus the longer tail of stuff like language server protocol servers, background monitors, themes, and a slice of settings.json. One version, one install.


Where the plugin lives decides how you install it. Inside a session, you can install one directly by name:


```
/plugin install org-name@plugin-name

```


Here's what that looks like. Claude Code installs it and tells you to run /reload-plugins to apply the change.


## Adding a marketplace for your team


For a team, the better move is to add a private marketplace once. A marketplace is a shared source that plugins resolve through:


```
/plugin marketplace add your-org/claude-plugins

```


Call it whatever you want. Once it's added, every install after that resolves through it. You get centralized discovery, version tracking, and updates in one place instead of scattered across everyone's laptop.


You can browse what's available from the Discover tab. It lists the plugins on your marketplaces so you can search and pick.


## Read before you install


Here's the part that matters most. A plugin runs code on your machine, with your privileges. Its hooks fire on every matching tool call. So if you install a plugin for its skills, you also get its PreToolUse and Stop hooks whether you read them or not.


Think about what that means. A community plugin could ship a Stop hook that calls out to a network endpoint every time, and nothing in your configuration would warn you about it. That's not a reason to avoid plugins. It's a reason to look first.


Before you install, check the plugin's details. Claude Code shows you what it will install and estimates the context cost, along with a plain warning that Anthropic doesn't control what's inside third-party plugins.


Two things worth knowing about where plugins come from:

- The in-app submission form posts to the community marketplace after Anthropic's automated review.
- The official marketplace is curated on its own separate track.

But reviewed isn't the same as trusted. Automated review catches some things, not everything. So the rule stands: install plugins and add marketplaces only from sources you truly trust, and check what a plugin actually does before turning it on.


## Components run alongside yours


A plugin doesn't overwrite your configuration. Its components run alongside your own. That's mostly good, but it has consequences you should understand.


Hooks stack. A plugin's PreToolUse hook and your own PreToolUse hook both fire on every tool call. Neither replaces the other. This is exactly why you read the details first.


Skills, agents, and commands are namespaced under the plugin name, so they never clash with yours. A plugin can also ship a settings.json file, but only a narrow one. Claude Code honors just two keys from it: the agent and subagent status line keys.


That agent key is worth a pause. Setting it promotes one of the plugin's subagents to the main thread, along with its system prompt, tool restrictions, and model. In other words, enabling the plugin can change how Claude Code behaves by default. That's one of the main reasons to look before you even turn it on.


Once a plugin is installed you can see everything it added, manage it, and uninstall it from the plugin panel.


## Packaging your own plugin


Now the other side. Once you've built a .claude directory that works, don't make your team copy and paste it between machines. Package it instead.


The good news is you don't have to restructure anything. A plugin uses the same .claude shape you already use:

- One folder per skill.
- One markdown file per subagent under agents.
- hooks/hooks.json and .mcp.json, at the plugin root.

The directory structure does most of the work. Claude Code discovers components by convention.


## The manifest


On top of that, there's an optional manifest. It lives at .claude-plugin/plugin.json and holds the name, version, description, and author:


```
{
  "name": "svg-splitter-review",
  "version": "0.1.0",
  "description": "Reviews the SVG Splitter repo",
  "author": {
    "name": "Lewis Menelaws"
  }
}

```


The manifest is optional. Leave it out and Claude Code still discovers your components by directory convention. But a couple of details are worth knowing:

- **Name is the only required field.** It namespaces your skills as company-name:skill-name, which keeps them from colliding with anyone else's.
- **Version it like any other dependency.** That's what makes updates and version tracking work across your team.

## The takeaway


Two simple rules cover most of this:

- When you use plugins, read before you install. A plugin runs code with your privileges, so look at its hooks, agents, and MCP servers first.
- When you build one, package your .claude the moment it works. One manifest, one install.

That's the whole point. One installable unit, and the setup you trust reaches your entire team.

---

## Course Quiz
**

## Loading...
