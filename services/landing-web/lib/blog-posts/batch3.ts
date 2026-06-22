import type { BlogPost } from '../blog';

// Cluster: Sentiment, NLP & AI analysis
export const batch3: BlogPost[] = [
  {
    slug: 'how-sentiment-analysis-works-vader',
    title: 'How Sentiment Analysis Works: A Plain-English Guide to VADER',
    excerpt: 'Before you trust a sentiment score, it helps to understand where it comes from. Rereflect uses VADER — a lexicon and rule-based analyzer built specifically for short, informal text — as its built-in sentiment engine. This post explains how VADER scores text, what those scores actually mean, and where the approach has real limits.',
    date: '2026-09-01',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['Sentiment Analysis', 'NLP', 'VADER', 'AI'],
    seoTitle: 'How Sentiment Analysis Works: A Plain-English Guide to VADER | Rereflect',
    seoDescription: 'Understand how VADER lexicon-based sentiment analysis scores customer feedback, what compound scores mean, where VADER excels, and where it falls short compared to LLM-based approaches.',
    sections: [
      {
        heading: 'What sentiment analysis is actually doing',
        content: [
          'Sentiment analysis assigns a valence — positive, negative, or neutral — to a piece of text. The goal is not to summarize what the text is about, but to capture the emotional polarity of how it was written. A review that says "the export took three minutes and I nearly gave up" is negative. One that says "slower than I expected but the results were worth it" is mixed. One that says "works exactly as described" is positive.',
          'That sounds straightforward, and for clear-cut cases it is. The hard part is handling everything in between: sarcasm, hedged praise, domain-specific jargon, intensifiers ("absolutely terrible" vs "terrible"), negations ("not bad at all"), and the casual abbreviated style of support tickets and in-app surveys.',
          'Different approaches handle this complexity in different ways. Rereflect ships with VADER as its built-in engine because VADER was designed specifically for the kind of informal, short-form text that customer feedback tends to be.',
        ],
      },
      {
        heading: 'How VADER scores a piece of text',
        content: [
          'VADER stands for Valence Aware Dictionary and sEntiment Reasoner. It is a lexicon and rule-based method, meaning it works from a curated list of words and phrases that have been human-rated for sentiment strength, combined with a set of grammatical rules that adjust those ratings in context.',
          'For each token in the text, VADER looks up a valence score — a number representing how positive or negative that word tends to be. It then applies a series of modifier rules before summing up the result:',
        ],
        listItems: [
          'Capitalization — "TERRIBLE" scores more negative than "terrible" because all-caps signals emphasis in informal writing.',
          'Punctuation — trailing exclamation marks amplify whatever valence the surrounding words already have.',
          'Degree modifiers — words like "very," "extremely," and "barely" scale the adjacent sentiment word up or down.',
          'Negations — "not good" flips the valence of "good"; VADER looks back a few tokens to catch these reversals.',
          'Special idioms — common phrases like "kind of" or "sort of" are handled as damping modifiers rather than parsed word-by-word.',
        ],
        content2: [
          'The output is three raw scores (positive, negative, neutral proportions that sum to 1.0) plus a compound score that ranges from -1.0 (maximally negative) to +1.0 (maximally positive). Rereflect maps this compound score to the three-way label — positive, neutral, negative — using conventional thresholds, and stores both the label and the raw compound value so you can filter and sort by either.',
        ],
      },
      {
        heading: 'Where VADER works well',
        content: [
          'VADER was built by researchers at Georgia Tech specifically to handle social media and user-generated text, which makes it a reasonably good fit for customer feedback. It handles:',
        ],
        listItems: [
          'Short text without extensive context — support tickets, NPS comments, in-app survey responses, and app-store reviews are all squarely in VADER\'s design target.',
          'Casual punctuation and capitalization — the kinds of stylistic signals that trip up models trained primarily on formal prose.',
          'Common English slang and intensifiers — the lexicon includes colloquial terms and accounts for the difference between "good," "really good," and "SO good."',
          'Speed and zero dependencies — VADER runs entirely in-process, requires no GPU, makes no network calls, and can score thousands of items per second on a modest machine.',
        ],
        content2: [
          'For teams running Rereflect without a configured LLM, VADER provides immediate, always-on sentiment scoring across all ingested feedback. That is genuinely useful even before any AI model is wired in.',
        ],
      },
      {
        heading: 'Where VADER has real limits',
        content: [
          'Being honest about limitations matters more than marketing sentiment scores as universally reliable. VADER has several known weaknesses you should account for when interpreting results:',
        ],
        listItems: [
          'Sarcasm and irony — "Oh great, another outage" reads as positive to a lexicon-based system because "great" has positive valence. VADER has no model of intent.',
          'Domain-specific language — technical terms that carry negative meaning in your product ("latency," "regression," "data loss") may be neutral in VADER\'s general lexicon.',
          'Long-form text — VADER was designed for short snippets. On a long support email, the scoring reflects a mixture of all sentences rather than the main concern being raised.',
          'Non-English text — VADER\'s lexicon is English-only. Feeding it text in other languages will produce unreliable scores.',
          'Nuanced mixed sentiment — "The onboarding is great but billing is a disaster" contains both strong positive and strong negative signals; the compound score will land somewhere in the middle, which may or may not reflect the practical priority.',
        ],
        content2: [
          'None of these are arguments against using VADER — they are arguments for understanding what you are looking at. Sentiment scores are signals, not verdicts. A cluster of feedback that VADER labels negative almost certainly contains real problems worth investigating, even if individual scores are imperfect.',
        ],
      },
      {
        heading: 'VADER vs. an LLM: when to upgrade',
        content: [
          'If you configure Rereflect with a language model, the LLM takes over the deeper categorization steps — pain point extraction, feature request classification, urgency reasoning — while VADER continues handling the basic sentiment pass. The LLM brings contextual understanding that VADER lacks: it can recognize sarcasm, infer domain-specific negativity, and reason about long-form text.',
          'That said, LLM-based sentiment is not always better in every dimension. It is slower, it costs tokens, and it introduces a dependency on either a hosted API key or a locally running model. VADER runs instantly with no configuration and no cost.',
          'The practical recommendation: start with VADER to establish a baseline sentiment signal across your feedback. If you find that scores on your specific type of feedback are consistently off — because your domain language is unusual, because your customers write in multiple languages, or because sarcasm is endemic to your feedback channel — that is when an LLM upgrade makes sense. The two approaches are complementary, not competing.',
        ],
      },
    ],
  },
  {
    slug: 'ai-feedback-categorization-explained',
    title: 'AI Feedback Categorization Explained: From Raw Text to Actionable Labels',
    excerpt: 'Sentiment scores tell you how customers feel. Categorization tells you what they are feeling that way about. Rereflect uses a combination of keyword matching and LLM-based classification to assign pain points, feature requests, and urgency flags to each piece of feedback. This post explains how that pipeline works and what drives its accuracy.',
    date: '2026-09-04',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'Categorization', 'NLP', 'Feedback Analysis'],
    seoTitle: 'AI Feedback Categorization Explained: From Raw Text to Labels | Rereflect',
    seoDescription: 'Learn how Rereflect combines keyword matching and LLM classification to categorize customer feedback into pain points, feature requests, and urgency flags — and what drives accuracy in each step.',
    sections: [
      {
        heading: 'Why categorization matters more than sentiment',
        content: [
          'Knowing that 40% of last month\'s feedback was negative is useful context. Knowing that 40% was negative, and that the dominant theme in that negative feedback was "CSV export failures in the billing module," is actionable. Categorization is what turns a sentiment trend into a product decision.',
          'The categorization problem is harder than the sentiment problem. Sentiment is a single dimension — positive to negative — and a lexicon-based rule system can approximate it reasonably well for short text. Categorization requires understanding what a piece of text is about, matching that meaning to one or more predefined categories, and doing so consistently across thousands of items that are written in different styles, with different levels of detail, by different people.',
          'Rereflect approaches this with a two-layer pipeline: a lightweight keyword pass for speed and a LLM pass for depth.',
        ],
      },
      {
        heading: 'Layer 1: keyword-based classification',
        content: [
          'The first layer uses TF-IDF-weighted keyword matching to make fast preliminary categorization decisions. Each category in your taxonomy is associated with a set of terms, and incoming feedback is scanned for those signals. Matches above a confidence threshold generate a preliminary label.',
          'Keyword matching is not sophisticated — it cannot understand context, handle synonyms gracefully, or catch the same concept expressed in five different ways. But it is fast, it is deterministic, and it is surprisingly effective for the subset of feedback that mentions the thing it is about directly. A ticket that says "the export button crashes" does not require a language model to recognize that it is about the export feature.',
          'For items where keyword signals are ambiguous or absent — which is a meaningful fraction of real-world feedback — the keyword pass flags them for the LLM layer rather than forcing a low-confidence label.',
        ],
      },
      {
        heading: 'Layer 2: LLM-based classification',
        content: [
          'The second layer sends feedback items (and their preliminary keyword signals) to the configured language model for deeper classification. The prompt includes your custom category taxonomy and descriptions, the raw feedback text, and any preliminary keyword signals from the first pass.',
          'The LLM can handle things keyword matching cannot: paraphrasing, implied meaning, multi-topic feedback, and context-dependent categorization. A piece of feedback that says "I keep having to redo things after navigating away" is about state persistence or navigation, not about any single keyword — but an LLM with the right category descriptions can recognize that.',
          'The tradeoff is cost and latency. Every LLM call consumes tokens and takes time. Rereflect uses the keyword layer to avoid sending items that can be classified confidently without a model, reserving LLM calls for the harder cases.',
        ],
        listItems: [
          'Pain point classification — maps complaints and friction signals to your defined pain-point categories.',
          'Feature request classification — identifies requests for new capabilities and maps them to your feature category taxonomy.',
          'Urgency scoring — reasons about signals like churn risk, SLA mentions, angry tone, and escalation language to assign an urgency flag.',
        ],
        content2: [
          'If no LLM is configured, Rereflect falls back to keyword-only classification and VADER sentiment. You get a coarser signal, but the pipeline still runs completely offline.',
        ],
      },
      {
        heading: 'What drives accuracy',
        content: [
          'Categorization accuracy is not a fixed property of the system — it varies based on several factors you have some control over:',
        ],
        listItems: [
          'Category description quality — vague category names produce vague classifications. A category described as "slowness, timeouts, and loading delays in the core editor" gives the model much stronger signal than one called "performance."',
          'Category distinctiveness — overlapping categories create ambiguity. If "billing" and "pricing" both exist and are not clearly distinguished, items that mention cost will land inconsistently.',
          'Feedback text length — very short items (one sentence or fewer) have less signal for the model to work with. Longer, more detailed feedback generally classifies more accurately.',
          'Model capability — a stronger model classifies more accurately, particularly on ambiguous or multi-topic items. Local smaller models trade some accuracy for privacy and cost.',
          'Language — English feedback generally classifies more accurately than other languages, depending on the model you have configured.',
        ],
      },
      {
        heading: 'Checking and improving your results',
        content: [
          'No categorization system is perfectly accurate on the first run, and the right response to imperfect results is not to distrust categorization entirely — it is to use the errors to improve the taxonomy.',
          'When you notice that a category is consistently attracting the wrong items, the usual cause is a description that is too broad or that overlaps with another category. Tightening the description or splitting the category tends to fix it. When items that should match a category keep missing it, the category probably needs broader or more varied description language.',
          'The pipeline is a tool, not an oracle. Treat the first round of categorization as a draft that you refine by looking at what it gets wrong. Most teams find that a few rounds of taxonomy refinement produce results they trust enough to act on without reviewing every item.',
        ],
      },
    ],
  },
  {
    slug: 'topic-clustering-customer-feedback',
    title: 'Topic Clustering in Customer Feedback: How TF-IDF Surfaces Themes',
    excerpt: 'When you have hundreds or thousands of feedback items, reading them one by one is not a strategy. Topic clustering groups feedback into thematic clusters automatically so you can see which issues are recurring patterns and which are one-offs. Rereflect uses TF-IDF-based clustering for this — here is what that means and what it produces.',
    date: '2026-09-07',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['NLP', 'Topic Clustering', 'TF-IDF', 'Feedback Analysis'],
    seoTitle: 'Topic Clustering in Customer Feedback: How TF-IDF Works | Rereflect',
    seoDescription: 'Understand how TF-IDF-based topic clustering groups customer feedback into thematic clusters, what the algorithm is actually doing, and how to interpret the themes it surfaces.',
    sections: [
      {
        heading: 'The scale problem in feedback analysis',
        content: [
          'At low volume — say, ten or twenty pieces of feedback a week — you can read everything and hold the themes in your head. At higher volumes, that stops working. The signal is still there; it is just buried in repetition. The same complaint about the same feature arrives in twenty different phrasings, and without a way to aggregate them, each instance looks like a one-off rather than a pattern.',
          'Topic clustering addresses this by grouping feedback items that share thematic content, regardless of the exact words used. The output is a set of clusters, each representing a recurring theme, with a label and a count of how many items belong to it. This lets you see at a glance that "export failures" is not a single ticket — it is forty tickets, and it deserves attention proportional to its volume.',
        ],
      },
      {
        heading: 'What TF-IDF is doing',
        content: [
          'TF-IDF stands for Term Frequency–Inverse Document Frequency. It is a classical information-retrieval technique that represents each piece of text as a vector of weighted term scores.',
          'The term frequency part is intuitive: words that appear more often in a document are more important to it. But frequency alone is a poor signal — common words like "the," "is," and "my" appear in everything and distinguish nothing.',
          'The inverse document frequency part corrects for this: it down-weights terms that appear in many documents across the corpus and up-weights terms that appear in relatively few. A word like "timeout" that appears in 30 out of 1,000 feedback items is carrying more signal than a word like "the" that appears in all 1,000.',
          'The result is a numeric vector for each feedback item where the high-scoring dimensions correspond to the distinctive vocabulary of that item. Items about similar topics will have similar vectors — even if they used different specific words — because they share the same distinctive vocabulary. Clustering algorithms (Rereflect uses k-means over these TF-IDF vectors) then group items with similar vectors together.',
        ],
      },
      {
        heading: 'What the clusters represent — and what they do not',
        content: [
          'TF-IDF clusters group items by shared vocabulary, not by human-interpretable meaning. Most of the time these align: items that share vocabulary tend to be about the same thing. But there are cases where they diverge:',
        ],
        listItems: [
          'Synonyms and paraphrasing — "slow" and "laggy" and "takes forever" all describe the same experience but have different TF-IDF scores. Items that describe the same problem in very different words may end up in different clusters.',
          'Multi-topic feedback — a single piece of feedback that mentions both "billing confusion" and "export failures" will land in whichever cluster its vocabulary is more similar to, not both.',
          'Domain vocabulary — highly technical or product-specific terms may drive cluster assignments in ways that feel unexpected to someone not aware of their relative frequency.',
          'Cluster count sensitivity — the number of clusters is a parameter. Too few and distinct themes merge; too many and single themes fragment. The right value depends on your corpus size and vocabulary range.',
        ],
        content2: [
          'Despite these limitations, TF-IDF clustering is effective at surfacing the major recurring themes in large feedback corpora. It is a directional tool, not a precise classifier — the clusters tell you where to look, and the individual items inside each cluster tell you the details.',
        ],
      },
      {
        heading: 'How Rereflect uses clustering in practice',
        content: [
          'Rereflect runs topic clustering as part of the analysis pipeline and attaches cluster tags to each feedback item. The tags are surfaced on the feedback detail view, in filter options, and in the dashboard\'s topic breakdown.',
          'The cluster labels are generated from the top-weighted terms in each cluster. These are not always elegant phrases — they reflect the dominant vocabulary of the group, which is sometimes a technical term and sometimes a common word that happens to be distinctive in your corpus. Treat them as signposts for the theme, not polished category names.',
          'If you want more semantically coherent cluster labels, the LLM-based categorization layer produces those — at the cost of tokens and latency. Topic clustering gives you an always-available, zero-cost view of thematic distribution that does not require a language model.',
        ],
      },
      {
        heading: 'Reading cluster output usefully',
        content: [
          'The most useful thing to do with clustering results is to look at volume and sentiment together. A large cluster of negative feedback represents a concentrated, recurring pain point — the combination of scale and polarity is the signal.',
          'Equally useful is watching how cluster composition changes over time. A cluster that has been large and stable for months represents a chronic issue. A cluster that appeared three weeks ago and has been growing represents something new. A cluster that shrunk after a release represents something you fixed.',
          'Topic clustering is a lens on the distribution of feedback themes, not a substitute for reading the items themselves. Use the clusters to decide where to focus, then read the items in that cluster to understand the details. The combination of the macro view and the micro view is where the actionable insight lives.',
        ],
      },
    ],
  },
  {
    slug: 'llm-vs-rules-feedback-analysis',
    title: 'LLM vs. Rule-Based Feedback Analysis: When Each Approach Wins',
    excerpt: 'There are two broad philosophies for automating feedback analysis: rules and lexicons (fast, predictable, free) or language models (flexible, contextual, costly). Rereflect uses both — but understanding the tradeoffs helps you configure the system in a way that actually fits your situation.',
    date: '2026-09-10',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'LLM', 'NLP', 'Feedback Analysis'],
    seoTitle: 'LLM vs. Rule-Based Feedback Analysis: When Each Approach Wins | Rereflect',
    seoDescription: 'Compare rule-based (VADER, TF-IDF, keywords) and LLM-based approaches to customer feedback analysis — when each performs better, what they cost, and how Rereflect combines both.',
    sections: [
      {
        heading: 'Two philosophies, one pipeline',
        content: [
          'The field of natural language processing has two long-running traditions. The first is rule-based and statistical: build explicit systems from human-curated knowledge — dictionaries, grammatical rules, frequency statistics — and apply them mechanically to text. The second is learned: train a neural network on enough text that it develops an implicit model of language and can generalize to novel inputs.',
          'For most of the 2010s, these traditions were positioned as competing. In practice, they are complementary, and the best-performing systems often use both. Rereflect\'s analysis pipeline is an example of this: it uses rule-based and statistical methods (VADER, TF-IDF, keyword matching) where they are sufficient, and calls a language model where they are not.',
          'Understanding the tradeoffs helps you configure Rereflect appropriately for your situation — and helps you interpret results honestly rather than expecting either approach to be perfect.',
        ],
      },
      {
        heading: 'Where rule-based approaches win',
        content: [
          'Rule-based methods have properties that matter for practical deployments:',
        ],
        listItems: [
          'Speed — VADER can score thousands of items per second. A TF-IDF classifier is similarly fast. No waiting for API latency or model inference time.',
          'Cost — rule-based methods run in-process with no per-call charges. There is no token budget to manage and no API key required.',
          'Privacy — text never leaves your infrastructure. For teams with data residency requirements or strict policies about sending customer content to third-party services, rule-based analysis is the only compliant option.',
          'Determinism — the same input always produces the same output. You can reason about the system\'s behavior and debug it when something looks wrong.',
          'No dependency — VADER and TF-IDF work without a configured model, API key, or internet connection. They run regardless of LLM availability.',
        ],
        content2: [
          'For straightforward sentiment classification on English informal text, VADER performs surprisingly well. For identifying that a feedback item is about "export" because it contains the word "export," keyword matching is perfectly adequate. Not every feedback item needs a language model.',
        ],
      },
      {
        heading: 'Where LLMs win',
        content: [
          'Language models bring capabilities that rule-based systems cannot replicate:',
        ],
        listItems: [
          'Contextual understanding — an LLM can recognize that "it keeps crashing on me" is negative and about reliability, even though "crashing" is not in the pain-point keyword list.',
          'Paraphrase and synonym handling — "sluggish," "slow," "takes forever," and "laggy" all map to the same underlying complaint. A language model handles these naturally; a keyword list requires each to be enumerated.',
          'Sarcasm and irony — "great, another outage" is negative despite containing the word "great." LLMs handle this far better than lexicon-based systems.',
          'Multi-language text — a capable multilingual model can classify feedback in French, Spanish, or Japanese without separate per-language rule sets.',
          'Complex multi-topic items — a single feedback item that touches billing, UX, and a specific bug can be correctly tagged to multiple categories by a model that reads it holistically.',
        ],
        content2: [
          'These advantages come at a cost: latency (LLM calls take seconds, not milliseconds), token spend (each item costs money if you are using a hosted API), and a dependency on a model being configured and available.',
        ],
      },
      {
        heading: 'How Rereflect combines them',
        content: [
          'Rereflect uses a tiered approach. VADER runs on every item, always, for sentiment scoring — it is fast, free, and good enough for the majority of English feedback. TF-IDF clustering runs across the corpus periodically to surface thematic groups. Keyword matching makes an initial categorization pass on each new item.',
          'The LLM layer runs on items where the keyword pass is ambiguous or where deeper categorization is needed — pain point extraction, feature request classification, urgency reasoning. If an LLM is configured, these steps use it. If not, the keyword-only results are used as a fallback.',
          'This means you can run a fully useful version of Rereflect with no LLM configured at all. You get sentiment, basic categorization, and topic clustering. When you add an LLM — whether a hosted API or a local model via Ollama — the categorization quality improves, particularly on ambiguous and nuanced items.',
        ],
      },
      {
        heading: 'Choosing the right configuration for your situation',
        content: [
          'The right balance depends on your constraints:',
        ],
        listItems: [
          'No LLM, fully offline — use Rereflect with just VADER and keyword matching. Good for small volumes, strict privacy requirements, or teams that want to start immediately without any AI configuration.',
          'Local LLM via Ollama — add a local model for better categorization while keeping data on your own infrastructure. Appropriate for teams with a GPU or a server with enough memory, and strong privacy or data residency requirements.',
          'Hosted API with your own key — use OpenAI, Anthropic, or another provider for the highest categorization quality. You pay the provider per token. Best for teams where accuracy is the priority and data residency is not a blocker.',
        ],
        content2: [
          'None of these configurations is universally correct. The point of Rereflect\'s design is that you can start with no model, see whether the results are useful, and add a model later if you want better accuracy — without changing anything else about how the system works.',
        ],
      },
    ],
  },
  {
    slug: 'measuring-ai-categorization-accuracy',
    title: 'Measuring AI Categorization Accuracy on Your Own Feedback',
    excerpt: 'Vendor accuracy claims for AI categorization tools are almost always measured on benchmark datasets that do not look like your feedback. The only accuracy number that matters is the one you measure on your own data. This post explains how to do that practically, without a machine learning background.',
    date: '2026-09-13',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'Categorization', 'Accuracy', 'Evaluation'],
    seoTitle: 'Measuring AI Categorization Accuracy on Your Own Feedback | Rereflect',
    seoDescription: 'Learn how to practically measure the accuracy of AI feedback categorization on your own data — without a machine learning background — and use those measurements to improve your taxonomy.',
    sections: [
      {
        heading: 'Why benchmark numbers do not apply to you',
        content: [
          'AI categorization tools often advertise accuracy figures: "90% precision on pain point detection," "95% recall on feature requests." These numbers sound reassuring. They are also almost meaningless for your specific use case.',
          'Accuracy benchmarks are measured on specific datasets, assembled by specific researchers, using specific category definitions. The domain of text, the vocabulary, the distribution of categories, and the ambiguity level of items all vary enormously between benchmark datasets and real-world feedback corpora. A model that achieves 95% accuracy on a benchmark might achieve 70% on your feedback — or 85%, or 60%. You do not know until you measure.',
          'This is not a criticism of benchmark methodology; benchmarks serve a legitimate purpose for comparing systems under controlled conditions. It is just an argument for measuring on your own data before drawing conclusions about whether a tool is working for you.',
        ],
      },
      {
        heading: 'The basic measurement approach: a labeled sample',
        content: [
          'The practical way to measure categorization accuracy is to create a labeled sample: a set of feedback items where you have manually assigned the correct categories, and where you can compare what the AI assigned.',
          'You do not need a large sample. A set of 50–100 items, sampled randomly from your actual feedback, gives you a meaningful signal. The goal is not statistical precision; it is a directional sense of where the categorization is working and where it is failing.',
          'The process is straightforward:',
        ],
        listItems: [
          'Sample randomly — pull a random set of items from your feedback history. Random sampling is important; cherry-picking "hard" items will give you an artificially pessimistic picture.',
          'Label manually — for each item, assign the categories you believe are correct, based on your own understanding of your product and customers.',
          'Compare to AI output — look at what the system assigned and note where it agrees with your labels and where it differs.',
          'Categorize the disagreements — note whether the AI missed a category you assigned, assigned a category you did not, or assigned a completely wrong one.',
        ],
      },
      {
        heading: 'What to measure: precision and recall',
        content: [
          'Two metrics capture most of what matters for categorization accuracy:',
        ],
        listItems: [
          'Precision — of all the items the AI assigned to category X, what fraction actually belong to category X? High precision means the system rarely mislabels things as X.',
          'Recall — of all the items that actually belong to category X, what fraction did the AI assign to X? High recall means the system rarely misses things that should be in X.',
          'F1 score — the harmonic mean of precision and recall, useful as a single combined metric if you want one number per category.',
        ],
        content2: [
          'In practice, precision and recall trade off against each other. A very conservative classifier (only assigns X when very confident) has high precision but low recall. An aggressive one (assigns X whenever there is any signal) has high recall but lower precision. For most feedback analysis use cases, recall matters more: it is worse to miss a real complaint than to occasionally miscategorize a neutral item.',
          'Calculate these per category, not just overall. Overall accuracy can look good while specific categories are performing poorly — and those are the categories your team is relying on for product decisions.',
        ],
      },
      {
        heading: 'Using measurement to improve your taxonomy',
        content: [
          'Measurement is only useful if it leads to action. The most common improvements come from patterns in the disagreements:',
        ],
        listItems: [
          'Systematic false positives in one category — usually means the category description is too broad, or overlaps with another category. Tighten the description or split the category.',
          'Systematic false negatives in one category — usually means the category description does not cover the vocabulary your customers actually use to describe the issue. Add examples or alternative phrasings.',
          'Consistent miscategorization between two specific categories — means those categories are not sufficiently distinct. Consider merging them or sharpening the distinction in their descriptions.',
          'Low accuracy on short items — very short feedback items have less signal. Consider whether these items contain enough information to be categorized meaningfully at all.',
        ],
        content2: [
          'After making taxonomy changes, run the labeled sample through the updated system and compare. If accuracy improved, the change helped. This iteration loop — measure, identify patterns, adjust taxonomy, remeasure — is how you actually improve a categorization system over time.',
        ],
      },
      {
        heading: 'Setting realistic expectations',
        content: [
          'Human labelers do not agree with each other 100% of the time on ambiguous categorization tasks. Inter-annotator agreement on feedback categorization is typically in the 70–85% range depending on category definition clarity and feedback ambiguity. An AI system that matches human labels 75% of the time on the same task is not a failed system — it is performing comparably to human agreement.',
          'The useful question is not "is the accuracy perfect" but "is it accurate enough to be useful." If a pain point category is capturing 80% of the relevant feedback and very few irrelevant items, the dashboard view for that category will be dominated by real signal. The 20% miss rate means you are not seeing every relevant item — but you are seeing enough to identify the pattern and act on it.',
          'Treat accuracy measurement as a tool for understanding and improving the system, not as a pass/fail test. Most teams find that a combination of good taxonomy design and one or two rounds of iteration produces results they trust enough to drive product decisions.',
        ],
      },
    ],
  },
  {
    slug: 'prompt-design-feedback-analysis',
    title: 'Prompt Design for Feedback Analysis: What Goes Into a Good Classification Prompt',
    excerpt: 'When Rereflect uses a language model to categorize feedback, the quality of the result depends heavily on the prompt — what context the model receives, how categories are described, and how the output format is specified. This post explains the design choices behind feedback analysis prompts and how your taxonomy descriptions feed into them.',
    date: '2026-09-16',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'Prompt Engineering', 'LLM', 'Categorization'],
    seoTitle: 'Prompt Design for Feedback Analysis: Classification Prompts | Rereflect',
    seoDescription: 'Learn how prompt design affects AI feedback categorization quality — what context matters, how category descriptions shape model output, and practical principles for writing better taxonomy descriptions.',
    sections: [
      {
        heading: 'Why the prompt matters',
        content: [
          'A language model\'s output is a function of its weights and its input. You cannot change the weights — that is the model\'s training — but you entirely control the input. For a feedback categorization task, the input is the prompt, and the quality of the categorization depends on how much useful context that prompt contains.',
          'This is not a theoretical point. The same feedback item sent to the same model with two different prompts can produce meaningfully different category assignments. A prompt that describes categories vaguely produces vague assignments. A prompt that gives the model clear, distinct category definitions produces cleaner assignments. The effort you put into your taxonomy descriptions shows up directly in categorization quality.',
        ],
      },
      {
        heading: 'The anatomy of a feedback categorization prompt',
        content: [
          'A well-structured categorization prompt for feedback analysis contains several components:',
        ],
        listItems: [
          'Task framing — a clear statement of what the model is being asked to do: classify this feedback item into one or more of the following categories.',
          'Category definitions — the full set of categories with their names and descriptions. This is where your taxonomy configuration is used; whatever you have written as the description for each category gets included here.',
          'The feedback text — the actual item being classified, clearly delimited from the surrounding prompt.',
          'Output format specification — explicit instructions for how to return the result (JSON with category IDs, comma-separated labels, structured fields), so the output can be parsed reliably.',
          'Edge case handling — instructions for what to do when no category fits, when multiple categories apply, or when the item is too ambiguous to classify confidently.',
        ],
        content2: [
          'Getting the output format specification right matters as much as the category definitions. An LLM that produces well-reasoned classification but returns it in a format the parser does not expect produces useless output. Structured output modes (available in most hosted APIs) help, but even without them, a clear and specific format instruction dramatically reduces parsing failures.',
        ],
      },
      {
        heading: 'Writing category descriptions that work',
        content: [
          'Your category descriptions are the most important variable in classification quality. A few principles hold across different feedback domains and model choices:',
        ],
        listItems: [
          'Describe the category, do not just name it — "Performance" tells the model almost nothing. "Slowness, loading delays, timeouts, and high latency in any part of the product" gives it something concrete to match against.',
          'Include examples of the vocabulary your customers actually use — if your customers say "laggy" and "stuck," mention those. The model needs to connect your category definition to the language of your feedback.',
          'Make categories mutually exclusive where possible — if two categories overlap significantly, the model will inconsistently assign items that could fit either. Draw the boundary explicitly: "This category covers X but NOT Y — items about Y belong in the Z category."',
          'Describe what is excluded, not just what is included — a category definition that only covers what belongs generates more false positives than one that also clarifies what does not belong.',
          'Avoid jargon the model may not know — internal product names or proprietary terminology may not be in the model\'s training data. If a category is defined around a product feature with a proprietary name, describe what the feature does, not just what it is called.',
        ],
      },
      {
        heading: 'Token budget and cost',
        content: [
          'Every character in the prompt is a token that costs money (on a hosted API) and adds latency. Prompt design for feedback categorization involves a tradeoff between thoroughness and cost.',
          'The category definitions are repeated for every item classified. A taxonomy with ten detailed category descriptions might add several hundred tokens to every call. At scale — thousands of items per week — that adds up. The practical strategies:',
        ],
        listItems: [
          'Keep descriptions precise, not exhaustive — a well-targeted 40-word description often outperforms a rambling 200-word one, and costs a fraction as much.',
          'Avoid redundancy across categories — if the same phrase appears in multiple category descriptions, it is doing no work. Descriptions derive their value from distinctiveness.',
          'Consider the keyword pre-filter — Rereflect\'s keyword layer handles items that are obviously in one category, reserving LLM calls for ambiguous cases. This reduces your effective per-item token spend without sacrificing accuracy on the hard cases.',
        ],
      },
      {
        heading: 'Iterating on prompts in practice',
        content: [
          'Prompt design is empirical, not theoretical. The way to know whether your category descriptions are working is to sample classified items, look at the ones that were miscategorized, and ask: what information would have prevented this error?',
          'If the model assigned "performance" to an item about "billing latency" — and you have separate categories for performance and billing — the solution is usually to add language to the billing category description that explicitly includes payment-related slowness, and to add language to the performance category that excludes billing-related delays.',
          'Make one change at a time, re-run on a small sample, and check whether the target cases improved without causing regressions elsewhere. Prompt iteration is quick — it does not require retraining anything — but it benefits from the same discipline as any other A/B-style comparison: change one variable, measure the effect.',
        ],
      },
    ],
  },
  {
    slug: 'multilingual-customer-feedback-analysis',
    title: 'Multilingual Customer Feedback Analysis: What Actually Works',
    excerpt: 'If your customers write in more than one language, your feedback analysis tool needs to handle that honestly. VADER is English-only. TF-IDF clustering works across languages but mixes them together. LLMs with multilingual capability can help — but the approach depends on the model you choose and the languages involved. Here is a clear-eyed look at the options.',
    date: '2026-09-19',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['NLP', 'Multilingual', 'AI', 'Feedback Analysis'],
    seoTitle: 'Multilingual Customer Feedback Analysis: What Actually Works | Rereflect',
    seoDescription: 'A practical look at analyzing customer feedback in multiple languages — what VADER, TF-IDF, and LLMs can and cannot do, and how to configure Rereflect for multilingual feedback corpora.',
    sections: [
      {
        heading: 'The multilingual problem is harder than it looks',
        content: [
          'Most feedback analysis tools are built and benchmarked on English text. If a meaningful fraction of your customers write in other languages, you are typically using a tool that was not designed for your actual data — and accuracy will be lower than you might assume.',
          'The multilingual problem has several dimensions. Sentiment lexicons are language-specific. Keyword lists and category examples need to be in the languages of your feedback to match. Tokenization and morphology work differently across languages. And the distribution of good multilingual models varies — some languages have much better coverage than others in existing model training data.',
          'There is no configuration that makes multilingual analysis as seamless as English-only analysis. But there are practical approaches that work well enough for the most common use cases.',
        ],
      },
      {
        heading: 'What VADER can and cannot do across languages',
        content: [
          'VADER is an English lexicon. Its sentiment scores are derived from English words and English grammatical rules. Feeding non-English text to VADER produces unreliable results:',
        ],
        listItems: [
          'Unknown tokens — words not in the English lexicon score as neutral. A Spanish negative sentence full of Spanish words scores near zero (neutral) because VADER has no opinion about any of them.',
          'False positives from cognates — Spanish, French, and Italian share many words with English cognates. "Fatal error" in French reads as English "fatal error" to VADER. This sometimes produces accidental correct scores, but inconsistently.',
          'No grammatical rule application — VADER\'s negation and modifier rules are built for English grammar. They do not apply to languages with different syntactic structures.',
        ],
        content2: [
          'If a significant fraction of your feedback is non-English, VADER\'s sentiment scores for those items will be close to neutral regardless of actual content. You can filter your VADER-based sentiment dashboards to English items, or treat the neutral score on non-English items as a signal that sentiment was not computed, rather than that the feedback was genuinely neutral.',
        ],
      },
      {
        heading: 'TF-IDF clustering across languages',
        content: [
          'TF-IDF clustering is language-agnostic in the sense that it works on tokens regardless of language. The practical problem is that it will create language-segregated clusters: Spanish feedback will cluster with other Spanish feedback about the same topic, but that Spanish cluster will be separate from the English cluster about the same topic — because the vocabulary is different.',
          'For a multilingual corpus, this means your topic clusters reflect language as much as they reflect theme. A single problem reported by English-speaking and Spanish-speaking customers will appear as two separate clusters rather than one. This is not wrong — it is an accurate reflection of the vocabulary distance — but it means you need to be aware that similar-sized clusters in different languages may represent the same underlying issue.',
          'If you want cross-language topic coherence, the practical options are either to translate all feedback to a common language before clustering, or to use a multilingual embedding model that maps text in different languages to a shared vector space before clustering. Rereflect\'s current TF-IDF implementation does not handle this automatically.',
        ],
      },
      {
        heading: 'Using an LLM for multilingual categorization',
        content: [
          'The most practical path to multilingual feedback categorization is a language model with strong multilingual capability. Most frontier hosted models (OpenAI, Anthropic, Google) handle a broad range of languages well, including common European languages and major Asian languages. Less common languages may have significantly lower accuracy.',
          'When using an LLM for multilingual classification, a few configuration choices matter:',
        ],
        listItems: [
          'Write category descriptions in English — most multilingual models have their strongest reasoning in English. Category descriptions in English work well even when the feedback text is in another language.',
          'Instruct the model to classify regardless of language — explicitly tell the model in the prompt that feedback may be in any language and that it should classify based on meaning, not language of origin.',
          'Check coverage for your specific languages — if you have significant feedback volume in a language you are not sure the model handles well, test it against a manually labeled sample before relying on it.',
          'Local models vary widely — Ollama and other local model runners offer models with different language coverage. A model like Mistral or Llama 3 may handle major European languages reasonably well; coverage for less common languages is usually weaker.',
        ],
      },
      {
        heading: 'A practical configuration for mixed-language feedback',
        content: [
          'If your feedback is primarily English with some non-English items, the simplest approach is to let VADER handle English items and flag non-English items for LLM-based sentiment as well as categorization. Most LLMs can detect the language of an item and adjust accordingly.',
          'If your feedback is substantially multilingual — say, 30% or more non-English — it is worth investing in a multilingual embedding approach for clustering, or committing to LLM-based processing for all categorization and sentiment tasks. The keyword pre-filter will be less effective because your keyword lists are likely English-only; relying more heavily on the LLM layer compensates.',
          'The honest position is that multilingual feedback analysis is more difficult than English-only, and the gap in accuracy is real. The most important thing is to know which items were analyzed in which way, so you can interpret your dashboards accordingly and not treat a high neutral-sentiment rate in non-English items as a product signal when it is actually an analysis gap.',
        ],
      },
    ],
  },
  {
    slug: 'detect-urgent-feedback-automatically',
    title: 'Detecting Urgent Feedback Automatically: Signals, Heuristics, and Limits',
    excerpt: 'Some feedback needs to be read today, not at the next weekly review. Rereflect\'s urgency detection layer flags items that show signs of churn risk, critical failures, escalation language, or other high-priority signals. This post explains what those signals are, how the detection works, and where it will miss things.',
    date: '2026-09-23',
    status: 'scheduled',
    readTime: '7 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'Urgency Detection', 'Churn Risk', 'Feedback Analysis'],
    seoTitle: 'Detect Urgent Customer Feedback Automatically: Signals and Limits | Rereflect',
    seoDescription: 'How Rereflect automatically detects urgent customer feedback using sentiment signals, keyword heuristics, and LLM-based reasoning — plus an honest look at what it misses.',
    sections: [
      {
        heading: 'The cost of missing urgent feedback',
        content: [
          'The majority of customer feedback can wait. A suggestion about a minor UI preference, a positive note about a feature, a low-priority question — none of these need immediate attention. But some feedback represents an actively unhappy customer, a critical failure, or an imminent churn risk. That subset has a short window. A customer signaling that they are about to leave may be reachable today and gone next week.',
          'Manual review at volume does not catch these reliably. By the time a weekly feedback review happens, the urgent items are buried under everything else that came in that week. Automatic urgency detection is an attempt to surface the subset that should not wait — so it can be routed to someone who can act on it quickly.',
        ],
      },
      {
        heading: 'The signals Rereflect looks for',
        content: [
          'Urgency is not a single thing. Rereflect\'s urgency detection looks for a combination of signals, each of which increases the probability that an item is high-priority:',
        ],
        listItems: [
          'Strong negative sentiment — a compound VADER score in the very negative range is correlated with urgent feedback, though not deterministic. Most very negative feedback is urgent; not all urgent feedback is maximally negative.',
          'Churn language — explicit phrases that signal intent to leave: "canceling," "switching to," "looking at alternatives," "not worth it anymore," "going to ask for a refund." These are strong signals when present.',
          'Escalation language — words and phrases that indicate the customer feels the issue is unresolved and escalating: "unacceptable," "this has been going on for weeks," "already contacted support," "need to speak to someone."',
          'Critical failure vocabulary — terms indicating that something is broken in a way that blocks the customer\'s work: "can\'t access," "lost data," "completely broken," "production is down."',
          'SLA or compliance references — mentions of contractual obligations, SLA terms, or compliance requirements often indicate that the impact of a failure is not just inconvenience.',
        ],
        content2: [
          'When an LLM is configured, Rereflect uses it to reason about urgency more holistically — considering the combination of signals and the overall context of the feedback, rather than checking for individual keywords. The LLM can identify urgency in items that do not use the exact phrases on a keyword list but clearly describe a critical situation.',
        ],
      },
      {
        heading: 'How the detection pipeline works',
        content: [
          'Urgency detection runs as part of the standard analysis pipeline on each new feedback item. The process:',
        ],
        listItems: [
          'Sentiment pre-filter — items with strong negative sentiment are weighted more heavily as urgency candidates. Items with neutral or positive sentiment can still be flagged, but face a higher bar.',
          'Keyword scan — the item is scanned for urgency-related vocabulary across the signal categories described above. Matches are weighted by signal type, with churn language and critical failure vocabulary scoring highest.',
          'LLM reasoning (if configured) — the LLM receives the feedback text and a description of urgency criteria, and returns a binary flag plus a brief reason. This catches cases that keyword matching misses.',
          'Final flag — items meeting the threshold are marked as urgent in the database and surfaced in the urgent feedback dashboard.',
        ],
        content2: [
          'The threshold for flagging is intentionally calibrated toward sensitivity (catching more) over specificity (fewer false positives). The cost of missing a genuinely urgent item is higher than the cost of reviewing an item that turns out to be fine. The trade-off means your urgent feedback queue will contain items that turn out not to need immediate action — but it will catch most of the ones that do.',
        ],
      },
      {
        heading: 'Where urgency detection fails',
        content: [
          'Honest enumeration of failure modes:',
        ],
        listItems: [
          'Polite frustration — some customers describe serious problems in calm, measured language. An item that says "I am becoming concerned about the reliability of this feature as it has failed three times this week" is urgent, but contains no keywords that trigger detection and reads as mildly negative in sentiment.',
          'Domain-specific criticality — a phrase that signals urgency in your product may be neutral in a general model. If "retry limit exceeded" means something is broken in your product, that needs to be in your urgency category description.',
          'Non-English items without LLM — keyword lists are English-centric. Non-English urgent feedback will be missed by the keyword layer if the LLM is not configured.',
          'Delayed urgency — some items describe slow-building problems ("this has been getting worse over the past few months") that are urgent in the sense that they represent a churning customer, but do not contain acute language. These are harder to catch without understanding the customer\'s history.',
        ],
        content2: [
          'Urgency detection is a filter that makes the urgent item review process faster — it does not replace it. The goal is to reduce the fraction of feedback you need to review immediately to a manageable subset, while catching most of the genuinely urgent items.',
        ],
      },
      {
        heading: 'Tuning urgency for your product',
        content: [
          'The default urgency signals are reasonable starting points, but "urgent" is product-specific. A data loss event is always urgent. Whether a feature request marked as blocking is urgent depends on who the customer is and your support policies.',
          'Rereflect\'s custom urgency configuration lets you describe what urgent means for your business. The description feeds into the LLM classification prompt, which means you can include product-specific signals ("any mention of data export failure is urgent") and exclusions ("billing questions are not urgent unless the customer mentions cancellation").',
          'Review your false negatives — items that should have been flagged but were not — periodically and use them to refine the urgency description. A few targeted additions to the description usually cover the systematic gaps.',
        ],
      },
    ],
  },
  {
    slug: 'feature-request-extraction-with-ai',
    title: 'Feature Request Extraction With AI: Surfacing What Customers Actually Want',
    excerpt: 'Feature requests are scattered throughout customer feedback — mixed into support tickets, embedded in complaints, and phrased in dozens of different ways. AI-based extraction identifies and aggregates them so your roadmap is grounded in what customers are actually asking for, not what you remember hearing. This post covers how the extraction works and how to use the output.',
    date: '2026-09-28',
    status: 'scheduled',
    readTime: '8 min read',
    author: 'Rereflect Team',
    tags: ['AI', 'Feature Requests', 'Product Management', 'Feedback Analysis'],
    seoTitle: 'Feature Request Extraction With AI: Surfacing Customer Requests | Rereflect',
    seoDescription: 'How Rereflect uses AI to extract and categorize feature requests from customer feedback — turning scattered asks across support tickets, surveys, and reviews into an aggregated, prioritizable list.',
    sections: [
      {
        heading: 'Why feature requests are hard to collect manually',
        content: [
          'Feature requests rarely arrive clearly labeled. A customer submitting a support ticket is usually describing a problem, not making a feature request — but embedded in that problem description is often an implicit request. "I wish I could filter this table by date" is a feature request. "Can I export just the items from last month?" is a feature request. "Every week I have to manually calculate this" is a feature request.',
          'At low volume, a human reading every ticket can pick these up. At scale, they get lost. The result is that product teams tend to act on the feature requests that were loudly and explicitly stated — by the customers who sent the most emails or showed up in the most calls — rather than on the requests that were most frequently implied across the full customer base.',
          'AI-based feature request extraction tries to surface the full distribution: what is being requested, how often, and in what context.',
        ],
      },
      {
        heading: 'What extraction identifies',
        content: [
          'Rereflect\'s feature request extraction looks for two categories of signal:',
        ],
        listItems: [
          'Explicit requests — direct statements of desire: "I\'d love to be able to...", "Is there a way to...", "It would be great if...", "Can you add...", "We need...". These are the easiest to catch because the language is unambiguous.',
          'Implicit requests — descriptions of workarounds, frustrations with missing functionality, or comparisons to other tools: "Right now I have to export to spreadsheet and do this manually," "Tool X has this and it saves us hours," "Every time I need to do X I have to leave the app." These require more inference to identify as feature requests.',
        ],
        content2: [
          'A keyword system catches explicit requests reasonably well. Implicit requests require a language model — recognizing that "I have to do this manually every week" contains a feature request requires understanding the context of what "this" refers to and inferring that automation is being implicitly requested.',
          'When no LLM is configured, Rereflect extracts explicit requests through keyword matching. With an LLM configured, it also captures the implicit requests that keyword matching misses.',
        ],
      },
      {
        heading: 'How extraction maps to categories',
        content: [
          'Raw feature request extraction produces a set of items that contain requests. To be useful for roadmap planning, those items need to be grouped and counted — which is where the feature request categorization taxonomy comes in.',
          'Your configured feature request categories define the buckets that requests get sorted into. If your taxonomy has a category for "reporting and analytics," requests like "I want to be able to export charts," "add a monthly summary report," and "we need aggregate views by segment" all land in that bucket. The count in that bucket across your full feedback history gives you a frequency signal: this is how many customers, across what time period, have requested something in this area.',
          'The quality of this aggregation depends on the same factors as any categorization: how clearly your categories are defined and how distinctly they are separated. A catch-all "integrations" category that includes both "connect to Salesforce" and "webhook support" produces an inflated count that obscures which specific integration type is being requested.',
        ],
      },
      {
        heading: 'Turning extracted requests into roadmap signal',
        content: [
          'Volume is a starting point, not a conclusion. A feature requested by 50 customers in a given month is not automatically more important than one requested by 5 — it depends who those customers are, what their request implies about your product strategy, and whether you can build it.',
          'More useful ways to read the extracted data:',
        ],
        listItems: [
          'Volume combined with customer segment — requests from customers in a specific tier, industry, or use-case cluster often reveal underserved segments more than raw count does.',
          'Requests co-occurring with churn signals — a feature request accompanied by urgency signals or negative sentiment is a different kind of signal than a neutral wish list item. "We will leave if X isn\'t available" deserves different treatment than "it would be nice if X existed."',
          'Velocity over time — a category of requests that is growing week over week represents a growing need. A stable category represents a chronic but not accelerating gap.',
          'Requests about the same area as pain points — if your most complained-about category and your most requested feature category overlap, you have high-confidence signal about where to focus.',
        ],
      },
      {
        heading: 'What extraction gets wrong',
        content: [
          'Feature request extraction is not perfect. Common failure modes:',
        ],
        listItems: [
          'Requests framed as questions — "Is there a way to do X?" is a feature request if X does not exist, but a support question if it does. The extraction layer may not know which is the case.',
          'Requests for things that already exist — customers sometimes request features that the product already has. These will be extracted as feature requests when they may actually be discoverability or documentation problems.',
          'Vague requests — "make it easier to use" or "improve the dashboard" express dissatisfaction but do not identify a specific request. These will be captured but cannot be meaningfully categorized.',
          'Compound requests — a paragraph that contains three separate feature asks may have the most prominent one extracted while the others are missed.',
        ],
        content2: [
          'None of these failure modes make the extraction useless — they mean you should treat the output as a distribution with noise rather than a complete and accurate enumeration. The high-frequency categories are real signal; the long tail deserves more skepticism.',
          'Periodically review a sample of the extracted items in your top categories and check whether they actually belong there. If they do, the count is meaningful. If the category is attracting a lot of mismatches, the description needs work.',
        ],
      },
    ],
  },
];
