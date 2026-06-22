import type { BlogPost } from '../blog';

// Cluster: Open-source, self-hosting, privacy, BYOK & local LLM
export const batch4: BlogPost[] = [
  {
    slug: 'self-host-rereflect-docker-compose',
    title: 'Self-Hosting Rereflect With Docker Compose',
    excerpt:
      'Rereflect ships as a set of Docker images that run together under a single docker-compose.yml. This guide walks through the full setup: cloning the repo, writing your .env file, starting the stack, and confirming everything is healthy — no cloud accounts required.',
    date: '2026-10-01',
    status: 'scheduled',
    readTime: '9 min read',
    author: 'Rereflect Team',
    tags: ['Self-Hosting', 'Docker', 'DevOps', 'Open Source', 'Getting Started'],
    seoTitle: 'Self-Hosting Rereflect With Docker Compose | Rereflect',
    seoDescription:
      'Step-by-step guide to self-hosting Rereflect using Docker Compose. Covers cloning, environment variables, starting the stack, and verifying a healthy deployment — no cloud accounts needed.',
    sections: [
      {
        heading: 'What you are actually running',
        content: [
          'Rereflect is made up of four services that cooperate through a shared network: the Next.js frontend, the FastAPI backend, a Celery worker that processes background jobs, and a Redis broker that connects them. PostgreSQL stores everything durable. All five pieces are described in a single docker-compose.yml that ships with the repository.',
          'Docker Compose handles starting these in the right order, wiring the internal DNS so they can reach each other by name, and giving you a single command to bring the whole stack up or down. If you have Docker Desktop or the Docker Engine plus the Compose plugin installed, you already have everything you need.',
        ],
        listItems: [
          'frontend — Next.js 16 app, listens on port 3000.',
          'backend-api — FastAPI server, listens on port 8000.',
          'worker — Celery worker, no external port, reads from Redis.',
          'redis — Broker for background tasks, listens on port 6379 (internal).',
          'db — PostgreSQL 16, listens on port 5432 (internal by default).',
        ],
      },
      {
        heading: 'Environment variables you need to set',
        content: [
          'Before starting the stack you need a .env file. The repository includes a .env.example with every supported variable and a comment describing each one. The mandatory ones for a minimal deployment are small in number.',
          'The two most important values are SECRET_KEY and LLM_ENCRYPTION_KEY. SECRET_KEY signs JWT tokens for your users — generate it with a secure random generator and keep it secret. LLM_ENCRYPTION_KEY encrypts any LLM API keys your users store in the app — it must be exactly 32 bytes encoded as URL-safe base64. Set SELF_HOSTED=true so the app does not try to call Rereflect\'s own backend for licence checks.',
        ],
        listItems: [
          'SECRET_KEY — random string used to sign JWT sessions. Generate with: python -c "import secrets; print(secrets.token_hex(32))"',
          'LLM_ENCRYPTION_KEY — 32-byte base64 key for encrypting stored LLM credentials. Generate with: python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"',
          'SELF_HOSTED=true — required flag that enables the self-hosted mode and disables cloud licence checks.',
          'DATABASE_URL — PostgreSQL connection string. The compose file sets a default using the bundled db service; override it to point at an external database.',
          'REDIS_URL — Redis connection string. Defaults to the bundled Redis container; override for an external broker.',
        ],
        content2: [
          'LLM configuration is optional at this stage. Without it, Rereflect uses VADER for local sentiment analysis. You can add an LLM key later through the settings UI once the stack is running.',
        ],
      },
      {
        heading: 'Starting the stack',
        content: [
          'Once your .env file is in place, bringing up Rereflect is a single command from the repository root. Docker Compose will pull the images on first run, then start each service in dependency order.',
          'A few things to watch for on first start: the backend runs Alembic migrations automatically before accepting traffic, so there will be a brief pause before the API responds. The Celery worker waits for Redis to be ready before it starts consuming jobs, which Compose handles through a health check in the compose file. If either service logs a connectivity error in the first ten seconds, that is normal startup sequencing — wait for everything to settle.',
        ],
        listItems: [
          'docker compose up -d — starts all services detached.',
          'docker compose logs -f backend-api — stream backend logs to watch migration progress.',
          'docker compose ps — confirm all services are in state "running" or "healthy".',
          'docker compose down — stops and removes containers but preserves volumes (your data survives).',
          'docker compose down -v — stops everything and deletes volumes (full reset, data is gone).',
        ],
        content2: [
          'After the stack is healthy, open http://localhost:3000 in a browser. You should see the Rereflect signup page. Create your first account — the first registered user becomes the owner of the initial organization.',
        ],
      },
      {
        heading: 'Exposing Rereflect to the internet',
        content: [
          'By default the stack only binds to localhost. To reach it from other machines — or to serve it publicly — you need a reverse proxy in front of the frontend and API. Nginx, Caddy, and Traefik all work well. The key points: proxy :3000 for the frontend, proxy :8000 for the API (or configure the API_URL environment variable in the frontend to point directly at a public API address), and terminate TLS at the proxy layer.',
          'If you are running on a server with a domain, Caddy handles TLS certificate provisioning automatically with a minimal configuration. Nginx is a reasonable choice if you are comfortable writing server blocks. The compose file does not force either choice — pick whichever fits your existing infrastructure.',
        ],
        listItems: [
          'Do not expose PostgreSQL or Redis ports publicly — they are internal services.',
          'Set CORS_ORIGINS in your .env to match the domain(s) the frontend will be served from.',
          'If using Caddy, a two-directive Caddyfile with reverse_proxy to the respective ports is sufficient for HTTPS on a domain you control.',
        ],
      },
      {
        heading: 'Keeping the stack updated',
        content: [
          'Rereflect is open source and ships new versions as tagged Docker images. To update, pull the new images and restart the stack. Alembic migrations run automatically on restart, so schema changes apply without a manual step.',
          'The safe update sequence is: pull new images, stop the stack, bring it back up. Because Alembic migrations are transactional, an interrupted update leaves the database in its previous valid state. Read the release notes before updating if a release includes a note about breaking migrations or required manual steps.',
          'Pinning image tags in your compose file (rather than using latest) gives you explicit control over when you take updates and lets you roll back by editing a single line.',
        ],
      },
    ],
  },
  {
    slug: 'own-your-customer-feedback-data',
    title: 'Why Owning Your Customer Feedback Data Actually Matters',
    excerpt:
      'Every piece of customer feedback you collect belongs to your users, and to you — but when you send it to a SaaS tool backed by a third-party AI, control quietly transfers. This post looks at what data ownership means in practice, and why self-hosting changes the equation.',
    date: '2026-10-04',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['Data Privacy', 'Self-Hosting', 'Open Source', 'Compliance'],
    seoTitle: 'Why Owning Your Customer Feedback Data Actually Matters | Rereflect',
    seoDescription:
      'Customer feedback data is sensitive. Understand the practical difference between SaaS data custody and true data ownership with a self-hosted tool like Rereflect.',
    sections: [
      {
        heading: 'What customers write in feedback forms',
        content: [
          'Customer feedback is not abstract data. It is specific: "The billing page charged me twice for the same seat," "I had to reset my password three times and then gave up," "Your API rate limits are blocking us from migrating off a competitor." That level of specificity is what makes feedback valuable — and what makes it sensitive.',
          'A single support ticket can contain a customer\'s name, their organization, the plan they are on, a complaint about a specific transaction, and a frustration that signals churn risk. Aggregated across thousands of users, a feedback database reveals which features are failing, which cohorts are unhappy, and where the product is losing people to competitors. That is commercially valuable — which means it is worth protecting.',
        ],
      },
      {
        heading: 'What happens when you send feedback to a SaaS tool',
        content: [
          'The standard SaaS model is: you send feedback text to the tool via API or CSV, the tool processes it (often by sending subsets to a third-party LLM API), and you get back categorized results. The tool stores the raw text and the derived data in its own database, under its own data retention and access control policies.',
          'In practice, this means at minimum two third parties have a copy of your customer feedback: the SaaS tool and whatever AI provider the tool uses for analysis. The SaaS tool\'s terms determine how long they keep it, whether they use it for model training, and what happens to it if the company is acquired. The AI provider\'s terms add a second set of retention and usage rules.',
          'None of this is necessarily malicious. But it does mean you have accepted a set of terms governing your customers\' data that your customers themselves did not consent to — and that you may need to disclose in your own privacy policy.',
        ],
      },
      {
        heading: 'What self-hosting actually changes',
        content: [
          'When you self-host Rereflect, the feedback text stays in your PostgreSQL database, on your infrastructure, in whatever region you choose. The analysis that Rereflect runs — sentiment scoring, pain point detection, urgency flagging — runs against a model you configure, using credentials you own. Nothing flows to a Rereflect server.',
          'If you use a hosted LLM key (OpenAI, Anthropic, etc.), the feedback text does flow to that provider when it is analyzed. If you use a local model via Ollama or another OpenAI-compatible runtime, even that is eliminated. The VADER fallback removes the LLM call entirely for sentiment analysis.',
          'The practical result is that you can draw a clear, honest line in your privacy policy: "Customer feedback is stored on our own infrastructure and processed locally." That is a statement many SaaS tools cannot truthfully make.',
        ],
      },
      {
        heading: 'Ownership is also about access and deletion',
        content: [
          'Data ownership is not only about where data is stored. It is also about whether you can access it, query it freely, and delete it completely. With a SaaS tool, deletion is typically "submit a request and we will process it within N days." Export is typically "download a CSV of what we decide to expose in our export UI."',
          'With a self-hosted Rereflect, your PostgreSQL database is your database. You can run any query, export in any format, and delete individual records or the entire dataset whenever you want. There is no intermediary to ask permission from, and no retention window you have to wait out.',
          'For teams operating under GDPR, CCPA, or contractual data processing agreements with enterprise customers, this is not a nice-to-have. It is the difference between being able to honour a deletion request and having to explain to a customer why their data is still sitting in a third-party system.',
        ],
      },
      {
        heading: 'The honest trade-offs',
        content: [
          'Self-hosting means you are responsible for the infrastructure: backups, uptime, upgrades, and security configuration. A managed SaaS tool handles those things for you in exchange for custody of your data. That is a legitimate trade-off, and different teams will land in different places.',
          'What matters is that the choice is explicit. If you have decided a managed tool is fine and you have read and understood its data handling terms, that is a reasonable decision. What is harder to justify is choosing a managed tool without having thought through what happens to the feedback data that flows through it.',
          'Rereflect is open source and MIT-licensed. You can read every line of code that processes your feedback. If you decide to self-host, the full deployment tooling is in the repository. If you decide a managed setup fits your situation better, you have made that decision with eyes open.',
        ],
      },
    ],
  },
  {
    slug: 'air-gapped-feedback-analysis-private',
    title: 'Running Rereflect in a Fully Air-Gapped Environment',
    excerpt:
      'Some teams cannot allow any outbound traffic from their analysis infrastructure — regulated industries, government contractors, or high-security environments. Rereflect can run completely air-gapped using the built-in VADER analyzer or a locally hosted model. Here is how to set it up.',
    date: '2026-10-07',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Air-Gapped', 'Privacy', 'Self-Hosting', 'Security', 'Compliance'],
    seoTitle: 'Running Rereflect in a Fully Air-Gapped Environment | Rereflect',
    seoDescription:
      'Deploy Rereflect with zero outbound network traffic. Use the built-in VADER fallback or a local LLM to analyze customer feedback in a fully air-gapped or network-restricted environment.',
    sections: [
      {
        heading: 'When air-gapped actually means air-gapped',
        content: [
          'Some security environments enforce strict outbound network controls — no traffic to external APIs, no calls to CDN-hosted dependencies, no model inference shipped off-box. This is common in government, defence, and heavily regulated industries such as healthcare or finance where data classification rules prohibit sending any customer-derived text to a public cloud endpoint.',
          'Most AI feedback tools are not compatible with this requirement because they are architecturally dependent on calling a third-party LLM API. Rereflect is different because the LLM step is optional. The product can run its entire analysis pipeline locally, with no outbound calls beyond what you explicitly configure.',
        ],
      },
      {
        heading: 'What generates outbound traffic in a default setup',
        content: [
          'Before you can lock things down, it helps to know what would call home in a permissive configuration. In a default Rereflect self-hosted deployment, there are three potential sources of outbound traffic: the Docker image pulls during initial setup, the LLM API calls if you have configured a hosted provider, and any telemetry or update-check calls if a tool in the stack makes them.',
          'The first — image pulls — is a one-time setup step you can handle by pre-pulling images on a networked machine and saving them as archives, then loading them on the air-gapped host. The second is the important one: if you configure an LLM API key pointing at a hosted provider, every piece of feedback that runs through the LLM step generates an outbound HTTPS request. The third is not a concern — Rereflect does not phone home and does not bundle any telemetry.',
        ],
        listItems: [
          'Docker image pulls — handle with docker save / docker load on the target host.',
          'LLM API calls — eliminated by using a local model or the VADER fallback.',
          'Rereflect telemetry — does not exist; the app makes no calls back to Rereflect servers.',
        ],
      },
      {
        heading: 'Option 1: VADER-only mode (fully local, zero model dependencies)',
        content: [
          'The simplest air-gapped configuration is to not configure an LLM at all. When no LLM_BASE_URL is set in your environment, Rereflect automatically uses the VADER sentiment analyzer for all feedback. VADER is a lexicon-based analyzer that runs in-process — it has no GPU requirements, no model files to download, and generates no network traffic.',
          'In VADER-only mode you get reliable sentiment scoring (positive, neutral, negative) on every piece of feedback. The LLM-driven steps — nuanced pain point categorisation, feature request extraction, urgency reasoning — are not available in their full form. For teams whose primary need is understanding sentiment distribution across large feedback volumes, VADER-only is often sufficient and gets to a working deployment in minutes.',
        ],
        listItems: [
          'Set SELF_HOSTED=true and configure SECRET_KEY and LLM_ENCRYPTION_KEY.',
          'Leave LLM_BASE_URL unset.',
          'Start the stack normally — VADER runs automatically as the fallback.',
          'No GPU, no model weights, no outbound traffic.',
        ],
      },
      {
        heading: 'Option 2: Local LLM via Ollama or a compatible server',
        content: [
          'If you need the full LLM-driven analysis pipeline in an air-gapped environment, the path is to run a model locally alongside Rereflect using a server that exposes an OpenAI-compatible API. Ollama is the most common choice; llama.cpp server and LM Studio are alternatives that expose the same interface.',
          'The workflow for an air-gapped host: pull the model weights and the Ollama binary on a networked machine, transfer them to the air-gapped host (or mount from internal storage), start Ollama, and set LLM_BASE_URL in Rereflect\'s environment to point at the local Ollama endpoint. Because the endpoint is OpenAI-compatible and local, no API key is needed.',
          'The choice of model affects analysis quality. A 7B-parameter model running on a CPU will be slower and less accurate than a 70B model on a machine with GPU. In practice, for routine sentiment and category classification on short feedback texts, a capable 7B model performs well enough for most production use cases.',
        ],
        listItems: [
          'Transfer model weights and runtime to the air-gapped host via approved media or internal repository.',
          'Start the local model server (e.g., ollama serve).',
          'Set LLM_BASE_URL to the local endpoint and LLM_MODEL to the model name.',
          'Leave LLM_API_KEY unset or set to a placeholder — local servers do not authenticate.',
          'All analysis now runs on the local host; no outbound traffic.',
        ],
      },
      {
        heading: 'Network policy recommendations',
        content: [
          'Even if you intend to run fully locally, defence-in-depth suggests enforcing the restriction at the network layer rather than relying on configuration alone. Running Rereflect in a network namespace with no default route, or behind a firewall rule that blocks all outbound traffic from the container network, ensures that a misconfiguration cannot silently start sending feedback to an external API.',
          'The specific egress rules depend on your environment. At minimum, block all traffic from the Rereflect containers to the public internet. If you allow internal-network traffic, restrict Rereflect to only the hosts it legitimately needs to reach: your PostgreSQL instance, your Redis instance, and your local LLM server if you are running one.',
          'Rereflect logs every LLM call — base URL, model, and completion status — at debug level. Review those logs periodically to confirm traffic is going where you expect.',
        ],
      },
    ],
  },
  {
    slug: 'byok-llm-keys-explained',
    title: 'BYOK Explained: How Rereflect Uses Your LLM Keys',
    excerpt:
      'BYOK — bring your own key — is a simple idea: you supply the API credential, you pay the provider directly, and no AI markup goes through Rereflect. This post explains exactly how Rereflect stores and uses your LLM key, which providers work, and what happens when no key is configured.',
    date: '2026-10-10',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['BYOK', 'AI', 'Privacy', 'Self-Hosting', 'LLM'],
    seoTitle: 'BYOK Explained: How Rereflect Uses Your LLM Keys | Rereflect',
    seoDescription:
      'Understand exactly how Rereflect\'s bring-your-own-key (BYOK) model works: key storage with AES encryption, which LLM providers are supported, per-request usage, and the no-key VADER fallback.',
    sections: [
      {
        heading: 'What BYOK means in Rereflect',
        content: [
          'Many AI SaaS tools include a hosted AI backend as part of the subscription. You pay them; they call a model provider on your behalf, mark up the cost, and the bill is bundled into your seat price. There is nothing wrong with this model, but it means you do not choose the provider, you cannot audit what gets sent to the model, and you are paying a markup on compute that is hidden in the subscription price.',
          'Rereflect does not work that way. There is no Rereflect AI backend. If you want LLM-powered analysis — sentiment with nuance, pain point extraction, feature request tagging, urgency reasoning — you configure a key from a provider you have signed up with directly. Rereflect calls that provider\'s API on your behalf using your credential. You pay the provider at their published rates. Rereflect adds no markup.',
          'This is what BYOK means in practice: the model provider relationship is between you and them, not mediated or marked up by Rereflect.',
        ],
      },
      {
        heading: 'How Rereflect stores your key',
        content: [
          'When you enter an API key through the settings UI, Rereflect encrypts it before writing it to the database. The encryption uses AES-256-GCM with a key you supply through the LLM_ENCRYPTION_KEY environment variable when you start the stack. This is a 32-byte secret that lives on your infrastructure — Rereflect never sees it, because Rereflect never runs the stack for you.',
          'At analysis time, the worker retrieves the encrypted key, decrypts it in memory using LLM_ENCRYPTION_KEY, and passes it in the Authorization header of the LLM API request. The decrypted key is never written to disk or logged. After the request completes, the in-memory credential is discarded.',
          'If someone extracts the database without also having LLM_ENCRYPTION_KEY, they get the ciphertext but not a usable key. Protecting LLM_ENCRYPTION_KEY is therefore important — treat it like a master secret, store it in a secrets manager if you have one, and rotate it if you believe it has been compromised.',
        ],
        listItems: [
          'Keys are encrypted with AES-256-GCM before database storage.',
          'LLM_ENCRYPTION_KEY lives only on your infrastructure and is never sent to Rereflect.',
          'Decryption happens in memory, at request time, in the Celery worker.',
          'The decrypted key is not logged, not written to disk, and not held beyond the request lifecycle.',
        ],
      },
      {
        heading: 'Which providers work',
        content: [
          'Rereflect uses the OpenAI-compatible API format for all LLM calls. Any provider that exposes an OpenAI-compatible endpoint works — you configure a base URL and a model name alongside the key.',
          'Providers known to work include OpenAI (gpt-4o, gpt-4o-mini, o3-mini), Anthropic (via their OpenAI-compatible endpoint), Google Gemini (via the OpenAI-compatible shim), Groq, Together AI, and any local runtime that speaks the same API format: Ollama, llama.cpp server, LM Studio, vLLM.',
          'For local runtimes, the key field can be left blank or set to a placeholder string — local servers typically do not authenticate and will accept or ignore the Authorization header.',
        ],
        table: {
          headers: ['Provider', 'Key required', 'Base URL needed'],
          rows: [
            ['OpenAI', 'Yes', 'No (uses default)'],
            ['Anthropic (OpenAI-compatible endpoint)', 'Yes', 'Yes'],
            ['Groq', 'Yes', 'Yes'],
            ['Together AI', 'Yes', 'Yes'],
            ['Ollama (local)', 'No', 'Yes (localhost)'],
            ['llama.cpp server (local)', 'No', 'Yes (localhost)'],
            ['vLLM (local)', 'Optional', 'Yes'],
          ],
        },
      },
      {
        heading: 'What each analysis call sends to the model',
        content: [
          'Understanding what is in the LLM request helps you make an informed decision about which provider to use. When Rereflect analyzes a piece of feedback, it constructs a prompt that contains: the feedback text itself, the analysis task description (classify sentiment, extract pain points, etc.), and any custom category definitions you have configured.',
          'The prompt does not include other customers\' feedback, account details beyond what you have added to the item, or internal system data. The scope is: this text, this task. You can inspect the exact prompt templates in the open-source codebase if you want to audit precisely what is sent.',
        ],
      },
      {
        heading: 'The no-key fallback',
        content: [
          'If you do not configure any LLM key, Rereflect falls back to VADER for sentiment analysis. VADER runs entirely in-process, makes no network calls, and has no dependency on an external provider. You get sentiment scores on every piece of feedback from day one — the more advanced LLM steps are available when you add a key later.',
          'This means you can evaluate Rereflect on your real data before committing to an LLM provider or signing up for any API account. Start with VADER, verify the ingestion pipeline works and the UI makes sense for your team, then add a key when you are ready for deeper analysis.',
        ],
      },
    ],
  },
  {
    slug: 'local-llm-cost-savings-feedback-analysis',
    title: 'The Real Cost of Analyzing Feedback With a Local LLM',
    excerpt:
      'Running a local model for feedback analysis eliminates per-token API costs. But local inference has its own costs — hardware, latency, and quality trade-offs. This post breaks down where local LLMs save money and where you pay in other ways.',
    date: '2026-10-13',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Local LLM', 'Cost', 'Self-Hosting', 'AI', 'Performance'],
    seoTitle: 'The Real Cost of Analyzing Feedback With a Local LLM | Rereflect',
    seoDescription:
      'Local LLMs eliminate API bills but come with hardware and quality trade-offs. A practical breakdown of the cost structure for running feedback analysis with Rereflect and a local model.',
    sections: [
      {
        heading: 'What you stop paying for',
        content: [
          'The most obvious benefit of running a local model is the elimination of per-token API costs. LLM providers charge per token — input tokens for the prompt and output tokens for the completion. A typical feedback analysis prompt (the feedback text plus task instructions) might be a few hundred input tokens, with a completion of a hundred or two hundred tokens.',
          'At published rates for capable frontier models, this is a small amount per item — fractions of a cent. But across thousands of items per month, and if you are re-analyzing feedback as categories or prompts evolve, the per-token cost accumulates. Moving to a local model replaces a recurring API bill with the fixed cost of whatever hardware runs the model.',
        ],
      },
      {
        heading: 'What you start paying for instead',
        content: [
          'Local inference is not free — it is a different cost structure. The main categories are hardware (purchase or rental), electricity, and maintenance overhead.',
          'If you are running a model on existing hardware — a developer workstation with a capable GPU, or a server that already runs other workloads — the incremental cost is primarily electricity. A GPU running inference at moderate utilization uses meaningful wattage, but spread across a high volume of analysis jobs the per-item electricity cost is negligible.',
          'If you need to purchase or rent dedicated hardware for the model, that upfront or monthly cost needs to be weighed against the API bill you are avoiding. The break-even calculation depends on your feedback volume, the model you would use via API, and the hardware cost in your context.',
        ],
        listItems: [
          'Existing hardware with idle GPU — primarily electricity cost, often near-zero per analysis item.',
          'Dedicated GPU server (rented) — fixed monthly cost; compare against expected API token spend.',
          'CPU-only inference — runs on commodity hardware but is significantly slower; works for low-volume use cases.',
          'Cloud VM with GPU — shifts from a per-token model to a per-hour model; may or may not be cheaper depending on volume.',
        ],
      },
      {
        heading: 'Quality trade-offs at different model sizes',
        content: [
          'Not all local models are equal. The practical consideration for feedback analysis is that quality degrades as you move to smaller models, and smaller models are typically what run on commodity hardware without a powerful GPU.',
          'For feedback analysis specifically — sentiment classification, pain point categorisation, feature request tagging — the task is structured and relatively constrained compared to open-ended generation. A capable 7B or 13B model with a well-written prompt performs reliably on clear, unambiguous feedback. It will make more errors on sarcastic feedback, domain-specific jargon, or feedback in languages it was not trained heavily on.',
          'The honest position: a 70B model running locally matches or approaches frontier hosted model quality on these tasks. A 7B model is meaningfully weaker but often good enough for the majority of your feedback volume. The VADER fallback is weaker still but handles high-volume sentiment tracking well. Which tier you need depends on how much your downstream decisions rely on the classifications being correct.',
        ],
        table: {
          headers: ['Setup', 'Hardware required', 'API cost', 'Analysis quality'],
          rows: [
            ['VADER (built-in fallback)', 'Any CPU', 'None', 'Sentiment only; fast and reliable'],
            ['Local 7B model (Ollama)', 'Moderate GPU or fast CPU', 'None', 'Good for clear feedback; weaker on edge cases'],
            ['Local 70B model (Ollama)', 'High-end GPU (24GB+ VRAM)', 'None', 'Near-frontier on structured analysis tasks'],
            ['Hosted API (OpenAI, Anthropic)', 'None (your server)', 'Per-token', 'Frontier quality; provider retention terms apply'],
          ],
        },
      },
      {
        heading: 'Latency: the hidden cost',
        content: [
          'Local models are often slower than hosted APIs, depending on your hardware. A frontier hosted API returns a response in one to three seconds for a typical feedback prompt. A local 7B model on a CPU might take ten to thirty seconds. A local 70B model on a good GPU might take three to eight seconds.',
          'For Rereflect this is less critical than it would be for a real-time user-facing app — analysis runs in background Celery jobs, so a user uploading a CSV of feedback is not waiting for each item to process synchronously. The feedback is queued, processed, and the dashboard updates as results come in. Slower inference means the dashboard reflects results later, not that the user experiences a hang.',
          'If you are processing very high volumes (tens of thousands of items) on a slow local model, the queue will take longer to drain. Right-size your model to your volume and hardware, or use the hosted API path for bursts.',
        ],
      },
      {
        heading: 'Making the decision',
        content: [
          'The clearest case for a local model is when privacy requirements rule out sending feedback to a cloud API, and you have hardware that can run a capable model without a significant new cost. In that case, you get privacy and zero API cost at the price of some quality degradation relative to frontier models.',
          'The clearest case for a hosted API is when you want the highest analysis quality with no hardware management, and your data handling terms permit sending feedback to the provider. You pay per token but avoid the operational overhead of running a model.',
          'The VADER fallback is the right starting point for any team: it costs nothing, requires no configuration beyond the base stack, and gives you working sentiment data immediately. Graduate to a local or hosted model when you need the deeper categorisation that VADER does not provide.',
        ],
      },
    ],
  },
  {
    slug: 'open-source-vs-saas-feedback-tools',
    title: 'Open-Source vs. SaaS Feedback Tools: An Honest Comparison',
    excerpt:
      'Self-hosted open-source feedback analysis tools and managed SaaS products are not just price-different — they involve different trade-offs in control, maintenance, and trust. Here is a clear-eyed comparison without a sales pitch.',
    date: '2026-10-16',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Open Source', 'Self-Hosting', 'Product', 'Decision-Making'],
    seoTitle: 'Open-Source vs. SaaS Feedback Tools: An Honest Comparison | Rereflect',
    seoDescription:
      'A practical comparison of self-hosted open-source and managed SaaS feedback analysis tools — covering data control, cost, maintenance burden, and when each model makes sense.',
    sections: [
      {
        heading: 'The actual differences',
        content: [
          'The open-source vs. SaaS distinction is sometimes treated as only a pricing question. It is not. Price is one dimension, but the more important differences are about control, custody, and trust.',
          'With a managed SaaS tool, the vendor controls the software, the infrastructure, and the data stored in it. They decide when to update, what the API limits are, whether to raise prices, and what happens to your data if they are acquired or shut down. You get reliability guarantees through an SLA, and you do not have to maintain anything. That is a genuine value proposition — managed reliability in exchange for custody.',
          'With a self-hosted open-source tool, you run the software on infrastructure you control. You decide the update schedule, the resource allocation, and the data retention policy. You are also responsible for backups, uptime, and security configuration. The code is auditable — you can read every line that processes your data. You are not subject to the vendor\'s pricing decisions or sunset risk.',
        ],
      },
      {
        heading: 'Side-by-side: what each model gives you',
        content: [
          'The table below covers the dimensions that matter most for a feedback analysis tool. Neither column is universally better — the right answer depends on your team\'s situation.',
        ],
        table: {
          headers: ['Dimension', 'Self-hosted open source', 'Managed SaaS'],
          rows: [
            ['Data custody', 'Yours entirely', 'Vendor holds it; subject to their terms'],
            ['AI key ownership', 'Your key, your provider, direct billing', 'Vendor\'s key or bundled AI (marked up)'],
            ['Code auditability', 'Full — MIT licensed, public repo', 'Closed; trust the vendor\'s security claims'],
            ['Pricing', 'Infrastructure cost only; no seat fees', 'Monthly SaaS fee; often per-seat or per-feedback'],
            ['Maintenance', 'Your responsibility: backups, updates, uptime', 'Vendor handles infrastructure'],
            ['Customisation', 'Fork or modify freely', 'Limited to what the vendor exposes'],
            ['Data portability', 'Export directly from your database anytime', 'Export via vendor API or UI; depends on their policy'],
            ['Vendor risk', 'None; code is yours, runs on your infra', 'Acquisition, shutdown, price change risk'],
          ],
        },
      },
      {
        heading: 'When SaaS is the right call',
        content: [
          'SaaS feedback tools make sense when your team does not have the operational capacity to maintain a self-hosted deployment, when you need guaranteed uptime backed by an SLA, or when you are moving fast and want to skip the infrastructure setup entirely.',
          'They also make sense if your data handling requirements do not rule out third-party data processing, and if the SaaS tool\'s terms are acceptable to your legal and security teams. Many teams at early stages are in this position — the priority is getting feedback data flowing and actionable, not optimising for data residency.',
          'The honest guidance: if your primary concern is speed of setup and you have no hard privacy constraints, a managed SaaS tool might serve you better in the short term. You can always migrate later when data ownership becomes a priority.',
        ],
      },
      {
        heading: 'When open source and self-hosting is the right call',
        content: [
          'Self-hosting becomes the correct choice when you have data residency requirements (GDPR, HIPAA, sector-specific), when your security team will not approve sending customer data to a third-party AI provider, when you need to audit the code that processes your customers\' feedback, or when the SaaS pricing structure does not work at your feedback volume.',
          'It is also worth considering when you want long-term stability without vendor risk. An open-source codebase cannot be sunset by a pricing decision. A copy of the code you run on your own infrastructure is not affected by an acquisition.',
          'Rereflect is MIT-licensed, which means you can run it indefinitely, modify it to fit your needs, and are not dependent on a commercial entity to keep the lights on.',
        ],
      },
      {
        heading: 'What open source does not fix',
        content: [
          'It is worth being clear about what self-hosting does not solve. It does not remove the operational burden — you are trading vendor management for infrastructure management, which is a different kind of work, not no work. It does not automatically give you better analysis quality — that depends on which LLM you configure, not on the software being open source.',
          'And open source does not mean unsupported. Rereflect has a public GitHub repository, issue tracker, and community. But it does mean that if you need a feature, you file an issue or contribute it yourself rather than asking a customer success manager to escalate it.',
          'Make the choice based on what your team is actually equipped to handle and what your real constraints are — not on a general preference for one model over the other.',
        ],
      },
    ],
  },
  {
    slug: 'gdpr-compliant-self-hosted-feedback',
    title: 'Running GDPR-Compliant Feedback Analysis With a Self-Hosted Tool',
    excerpt:
      'GDPR imposes real obligations on how you process customer feedback: lawful basis, data minimisation, deletion rights, and cross-border transfer restrictions. Self-hosting Rereflect addresses the hardest of these by keeping data inside your own infrastructure.',
    date: '2026-10-20',
    status: 'scheduled',
    readTime: '9 min read',
    author: 'Rereflect Team',
    tags: ['GDPR', 'Compliance', 'Privacy', 'Self-Hosting', 'Data Protection'],
    seoTitle: 'Running GDPR-Compliant Feedback Analysis With a Self-Hosted Tool | Rereflect',
    seoDescription:
      'How self-hosting Rereflect helps address GDPR requirements for customer feedback data: data residency, deletion rights, processing transparency, and avoiding third-party transfer issues.',
    sections: [
      {
        heading: 'Why feedback data is in scope for GDPR',
        content: [
          'Feedback from your users almost certainly contains personal data under GDPR\'s definition. A support ticket that says "I am having trouble with my account" contains the submitter\'s identity by association even if you strip the email address, because it is linked to an account. Feedback that mentions a name, a specific transaction, or an identifiable situation is unambiguously personal data.',
          'This means you need a lawful basis for processing it, you need to be able to respond to deletion requests (the right to erasure), and you need to be able to explain to a user or supervisory authority what you are doing with their data and where it flows.',
          'Note: this post describes how Rereflect\'s self-hosted architecture supports GDPR compliance; it is not legal advice. Your specific compliance requirements depend on your data, your users, and the advice of your legal counsel.',
        ],
      },
      {
        heading: 'The third-party transfer problem with SaaS tools',
        content: [
          'The most common GDPR friction point with managed SaaS feedback tools is international data transfer. If your users are in the EU and the SaaS tool processes data on US servers (or sends it to a US-based LLM API), you need a valid transfer mechanism: Standard Contractual Clauses, a data processing agreement with the vendor, or reliance on another adequacy decision.',
          'In practice, the chain gets complicated. The SaaS tool is the processor; you are the controller. But the SaaS tool may use a sub-processor (the LLM API) that has its own data handling terms. Getting that sub-processor chain documented in a way that satisfies a data processing agreement is real work — and if any link in the chain is in a jurisdiction with inadequacy concerns, you have a problem.',
          'Self-hosting eliminates this chain for the storage and processing steps. Your feedback stays in a database you run, in a region you choose. If you also use a local LLM, the analysis step eliminates the LLM provider from the chain entirely.',
        ],
      },
      {
        heading: 'Data residency: choosing your region',
        content: [
          'When you self-host Rereflect, you choose where the PostgreSQL database runs. Run it in the EU and your feedback data never leaves EU infrastructure. This is a meaningful compliance posture that a SaaS tool with US-based infrastructure cannot match without explicit contractual and technical guarantees.',
          'Concretely: if you deploy the docker-compose stack on a server in Frankfurt, Amsterdam, or another EU data centre, and you do not configure an LLM key pointing at a non-EU provider, your feedback data stays in the EU throughout its lifecycle. With a local Ollama model alongside the stack, even the analysis calls are on the same host.',
          'Document this in your Records of Processing Activities (ROPA): "Customer feedback is stored in a PostgreSQL database hosted in [region] and processed by Rereflect running on the same infrastructure." That is a clear, accurate, auditable statement.',
        ],
      },
      {
        heading: 'Handling deletion requests (the right to erasure)',
        content: [
          'GDPR Article 17 gives individuals the right to request deletion of their personal data. For feedback data this means you need to be able to find all feedback associated with a specific user and delete it when requested.',
          'With a self-hosted Rereflect, the database is yours. You can write a direct SQL query, or use the admin interface, to find all feedback items linked to a user (by email, user ID, or account reference) and hard-delete them. The deletion takes effect immediately. There is no "submit a request and we will process it within 30 days" queue, because the data is in your own database.',
          'If you use an LLM provider for analysis, be aware that the provider\'s own data retention policy may mean they retain the text of the prompt for some period (check their terms). If this is a concern, use a local model or the VADER fallback, which sends nothing to any external service.',
        ],
        listItems: [
          'Feedback text and derived data (sentiment, categories) are stored in your PostgreSQL database.',
          'Delete items directly via the Rereflect UI, the API, or SQL queries against your database.',
          'Deletion is immediate — no vendor queue.',
          'If using a hosted LLM provider: check their data retention terms for prompts and completions.',
          'With a local model or VADER: no data leaves your infra, so no external retention concern.',
        ],
      },
      {
        heading: 'Practical checklist for GDPR and self-hosted Rereflect',
        content: [
          'This is not an exhaustive compliance checklist — work with legal counsel for your specific situation. These are the self-hosting configuration choices that have the most direct bearing on GDPR considerations for feedback data.',
        ],
        listItems: [
          'Host PostgreSQL in an EU region if your users are in the EU.',
          'Configure SELF_HOSTED=true to disable any calls to Rereflect cloud services.',
          'Use a local LLM or VADER to eliminate feedback text flowing to a third-party AI provider.',
          'If using a hosted LLM, ensure you have a DPA with the provider that covers sub-processor use.',
          'Document data flows in your ROPA: where feedback is stored, how it is processed, how long it is retained.',
          'Implement a deletion workflow: define the process for responding to erasure requests and confirm you can execute it against your database.',
          'Set a data retention policy and implement it: decide how long feedback is kept and configure periodic deletion if needed.',
        ],
      },
    ],
  },
  {
    slug: 'choosing-a-local-model-feedback-analysis',
    title: 'Choosing a Local LLM for Feedback Analysis: A Practical Guide',
    excerpt:
      'Not all local models are equally suited to feedback analysis. The task — classify sentiment, identify pain points, extract feature requests — is structured and instruction-following, which means model choice and prompt quality both matter. Here is how to evaluate and pick.',
    date: '2026-10-24',
    status: 'scheduled',
    readTime: '9 min read',
    author: 'Rereflect Team',
    tags: ['Local LLM', 'AI', 'Self-Hosting', 'Performance', 'Model Selection'],
    seoTitle: 'Choosing a Local LLM for Feedback Analysis: A Practical Guide | Rereflect',
    seoDescription:
      'How to evaluate and choose a local LLM for customer feedback analysis with Rereflect. Covers model families, hardware requirements, instruction-following quality, and practical starting points.',
    sections: [
      {
        heading: 'What the feedback analysis task actually requires from a model',
        content: [
          'Feedback analysis is a structured classification task, not open-ended generation. The model reads a piece of customer feedback, then needs to: assign a sentiment label from a defined set, identify which pain point categories apply from a list, extract feature requests as structured output, and reason about urgency based on described criteria.',
          'The critical model property is instruction-following — the ability to read a prompt that says "classify this feedback into one of these categories and respond in this JSON format" and actually do that reliably. A model that generates creative prose but fails to follow structured output instructions is less useful for this task than a smaller model with strong instruction-following.',
          'Contextual understanding matters for edge cases: sarcasm, domain-specific language, feedback in a language the model was not primarily trained on. For the bulk of straightforward feedback, this is less discriminating — most capable models handle clear negative feedback reliably.',
        ],
      },
      {
        heading: 'Model families worth considering',
        content: [
          'The open-weight model landscape changes quickly. Rather than specific version recommendations that will date quickly, here are the model families that have shown strong instruction-following on structured classification tasks — all are available through Ollama.',
          'The Llama family (Meta) has good instruction-following in its instruction-tuned variants and broad multilingual capability in larger sizes. The Mistral and Mixtral families are known for strong performance at smaller parameter counts, which matters if you are running on commodity hardware. The Phi family (Microsoft) punches above its weight at small sizes for structured tasks. The Gemma family (Google) performs well on instruction-following benchmarks.',
          'In general, prefer the instruction-tuned (chat or instruct) variant of any model over the base variant — base models are not fine-tuned for instruction-following and will give inconsistent structured output.',
        ],
        listItems: [
          'Llama 3 / Llama 3.1 instruct variants — strong instruction-following, available in 8B and 70B.',
          'Mistral / Mistral Nemo — good performance at 7B and 12B; efficient on moderate hardware.',
          'Mixtral 8x7B — mixture-of-experts; good quality with reasonable inference cost.',
          'Phi-3 / Phi-4 — strong for structured tasks at 3B-14B; runs on CPUs.',
          'Gemma 2 — Google family, competitive instruction-following at 9B and 27B.',
        ],
      },
      {
        heading: 'Hardware requirements by model size',
        content: [
          'Model size determines what hardware you need. The key constraint is VRAM (for GPU inference) or RAM (for CPU inference). GPU inference is significantly faster and is the practical choice for any meaningful feedback volume.',
          'As a rough guide: 7B models need around 6-8GB VRAM for 4-bit quantised inference; 13B models need around 10-12GB; 34B models need around 20-24GB; 70B models need around 40-48GB, though 4-bit quantised versions can fit in less. CPU-only inference is viable for low-volume use cases with models up to 13B, but inference time is measured in tens of seconds per completion rather than seconds.',
        ],
        table: {
          headers: ['Model size', 'Minimum VRAM (4-bit quant)', 'CPU inference', 'Typical inference time per item'],
          rows: [
            ['3-7B', '4-6 GB', 'Feasible (slow)', '2-10s GPU / 15-45s CPU'],
            ['13B', '8-10 GB', 'Feasible (slow)', '5-15s GPU / 30-120s CPU'],
            ['34B', '20-24 GB', 'Very slow', '10-30s GPU'],
            ['70B', '36-48 GB', 'Impractical', '20-60s GPU'],
          ],
        },
        content2: [
          'Consumer GPUs with 8-12GB VRAM (e.g., RTX 3060 12GB, RTX 4070) run 7B models comfortably. GPUs with 24GB VRAM (e.g., RTX 3090, RTX 4090) open up 13B and some 34B models. Multi-GPU setups or server GPUs are needed for reliable 70B inference.',
        ],
      },
      {
        heading: 'Testing a model before committing',
        content: [
          'Before switching Rereflect to a new local model for production, run a set of test feedback items through it and check the output quality. The key things to look for: does it produce valid JSON in the expected schema, does it correctly classify clear positive and negative feedback, does it handle ambiguous or sarcastic feedback reasonably, and does it stay within the category labels you have defined rather than inventing new ones.',
          'A simple test set of twenty to forty feedback items — covering positive, negative, and ambiguous cases, and including any domain-specific language your users tend to use — gives you a useful baseline. Compare the local model\'s classifications against what you would expect, or against output from a hosted frontier model if you have one available.',
          'If a model fails consistently on structured output (producing free text instead of JSON, or inventing categories), try a different instruction-following variant or a different model family before concluding that local inference will not work for your use case.',
        ],
      },
      {
        heading: 'The VADER baseline and when it is enough',
        content: [
          'Before investing in local model infrastructure, consider whether the VADER fallback meets your needs. VADER gives you reliable sentiment scoring across large feedback volumes with zero hardware requirements. If your primary analytics use case is "what percentage of feedback this week was negative, and is that trending up or down," VADER answers that question well.',
          'Local LLMs add value when you need the categorisation layer: which pain points are users hitting most, which features are most requested, which items are urgent churn risks. If you are not yet acting on that level of analysis, VADER is the faster and cheaper path to get started. You can switch Rereflect to a local model later with a single configuration change when you are ready for it.',
        ],
      },
    ],
  },
  {
    slug: 'backup-and-restore-self-hosted-rereflect',
    title: 'Backup and Restore for a Self-Hosted Rereflect Deployment',
    excerpt:
      'When you self-host, you own the backup responsibility. Rereflect\'s data lives in PostgreSQL — structured, straightforward to back up, and easy to restore. This guide covers what to back up, how often, and how to verify your backups actually work.',
    date: '2026-10-28',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['Self-Hosting', 'Backup', 'DevOps', 'PostgreSQL', 'Disaster Recovery'],
    seoTitle: 'Backup and Restore for a Self-Hosted Rereflect Deployment | Rereflect',
    seoDescription:
      'A practical guide to backing up and restoring a self-hosted Rereflect instance. Covers PostgreSQL dumps, environment secrets, backup schedules, and restore verification.',
    sections: [
      {
        heading: 'What needs to be backed up',
        content: [
          'A Rereflect deployment has two categories of data that matter for recovery: the PostgreSQL database and the environment secrets.',
          'The database holds everything: organizations, users, feedback items, analysis results, categories, integrations, and settings. If you lose the database without a backup, that data is gone. The environment secrets — particularly SECRET_KEY and LLM_ENCRYPTION_KEY — are not stored in the database. If you lose LLM_ENCRYPTION_KEY, any LLM API keys stored in the database become unrecoverable (they are encrypted ciphertext without the key). If you lose SECRET_KEY, existing user sessions are invalidated but users can log in again.',
        ],
        listItems: [
          'PostgreSQL database — all application data.',
          'LLM_ENCRYPTION_KEY — required to decrypt stored LLM API keys. Cannot be recovered from the database.',
          'SECRET_KEY — signs JWT sessions. Loss invalidates existing sessions but is not data loss.',
          'Any custom configuration in docker-compose.yml or .env beyond the defaults.',
        ],
      },
      {
        heading: 'Backing up the PostgreSQL database',
        content: [
          'The standard PostgreSQL backup tool is pg_dump. It produces a SQL dump file that can restore the database to the exact state at the time of the dump. For a Rereflect deployment using the bundled Docker database service, you run pg_dump inside the container.',
          'A compressed dump of a Rereflect database with a few thousand feedback items is typically a small file — tens of megabytes at most. Store it somewhere other than the host running the database: an object storage bucket (S3, Backblaze B2, Cloudflare R2), a separate server, or wherever your existing backup infrastructure is.',
        ],
        listItems: [
          'docker exec rereflect-db pg_dump -U postgres rereflect | gzip > rereflect_$(date +%Y%m%d_%H%M%S).sql.gz',
          'Copy the dump file off the host: scp, rclone to object storage, or your preferred transfer method.',
          'Back up .env (including LLM_ENCRYPTION_KEY and SECRET_KEY) separately from the database dump.',
          'Automate with a cron job or systemd timer for unattended daily backups.',
        ],
      },
      {
        heading: 'Backup frequency and retention',
        content: [
          'How often to back up depends on how much data you can afford to lose. For a team actively importing and analysing feedback, a daily backup means losing at most a day of analysis results in a worst case. For teams with high feedback import volume or active usage throughout the day, hourly backups may be more appropriate.',
          'A practical retention policy for most self-hosted deployments: keep daily backups for 14 days, weekly backups for 3 months, and monthly backups for a year. The exact numbers depend on your storage constraints and recovery point objective (RPO). Object storage is cheap enough that over-retaining costs very little compared to the risk of needing a backup that does not exist.',
          'Automate retention management — manual cleanup is a task that gets forgotten. Most object storage providers support lifecycle rules that automatically delete objects older than a defined age.',
        ],
        table: {
          headers: ['Backup type', 'Suggested frequency', 'Suggested retention'],
          rows: [
            ['Database dump (pg_dump)', 'Daily (minimum)', '14 daily, 12 weekly, 12 monthly'],
            ['Environment secrets (.env)', 'On any change', 'Encrypted, stored in secrets manager or separate secure location'],
            ['docker-compose.yml', 'On any change', 'Version-controlled in a private repo'],
          ],
        },
      },
      {
        heading: 'Restoring from a backup',
        content: [
          'A backup you have never tested is an assumption, not a guarantee. The restore process for Rereflect is straightforward, but you should run through it at least once to verify it works before you need it in an emergency.',
          'To restore: start with a fresh Rereflect stack (or stop the existing one), drop and recreate the database, then load the dump. With the bundled Docker database service, you connect to the container and run psql to execute the dump file.',
        ],
        listItems: [
          'Stop the Rereflect stack: docker compose down',
          'Start only the database service: docker compose up -d db',
          'Drop and recreate the database: docker exec rereflect-db psql -U postgres -c "DROP DATABASE IF EXISTS rereflect; CREATE DATABASE rereflect;"',
          'Load the dump: gunzip -c rereflect_backup.sql.gz | docker exec -i rereflect-db psql -U postgres rereflect',
          'Restore your .env with the original LLM_ENCRYPTION_KEY and SECRET_KEY.',
          'Start the full stack: docker compose up -d',
          'Verify: open the UI and confirm feedback, organizations, and settings are present.',
        ],
      },
      {
        heading: 'Verifying backups periodically',
        content: [
          'The only reliable way to know a backup works is to restore it to a test environment and verify the result. This does not need to be elaborate — a monthly restore to a temporary Docker environment on your laptop, followed by a basic sanity check that the UI loads and data is present, is sufficient for most self-hosted deployments.',
          'Set a calendar reminder to run through the restore procedure quarterly. It takes fifteen to thirty minutes, and it is the step that turns a backup policy into actual disaster recovery capability.',
          'Also verify that your backup storage is accessible: download the most recent dump periodically to confirm the file is intact and the storage credentials are valid. Object storage credentials expire; automated backup jobs can fail silently. A quick periodic check that the latest backup file exists and has a reasonable size catches most failure modes before they matter.',
        ],
      },
    ],
  },
];
