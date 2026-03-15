"""
Generates English lesson content via Groq (llama-3.3-70b-versatile).
7 lesson types, rotated evenly.
"""

import os
import re
import json
import random
from groq import Groq
from src.logger import setup_logger

logger = setup_logger("content")

POST_TYPES = [
    "vocabulary",
    "grammar",
    "idioms",
    "pronunciation",
    "common_mistakes",
    "phrases",
    "fun_fact",
    "slang",
    "business_english",
    "phrasal_verbs",
    "confusing_words",
    "writing_tips",
    "prepositions",
    "collocations",
    "american_vs_british",
    "word_origins",
    "synonyms_nuance",
    "sentence_starters",
    "linking_words",
    "formal_vs_informal",
    "numbers_and_dates",
    "questions_forms",
    "modal_verbs",
    "passive_voice",
    "conditionals",
    "reported_speech",
    "articles",
    "punctuation",
    "word_families",
    "expressions_with_time",
    "body_language_vocab",
    "food_and_cooking",
    "travel_english",
    "email_phrases",
    "small_talk",
]

SYSTEM = (
    "You are an expert English teacher creating viral educational Telegram content. "
    "Content must be clear, engaging, and immediately useful. "
    "Use emojis naturally. Respond with valid JSON ONLY — no markdown fences, no extra text."
)

PROMPTS = {

"vocabulary": """Pick ONE advanced-but-useful English word learners should know.
Not too basic, not too obscure. Genuinely useful in daily life or work.

Return ONLY this JSON:
{
  "post_type": "vocabulary",
  "subject": "<the word>",
  "image_keywords": ["<vivid real-world scene>", "<context or emotion>", "<visual metaphor>"],
  "content": "📖 Word of the Day\\n\\n✨ [WORD] /phonetic/ (part of speech)\\n\\n💡 Meaning: one clear definition\\n\\n📌 Examples:\\n→ sentence 1\\n→ sentence 2\\n→ sentence 3\\n\\n🔁 Synonyms: w1 • w2 • w3\\n\\n🧠 Memory Tip: clever trick to never forget it\\n\\n#WordOfTheDay #Vocabulary #LearnEnglish"
}""",

"grammar": """Teach ONE grammar rule that confuses intermediate learners.
Clear right vs wrong examples.

Return ONLY this JSON:
{
  "post_type": "grammar",
  "subject": "<rule name>",
  "image_keywords": ["<scene for the topic>", "<keyword2>", "<keyword3>"],
  "content": "📐 Grammar Lesson\\n\\n📌 Topic: [Rule]\\n\\n📖 The Rule:\\n[1-2 sentence explanation]\\n\\n✅ Correct:\\n→ example 1\\n→ example 2\\n\\n❌ Wrong:\\n→ mistake 1\\n→ mistake 2\\n\\n💡 Quick Trick: one way to remember this\\n\\n#EnglishGrammar #GrammarTips #LearnEnglish"
}""",

"idioms": """Teach ONE English idiom native speakers actually use. Surprising or funny origin preferred.

Return ONLY this JSON:
{
  "post_type": "idioms",
  "subject": "<the idiom>",
  "image_keywords": ["<literal visual of idiom words>", "<metaphorical scene>", "<everyday usage context>"],
  "content": "🗣 English Idiom\\n\\n💬 \\"[THE IDIOM]\\"\\n\\n📝 Meaning: plain English meaning\\n\\n🏛 Origin: 1-2 sentences on where it came from\\n\\n✅ In use:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n⚡ Similar: idiom1 • idiom2\\n\\n#EnglishIdioms #LearnEnglish #Idioms"
}""",

"pronunciation": """Pick ONE commonly mispronounced word — spelling that tricks people.

Return ONLY this JSON:
{
  "post_type": "pronunciation",
  "subject": "<the word>",
  "image_keywords": ["<visual of what the word means>", "<usage context>", "<person speaking>"],
  "content": "🎤 Pronunciation Fix\\n\\n🔤 Word: [WORD]\\n\\n❌ People say: [wrong]\\n✅ Correct: /phonetic/\\n\\n👄 How to say it:\\n[step-by-step mouth tip]\\n\\n📝 Same pattern:\\n→ word1 /ph/\\n→ word2 /ph/\\n→ word3 /ph/\\n\\n🧠 Trick: [clever memory tip]\\n\\n#Pronunciation #EnglishTips #LearnEnglish"
}""",

"common_mistakes": """Teach ONE English mistake even advanced learners make. Wrong version sounds natural to non-natives.

Return ONLY this JSON:
{
  "post_type": "common_mistakes",
  "subject": "<e.g. Make vs Do>",
  "image_keywords": ["<context scene>", "<real-world situation>", "<keyword3>"],
  "content": "⚠️ Common English Mistake\\n\\n🚫 Mistake: [what people get wrong]\\n\\n❌ Wrong:\\n→ sentence 1\\n→ sentence 2\\n\\n✅ Correct:\\n→ sentence 1\\n→ sentence 2\\n\\n📖 Why? [clear explanation]\\n\\n💡 Rule: [one rule that fixes it forever]\\n\\n#CommonMistakes #EnglishTips #LearnEnglish"
}""",

"phrases": """Teach 5 natural phrases on ONE useful everyday theme. Real English, not textbook.

Return ONLY this JSON:
{
  "post_type": "phrases",
  "subject": "<theme e.g. Polite Disagreement>",
  "image_keywords": ["<scene matching theme>", "<people in that situation>", "<environment>"],
  "content": "💬 5 English Phrases\\n\\n🎯 Theme: [Theme]\\n\\n1️⃣ \\"phrase\\"\\n   💭 When: explanation\\n\\n2️⃣ \\"phrase\\"\\n   💭 When: explanation\\n\\n3️⃣ \\"phrase\\"\\n   💭 When: explanation\\n\\n4️⃣ \\"phrase\\"\\n   💭 When: explanation\\n\\n5️⃣ \\"phrase\\"\\n   💭 When: explanation\\n\\n✏️ Try one today!\\n\\n#EnglishPhrases #LearnEnglish #DailyEnglish"
}""",

"fun_fact": """Share ONE surprising fact about English — word origins, grammar quirks, history. Make learners say "wow!"

Return ONLY this JSON:
{
  "post_type": "fun_fact",
  "subject": "<short description>",
  "image_keywords": ["<vivid visual for the fact>", "<historical or concept scene>", "<symbolic image>"],
  "content": "🤯 English Fun Fact\\n\\n❓ Did you know...\\n\\n[2-3 sentences explaining the fact engagingly]\\n\\n🔍 Why it matters:\\n[1-2 sentences for learners]\\n\\n💬 Example:\\n→ [fact in action]\\n\\n🧠 Bonus: [one extra related fact]\\n\\n#EnglishFacts #DidYouKnow #LearnEnglish"
}""",


"slang": """Teach ONE piece of English slang or informal expression that young people and natives actually use today.

Return ONLY this JSON:
{
  "post_type": "slang",
  "subject": "<the slang word/phrase>",
  "image_keywords": ["<casual social scene>", "<youth culture context>", "<visual metaphor>"],
  "content": "😎 English Slang\\n\\n🔥 Expression: \\\"[SLANG]\\\"\\n\\n📝 Meaning: plain English meaning\\n\\n⚠️ Formality: [when to use / when NOT to use]\\n\\n✅ In real life:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n🔄 Formal version: [how to say it formally]\\n\\n#EnglishSlang #InformalEnglish #LearnEnglish"
}""",

"business_english": """Teach ONE Business English phrase, expression or concept professionals use in emails, meetings, or the workplace.

Return ONLY this JSON:
{
  "post_type": "business_english",
  "subject": "<the phrase or concept>",
  "image_keywords": ["<professional office scene>", "<business meeting context>", "<workplace visual>"],
  "content": "💼 Business English\\n\\n📌 Expression: \\\"[PHRASE]\\\"\\n\\n📝 Meaning: what it means in business context\\n\\n✅ Use it in:\\n→ email example\\n→ meeting example\\n→ presentation example\\n\\n⚠️ Avoid: [common mistake with this phrase]\\n\\n💡 Pro Tip: [one tip to sound more professional]\\n\\n#BusinessEnglish #ProfessionalEnglish #LearnEnglish"
}""",

"phrasal_verbs": """Teach ONE commonly used English phrasal verb. Focus on ones with surprising or non-obvious meanings.

Return ONLY this JSON:
{
  "post_type": "phrasal_verbs",
  "subject": "<the phrasal verb>",
  "image_keywords": ["<visual scene of the literal words>", "<context of actual meaning>", "<everyday situation>"],
  "content": "🔗 Phrasal Verb\\n\\n💬 \\\"[PHRASAL VERB]\\\"\\n\\n📝 Meaning: clear definition\\n\\n✅ Examples:\\n→ sentence 1\\n→ sentence 2\\n→ sentence 3\\n\\n⚡ Related phrasal verbs:\\n→ [similar1] = meaning\\n→ [similar2] = meaning\\n\\n🧠 Memory Tip: trick to remember it\\n\\n#PhrasalVerbs #EnglishTips #LearnEnglish"
}""",

"confusing_words": """Pick TWO English words that learners constantly confuse with each other (e.g. affect/effect, lay/lie, fewer/less).

Return ONLY this JSON:
{
  "post_type": "confusing_words",
  "subject": "<word1> vs <word2>",
  "image_keywords": ["<visual contrast scene>", "<context of word1>", "<context of word2>"],
  "content": "🤔 Confusing Words\\n\\n⚔️ [WORD1] vs [WORD2]\\n\\n📘 [WORD1]:\\n→ Meaning: definition\\n→ Example: sentence\\n\\n📗 [WORD2]:\\n→ Meaning: definition\\n→ Example: sentence\\n\\n🔑 The Trick:\\n[one clear rule that tells them apart forever]\\n\\n✅ Quick test:\\n→ \\\"___ sentence with blank\\\" → answer: [WORD1 or WORD2]\\n\\n#ConfusingWords #EnglishGrammar #LearnEnglish"
}""",


"writing_tips": """Teach ONE practical English writing tip that makes writing clearer, more professional, or more natural.

Return ONLY this JSON:
{
  "post_type": "writing_tips",
  "subject": "<the writing tip>",
  "image_keywords": ["<person writing scene>", "<professional writing context>", "<notebook or laptop>"],
  "content": "✍️ Writing Tip\\n\\n📌 Tip: [TITLE]\\n\\n❌ Weak writing:\\n→ example 1\\n→ example 2\\n\\n✅ Strong writing:\\n→ example 1\\n→ example 2\\n\\n📖 Why it works:\\n[1-2 sentence explanation]\\n\\n💡 Rule: [one rule to apply immediately]\\n\\n#WritingTips #EnglishWriting #LearnEnglish"
}""",

"prepositions": """Teach ONE tricky English preposition usage that confuses learners — focus on in/on/at, or verb+preposition combos.

Return ONLY this JSON:
{
  "post_type": "prepositions",
  "subject": "<e.g. in vs on vs at for time>",
  "image_keywords": ["<visual scene for the preposition>", "<spatial or time context>", "<real-life situation>"],
  "content": "📍 Prepositions\\n\\n🎯 Focus: [TOPIC]\\n\\n📘 The Rule:\\n[clear 1-2 sentence explanation]\\n\\n✅ Correct use:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n❌ Common mistakes:\\n→ wrong example 1\\n→ wrong example 2\\n\\n🧠 Memory Trick: [one trick to remember it]\\n\\n#Prepositions #EnglishGrammar #LearnEnglish"
}""",

"collocations": """Teach ONE group of English collocations — words that naturally go together. Focus on verb+noun or adjective+noun combos natives use automatically.

Return ONLY this JSON:
{
  "post_type": "collocations",
  "subject": "<e.g. make vs do collocations>",
  "image_keywords": ["<scene matching the collocation theme>", "<everyday activity>", "<natural context>"],
  "content": "🔗 English Collocations\\n\\n🎯 Theme: [THEME]\\n\\n✅ Natural combinations:\\n→ [word1 + word2] — example sentence\\n→ [word1 + word3] — example sentence\\n→ [word1 + word4] — example sentence\\n→ [word1 + word5] — example sentence\\n\\n❌ Unnatural (avoid):\\n→ wrong combo 1\\n→ wrong combo 2\\n\\n💡 Why it matters: natives use these automatically — learners must memorize them\\n\\n#Collocations #EnglishFluency #LearnEnglish"
}""",

"american_vs_british": """Teach ONE clear difference between American and British English — vocabulary, spelling, or pronunciation.

Return ONLY this JSON:
{
  "post_type": "american_vs_british",
  "subject": "<the difference topic>",
  "image_keywords": ["<American flag or city>", "<British flag or city>", "<visual of the word/concept>"],
  "content": "🇺🇸 vs 🇬🇧 American vs British English\\n\\n📌 Topic: [TOPIC]\\n\\n🇺🇸 American:\\n→ word/phrase 1\\n→ word/phrase 2\\n→ word/phrase 3\\n\\n🇬🇧 British:\\n→ equivalent 1\\n→ equivalent 2\\n→ equivalent 3\\n\\n💬 Example sentence:\\n🇺🇸 [American version]\\n🇬🇧 [British version]\\n\\n💡 Tip: [which to use and when]\\n\\n#AmericanEnglish #BritishEnglish #LearnEnglish"
}""",


"word_origins": """Share the surprising etymology of ONE English word — where it came from and how its meaning evolved.

Return ONLY this JSON:
{
  "post_type": "word_origins",
  "subject": "<the word>",
  "image_keywords": ["<historical scene>", "<origin culture or place>", "<modern usage context>"],
  "content": "🏛 Word Origin\\n\\n📖 Word: [WORD]\\n\\n🗺 Origin: [language/culture it came from]\\n\\n📜 History:\\n[2-3 sentences on how meaning evolved]\\n\\n✅ Today we use it to mean:\\n→ example 1\\n→ example 2\\n\\n🤯 Surprising fact: [one wow detail]\\n\\n#Etymology #WordOrigins #LearnEnglish"
}""",

"synonyms_nuance": """Teach the subtle differences between 3-4 English synonyms that learners treat as identical but natives use differently.

Return ONLY this JSON:
{
  "post_type": "synonyms_nuance",
  "subject": "<e.g. big vs large vs huge vs enormous>",
  "image_keywords": ["<visual showing scale or contrast>", "<usage context>", "<comparison scene>"],
  "content": "🎭 Synonyms — Spot the Difference\\n\\n🎯 Words: [WORD1] • [WORD2] • [WORD3]\\n\\n📘 [WORD1]: [nuance + example]\\n📗 [WORD2]: [nuance + example]\\n📙 [WORD3]: [nuance + example]\\n\\n⚡ Quick rule:\\n[one sentence that captures the key difference]\\n\\n✅ Native would say:\\n→ [natural example]\\n❌ Not:\\n→ [unnatural example]\\n\\n#Synonyms #EnglishVocabulary #LearnEnglish"
}""",

"sentence_starters": """Teach 6 natural ways to start sentences in English — for writing, speaking, or presentations.

Return ONLY this JSON:
{
  "post_type": "sentence_starters",
  "subject": "<theme e.g. Giving Your Opinion>",
  "image_keywords": ["<person speaking confidently>", "<writing or presenting scene>", "<communication context>"],
  "content": "🚀 Sentence Starters\\n\\n🎯 Theme: [THEME]\\n\\n1️⃣ \\\"[Starter]...\\\" — [when to use]\\n2️⃣ \\\"[Starter]...\\\" — [when to use]\\n3️⃣ \\\"[Starter]...\\\" — [when to use]\\n4️⃣ \\\"[Starter]...\\\" — [when to use]\\n5️⃣ \\\"[Starter]...\\\" — [when to use]\\n6️⃣ \\\"[Starter]...\\\" — [when to use]\\n\\n✏️ Try one in your next message!\\n\\n#EnglishSpeaking #SentenceStarters #LearnEnglish"
}""",

"linking_words": """Teach ONE group of English linking words/connectors with clear examples of how to use them naturally.

Return ONLY this JSON:
{
  "post_type": "linking_words",
  "subject": "<e.g. Contrast connectors: however, nevertheless, although>",
  "image_keywords": ["<connected ideas visual>", "<writing or speech context>", "<flow and structure scene>"],
  "content": "🔗 Linking Words\\n\\n🎯 Function: [FUNCTION e.g. Adding contrast]\\n\\n📌 Words: [word1] • [word2] • [word3]\\n\\n📘 [word1]:\\n→ rule: [position in sentence]\\n→ example sentence\\n\\n📗 [word2]:\\n→ rule: [position in sentence]\\n→ example sentence\\n\\n📙 [word3]:\\n→ rule: [position in sentence]\\n→ example sentence\\n\\n💡 Key difference: [what makes each one unique]\\n\\n#LinkingWords #EnglishWriting #LearnEnglish"
}""",

"formal_vs_informal": """Show ONE concept expressed both formally and informally in English — emails, requests, complaints, etc.

Return ONLY this JSON:
{
  "post_type": "formal_vs_informal",
  "subject": "<e.g. Making a Request>",
  "image_keywords": ["<formal office scene>", "<casual friends scene>", "<contrast visual>"],
  "content": "👔 Formal vs 😊 Informal\\n\\n🎯 Situation: [SITUATION]\\n\\n😊 Informal:\\n→ \\\"[example 1]\\\"\\n→ \\\"[example 2]\\\"\\n→ \\\"[example 3]\\\"\\n\\n👔 Formal:\\n→ \\\"[example 1]\\\"\\n→ \\\"[example 2]\\\"\\n→ \\\"[example 3]\\\"\\n\\n💡 Rule: [when to use each]\\n\\n#FormalEnglish #InformalEnglish #LearnEnglish"
}""",

"numbers_and_dates": """Teach ONE tricky aspect of how English speakers say numbers, dates, times, prices, or statistics.

Return ONLY this JSON:
{
  "post_type": "numbers_and_dates",
  "subject": "<e.g. How to say years and decades>",
  "image_keywords": ["<calendar or clock scene>", "<numbers visual>", "<real-life context>"],
  "content": "🔢 Numbers in English\\n\\n🎯 Topic: [TOPIC]\\n\\n📖 The Rule:\\n[clear explanation]\\n\\n✅ Correct:\\n→ [number/date] = say it as \\\"[pronunciation]\\\"\\n→ [number/date] = say it as \\\"[pronunciation]\\\"\\n→ [number/date] = say it as \\\"[pronunciation]\\\"\\n\\n❌ Common mistakes:\\n→ wrong example 1\\n→ wrong example 2\\n\\n💡 Trick: [memory aid]\\n\\n#EnglishNumbers #LearnEnglish #EnglishTips"
}""",

"questions_forms": """Teach ONE aspect of forming questions in English naturally — question tags, indirect questions, negative questions, etc.

Return ONLY this JSON:
{
  "post_type": "questions_forms",
  "subject": "<e.g. Indirect Questions>",
  "image_keywords": ["<conversation scene>", "<question mark visual>", "<people talking>"],
  "content": "❓ Asking Questions in English\\n\\n🎯 Topic: [TOPIC]\\n\\n📖 The Rule:\\n[clear 1-2 sentence explanation]\\n\\n✅ Natural way:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n❌ Unnatural / wrong:\\n→ mistake 1\\n→ mistake 2\\n\\n💡 When to use: [context and tips]\\n\\n#EnglishQuestions #EnglishGrammar #LearnEnglish"
}""",

"modal_verbs": """Teach ONE modal verb (can/could/should/must/might/would/shall/ought to) with all its uses and nuances.

Return ONLY this JSON:
{
  "post_type": "modal_verbs",
  "subject": "<the modal verb>",
  "image_keywords": ["<scene showing possibility or obligation>", "<real-life situation>", "<person deciding>"],
  "content": "⚙️ Modal Verb: [MODAL]\\n\\n📌 Main uses:\\n\\n1️⃣ [Use 1 e.g. Ability]:\\n→ example sentence\\n\\n2️⃣ [Use 2 e.g. Permission]:\\n→ example sentence\\n\\n3️⃣ [Use 3 e.g. Possibility]:\\n→ example sentence\\n\\n⚠️ Don't confuse:\\n[MODAL] vs [similar modal] — key difference\\n\\n✅ Natural examples:\\n→ sentence 1\\n→ sentence 2\\n\\n#ModalVerbs #EnglishGrammar #LearnEnglish"
}""",

"passive_voice": """Teach when and how to use passive voice in English naturally — when it helps vs when to avoid it.

Return ONLY this JSON:
{
  "post_type": "passive_voice",
  "subject": "<specific passive voice topic>",
  "image_keywords": ["<action being done to something>", "<professional or news context>", "<transformation scene>"],
  "content": "🔄 Passive Voice\\n\\n📌 Topic: [TOPIC]\\n\\n📖 Structure: [be + past participle]\\n\\n✅ Use passive when:\\n→ reason 1 + example\\n→ reason 2 + example\\n\\n❌ Avoid passive when:\\n→ reason + example\\n\\n🔁 Active → Passive:\\n→ \\\"[active sentence]\\\"\\n→ \\\"[passive version]\\\"\\n\\n💡 Tip: [one practical tip]\\n\\n#PassiveVoice #EnglishGrammar #LearnEnglish"
}""",

"conditionals": """Teach ONE conditional form (0,1,2,3 or mixed) with clear real-life examples.

Return ONLY this JSON:
{
  "post_type": "conditionals",
  "subject": "<e.g. Second Conditional>",
  "image_keywords": ["<hypothetical or imaginary scene>", "<cause and effect visual>", "<decision making context>"],
  "content": "🔀 Conditionals\\n\\n🎯 Type: [TYPE] — [when to use it]\\n\\n📖 Structure:\\n[If + tense], [tense]\\n\\n✅ Examples:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n❌ Common mistake:\\n→ wrong version\\n✅ Correct:\\n→ fixed version\\n\\n💡 Remember: [one key tip]\\n\\n#Conditionals #EnglishGrammar #LearnEnglish"
}""",

"reported_speech": """Teach ONE aspect of reported speech in English — how to report what someone said, asked, or thought.

Return ONLY this JSON:
{
  "post_type": "reported_speech",
  "subject": "<e.g. Reporting Questions>",
  "image_keywords": ["<person relaying information>", "<conversation reporting scene>", "<speech bubble visual>"],
  "content": "💬 Reported Speech\\n\\n🎯 Topic: [TOPIC]\\n\\n📖 The Rule:\\n[clear explanation of tense backshift or structure]\\n\\n🔁 Direct → Reported:\\n→ Direct: \\\"[sentence]\\\"\\n   Reported: [reported version]\\n→ Direct: \\\"[sentence]\\\"\\n   Reported: [reported version]\\n→ Direct: \\\"[sentence]\\\"\\n   Reported: [reported version]\\n\\n⚠️ Watch out: [common mistake]\\n\\n#ReportedSpeech #EnglishGrammar #LearnEnglish"
}""",

"articles": """Teach ONE specific rule about using a/an/the in English — one of the hardest topics for learners.

Return ONLY this JSON:
{
  "post_type": "articles",
  "subject": "<specific article rule>",
  "image_keywords": ["<scene showing the/a context>", "<specific vs general visual>", "<real-life situation>"],
  "content": "📎 Articles: a / an / the\\n\\n🎯 Rule: [SPECIFIC RULE]\\n\\n📖 Explanation:\\n[2-3 sentence clear explanation]\\n\\n✅ Correct use:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n❌ Wrong:\\n→ mistake 1\\n→ mistake 2\\n\\n🧠 Trick: [memory aid]\\n\\n#Articles #EnglishGrammar #LearnEnglish"
}""",

"punctuation": """Teach ONE punctuation rule in English that learners often get wrong — commas, semicolons, apostrophes, colons, etc.

Return ONLY this JSON:
{
  "post_type": "punctuation",
  "subject": "<the punctuation mark and rule>",
  "image_keywords": ["<writing or editing scene>", "<text with punctuation visual>", "<professional document>"],
  "content": "✏️ Punctuation\\n\\n🎯 Focus: [PUNCTUATION MARK]\\n\\n📖 The Rule:\\n[clear explanation]\\n\\n✅ Correct:\\n→ example 1\\n→ example 2\\n→ example 3\\n\\n❌ Common mistakes:\\n→ wrong example 1\\n→ wrong example 2\\n\\n💡 Quick test: [simple way to know if you need it]\\n\\n#Punctuation #EnglishWriting #LearnEnglish"
}""",

"word_families": """Teach ONE English word family — noun, verb, adjective, adverb forms of the same root word.

Return ONLY this JSON:
{
  "post_type": "word_families",
  "subject": "<root word>",
  "image_keywords": ["<visual of the root concept>", "<usage context scene>", "<transformation or growth visual>"],
  "content": "🌳 Word Family\\n\\n🌱 Root: [ROOT WORD]\\n\\n📘 Noun: [word] — example sentence\\n📗 Verb: [word] — example sentence\\n📙 Adjective: [word] — example sentence\\n📕 Adverb: [word] — example sentence\\n\\n✅ All in one paragraph:\\n[short paragraph using all 4 forms naturally]\\n\\n💡 Why learn word families? [one sentence benefit]\\n\\n#WordFamilies #EnglishVocabulary #LearnEnglish"
}""",

"expressions_with_time": """Teach 5-6 natural English expressions about time that natives use constantly.

Return ONLY this JSON:
{
  "post_type": "expressions_with_time",
  "subject": "<theme e.g. Being Late or Early>",
  "image_keywords": ["<clock or time visual>", "<person rushing or waiting>", "<time concept scene>"],
  "content": "⏰ Time Expressions\\n\\n🎯 Theme: [THEME]\\n\\n1️⃣ \\\"[expression]\\\" — meaning + example\\n2️⃣ \\\"[expression]\\\" — meaning + example\\n3️⃣ \\\"[expression]\\\" — meaning + example\\n4️⃣ \\\"[expression]\\\" — meaning + example\\n5️⃣ \\\"[expression]\\\" — meaning + example\\n\\n✅ Use one today!\\n\\n#TimeExpressions #EnglishPhrases #LearnEnglish"
}""",

"body_language_vocab": """Teach vocabulary for describing body language, facial expressions, and gestures in English.

Return ONLY this JSON:
{
  "post_type": "body_language_vocab",
  "subject": "<theme e.g. Expressions of Surprise>",
  "image_keywords": ["<person showing the expression>", "<body language scene>", "<face or gesture visual>"],
  "content": "🤸 Body Language Vocabulary\\n\\n🎯 Theme: [THEME]\\n\\n1️⃣ [word/phrase] — what it looks like + example\\n2️⃣ [word/phrase] — what it looks like + example\\n3️⃣ [word/phrase] — what it looks like + example\\n4️⃣ [word/phrase] — what it looks like + example\\n5️⃣ [word/phrase] — what it looks like + example\\n\\n💡 Why it matters: understanding body language vocabulary helps you describe people naturally in English\\n\\n#BodyLanguage #EnglishVocabulary #LearnEnglish"
}""",

"food_and_cooking": """Teach English vocabulary related to food, cooking methods, or restaurant situations that learners need to know.

Return ONLY this JSON:
{
  "post_type": "food_and_cooking",
  "subject": "<specific food/cooking theme>",
  "image_keywords": ["<food or cooking scene>", "<kitchen or restaurant>", "<the specific food/method>"],
  "content": "🍽 Food & Cooking English\\n\\n🎯 Theme: [THEME]\\n\\n📖 Key vocabulary:\\n→ [word1]: meaning + example\\n→ [word2]: meaning + example\\n→ [word3]: meaning + example\\n→ [word4]: meaning + example\\n→ [word5]: meaning + example\\n\\n✅ Natural sentences:\\n→ example 1\\n→ example 2\\n\\n💡 Tip: [cultural or usage note]\\n\\n#FoodEnglish #CookingVocabulary #LearnEnglish"
}""",

"travel_english": """Teach practical English phrases and vocabulary for ONE travel situation — airport, hotel, asking for directions, etc.

Return ONLY this JSON:
{
  "post_type": "travel_english",
  "subject": "<specific travel situation>",
  "image_keywords": ["<travel scene>", "<airport hotel or street>", "<person navigating>"],
  "content": "✈️ Travel English\\n\\n🎯 Situation: [SITUATION]\\n\\n💬 Useful phrases:\\n1️⃣ \\\"[phrase]\\\" — when to use\\n2️⃣ \\\"[phrase]\\\" — when to use\\n3️⃣ \\\"[phrase]\\\" — when to use\\n4️⃣ \\\"[phrase]\\\" — when to use\\n5️⃣ \\\"[phrase]\\\" — when to use\\n\\n⚠️ Watch out: [one common tourist mistake]\\n\\n#TravelEnglish #EnglishPhrases #LearnEnglish"
}""",

"email_phrases": """Teach 5-6 professional email phrases for ONE specific email function — opening, closing, requesting, apologizing, etc.

Return ONLY this JSON:
{
  "post_type": "email_phrases",
  "subject": "<email function e.g. Making a Polite Request>",
  "image_keywords": ["<person writing email>", "<laptop and professional context>", "<office communication scene>"],
  "content": "📧 Email Phrases\\n\\n🎯 Function: [FUNCTION]\\n\\n✅ Professional phrases:\\n1️⃣ \\\"[phrase]\\\"\\n2️⃣ \\\"[phrase]\\\"\\n3️⃣ \\\"[phrase]\\\"\\n4️⃣ \\\"[phrase]\\\"\\n5️⃣ \\\"[phrase]\\\"\\n\\n📝 Full example:\\n[2-3 sentence email excerpt using one phrase]\\n\\n⚠️ Avoid: [informal version people mistakenly use]\\n\\n#EmailEnglish #BusinessEnglish #LearnEnglish"
}""",

"small_talk": """Teach natural English small talk phrases for ONE social situation — meeting someone new, office chat, complimenting, etc.

Return ONLY this JSON:
{
  "post_type": "small_talk",
  "subject": "<social situation e.g. Meeting Someone New>",
  "image_keywords": ["<people chatting casually>", "<social gathering>", "<friendly conversation scene>"],
  "content": "💬 Small Talk\\n\\n🎯 Situation: [SITUATION]\\n\\n✅ Natural phrases:\\n1️⃣ \\\"[phrase]\\\" — tip on using it\\n2️⃣ \\\"[phrase]\\\" — tip on using it\\n3️⃣ \\\"[phrase]\\\" — tip on using it\\n4️⃣ \\\"[phrase]\\\" — tip on using it\\n5️⃣ \\\"[phrase]\\\" — tip on using it\\n\\n😬 Avoid saying:\\n→ [awkward/unnatural phrase]\\n\\n💡 Golden rule: [one tip for natural small talk]\\n\\n#SmallTalk #EnglishSpeaking #LearnEnglish"
}""",

}


class ContentGenerator:
    def __init__(self):
        self.client      = Groq(api_key=os.environ["GROQ_API_KEY"])
        self._last_types: list = []

    def generate(self, preferred_type: str = None) -> dict:
        if preferred_type and preferred_type in POST_TYPES:
            post_type = preferred_type
        else:
            avoid     = set(self._last_types[-2:])
            available = [t for t in POST_TYPES if t not in avoid] or list(POST_TYPES)
            post_type = random.choice(available)

        self._last_types.append(post_type)
        if len(self._last_types) > 4:
            self._last_types.pop(0)

        logger.info(f"Generating [{post_type}]...")

        res = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": PROMPTS[post_type]},
            ],
            temperature=0.85,
            max_tokens=1000,
        )

        raw = res.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$",          "", raw, flags=re.MULTILINE)
        raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
        m   = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            raw = m.group(0)

        data = json.loads(raw)
        logger.info(f"Content ready: [{data['post_type']}] {data.get('subject', '')}")

        # توليد keywords ذكية بناءً على المحتوى الفعلي
        try:
            data["image_keywords"] = self._smart_keywords(
                data["post_type"],
                data.get("subject", ""),
                data.get("content", ""),
            )
            logger.info(f"Smart keywords: {data['image_keywords']}")
        except Exception as e:
            logger.warning(f"Smart keywords failed, keeping original: {e}")

        return data

    def _smart_keywords(self, post_type: str, subject: str, content: str) -> list:
        """يبعت المحتوى لـ Groq ويرجع 3 keywords محددة للصورة."""
        prompt = (
            f"You are a visual search expert. Based on this English lesson, suggest EXACTLY 3 "
            f"short image search keywords (2-4 words each) that would find a HIGHLY RELEVANT, "
            f"visually interesting photo for this specific lesson.\n\n"
            f"Lesson type: {post_type}\n"
            f"Subject: {subject}\n"
            f"Content snippet: {content[:300]}\n\n"
            f"Rules:\n"
            f"- Keywords must reflect the SPECIFIC topic, not just 'English lesson'\n"
            f"- Think visually: what scene, object, or emotion fits this content?\n"
            f"- Use real-world photography keywords (no cartoon, no illustration)\n"
            f"- Return ONLY a JSON array of 3 strings, nothing else\n\n"
            f'Example: ["frustrated student exam", "grammar chalkboard close", "pencil paper mistake"]'
        )
        res = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Return ONLY a valid JSON array of 3 strings. No explanation."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.6,
            max_tokens=80,
        )
        raw = res.choices[0].message.content.strip()
        raw = re.sub(r"```(?:json)?\s*", "", raw)
        raw = re.sub(r"```", "", raw)
        m   = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            keywords = json.loads(m.group(0))
            if isinstance(keywords, list) and len(keywords) >= 2:
                return [str(k) for k in keywords[:3]]
        raise ValueError(f"Invalid keywords response: {raw}")
