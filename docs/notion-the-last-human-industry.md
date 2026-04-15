[Skip to content](https://vexorai.notion.site/the-last-human-industry#main)

# The Last Human Industry

Vexor × Project Europe — Barcelona Hackathon Track Brief

> You wanna know what's more important than throwin' away money at a strip club? Credit
> — JAY-Z, The Story of O.J.

### The setup

Credit is the engine of capitalism — borrow today, build tomorrow. The entire financial system, from high-street banks to the most exotic leveraged products, runs on one careful dance: get paid back if it works, lose if it doesn't.

Everyone uses internal 'voodoo' models to predict who will pay. In reality, they're black boxes that give a false sense of safety.

At Vexor we deal with the most acute version of the problem: what happens when the credit wasn't paid back?

Today we dive straight into the biggest leagues — $10bn+ AUM debt servicers processing thousands of these cases daily.

A servicer buys a portfolio of 50,000 delinquent accounts for cents on the euro. From day one, the clock is running. Every month without recovery, the portfolio bleeds value.

They pick up the phone. 71% of calls never reach the debtor. Wrong number. Voicemail. Rings out forever.

They go to court. Months later, a state-run asset registry returns a report. 73% of the time it says: nothing seizable.

So what's left? A name. A debt. A silence.

This is the reality of one of Europe's largest asset managers, today. This is where you come in.

### The challenge

Do not build a credit scoring model. Do not build a payment prediction ML pipeline. The financial industry has spent 40 years and billions trying that. It's a solved-to-death, zero-margin game. If everyone in the industry has the same historical data, no one wins.

The money is in the information you don't have.

This is a game of leverage. Every hour a collector spends chasing a debtor who said "I have no job, I have no money, I can't pay you" is an hour of lost margin. But what if the AI already knew — before the call — that this person is employed, has a car registered in their name, owns a small business, posts from a beachfront apartment on Instagram?

That's leverage. That's a negotiation that ends in a settlement instead of a ten-year legal saga.

Your job: build an AI agent that takes minimal starting information — a name, a country, maybe a phone or an address — and returns something useful enough that a human collector picks up the phone with a real angle.

### What a good solution does

A good solution turns silence into a decision.

Given a row from the dataset, it goes out, finds what it can, and returns a picture of the person — enough context that a collector, a lawyer, or a strategist can decide what to do next and why.

It could be a structured profile. It could be a conversational briefing. It could be a prioritized queue. It could be something we haven't thought of. What matters is that the output moves the case forward — from a name nobody can reach to a case somebody knows how to work.

Surprise us.

### What we'll judge on

We are not judging accuracy of the final answer. 24 hours is not enough to build a perfect enrichment pipeline, and we don't expect one.

We are judging whether you retrieved the right raw information, correctly sourced, in a form we can build on. If the foundation is honest and defensible, the accuracy comes later. If it's not, nothing built on top of it matters.

Specifically:

Relevance of what you found — is this the kind of signal a real collector could use?

Defensibility of sources — every claim traceable to a public source. No hallucinations. No guessing.

Reasoning transparency — can we see why the agent concluded what it did?

Honesty about gaps — cases with nothing findable should say so, not fabricate.

### What you're getting

A CSV of 100 cases:

\[\
\
[DATASET LINK](https://docs.google.com/spreadsheets/d/1diB-WSNJejieFJa3dEeQ0k5aR5djHHICT5QHQodNxWo/edit?usp=sharing)\
\
\]

Each row: a case ID, a country, a debt amount, a call-attempt outcome, and a legal asset-report outcome. That's it. Minimal by design — the servicer really does start from this little.

The dataset is anonymized. There are no real names or identifying details — it exists so you can understand the shape of the industry: the distribution of information available, how often calls fail, how rarely asset reports find anything. The debt and call/legal histories are distribution-matched to real data from ~5,000 collection calls and real asset reports. The skew is real: most calls fail, most reports find nothing. Build for the reality.

If you need one or two real cases to actually build and test your enrichment pipeline end-to-end, use your own name or someone you personally know. That way you can verify the agent's output against ground truth.

If you need API credits for an external third-party service, just reach out to me and we'll sort it out.

### The prize

F1 Grand Prix tickets (Barcelona, June) for the winning team. The MVP also gets a two-week sprint building a real version of this inside Vexor's platform, for real portfolios, with real debtors.

### Why this matters

Debt collection is not glamorous. No one puts it on a pitch deck. But it is one of the last industries where AI changes the unit economics overnight — because for the first time, a machine can do at 9am what a court process needs six months to deliver.

You are not building a toy. You are building the thing that decides whether a €3 billion portfolio returns 40% or 70%.

That is real money, moved by your code, in 24 hours.

Let's go.

### How judging actually works

A 2-minute demo at the end is a terrible way to evaluate 24 hours of work. A great builder with a rough pitch loses to a mediocre builder who rehearsed. We're not doing that.

Instead, I'll be on the floor throughout the hackathon. Expect me to swing by your team every few hours — short conversations, not formal check-ins.

What that means for you:

Share your git repo with me at the start. I'll follow commits as you go. How you build matters as much as what you ship.

My github

: AlenTadevosyan

Be ready to walk me through your latest work whenever I stop by. No slides needed — just open the code and talk me through what you did and why.

Tell me what's hard. What you tried that didn't work is often more interesting than what did. Honesty beats polish.

Surprise me. If you find something in the dataset we didn't flag, or approach the problem in a way we didn't expect, say so. That's the signal we're looking for.

The final demo still happens and still matters. But by then, I'll already know who built what. The demo is your chance to tell the story — not prove the work.