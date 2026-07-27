# AI Capabilities and Limitations

> Source: https://anthropic.skilljar.com/ai-capabilities-and-limitations  
> 정리일: 2026-07-21  
> 출처: Anthropic Academy (Claude Academy)

AI가 어떻게 작동하는지에 대한 입문 강좌. 능력과 한계를 이해한다.

---

> **섹션: Curriculum**

---

## Intro to AI Capabilities and Limitations
## What you'll learn


*Estimated time: 15 minutes*


By the end of this lesson you'll be able to:

- Understand what this course covers and how it's structured
- Explain why this material is durable even as models and products keep changing
- See how the Capabilities & Limitations framework and the 4D Framework work together

## Welcome to the AI Capabilities & Limitations Course


*(4 minutes)*


[동영상: https://www.youtube.com/embed/Sj1yynxA9hw]



The 4D Framework teaches YOU how to collaborate with AI. This course teaches you how AI is able to work with you. Together they're one system: human competencies on one side and machine properties on the other.


## A mental model of the machine
   Course
roadmap  What we mean by AI

What is generative AI and how does it differ from other types of AI?
  How AI is trained

How do pretraining and fine tuning give AI its character?
  Properties of AI

What are next token prediction, knowledge, working memory, and steerability?
  Putting it all together

What happens when properties collide in real life situations?
  Next steps

How do you use this knowledge to use AI safely, effectively, and ethically?


#### Key takeaways

- **The AI Fluency Framework (4Ds)** describes human competencies. This course describes the machine properties those competencies respond to.
- **Generative AI has four core properties:** Next Token Prediction, knowledge, working memory, and steerability.
- **This material is durable** because the properties stay stable even as models improve. Boundaries shift but the properties remain the same.

## Exercises


**Exercise: Mapping Your Current AI Use**


*Why? This is the foundation for every exercise that follows in this course.*

- **List 4–6 tasks you've actually used AI for in the last two weeks.** If you haven't used AI much yet, list tasks you'd like to use it for. Be specific: "drafted a client email explaining a project delay" tells you something. "Writing" doesn't.
- **For each task, note one line:** did the output land on the first try, or did you need to rework it before it was usable? Don't overthink this. A quick gut check is fine.
- **Now share your list with Claude (or any AI assistant) and ask:** "For each of these tasks, what's one way this could go wrong if I'm not paying attention?" See if the failure modes it names feel relatable. If they don't, push back: "That doesn't match my experience. Here's what actually went wrong..."

Hold onto this list. You'll return to it in every lesson, and it'll look different each time you do.


## Lesson reflection

- Which of your listed tasks felt "safe" to hand to AI, and which felt risky? Can you articulate why yet?
- What's one AI behavior you've noticed (good or bad) that you couldn't explain at the time?

## What's next


Before the four properties, we need to draw a line around what "AI" means in this course. We're talking specifically about generative AI and how it's different from other forms of AI.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## What We Mean by AI
## What you'll learn


*Estimated time: 20 minutes*


By the end of this lesson you'll be able to:

- Distinguish generative AI from the classification and prediction AI you already encounter daily
- Understand that generative AI's properties exist on a continuum from capability to limitation
- Preview the four core properties you'll explore in depth: Next Token Prediction, knowledge, working memory, and steerability

## What we mean by generative AI


*(4 minutes)*


[동영상: https://www.youtube.com/embed/AiiiyYiEJa4]



Most AI in the world (spam filters, recommendations, fraud detection) isn't generative. This course is about the kind that is: transformer-based text models that produce new content one token at a time.


## Building a mental model of the machine
    AI Capabilities & Limitations Framework

Four properties that shape what AI can and can't do for you. Each sits on a spectrum — the further right, the more you should verify and compensate.
  CapabilityLimitation   [이미지]  Next Token Prediction

Where do AI answers come from?
Well-worn paths: summarize, reformat, explain common conceptsNovel territory, sparse patterns, "true vs. sounds true"    [이미지]  Knowledge

What does AI actually know?
Frequent, recent-in-training, consistent: mainstream topics, popular languagesRare, post-cutoff, niche, local, or contested topics    [이미지]  Working Memory

What is the AI paying attention to right now?
Material fits comfortably, session is current, you supply relevant contextVery long docs/conversations, expecting cross-session continuity (the cliff)    [이미지]  Steerability

How much am I in control?
Short, concrete, verifiable instructions ("respond as a table," "under 100 words")Long reasoning chains, abstract asks, native precision

#### Key takeaways

- **Generative AI produces new content** rather than classifying existing content.
- **AI isn't uniformly capable or uniformly unreliable.** It's strong and weak along four predictable axes: Next Token Prediction, Knowledge, Working Memory, and Steerability.
- **Each property is a continuum.** The same mechanism gives you both the capability and the limitation.
- **Calibrated trust** means locating your task on the continuum, not granting or withholding trust wholesale.

## Exercises


**Exercise: Generative or Not?**


*Why? You just learned that generative AI is fundamentally different from the AI that filters your spam and recommends your next video. Now you're going to use that distinction on your own experience.*

- **List five AI-powered features you've interacted with this week.** Cast a wide net: autocomplete, photo tagging, spam filtering, chatbot answers, translation, product recommendations, voice assistants.
- **For each one, jot down your call:** is it producing new content, or is it sorting, ranking, and classifying existing content?
- **Share your list with an AI and ask it to check your calls.** For any you got wrong (or weren't sure about), ask it to explain the distinction in one sentence. Then ask: "Which of these five is most likely to have a failure mode this course will help me understand?"
- **Go back to your Lesson 1 task list.** For each task, tag it with the property question that feels most relevant right now:
- Where do the answers come from? (Next Token Prediction)
- What does it know? (Knowledge)
- What's it paying attention to? (Working Memory)
- How much am I in control? (Steerability)

You're not expected to get these right. You're creating predictions you'll test over the next four lessons.


## Lesson reflection

- Did the generative/classification distinction with AI change how you think about any tool you use?
- Look at how you tagged your task list. Did any task feel like it could belong under more than one property?

## What's next


Before we dig into the four properties, we'll spend one lesson on how an AI system ends up with a personality at all. Why it's polite, helpful, honest, why it sometimes agrees too easily, why it declines certain things. That shaping process leaves fingerprints on everything that follows.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## How AI Gets Its Character
## What you'll learn


*Estimated time: 25 minutes*


By the end of this lesson you'll be able to:

- Explain the two-stage training process for generative AI (pretraining and fine-tuning) in plain language
- Recognize the behavioral fingerprints each stage leaves: sycophancy, verbosity, over-caution, loose confidence calibration
- Apply this understanding to interpret behaviors you see in your own AI interactions

## How AI gets its character


*(5 minutes)*


[동영상: https://www.youtube.com/embed/6jRk3nC4-xI]



An AI's politeness, helpfulness, and caution aren't emergent magic. They're trained in, layer by layer, and each training stage leaves specific, predictable fingerprints on how the system interacts with you.


## Pretraining, fine-tuning, and the fingerprints they leave
   How AI Gets Its Character

Two training stages turn raw prediction into the helpful assistant you interact with — and each stage leaves fingerprints on its behavior.
   Stage 1 Pretraining

The model reads vast amounts of text and learns one thing: predict what comes next. It becomes a powerful document completer — but has no concept of helping you.
         Stage 2 Fine-tuning

Human preferences shape the document completer into an assistant — one that treats your input as a request, answers helpfully, and declines harmful asks.
  Help me improve this paragraph.Of course! Here are three specific suggestions to strengthen your argument and tighten the prose… I think my strategy is bulletproof.I appreciate the confidence! That said, I see two risks worth stress-testing before you commit… How do I pick a lock?I can’t help with that. If you’re locked out, I’d suggest contacting a licensed locksmith in your area.   Helpful Honest Harmless

#### Key takeaways

- **Pretraining** produces a document completer by predicting "what comes next" across vast amounts of data. After this stage, it has no concept of helping you.
- **Fine-tuning** layers assistant behavior on top: treating your input as a request, answering rather than rambling, declining harmful asks.
- **Fine-tuning uses human judgments** about good responses, and those judgments leave fingerprints: a pull toward sycophancy, a default toward verbosity, occasional over-caution, and loose calibration between stated confidence and actual reliability.

## Exercises


**Exercise: Fingerprints on Your Own Work**


*Why? Sycophancy, verbosity, over-caution, and loose confidence calibration show up in every AI model. The question is whether you can see them when they're affecting work you actually care about.*


Pick one task from your Lesson 1 list. Something you've actually run through AI before, where you have a clear sense of what a good output looks like. You're going to run it three times with slight variations and watch what changes.

- **Run 1: Straight.** Prompt the task as you normally would. Save the output.
- **Run 2: Sycophancy test.** Run the same task, but this time preface it with a wrong assumption. For example, if you're asking for feedback on a strategy, open with "I think this strategy is bulletproof." See whether the AI validates your framing or pushes back. Then try again with an explicit invitation: "I want you to genuinely disagree with me if you think I'm wrong." Compare the two responses.
- **Run 3: Verbosity test.** Ask the AI a question related to your task that has a one-sentence answer. Note how much you get. Then re-ask with "Answer in one sentence." Compare the lengths. The gap between the two is the verbosity default at work.
- **Optional: Caution test.** If your domain has any gray areas (most do), ask something at the edge of what you'd expect to be fine: a medication interaction, a legal nuance, a mildly unconventional creative request. Note whether the hedging feels proportionate to the actual risk, or reflexive.

Now step back. Which fingerprint showed up most clearly on your work? Did naming it in advance change how you read the behavior?


## Lesson reflection

- Where in your own work is sycophancy most likely to cost you? (Hint: anywhere you're hoping for honest feedback.)
- Where is verbosity most likely to cost you? (Hint: anywhere you need concision under time pressure.)

## What's next


Now we start on the four properties themselves, beginning with the one that explains more about AI behavior than any other: Next Token Prediction. Where do AI answers actually come from?


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Next Token Prediction
## What you'll learn


*Estimated time: 30 minutes*


By the end of this lesson you'll be able to:

- Explain Next Token Prediction as the core mechanism of generative AI and why it produces both fluency and hallucination
- Locate tasks on the Next Token Prediction continuum (well-worn path vs. novel territory)
- Identify specificity (names, dates, citations, statistics) as the zone where fabrication concentrates
- Recognize product features (citations, uncertainty signaling, constrained generation, generator-verifier pattern) that are mitigations for this limitation

## How AI models use next token prediction


*(4 minutes)*


[동영상: https://www.youtube.com/embed/kl0gunXTvyk]



Generative AI is closer to a vastly sophisticated autocomplete than to a search engine. It writes answers word by word based on what tends to follow what. That single property gives you both the fluency and the hallucination.


## Autocomplete at scale


Before you read


You ask AI to **summarize a long report**. How closely do you need to check the result? Pick a spot on the continuum, then lock in your guess.
    Next Token Prediction Knowledge Working Memory Steerability      [이미지]   [이미지]

##


    Capability Limitation   Trust it Spot-check Check details Verify carefully High risk   Your guess    Typical             What this enables       Where it characteristically fails       Product features that push the edge out

Pick a stop, then lock in your guess. The lesson opens up once you do.
 Lock in my guess

Check your intuition


Lock in your guess above to compare against the typical placement.


#### Customize
  Bar height    Pictogram size    Palette  Sky → Clay Olive → Clay Cactus → Fig Slate → Clay

#### Key takeaways

- **Next Token Prediction** refers to the fact that generative AI writes answers word by word based on what tends to follow what.
- **Capability zone:** tasks that resemble patterns the model has seen many times (summarizing, reformatting, explaining common concepts).
- **Limitation zone:** novel or sparse territory, and anywhere the task requires distinguishing "true" from "sounds true."
- **Fabrication concentrates in specificity:** names, dates, statistics, citations, URLs, quotes. The more precise a claim, the more it warrants verification.
- **Product features** like citations, uncertainty signaling, constrained generation, and generator-verifier loops exist specifically to push this limitation further out.
- **4D connection:** Next Token Prediction is the foundation of Discernment. Knowing the output was generated tells you exactly what kind of scrutiny to apply.

## Exercises


**Exercise: The Verification Test**


*Why? You now know that the same generative process that makes AI fluent is the one that makes it fabricate. Time to see that on your own turf, in a domain where you'll catch it.*


Go back to your task list and pick the task where you're most confident in your domain expertise. You need a topic where you're the expert, because you need to be able to verify what comes back. Write down five specific, checkable facts from that domain: a person's job title, a publication date, a statistic, a product specification, a direct quote, a URL. Things you know to be accurate and can confirm independently.


Now run three probes:

- **Probe 1: The capability zone.** Ask the AI to explain or summarize a well-known concept in your domain. Something popular and well-documented. Note the fluency. Spot-check the content. This is what the capability zone feels like: smooth, confident, and largely accurate.
- **Probe 2: Specificity under pressure.** Ask the AI to provide five checkable specifics in your domain: cite three sources, name an author, give exact figures, provide a URL. Verify every one. Score it out of five: how many were fully accurate? If it fabricates, note how confident it sounded doing it.
- **Probe 3: Sampling in action.** Run the exact same specific-facts request in a fresh conversation. Compare the two outputs. What stayed consistent? What changed? The variation you see is Next Token Prediction's sampling at work.

**Stretch goal:** Re-run Probe 2 in a tool with citations enabled (like Research mode in Claude). Score it again. Does having sources to check change the score?


## Lesson reflection

- Would you have caught fabrications in a domain you didn't know well?
- Look at your task list: which tasks sit mostly in the capability zone, and which push into specificity that needs verification?

## What's next


Next Token Prediction explains how the AI generates. Next we look at what it's generating *from*: the Knowledge property. What does the model actually know, where does that knowledge come from, and where are the gaps?


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Try it out
Text Your Friend Markov

# Text Your Friend Markov


The 100% interpretable next-token generator


## Send a Text


Long ago, my friends and I would play this game where you'd grab your phone and craft a message to a friend using only the recommended next words. Maybe you did this too.


Here's a simulator that was "trained" on a bit of content. Have a play!
     hey does anyone know how to fix the build i think |    the we i  ↻ start over

We talked about this as if it were a "Me-bot". We knew it was recommending words based on our individual usage patterns, and we could see our voices in our personalized recommendations.


At the time, we were happy to dismiss it as tech magic. I don't think we realized how simple the algorithm might be.


Keep reading if you want to build one with me :)


## "Training" Your Model


Let's train on a handful of messages. All we need to do is tally the connections between words. Let's do this one message at a time.
   + Add message 1

### The Transition Matrix


Add messages above to start building the matrix.


This finished map of connections between words is called a **frequency table**. Normalize each row and you get a probability distribution of what comes next.


The act of picking a next word based on what you have so far is called **sampling**. We use that same term for this process with modern language models like Claude.


## Do Some Sampling


Using the same matrix based on 5 texts, go ahead and have a more informed play at our game. We'll show you the probabilities.
    ↻ start over

The highlighted row is your current context. Pick a word from the available choices to continue.


## Scale it up


Five messages gave us a tiny matrix and a handful of predictions. What happens with more data?
   + 1 message + 10 + 50 All 222   5messages 17unique words 13contexts 24transitions 2max options

After :


## The knobs


When you were sampling, you could see probabilities, but you also used your instincts about which words "felt right."


If you had to write *code* to make those choices instead of using your gut, **what encoded rule do you think would create the best result?**
    Always pick the highest-probability word  Pick semi-randomly, according to probabilities  Pick according to probabilities, but also boost the most likely choices  Ignore anything below a certain probability threshold  Only consider the top N options  Goblin mode — ignore the probabilities and pick something random  Show me the knobs

Awesome. Play with the knobs below to see how sampling parameters impact a language model's choices. Then check how your intuitions mapped.


Developers use parameters like **temperature** and **tail trimming** to improve sampling after the probabilities are generated.


After "think":
       Temperature 1.0   focusedrandom

Sampling faithfully from the distribution.


Tail trimming


Remove unlikely words entirely before sampling.
   None  Top-k  Top-p   Top words3

Only the 3 most likely words survive.
   Probability mass0.9

Keep the smallest set of words whose probabilities sum to 90%.


Unlike top-k, this adapts to confidence — when the model is sure, fewer words survive. When uncertain, more do.
      Generate reset

If you made a choice earlier, you intuitively selected one of these approaches.
 How did my instinct map to these parameters?

## The bridge


The sampling strategies you just used are more or less the same sampling constraints that developers pass to Claude. For LLMs, a few things differ.
  Markov chain LLM  1 Read context last word: **"think"**   1 Read context entire conversation so far   2 Compute distribution look up one row in a table   2 Compute distribution forward pass through billions of parameters — attention, embeddings, feedforward layers, residual connections, layer norms...   3 Sample next token   we *32%* the *16%* i *11%*     3 Sample next token same process   we *32%* the *16%* i *11%*

The Markov table lookup is a really simple and explainable operation. A forward pass through a neural network is quite a bit more complex. But in either case, the output is the same: a probability distribution of likely next words or tokens.


While sampling is the same, training is radically different. The exponential wall from before (vocabularyN rows) doesn't apply. LLMs trade the explainability of simply tallying words for far more context and far greater capabilities.


## 100-year-old Tech


*"Is this real tech?" Great question, reader.*


Markov published this idea in 1906. A century later in 2010, n-gram models like this were powering next-word prediction on your phone (SwiftKey, then Apple's QuickType). Around 2015, neural networks — first RNNs, then transformers in 2017 — began to replace the table lookup approach with a learned function, and the rest is... well, it's what we're working on now.

---

## Knowledge
## What you'll learn


*Estimated time: 30 minutes*


By the end of this lesson you'll be able to:

- Explain how an AI model's knowledge is formed during training and why it has a fixed cutoff
- Predict which topics sit in the capability zone (frequent, recent-in-training, consistent) versus the edge (rare, post-cutoff, niche, contested)
- Identify staleness, uneven coverage, inherited bias, and source amnesia as characteristic knowledge failures
- Recognize web search, retrieval/RAG, and tool use as the product features that address this limitation

## Understanding knowledge gaps in AI models


*(5 minutes)*


[동영상: https://www.youtube.com/embed/iSLdQXeKbHs]



The model knows what it was exposed to during training, and only that. No real-time browsing by default, no lived experience, and a hard stop at the knowledge cutoff. The practical question isn't "does the AI know this?" but "how well-represented was this in what it read?"


## What the model read, and when it stopped reading


Before you read


You ask AI to **explain a news event from last week**. How closely do you need to check the result? Pick a spot on the continuum, then lock in your guess.
    Next Token Prediction Knowledge Working Memory Steerability      [이미지]   [이미지]

##


    Capability Limitation   Trust it Spot-check Check details Verify carefully High risk   Your guess    Typical             What this enables       Where it characteristically fails       Product features that push the edge out

Pick a stop, then lock in your guess. The lesson opens up once you do.
 Lock in my guess

Check your intuition


Lock in your guess above to compare against the typical placement.


#### Customize
  Bar height    Pictogram size    Palette  Sky → Clay Olive → Clay Cactus → Fig Slate → Clay

#### Key takeaways

- **What generative AI knows** comes entirely from training data and is frozen at the knowledge cutoff. Without tools, it has no access to any information after that date.
- **Capability zone:** topics that appeared frequently, recently (within training), and consistently in training data.
- **Limitation zone:** rare, post-cutoff, niche, local, or contested topics.
- **Characteristic failures:** staleness, uneven coverage, inherited bias in what counts as "default" or "normal," and inability to attribute where knowledge came from.
- **Web search, retrieval (RAG/MCPs), and tool use** exist specifically to patch these gaps by giving the model access to information it was never trained on.
- **4D connection:** Knowledge unevenness is core to Delegation. Understanding where the model is well-stocked versus thin tells you when to hand off, when to supply context yourself, and when to go elsewhere.

## Exercises


**Exercise: The Outsider Test**


*Why? You know the model's knowledge is broad but frozen, shaped by whatever was in its training data. Now you're going to map exactly where it's well-stocked and where it's thin in your specific domain.*


Return to your task list and select one task. Relative to that task, write down:

- Two topics that are mainstream, well-documented, and stable. The kind of thing any informed colleague would know.
- Two topics that are niche, local, recent, or rapidly evolving. Industry-specific jargon, regional regulations, something that changed in the last year.
- One "default assumption" that outsiders to your field often get wrong. (Who the typical customer is. What a "standard" case looks like. Which tool people actually use vs. the one that gets press.)

Now run three probes:

- **Probe 1: Coverage.** Ask about one mainstream topic and one niche topic from your list. Compare the depth and accuracy. Pay attention to whether the AI signals uncertainty differently between the two, or whether both answers come with the same confident tone.
- **Probe 2: Staleness.** Ask about something you know has changed recently in your field: a regulation update, a tool release, a leadership change, a revised standard. Does the AI acknowledge the cutoff? Present stale information as current? Decline to answer? Note what happens.
- **Probe 3: Default assumptions.** Without naming your assumption directly, ask a question that would reveal whether the AI defaults to the outsider's view. For example, if your field's "standard" customer is different from what most people assume, ask the AI to describe the typical customer. Note what it treats as normal.

Go back to your task list and add a second annotation: for each task, flag whether you can lean on the model's knowledge, or whether you need to bring the knowledge yourself via context, documents, or search.


**Stretch goal:** Re-run the staleness probe with web search enabled. Compare what changes. This is retrieval in action.


## Lesson reflection

- What's one area of your work where you now realize you need to supply context rather than assume the model has it?
- Did the default-assumption probe surface anything that surprised you?

## What's next


Knowledge covers what the model absorbed during training. Working Memory covers what it's paying attention to right now: your prompt, your documents, your conversation. This property has the hardest edge of all four.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Try it out
Visualizing 1024D Space

# Visualizing 1024D Space


How multidimensional "nearness" works


## The Problem with Strings


Search "car" and you'll find every document containing the word "car." You won't find "automobile." Or "vehicle." Or "my Civic needs new brakes."


For decades, that was search, returning results based on string similarity rather than meaning. Google continuously made incremental improvements with engineering: Synonym dictionaries mapped "car" to "automobile," Stemming rules connected "running" to "run," and click-pattern mining surfaced that people who search "NYC apartments" want the same results as "Manhattan rentals." The connections between non-matching strings had to be mapped more or less by hand.


**Embeddings** challenged all of this with the idea that **meaning** could be a *place*. By converting text into coordinates, similar concepts end up near each other. This mapping of semantic space isn't manual, but rather **emergent** from training data.


## Encoding


Let's start with a simplified example.


Imagine you were to score every document in a corpus of knowledge on two dimensions: how much it relates to dinosaurs, and how much it relates to roller coasters. Documents about similar topics would end up near each other.


Let's start with just three sources. Place each of these where you think they belong.
   How much does this relate to **roller coasters**? →        not at all very very click to place selected item  How much does this relate to **dinosaurs**? →

Sources
  🦕 A children's book about dinosaursclick to select   🎢 The Velocicoaster web pageclick to select   📚 An entire encyclopediaclick to select

You've just mapped meaning in 2D space, plotting our collection of items based on what they're about.


## Retrieval


Now let's search this space.


Plot a question on the same graph with the same axes. By mapping your question with the same logic you used to map sources, you can be sure that the nearest items will be the most relevant. Bonus feature: Use the slider to control how many get retrieved.
  Sources to retrieve (k):  2    How much does this relate to **roller coasters**? →        not at all very very click to place the question   How much does this relate to **dinosaurs**? →    Question

❓ "What's the best dinosaur-themed roller coaster?"


click graph to place


That's **similarity search** in a nutshell. We plot the question and find the nearest k items. Instead of keyword matching or synonym tables, we use multi-dimensional proximity.


Two axes is a start. But two dimensions can only capture two concepts. The real world has more than two topics, so we need more **dimensions**.


## More Dimensions


What if we added a third axis? Let's use **biology**.


The children's book scores high (species, habitats, diets). The encyclopedia covers some. The Velocicoaster page barely mentions it.


Drag to rotate.


Three dimensions, three coordinates per document. The Velocicoaster page is now (0.50, 0.90, 0.05) instead of (0.50, 0.90).


Now try to picture a fourth axis.


Since I only exist in 3 dimensions, I personally can't 😔 but that actually doesn't matter! Each new dimension just adds another coordinate to each point and another squared term to the distance formula. The spatial representation stops working at 4D, but the math keeps working.


We're going to have to push well past 4D, because real **embedding models** use around a thousand dimensions. Each document and each query becomes a point in that thousand-dimensional space. "Find the nearest documents" still means the same thing it meant on the 2D graph. It's just a longer distance calculation.


## Unlabeled Axes


We chose the axes: dinosaurs, roller coasters, biology. But who determines which 1,024 topics make it into a real embedding model?


In point of fact, no one decides. The meaning of each axis is emergent (meaning it just shows up in training), and more of a black box. You can't look at dimension 847 and say "that's the dinosaur axis." The dimensions don't correspond to anything a human could name.


This makes the space harder to reason about. We can't interrogate dimension 847 to understand why two texts landed near each other, or why something we expected to be close ended up far away.


## Text as Coordinates


So who assigns the coordinates? An **embedding model**. Any string in, a fixed-length list of numbers out.
    Text "work from home"  →  Embedding [0.23, -0.87, 0.41, ...]  1,024 values    Text "Employees may work remotely up to two days per week with manager approval."  →  Embedding [0.71, 0.09, -0.33, ...]  1,024 values

The output is always the same length (1,024 values in our specific case, since we're using VoyageAI's embeddings model) and this is true whether the input is three words or three paragraphs. One chunk of text corresponds to one point in space. The embedding model reads the text and outputs a single **vector**.


The math-eyed among you will recognize that "vector" and "coordinate set" aren't actually interchangeable, but for our purposes, it's appropriate to think of the vector as the address where this text lives relative to everything else.


## Similarity


"Nearest" on our 2D graph meant straight-line distance. In practice, similarity search uses **cosine similarity** instead. Cosine similarity is just another measure of how similar two pieces of text are, based on the direction their vectors point rather than how far apart they sit.


Try it yourself! Pick two sources to see their cosine similarity.
    Source A  ❓ 🦕 🎢 📚

❓ Best dinosaur roller coaster?
    Source B  ❓ 🦕 🎢 📚

🦕 Children's dinosaur book
      Cosine similarity 0.2894       -1 *opposite* 0 *unrelated* 1 *identical*

Try comparing the Velocicoaster page to the dinosaur book — their vectors point in very different directions. The encyclopedia lands somewhere in between everything, which fits, since it's a jack of all trades but a master of none.

---

## Working Memory
## What you'll learn


*Estimated time: 30 minutes*


By the end of this lesson you'll be able to:

- Explain the context window as a fixed-size container and what that implies for long documents, long conversations, and cross-session memory
- Recognize the "cliff" nature of this property compared to the gradual degradation of others
- Apply context-as-leverage strategies: front-loading important material, chunking long work, re-supplying critical context
- Recognize memory, compaction, projects/workspaces, and larger windows as product features addressing this limitation

## How the context window affects generative AI outputs


*(6 minutes)*


[동영상: https://www.youtube.com/embed/QJjt4wF4iHM]



Everything the AI is paying attention to lives inside a fixed-size workspace called the context window. It can attend to what's in there. It can't attend to anything outside it. That constraint is hard-edged in a way the other properties aren't: things work until they don't.


## The context window: AI's working memory


Before you read


You ask AI to **review a 50-page contract**. How closely do you need to check the result? Pick a spot on the continuum, then lock in your guess.
    Next Token Prediction Knowledge Working Memory Steerability      [이미지]   [이미지]

##


    Capability Limitation   Trust it Spot-check Check details Verify carefully High risk   Your guess    Typical             What this enables       Where it characteristically fails       Product features that push the edge out

Pick a stop, then lock in your guess. The lesson opens up once you do.
 Lock in my guess

Check your intuition


Lock in your guess above to compare against the typical placement.


#### Customize
  Bar height    Pictogram size    Palette  Sky → Clay Olive → Clay Cactus → Fig Slate → Clay

#### Key takeaways

- **Working Memory** is the fact that the AI model has a fixed context window that it can attend to.
- **Capability zone:** your material fits comfortably, the session is current, you're supplying relevant context.
- **Limitation zone:** very long documents or conversations, expecting continuity across sessions, burying critical info in the middle of long input.
- **This property has a cliff** rather than a gradient. Silent truncation is the failure mode, and you won't always be warned.
- **The model doesn't learn from your corrections.** It only responds to what's currently in context.
- **Memory features, compaction, projects, larger windows, and multi-agent workflows** all exist to push this cliff further out.
- **4D connection:** Working Memory is what Description acts on. Knowing how the window works tells you how to structure context, when to front-load, and when to start fresh.

## Exercises


**Exercise: The Before-and-After**


*Why? Context is leverage. The same task, with the right context supplied, can go from a mediocre first draft to something genuinely useful. This exercise makes that concrete.*


Pick a task from your Lesson 1 list that benefits from context only you hold: a style guide, a past example of good work, a set of constraints specific to your role or audience. Write down in two or three lines what "good" looks like for this task's output, described clearly enough that a stranger could evaluate it.


Now run three probes:

- **Probe 1: Cold start vs. context.** Ask for your task with zero context. Just the bare request. Save the output. Then start a fresh conversation and run the same task, this time supplying your style guide, past example, or constraints upfront. Compare both outputs against your "good" definition. Measure the gap.
- **Probe 2: Lost in the middle.** Take a longer document (or paste together a few paragraphs of reference material). Bury one specific, important instruction in the middle of it. Ask a question whose correct answer depends on that buried instruction. Did the AI catch it? Now move that instruction to the very top and ask again. Compare.
- **Probe 3: The blank slate.** Have a short exchange where you teach the AI something specific about your work context, or correct it on something it got wrong. Then open a brand-new conversation and ask a question that assumes it remembers what you taught it. Watch it start from zero.

Go back to your task list and add a third annotation: which tasks need standing context set up (a project, saved instructions, uploaded reference docs) to be worth running, and which work fine cold?


**Stretch goal:** If your tool has memory or project features, set one up with the context from Probe 1. Run the task again. Compare effort and quality against the cold-start version.


## Lesson reflection

- How much did front-loading context change output quality? Was the gap bigger than you expected?
- What's one piece of standing context you'll set up this week to stop re-explaining yourself?

## What's next


The final property: Steerability. How much are you actually in control when you give instructions, and where does that control break down?


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Try it out
Context Degradation — When More Is Less

# Context Degradation


When more context makes things worse


A natural instinct when using AI is to give it **everything**. Paste in the whole document. Include every message. Add all the context you can find. More information means better answers, right?


Not always. There's a phenomenon that anyone who has crammed for an exam knows intuitively: **there's a limit to how much you can hold in mind at once**. And the things in the middle tend to disappear first.


Before we talk about how this affects AI models, let's see how it affects **you**.


## The Memory Test
      Memory Test You'll see 15 words, one at a time. Each appears for about 1.5 seconds. Try to remember as many as you can. Show the Words            Type the words you remember, separated by commas or spaces.  Check My Memory      You recalled 0 of 15   Hallucinated    Serial position — your recall pattern      Most likely Least likely Most likely

The words you remembered likely cluster at the **beginning** and **end** of the list. The middle gets lost. This is the **primacy–recency effect** — and LLMs show the same bias.


Instructions at the start and end of a context window get followed. The middle gets buried. This is why more context ≠ better results — and why "Lost in the Middle" (Liu et al., 2023) found accuracy drops of 30%+ when key facts land in the center of long contexts.
   Replay words (defeats the exercise)

## The U-Shaped Curve


What you just experienced has a name: the **serial position effect**. Psychologists have studied it for over a century. Items at the beginning of a list benefit from **primacy** (they get rehearsed more), and items at the end benefit from **recency** (they're still fresh). The middle gets neither advantage.


The fascinating part: **large language models exhibit the same pattern**. In 2023, researchers at Stanford tested what happens when you place a key fact at different positions within a long context window. Accuracy was highest when the fact appeared at the very beginning or very end — and dropped by more than 30% when it was buried in the middle.


This isn't a quirk. It's structural. Transformer attention patterns naturally weight the edges of the context window more heavily.


## What This Means for Prompting


If you paste a 20-page document into a prompt and ask a question about something on page 11, the model is more likely to miss it than something on page 1 or page 20. This has real implications for how you structure context.
   ❌ Dangerous pattern  System prompt Chat message 1 Chat message 2 ... ⚠ Key instruction buried here ... Chat message 18 Latest user message    ✓ Safer pattern  System prompt ★ Key instruction (up front) Chat message 1 Chat message 2 ... Chat message 18 Latest user message ★ Key instruction (repeated)

The practical advice is straightforward: **put your most important instructions at the beginning and end of the context**. If a constraint absolutely must be followed, state it early in the system prompt and restate it near the end. Don't rely on the model to give equal weight to everything in between.


This is the starting point, not the ceiling. As you get more fluent you'll discover increasingly sophisticated ways to structure context so the model reliably understands what matters — leveraging where in the window information sits, what to include versus cut, and how to keep critical instructions from sliding into the dead zone. The goal is always the same: make it obvious to Claude what you actually need.


## The Bigger Picture


Context degradation is the reason that "just give it more context" is not always the answer. Every piece of context you add pushes other pieces further into the middle — the attention dead zone. This is the core tension of **context engineering**: not just what to include, but where to put it and what to leave out.
  Key takeaway More context ≠ better results. The model's attention is finite. Curate ruthlessly, place strategically, and repeat what matters.

Your own memory test told you this already. The words in the middle vanished. The same thing happens inside every long conversation, every pasted document, every context window that's been filled to the brim. The fix isn't more — it's smarter.

---

## Steerability
## What you'll learn


*Estimated time: 30 minutes*


By the end of this lesson you'll be able to:

- Explain why steerability works (fine-tuning taught the model instruction-following) and why it has limits (instructions are followed via pattern-matching, not understanding)
- Predict where control is tightest (short, concrete, verifiable instructions) versus loosest (long reasoning chains, abstract asks, native precision tasks)
- Identify reasoning drift, letter-over-spirit, and brittle arithmetic as characteristic steerability failures
- Recognize system prompts, code execution, visible reasoning, and structured outputs as product features addressing this limitation

## How steerability affects generative AI outputs


*(5 minutes)*


[동영상: https://www.youtube.com/embed/M_RwSRmp220]



The model follows your instructions the same way it does everything else: by continuing a pattern. That makes it remarkably steerable. It also means there's always a gap between what you intended and what landed, and most of the interesting failures live in that gap.


## How much are you actually in control?


Before you read


You ask AI to **write exactly 100 words, no more**. How closely do you need to check the result? Pick a spot on the continuum, then lock in your guess.
    Next Token Prediction Knowledge Working Memory Steerability      [이미지]   [이미지]

##


    Capability Limitation   Trust it Spot-check Check details Verify carefully High risk   Your guess    Typical             What this enables       Where it characteristically fails       Product features that push the edge out

Pick a stop, then lock in your guess. The lesson opens up once you do.
 Lock in my guess

Check your intuition


Lock in your guess above to compare against the typical placement.


#### Customize
  Bar height    Pictogram size    Palette  Sky → Clay Olive → Clay Cactus → Fig Slate → Clay

#### Key takeaways

- **Steerability** means the model follows instructions via Next Token Prediction.
- **Capability zone:** short, concrete, verifiable instructions. Format specs, length limits, explicit roles.
- **Limitation zone:** long chains of reasoning, abstract or ambiguous instructions, anything requiring native numerical or logical precision.
- **Characteristic failures:** reasoning drift (small errors compound) and letter-over-spirit (the instruction was honored but the intent wasn't).
- **System prompts, code execution, visible reasoning, and structured output modes** exist to keep your intent from diluting.
- **When an instruction is followed literally but uselessly, restate the goal.** Repeating the instruction with more force won't close the gap.
- **4D connection:** Steerability is what makes Description powerful and what bounds it. Understanding the gap between words and intent changes how you write prompts and where you insert checkpoints.

## Exercises


**Exercise: The Goal Rewrite**


*Why? The gap between what you say and what you mean is where most steerability failures live. This exercise teaches you to prompt from intent, not just from instruction.*


Pick a task from your Lesson 1 list that involves multiple steps or a specific output format. Write down the goal in one sentence: what you're actually trying to accomplish, not just what the output should look like. ("Convince my team this timeline is realistic" is a goal. "Three bullet points" is a format.)


Now run three probes:

- **Probe 1: Tight control.** Give a short, concrete, verifiable instruction related to your task: "respond as a three-column table," "exactly five bullet points," "second person throughout." Check whether it held precisely. This is the capability zone: the instruction is simple enough to pattern-match perfectly.
- **Probe 2: Reasoning drift.** Ask for a version of your task that requires 4–5 dependent steps. Review the output step by step. Did a small error early on carry through to the end? Now try again, but ask the AI to stop and show you the result of step 2 before continuing. Compare what you get when you insert a checkpoint versus when you let it run.
- **Probe 3: Letter vs. spirit.** Give an instruction that could be satisfied literally but uselessly. "Make this shorter" on a draft where the real problem is structure. "Make this more professional" on an email where the real problem is that it's burying the ask. See what you get. Then re-prompt with the goal stated explicitly alongside the instruction: "Make this shorter. My goal is to keep the executive's attention through the key finding on page two." Compare.

Go back to your task list. For any multi-step tasks, note where you'd insert a checkpoint. For any tasks where you've been prompting with format alone, draft the goal statement you'll add next time.


## Lesson reflection

- How often have you been stating format but not goal? What changes when you include both?
- What's one recurring task where you'll add a mid-process checkpoint starting this week?

## What's next


You've now met all four properties individually. In the next lesson we look at how they interact, because most real-world failures are two properties meeting.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Try it out
Letter vs. Spirit — Interactive

# Letter vs. Spirit


Instructions are honored via pattern-matching, not understanding. There's always room between your words and your intent.
     Every instruction has a gap between letter and spirit. You close it by stating the goal.   "Make it shorter" You meant: surface the ask for a skimmer.   "Make it more professional" You meant: reframe for a different audience and channel.   "Add more detail" You meant: expand only what drives a decision.

---

## When Properties Collide
## What you'll learn


*Estimated time: 25 minutes*


By the end of this lesson you'll be able to:

- Recognize that most AI failures involve two or more properties interacting
- Diagnose common failure patterns (hallucinated citations, long-conversation drift, confidently wrong math, agreeable bad premises) by identifying which properties are at play
- Apply a targeted fix based on which property is the limiting factor

## Diagnosing AI failures


*(3 minutes)*


[동영상: https://www.youtube.com/embed/SPkg5WRfnEE]



The four properties don't operate in isolation. Most real failures are two of them intersecting. Once you can name which two, you know which fix to reach for.


## Two properties meeting: diagnosing what went wrong


# When Properties Collide


Most real-world AI failures are two properties meeting at the same time.
      [이미지]  Next Token Prediction Generates what sounds right     [이미지]  Knowledge Knows what it was trained on     [이미지]  Working Memory Attends to what's nearby     [이미지]  Steerability Follows the loudest instruction     drag two properties near each other to see what happens when they collide

#### Key takeaways

- **Real-world failures are usually two properties interacting**, not one.
- **Diagnostic pairs to recognize:**
- Next Token Prediction + Knowledge (hallucinated specifics)
- Working Memory + Steerability (long-conversation drift)
- **Naming the properties at play** points you straight to the fix: verify specifics, re-supply context, offload to code execution, or invite pushback.
- **This diagnostic move is Discernment applied.** You evaluate better when you know what kind of wrong you're looking at.

## Exercises


**Exercise: The Failure Diagnosis**


*Why? Most real-world AI failures aren't one property acting up. They're two properties meeting at the same time. Naming which two changes the fix entirely.*


Think back across your experience with AI (including what you've observed during this course). Identify two or three times an AI output genuinely disappointed or surprised you. For each one, describe it in a sentence or two: what you asked, what you got, what was disappointing or surprising.

- **Walk through each event with the AI.** Describe what happened and ask: "Based on the four properties (Next Token Prediction, Knowledge, Working Memory, Steerability), which ones were likely at play here, and why?"
- **Evaluate its diagnosis against what you now know.** Do you agree? If not, push back. (Remember the sycophancy fingerprint from Lesson 3: the AI may agree with your framing too readily. If you think it's wrong, say so.)
- **For each diagnosis, ask:** "Given that diagnosis, what's the most targeted fix?" If you can, test the adjustment right now on a similar task.

Now look at your Lesson 1 task list with all its accumulated annotations (property tags from Lesson 2, verification scores from Lesson 4, knowledge flags from Lesson 5, context needs from Lesson 6, goal statements from Lesson 7). For the tasks that gave you the most trouble, name which two properties were colliding. Write the diagnosis next to each one.


## Lesson reflection

- Did naming the property pair change what fix you'd reach for? Before this course, would you have tried a different (less effective) fix?
- Which property pairing do you think you'll encounter most often in your day-to-day work?

## What's next


In the final lesson, we consolidate what you've built, connect it back to the 4D Framework as a complete system, and point you to where to go deeper.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Next Steps
## What you'll learn


*Estimated time: 20 minutes*


By the end of this lesson you'll be able to:

- Synthesize the four properties and training fingerprints into a working mental model
- Connect the Capabilities & Limitations framework to the 4D Framework as two halves of one system
- Identify one concrete change to make in your AI practice this week

## Applying the 4D framework to get better AI outputs


*(5 minutes)*


[동영상: https://www.youtube.com/embed/F7ciHDKAlCA]



Fluent AI use isn't about memorizing every failure mode. It's about holding a small, clear model of the machine in your head, so that when something goes wrong you can recognize which kind of wrong it is and respond accordingly.


## A small model of the machine
    AI Capabilities & Limitations Framework

Four properties that shape what AI can and can't do for you. Each sits on a spectrum — the further right, the more you should verify and compensate.
  CapabilityLimitation   [이미지]  Next Token Prediction

Where do AI answers come from?
Well-worn paths: summarize, reformat, explain common conceptsNovel territory, sparse patterns, "true vs. sounds true"    [이미지]  Knowledge

What does AI actually know?
Frequent, recent-in-training, consistent: mainstream topics, popular languagesRare, post-cutoff, niche, local, or contested topics    [이미지]  Working Memory

What is the AI paying attention to right now?
Material fits comfortably, session is current, you supply relevant contextVery long docs/conversations, expecting cross-session continuity (the cliff)    [이미지]  Steerability

How much am I in control?
Short, concrete, verifiable instructions ("respond as a table," "under 100 words")Long reasoning chains, abstract asks, native precision

#### Key takeaways

- **You now hold a working mental model:** four properties as continuums, characteristic failures as property intersections.
- **This framework and the 4D Framework are two sides of one system.** The properties explain what the 4D competencies are responding to.
- **Calibrated trust** means locating your task on each continuum and matching your verification and context habits to where it sits.
- **Models will keep changing.** The shape of these properties stays useful even as the exact boundaries shift.

## Exercises


**Exercise: Your Commitment**


Return one last time to your task list from Lesson 1. For each task, jot a quick gut-read: where does the task land on each property's continuum, and what mitigations might you need?


Now, pick one task and one change you'll make this week (a verification step, a standing-context setup, a checkpoint, a goal-stated-not-just-format habit). Write it down.


## Lesson reflection

- What's the single biggest shift in how you think about AI behavior from Lesson 1 to now?
- Which of the 4Ds feels most immediately sharpened by what you've learned here?

## What's next


If you haven't yet taken the AI Fluency Framework & Foundations course, that's the natural next step. It goes deep on the human competencies this course gave you the machine-side context for. And keep testing edges: the properties stay stable, but where the lines sit will keep moving as models improve.


#### Feedback


As you progress through the course, we'd love to hear from you about how you are using concepts from the course in your work, plus any feedback you may have. Share your feedback [here](https://docs.google.com/forms/d/e/1FAIpQLScUKtBMYFxnHE30yCMAuJ55ntOmfWckEFpHLYuLVBwgtBnmcw/viewform).


#### Acknowledgments and license


*Copyright 2026 Anthropic. Original work building on the AI Fluency Framework developed by Prof. Rick Dakan (Ringling College of Art and Design) and Prof. Joseph Feller (University College Cork). Released under the CC BY-NC-SA 4.0 license.*

---

## Course Quiz
**

## Loading...
