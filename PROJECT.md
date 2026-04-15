# Nordés — Debt Intelligence Agent

> Turn silence into a decision. Turn a name into a case somebody knows how to work.

**Hackathon:** Vexor × Project Europe — Barcelona
**Track:** The Last Human Industry (Debt Collection)
**Prize:** F1 Grand Prix Barcelona tickets + 2-week sprint building inside Vexor's platform

---

## The Problem

A debt servicer buys 50,000 delinquent accounts. From day one, value bleeds. The reality:

- **71% of calls never reach the debtor** — wrong number, voicemail, rings out
- **73% of legal asset reports find nothing seizable**
- A collector picks up the phone with zero context and zero leverage
- Someone says "I have no money, I can't pay" — the collector has no way to challenge that
- Courts take 6 months to return what an AI could find in 6 minutes

**The money is in the information you don't have.**

---

## Our Solution

An AI agent that takes minimal starting information (name, country, maybe a phone or address) and builds an **actionable intelligence dossier** — enough context that a collector picks up the phone with a real angle.

The agent doesn't predict. It **investigates**.

### Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    INPUT (CSV Row)                    │
│  case_id, country, debt_eur, debt_origin,            │
│  debt_age_months, call_attempts, call_outcome,       │
│  legal_asset_finding                                 │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│              ENRICHMENT ORCHESTRATOR                 │
│         (AI Agent — Claude / LLM backbone)           │
│                                                      │
│  Decides which sources to query based on:            │
│  - Country (legal frameworks differ)                 │
│  - Available PII                                     │
│  - Cost/benefit of each lookup                       │
│  - What's already known                              │
└──┬──────────┬──────────┬──────────┬─────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌──────────────┐
│ OSINT│ │  RRSS  │ │  Clay  │ │ Public       │
│ Core │ │ Social │ │ Enrich │ │ Registries   │
└──┬───┘ └───┬────┘ └───┬────┘ └──────┬───────┘
   │         │          │             │
   ▼         ▼          ▼             ▼
┌─────────────────────────────────────────────────────┐
│              INTELLIGENCE SYNTHESIS                  │
│                                                      │
│  - Cross-reference findings                          │
│  - Confidence scoring per claim                      │
│  - Source attribution (every fact traceable)          │
│  - Gap identification (what we DON'T know)           │
│  - Suggested negotiation angle                       │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│                  OUTPUT: DOSSIER                      │
│                                                      │
│  Structured profile + recommended action +           │
│  confidence level + source citations                 │
└─────────────────────────────────────────────────────┘
```

---

## Enrichment Lines (Research Areas)

### 1. Login / Account Existence Checkers

Check if an email/phone is registered on various platforms. This reveals digital footprint without accessing any account.

| Technique | What it reveals | Tools/APIs |
|-----------|----------------|------------|
| Email enumeration | Platform presence (LinkedIn, Facebook, Twitter, Instagram, etc.) | Holehe, Maigret, custom checkers |
| Phone lookup | Messaging apps (WhatsApp, Telegram, Viber), carrier info | WhatsApp Business API check, Telegram API |
| Username OSINT | Cross-platform identity linking | Sherlock, Maigret, WhatsMyName |

**Value for debt collection:** If someone claims unemployment but has an active LinkedIn profile showing current employment — that's leverage.

### 2. Social Media Profile Analysis (RRSS)

Public profile data reveals lifestyle, employment, assets, and location.

| Signal | What it indicates | Source |
|--------|-------------------|--------|
| Current employer in bio/profile | Employment status, income estimation | LinkedIn, Facebook, Instagram |
| Location tags, check-ins | Current address, travel patterns | Instagram, Facebook |
| Lifestyle indicators | Spending capacity (cars, vacations, properties) | Instagram, TikTok, Facebook |
| Business pages/profiles | Self-employment, unreported income | Facebook, Instagram, Google Business |
| Recent activity timestamps | Whether profile is active/current | Any platform |
| Connections/followers | Network mapping for locating through relatives | Facebook, LinkedIn |

**Value:** A debtor who says "I can't pay" but posts vacation photos from Maldives has a credibility problem.

### 3. Clay.com Enrichment (Waterfall)

Clay aggregates 75+ data providers in a single API call. Relevant enrichments:

| Provider Category | Data Points | Providers in Clay |
|-------------------|-------------|-------------------|
| Contact info | Verified email, phone, address | Clearbit, Apollo, Hunter, Lusha |
| Employment | Current company, title, tenure | LinkedIn enrichment, Apollo, PDL |
| Company data | Revenue, size, funding, tech stack | Clearbit, HG Insights, Crunchbase |
| Social profiles | All linked social accounts | FullContact, People Data Labs |
| Demographics | Age, education, location history | People Data Labs |

**Value:** One API call to Clay can return a complete professional profile from just a name + company or email.

### 4. Public Registries & Legal Data

Varies by country — this is where country-specific logic matters most.

| Country | Registry | What it reveals |
|---------|----------|-----------------|
| ES | Registro Mercantil, BOE, BORME | Company ownership, directorships, insolvency filings |
| PT | Portal da Justiça, Registo Comercial | Company roles, property (Conservatória) |
| IT | Registro Imprese, Visura Camerale | Company participation, UBO |
| DE | Handelsregister, Unternehmensregister | Company ownership, Grundbuch (property) |
| FR | Infogreffe, Societe.com, BODACC | Company roles, legal proceedings |
| PL | KRS (Krajowy Rejestr Sądowy) | Company registry, financial filings |
| NL | KvK (Kamer van Koophandel) | Company ownership |
| DK | CVR (Det Centrale Virksomhedsregister) | Company data, free API |
| BE | KBO/BCE (Kruispuntbank) | Company registry |

**Value:** If legal asset reports find "no assets," but the debtor is a director of 3 companies in the Registro Mercantil, the asset report missed something.

### 5. Data Breach Databases (HIBP + others)

Check if an email/phone appears in known breaches. **Not to access data, but to confirm identity.**

| What it reveals | How it helps |
|-----------------|-------------|
| Email confirmed as belonging to person | Validates contact info |
| Services the person uses | Digital footprint mapping |
| Associated usernames | Cross-platform identity linking |
| Historical addresses from old breaches | Alternative contact addresses |

**Tool:** Have I Been Pwned API (ethical, legal, widely used in security).

### 6. Family & Network Mapping

When the debtor is unreachable, finding connected people can help locate them.

| Technique | Source |
|-----------|--------|
| Shared surname + location search | Social media, public records |
| Facebook family connections (if public) | Facebook graph |
| LinkedIn connections from same company | LinkedIn |
| Property co-ownership records | Land registries |
| Company co-directorships | Business registries |

**Value:** 17% of calls in the dataset reach a "relative" — family network mapping can be systematic instead of accidental.

### 7. Automated Public Records Requests

Some European jurisdictions allow automated queries to public databases.

| Type | Countries | How |
|------|-----------|-----|
| Company director lookups | All EU via OpenCorporates API | API |
| Property registry checks | Varies (some have APIs) | Web scraping / API |
| Court records / insolvency | Varies | ECLI search, national portals |
| Vehicle registries | Limited public access | Varies by country |
| Professional license lookups | Most EU countries | National regulator websites |

---

## Judging Criteria (What Vexor Cares About)

They are **NOT** judging accuracy. 24h is not enough for a perfect pipeline.

They **ARE** judging:

1. **Relevance of signals found** — is this what a real collector could use?
2. **Defensibility of sources** — every claim traceable. No hallucinations. No guessing.
3. **Reasoning transparency** — can they see WHY the agent concluded X?
4. **Honesty about gaps** — if nothing was found, say so. Don't fabricate.

### Implications for our build:
- Source attribution is non-negotiable. Every fact needs a URL or API response citation.
- The agent must distinguish between "confirmed" vs "possible" vs "not found."
- Saying "nothing found for this person" is better than inventing a profile.
- The reasoning chain should be visible (chain-of-thought or decision log).

---

## Dataset Summary

100 anonymized cases. Distribution-matched to real data (~5,000 calls + real asset reports).

| Dimension | Breakdown |
|-----------|-----------|
| **Countries** | PT (40), ES (15), IT (12), DE (10), PL (8), FR (6), NL (4), DK (3), BE (2) |
| **Debt origins** | Credit card (25), Telecom (20), Personal loan (18), Consumer loan (12), Utility (10), Auto loan (8), SME loan (5), Mortgage shortfall (2) |
| **Call outcomes** | Rings out (37), Not debtor (17), Invalid number (17), Voicemail (10), Denies identity (5), Relative (4), Busy (4), Other (6) |
| **Asset findings** | No assets found (43), Not seizable (30), Not initiated (7), Bank account (7), Employment income (6), Pension (3), Vehicle (2), Multiple (2) |

**Key insight:** The dataset is anonymized — no real names. For the demo, we use our own names or public figures to show the pipeline working end-to-end.

---

## Tech Stack (Proposed)

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent orchestration | Claude API (Anthropic) | Best reasoning, tool use, chain-of-thought |
| Data enrichment | Clay API | Waterfall enrichment, 75+ providers |
| OSINT toolkit | Holehe, Sherlock, Maigret | Email/username/phone enumeration |
| Public registries | OpenCorporates API + scrapers | Company/director lookups across EU |
| Breach check | HIBP API | Email validation, service enumeration |
| Social media | Platform-specific scrapers/APIs | Profile data extraction |
| Frontend | Streamlit or simple web UI | Quick demo interface |
| Backend | Python | Fastest for hackathon prototyping |

---

## MVP Scope (24h)

### Must have
- [ ] Agent that takes a name + country and runs enrichment pipeline
- [ ] Clay enrichment integration
- [ ] At least 2-3 OSINT sources (login checkers, social media, business registries)
- [ ] Structured output with source citations for every claim
- [ ] Confidence scoring (confirmed / probable / uncertain)
- [ ] Honest gap reporting
- [ ] Demo on 2-3 real cases (own names)

### Nice to have
- [ ] Country-specific registry lookups
- [ ] Family/network mapping
- [ ] Prioritization score (which cases to work first based on enrichment results)
- [ ] Batch processing of the full CSV
- [ ] Suggested negotiation angle per case
- [ ] Cost tracking (how much each enrichment costs vs. debt value)

### Out of scope
- Credit scoring / payment prediction models
- Actual debt collection automation
- Compliance/GDPR framework (mention in demo, don't build)

---

## Legal & Ethical Considerations

Everything we use must be from **public sources** or **legitimate APIs**:

- OSINT from publicly available profiles (not hacked/leaked personal data)
- Business registries are public by law in EU
- HIBP is a legitimate security service
- Clay aggregates public and commercially available data
- No accessing private accounts, no social engineering, no unauthorized data access

For the demo, emphasize: "Every fact is traceable to a public source. The agent cannot fabricate."

---

## Team Notes

- **Hackathon name:** Nordés
- **Judge:** ArlenTadevosyan (Vexor) — will check git commits throughout, not just final demo
- **Demo format:** 2-minute final demo, but judge visits throughout — be ready to walk through code anytime
- **Share git repo at start**
