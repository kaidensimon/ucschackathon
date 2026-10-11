# Research: consensus

Read-only research on 2026-10-10. Nothing was run on the GX10. The re-check section overrides the findings where they differ.

## Summary
The plan's protocol is buildable, but four parts go against published evidence, and "the engine checks which answers match" has no validated method for free-form answers.

1. Rounds: most of the measurable gain from a council comes from a vote over independent first answers. Extra rounds do not raise accuracy on average and do raise conformity. Make round 1 independent, ballot at once, and design for 2 to 3 rounds.
2. Matching: use a clerk-written list of distinct positions plus one constrained-JSON ballot per seat, counted in code. Use typed ballots for yes/no, pick-one, number and date questions. Embedding clustering is rejected because embeddings are weak on negation and numbers. The clerk step is unverified with small local models and needs a fixture test on the GX10.
3. Conflicts with the evidence:
   - agents answering each other by name (identity bias);
   - one model in two seats counted as two votes;
   - a skeptic role that also governs the vote;
   - letting models rewrite council.md when it is over budget.
4. The 80% bar is defensible as a strict release bar, because "No consensus" still releases an answer. With 3 or 4 seats it is unanimity and will often run to the time limit (my estimate), and pressure on the last dissenter is a conformity risk.
5. Citations: make "verbatim quote found on the cited page" a hard gate checked in code. Treat model-judged support as a soft flag only; the best checkers score about 75 to 77 on the LLM-AggreFact benchmark.
6. Learning: the four review questions miss provenance, specificity, duplicates, evidence strength and after-the-fact monitoring.
7. Hidden instructions: llama-server currently turns special-token strings inside message text into real control tokens (fix still open), and the Downloads watch folder brings in files the owner did not write.
8. Prior art: karpathy/llm-council has no licence. I found no project that combines a seated view with a supermajority threshold on matched answers.

Caveats:
- I read the plan's text by extracting it with macOS PDFKit; the wireframes were not seen.
- Figures were pulled from arXiv pages by an automated reader, mostly from abstracts or the first 100,000 characters of the HTML. Spot-check any number before it goes into a spec.
- For Zhang et al. (2502.08788) only the abstract was readable.
- Estornell and Liu (NeurIPS 2024) appeared only in search results and is not cited.

## Claims

### K1a [partly]
Having several models debate gives a better answer than asking one model once.

Evidence: Du et al. (arXiv 2305.14325; 3 agents, 2 rounds by default) reported gains, and a 4-small-model test scored 80.9% for deliberate-then-vote against 71.7% for the best single model on MMLU-Pro Math, mostly not statistically significant. Three re-evaluations found debate often fails to beat one model with strong prompting or self-consistency: Zhang et al. 2502.08788 (5 methods, 9 benchmarks, abstract only), Wang et al. 2402.18272 and Smit et al. 2311.17371.

For the build: Present the council as several independent opinions plus a cross-check, not as a guarantee of a better answer. Keep the phase 2 single-model chat as the quick path for simple questions.

Sources: https://ar5iv.labs.arxiv.org/html/2305.14325, https://arxiv.org/abs/2502.08788, https://arxiv.org/abs/2402.18272, https://arxiv.org/abs/2311.17371, https://github.com/andybhall/llm-council-governance

### K1b [refuted] (load-bearing)
Rounds of debate reliably add accuracy beyond a simple majority vote of the models' independent first answers.

Evidence: Choi, Zhu and Li, 'Debate or Vote' (arXiv 2508.17536, NeurIPS 2025 spotlight; 5 agents, 7 benchmarks): majority voting accounts for most of the gain. Qwen2.5-7B averaged 0.7205 single, 0.7691 majority vote, and 0.7377 / 0.7112 / 0.7050 for debate at 2 / 3 / 5 rounds; they model debate as a process whose expected correctness does not rise between rounds. Exceptions exist (one task favoured debate).

For the build: Make round 1 a set of answers written without seeing each other, ballot immediately, and release at once if 80% already match. Treat later rounds as a way to resolve disagreement, and store the independent first-round tally to show on the answer card.

Sources: https://arxiv.org/abs/2508.17536, https://arxiv.org/html/2508.17536

### K1c [refuted] (load-bearing)
Letting the debate run more rounds until the time limit is harmless or helpful.

Evidence: Several papers report harm from extra rounds: Kaesberg et al. 2502.19130 (slightly lower accuracy), Weng et al. 2501.13381 (one model's conformity rate rose from 33.9% at 1 round to 44.4% at 5), Wynn et al. 2509.05396 (3 agents, 2 rounds: correct-to-wrong flips outnumber wrong-to-correct and the gap grows in round 2; every group declined on CommonsenseQA). Yao et al. 2509.23055 suggest capping at 2 to 3 exchanges; Du et al. saw gains flatten after 4 rounds.

For the build: Design for 2 to 3 rounds, the typical published setting with 3 to 5 agents. Keep ballots secret and simultaneous so no seat sees the running tally before it votes, and offer the owner an optional early stop when no seat has changed its vote for 2 rounds.

Sources: https://arxiv.org/html/2502.19130, https://arxiv.org/html/2501.13381, https://arxiv.org/html/2509.05396, https://arxiv.org/html/2509.23055, https://ar5iv.labs.arxiv.org/html/2305.14325

### K1d [partly] (load-bearing)
Seating different models is better than seating copies of one model.

Evidence: For: Zhang et al. call model heterogeneity 'a universal antidote', ReConcile 2309.13007 says diversity is critical, and Wu et al. 2511.07784 name reasoning strength and group diversity as the dominant drivers. Against: Li et al. 2502.00674 found mixing lowers average quality (one top model sampled repeatedly beat a mix by 6.6% on AlpacaEval 2.0), Wynn et al. found a weaker agent drags a stronger one down, and Kim et al. 2506.07962 (350+ models) found models agree 60% of the time when both are wrong.

For the build: Have the seat picker favour different model families of similar strength, and warn when one seat is much weaker. Mark seats that share a model (the plan allows this) because their votes are not independent evidence, and say so on the answer card.

Sources: https://arxiv.org/abs/2502.08788, https://arxiv.org/abs/2309.13007, https://arxiv.org/abs/2511.07784, https://arxiv.org/abs/2502.00674, https://arxiv.org/html/2509.05396, https://arxiv.org/abs/2506.07962

### K2a [partly] (load-bearing)
The engine can tell which free-form one-sentence answers match by having a clerk list the distinct positions and each agent vote for one by id in constrained JSON.

Evidence: The mechanics are verified: llama.cpp turns a JSON schema, including enum, into a grammar through the `json_schema` body field or `response_format`, so a ballot always parses; Kaesberg et al. had agents choose among numbered candidate solutions. No paper I opened measures how accurately a small local model partitions arbitrary free-form answers, so reliability on the GX10 is unverified. Kaesberg et al. also found approval voting (many picks per agent) reached no decision in 59% of cases.

For the build: Adopt this as the main method: one clerk call lists mutually exclusive positions with ids, each seat casts exactly one vote from an enum that includes NONE, and code counts. Build a fixture set of tricky answer groups in phase 4 and measure the clerk before trusting the Agreed badge.

Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/grammars/README.md, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/common/json-schema-to-grammar.cpp, https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://arxiv.org/html/2502.19130

### K2b [refuted] (load-bearing)
Clustering the one-sentence answers by embedding similarity is enough to detect agreement.

Evidence: Cao 2504.00584 (ECAI 2025) found universal embedding models often rate a sentence and its negation as similar; Deng et al. 2509.05691 found 13 embedding models struggle with numeric detail (their example: 2% versus 20% growth). llm-consortium's own docs say its clustering measures agreement in response shape, not correctness, and ai-counsel's 0.70 and 0.85 similarity thresholds are shipped defaults with no accuracy evidence.

For the build: Never count votes by embedding similarity. At most use it to raise a flag, for example when the clerk merged two answers whose numbers or polarity differ.

Sources: https://arxiv.org/abs/2504.00584, https://arxiv.org/abs/2509.05691, https://github.com/irthomasthomas/llm-consortium, https://raw.githubusercontent.com/blueman82/ai-counsel/HEAD/docs/convergence-detection.md, https://raw.githubusercontent.com/blueman82/ai-counsel/HEAD/docs/structured-voting.md

### K2c [partly]
A model judging pairs of answers as equivalent is a reliable way to group them.

Evidence: Kuhn et al. 2302.09664 clustered short answers by two-way entailment using DeBERTa-large fine-tuned on MNLI with the question attached: about 93% to 95% correct on short question-answer sets, 61% on noisy samples, and membership can depend on comparison order. Belmadani et al. 2603.04033 found a judge's agreement with experts varies widely with which model wrote the answer. Seven seats means 21 pairs (my arithmetic).

For the build: Keep pairwise judging as a narrow second check, for example to confirm the clerk's merge of the two leading positions when that merge decides the outcome. Do not make it the main method.

Sources: https://arxiv.org/html/2302.09664v3, https://arxiv.org/abs/2603.04033

### K2d [confirmed] (load-bearing)
For narrow question kinds (yes/no, pick one, a number, a date), typed answers can be compared exactly.

Evidence: Every accuracy figure in the debate papers I opened comes from tasks with typed answers such as multiple choice or a number, where matching is an exact comparison. Chen et al. 2311.17311 proposed Universal Self-Consistency precisely because answer extraction and voting do not apply to free-form answers.

For the build: Have the clerk classify the question at the start. For yes/no, pick-one, number-with-unit or date questions use a typed ballot schema and compare in code (unit normalisation and numeric tolerance); otherwise fall back to the position-list ballot.

Sources: https://arxiv.org/abs/2311.17311, https://arxiv.org/html/2508.17536, https://arxiv.org/html/2502.19130

### K3a [partly] (load-bearing)
Agents should answer each other by name.

Evidence: Choi, Zhu and Li 2510.07517 (ACL 2026) found identity labels skew debate: 18 of 20 model-dataset cases showed deference to peers. Removing the labels cut one model's conformity-versus-obstinacy gap from 0.608 to 0.024, with flips from correct to wrong down 64.3% and helpful corrections down 14.9%; the effect on final accuracy was not in the text I read. karpathy/llm-council also anonymises answers as 'Response A/B/C' for peer review.

For the build: Inside prompts, show other seats' positions under neutral labels reshuffled each round, with no model names and no marker of which text is the reader's own. Keep names in the UI by mapping labels back to seats in the engine, so Chat View can still show who a reply is addressed to.

Sources: https://arxiv.org/abs/2510.07517, https://arxiv.org/html/2510.07517, https://raw.githubusercontent.com/karpathy/llm-council/master/backend/council.py

### K3b [confirmed] (load-bearing)
Requiring agents to cite file and page improves the debate.

Evidence: Khan et al. 2402.06782 used a tool that marks each quote verified or unverified by exact match against the source and told judges to trust only verified quotes. Arguments without quotes lowered judge accuracy because the wrong side could invent facts; debate reached 76% against 54% for one-sided consultancy with model judges.

For the build: Require a verbatim quote with every citation, not just file and page. Show each quote's verified or unverified mark to the other agents as well as to the owner.

Sources: https://arxiv.org/abs/2402.06782, https://ar5iv.labs.arxiv.org/html/2402.06782

### K3c [partly]
Asking each agent for a confidence score and using it in the tally improves the outcome.

Evidence: ReConcile 2309.13007 used confidence-weighted voting as part of a method gaining up to 11.4%. But Xiong et al. 2306.13063 (ICLR 2024) found verbalised confidence is overconfident, and Wu et al. 2511.07784 found showing confidence gave limited gains.

For the build: Count seats, not confidence: do not weight the 80% tally by self-reported confidence and do not show one seat's confidence to the others. If collected at all, show it to the owner only.

Sources: https://arxiv.org/abs/2309.13007, https://arxiv.org/abs/2306.13063, https://arxiv.org/abs/2511.07784

### K3d [partly] (load-bearing)
Giving a seat a stance such as skeptic improves the debate.

Evidence: Liang et al. 2305.19118 found a modest level of disagreement is needed. Smit et al. 2311.17371 found an agreement setting moved one protocol from worst to best, with high agreement helping medical questions and hurting counter-intuitive ones. Yao et al. 2509.23055 found all-agreeable groups worst and mixed groups best; Weng et al. found a stronger persona raises independence but is prompt-sensitive.

For the build: A role shapes how a seat argues, never how it votes. The ballot prompt must drop the role and ask for the seat's honest answer, otherwise a permanent skeptic makes 3- and 4-seat councils unable to agree. Default to at most one challenger seat.

Sources: https://arxiv.org/abs/2305.19118, https://arxiv.org/html/2311.17371, https://arxiv.org/html/2509.23055, https://arxiv.org/html/2501.13381

### K3e [partly]
One agent from the agreeing group should write the final answer.

Evidence: Liang et al. warn that with different models the model acting as judge may not be fair. In a 4-small-model test, deliberate-then-chairman-writes scored 75.4% against 80.9% for deliberate-then-vote (not statistically significant). Yao et al. found a central judge fairly robust to its own agreeableness.

For the build: Keep the plan, but fix the winning position statement as the headline the writer must keep word for word. Pick the writer by a fixed rule and run the quote check on the final answer too.

Sources: https://arxiv.org/abs/2305.19118, https://github.com/andybhall/llm-council-governance, https://arxiv.org/html/2509.23055

### K3f [confirmed]
Keeping dissent visible (one-line notes, vote split) is worth the screen space.

Evidence: Agreement is not correctness: Du et al. saw agents confidently converge on wrong answers, Wynn et al. saw correct answers abandoned under peer pressure, and Wang et al. 2604.07667 found a calibrated check intercepted 81.9% of wrong-consensus cases in their 3-agent test.

For the build: Keep dissent notes as planned. Also record and show which seats changed their vote and in which round, plus the independent first-round tally.

Sources: https://ar5iv.labs.arxiv.org/html/2305.14325, https://arxiv.org/html/2509.05396, https://arxiv.org/abs/2604.07667

### K4a [partly]
An existing open-source council app can serve as a base or code reference.

Evidence: karpathy/llm-council (25.3k stars, last push 2025-11-22, FastAPI + React + Vite, OpenRouter) runs first answers, anonymised peer ranking parsed from a 'FINAL RANKING:' text block, then a chairman synthesis; the repo has no LICENSE file and the GitHub API reports no licence. Licensed projects with reusable ideas: blueman82/ai-counsel (MIT), amiable-dev/llm-council (MIT, no web UI), appleweiping/WEIPING_COUNCIL (MIT), irthomasthomas/llm-consortium (Apache-2.0); TrentPierce/PolyCouncil is Polyform Noncommercial 1.0.0 and MultiMind-AI states no licence.

For the build: Write the engine fresh; do not copy code from karpathy/llm-council because it carries no licence. Borrow ideas only: a tab per model, anonymised labels, replay with JSON export, and a named impasse state.

Sources: https://github.com/karpathy/llm-council, https://api.github.com/repos/karpathy/llm-council, https://raw.githubusercontent.com/karpathy/llm-council/master/backend/council.py, https://github.com/blueman82/ai-counsel, https://github.com/amiable-dev/llm-council, https://github.com/appleweiping/WEIPING_COUNCIL, https://github.com/irthomasthomas/llm-consortium, https://github.com/TrentPierce/PolyCouncil, https://github.com/JitseLambrichts/MultiMind-AI

### K4b [partly]
No existing project already has a seated table view or an agreement threshold.

Evidence: A seated view exists: Consilium (Hugging Face hackathon Space) has a 'visual roundtable ... including speech bubbles' built on the Gradio component gradio_consilium_roundtable (PyPI 0.0.6, Apache-2.0, described as poker-style). Thresholds exist: ai-counsel stops when 0.66 of models vote to stop and reports unanimous, majority or tie; WEIPING_COUNCIL stops when 0.7 of members begin with 'CONSENSUS: YES' (5 rounds maximum); llm-consortium has `--confidence-threshold`. I found none combining a seated view with a supermajority on matched answers.

For the build: The Table View must be built from scratch; the roundtable is a Gradio component, not React. Its state shape is worth copying: participants, messages, currentSpeaker, a separate thinking list, and a list of which bubbles are showing.

Sources: https://huggingface.co/spaces/Agents-MCP-Hackathon/consilium_mcp, https://huggingface.co/spaces/Agents-MCP-Hackathon/gradio_consilium_roundtable, https://pypi.org/pypi/gradio_consilium_roundtable/json, https://raw.githubusercontent.com/blueman82/ai-counsel/HEAD/docs/convergence-detection.md, https://raw.githubusercontent.com/appleweiping/WEIPING_COUNCIL/HEAD/backend/protocols/consensus_protocol.py, https://github.com/irthomasthomas/llm-consortium

### K5a [partly] (load-bearing)
A small always-loaded file of council-vetted lessons will make later answers better.

Evidence: Lesson files can help (Reflexion 2303.11366; Dynamic Cheatsheet 2504.07952; ACE 2510.04618 reports +10.6% on agent benchmarks), but ACE states that without reliable feedback the context gets 'polluted by spurious or misleading signals' and can fall below the base model. Gloaguen et al. 2602.11988 found repository context files did not raise task success and added over 20% cost; Xiong et al. 2505.16067 found agents copy stored experience so errors compound.

For the build: Tie every Lesson to a ground-truth signal from the owner (a correction or a 'This was wrong'), not to the council's own opinion of itself. Track per-entry helped and harmed counts and measure the phase 6 exit test by replaying the original question.

Sources: https://arxiv.org/abs/2303.11366, https://arxiv.org/abs/2504.07952, https://arxiv.org/html/2510.04618, https://arxiv.org/abs/2602.11988, https://arxiv.org/abs/2505.16067

### K5b [partly] (load-bearing)
The four review questions (is it true, will it matter again, does it clash with an entry, is it too broad) cover the known failure modes.

Evidence: They cover over-general rules and contradictions at admission; Claude Code's memory docs confirm contradictions make a model 'pick one arbitrarily' and that files over about 200 lines reduce adherence. Not covered: 'is it true' is judged by the same models that erred; nothing asks where the lesson came from (MINJA 2503.03704 shows memory can be poisoned through normal use); and model-written merges risk collapse (ACE: a rewrite shrank a context from 18,282 to 122 tokens and accuracy fell from 66.7% to 57.1%).

For the build: Add checks for provenance, specificity, duplicates and evidence strength, plus helped/harmed counters with automatic retirement (ExpeL removes an insight when its count reaches zero). Merge entries in code by id; never let a model rewrite the whole file.

Sources: https://code.claude.com/docs/en/memory, https://arxiv.org/abs/2503.03704, https://arxiv.org/html/2510.04618, https://ar5iv.labs.arxiv.org/html/2308.10144

### K6a [confirmed] (load-bearing)
Requiring a verbatim quote and checking that it exists on the cited page is a cheap, reliable check.

Evidence: Khan et al. used exactly this: exact string match marks a quote verified or unverified. Anthropic's guidance recommends extracting word-for-word quotes first and retracting any claim with no supporting quote. The check proves the quote exists, not that it supports the claim.

For the build: Make 'quote found on the cited page' a hard gate run in code, after normalising Unicode, whitespace, line-break hyphens and quote marks, and allowing a span across a page break. Keep page-level text with offsets in the index from phase 2 so this is possible.

Sources: https://ar5iv.labs.arxiv.org/html/2402.06782, https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations, https://platform.claude.com/docs/en/build-with-claude/citations

### K6b [partly] (load-bearing)
A local model can reliably judge whether the cited passage supports the claim.

Evidence: On the LLM-AggreFact leaderboard the best checkers score in the mid-70s: Bespoke-MiniCheck-7B 77.4, Granite Guardian 3.3 (8B) 76.5, Qwen2.5-72B 75.6, MiniCheck-Flan-T5-L (0.8B, MIT) 75.0, Llama-3.3-70B 74.5. Bespoke-MiniCheck-7B is CC BY-NC 4.0, 4.7 GB on Ollama, and takes 'Document: ... Claim: ...' and answers Yes or No. ALCE 2305.14627 found even the best models lacked complete citation support about half the time on one dataset.

For the build: Treat model-judged support as a soft 'support not confirmed' flag, never as a gate or an automatic source of lessons; at these scores roughly one judgment in four is wrong on the benchmark. Whether a MiniCheck model runs under llama-server on the GX10 is unverified.

Sources: https://llm-aggrefact.github.io/, https://arxiv.org/abs/2404.10774, https://huggingface.co/bespokelabs/Bespoke-MiniCheck-7B, https://ollama.com/library/bespoke-minicheck, https://huggingface.co/api/models?search=MiniCheck, https://arxiv.org/abs/2305.14627

### K7 [refuted] (load-bearing)
Because the council reads only the owner's own files and never the web, hidden instructions in files need no special handling.

Evidence: llama.cpp issue #24382 shows llama-server tokenises special-token strings inside a user message as real control tokens, which 'can be used to break the chat template'; its replacement, #28249, is open and an escape-flag request (#26273) was closed as not planned. Lee and Tiwari 2410.07283 show injected prompts spreading agent to agent. The plan's watched Downloads folder also brings in files the owner did not write.

For the build: In the gateway, neutralise each seated model's special-token strings in all file text and wrap passages in clear data markers. Keep raw file text out of council.md and stop the browser loading external images or links from model output. Keep the one-click inbox for watched folders.

Sources: https://github.com/ggml-org/llama.cpp/issues/24382, https://github.com/ggml-org/llama.cpp/issues/28249, https://github.com/ggml-org/llama.cpp/issues/26273, https://arxiv.org/abs/2410.07283, https://arxiv.org/abs/2403.14720, https://arxiv.org/html/2506.08837v3, https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/

### K8 [partly] (load-bearing)
80% of seats, rounded up, is a sensible agreement bar.

Evidence: It is a strict bar that lowers the chance of releasing a wrong 'Agreed' answer; in human lab juries Guarnaschelli et al. (2000) found fewer wrong convictions under unanimity than majority. The cost is deadlock and pressure: in Kaesberg et al. unanimity decided in the first turn 59.5% of the time against about 80% for majority and two-thirds rules, and Weng et al. show conformity rises with majority size. My estimate, assuming independent seats each right 70% of the time: all 3 of 3 agree on the right answer at first ask 34% of the time, 4 of 5 53%.

For the build: Keep the owner's rule and compute the bar with whole numbers (4 times seats, divided by 5, rounded up) to give 3, 4, 4, 5, 6. Expect 'No consensus' to be common with 3 and 4 seats, so design that state as a normal, well-presented outcome with a fixed tie-break, not as an error.

Sources: https://arxiv.org/html/2502.19130, https://arxiv.org/html/2501.13381, https://www.cambridge.org/core/journals/american-political-science-review/article/abs/an-experimental-study-of-jury-decision-rules/45C42F6E2923E08D3A4A2B7735B1C955, https://lawschool.cornell.edu/wp-content/uploads/2020/12/IsUnanimityANightmare.pdf, https://arxiv.org/abs/2508.17536

## Recommendations
- **How the engine decides that answers match**: Three steps at the end of each round. (1) A clerk call returns a JSON list of mutually exclusive positions, each with a short id and a one-sentence statement; numbers carry units and an 'it depends' answer must state its condition. (2) Each seat, in a separate short call with thinking off, casts one vote constrained to an enum of the ids plus NONE; the list is shuffled per seat and no seat sees another's vote. (3) Code counts. Any NONE triggers one clerk revision. For yes/no, pick-one, number and date questions, skip the clerk and use a typed ballot compared in code. _Why:_ Each seat attests to its own position, so no third party has to rule on equivalence; a grammar-constrained ballot always parses; cost is one clerk call plus one short call per seat. llama.cpp supports enum in JSON-schema grammars, but the schema is not shown to the model, so the prompt must describe it. Keep free-text reasoning in the debate turn: Tam et al. 2408.02442 found format restrictions reduce reasoning quality.
- **Round structure of a debate**: Round 1: every seat researches and answers without seeing the others, then ballots. If 80% already match, release. Otherwise run rounds of critique and revision, planning for 2 to 3 rounds in total, with a secret simultaneous ballot after each. Record every seat's vote per round. _Why:_ The independent vote carries most of the accuracy gain, and later rounds add conformity rather than accuracy (Choi et al.; Weng et al.; Wynn et al.; Yao et al.). It also gives the fastest release when the council already agrees.
- **How agents refer to each other**: Neutral position labels in prompts, reshuffled each round, with no model names and no marker of the reader's own earlier text. The engine keeps the label-to-seat map so Table View and Chat View still show names and who is being answered. _Why:_ Identity labels caused deference to peers in 18 of 20 model-dataset cases; removing them cut harmful flips far more than helpful corrections (Choi et al. 2510.07517). The owner still sees agents answering each other by name.
- **Checking citations**: Every citation carries file id, page and a verbatim quote. Code checks the quote appears on that page after light normalisation, and marks it verified or unverified in the transcript that other agents and the owner see. As an optional second stage, a grounding checker (Bespoke-MiniCheck-7B, or a seated general model) labels 'support not confirmed'. _Why:_ The existence check is exact, costs no model time, and was shown to matter for judging debates (Khan et al.). Support judging tops out around 75 to 77 on LLM-AggreFact, so it should inform, not block.
- **How council.md is reviewed and maintained**: Review by one independent constrained-JSON ballot per seat (the four plan questions plus provenance, specific-enough-to-act-on, and duplicate-of-existing), with no debate rounds. Store entries as records with id, scope, evidence, vote, and helped and harmed counts; apply accepted changes in code and render the markdown from the records. Load only entries whose scope matches the question when the file nears its budget. _Why:_ Independent ballots capture most of the benefit of a vote at a fraction of the time. Merging in code avoids the collapse seen when a model rewrites a whole context (ACE). Counters give the after-the-fact signal the four questions lack (ACE, ExpeL).
- **Basic hygiene against instructions hidden in files**: (1) In the gateway, break or escape each seated model's special-token strings in file text and in text passed between agents. (2) Wrap retrieved passages in explicit data markers with a standing instruction that they are material, not instructions. (3) Give agents no tools beyond search and read. (4) Draft council.md candidates only from owner signals and engine checks, never from raw file text. (5) Serve the UI with a content security policy that blocks external images and requests. (6) Keep the one-click inbox for watched folders. _Why:_ llama-server currently parses special-token strings in message text as control tokens and the fix is still open. Marking data cut attack success from over 50% to under 2% on GPT-family models (Hines et al.; untested on small local models). The file and the owner's browser are the only persistent and outbound channels in an otherwise offline design.
- **Threshold arithmetic, ties and labels**: Compute the bar in integers as 4 times seats, divided by 5, rounded up. On time-out or Stop, release the position with the most votes; break ties by most first-round votes, then most verified quotes, then seat order, and say when a tie was broken. Show the first-round independent tally beside the final vote. _Why:_ Whole-number arithmetic avoids rounding surprises and matches the plan's table (3, 4, 4, 5, 6). The plan does not say what 'most support' means in a tie; Kaesberg et al. simply fall back to the first agent's answer, which is arbitrary.
- **Roles and the final writer**: Roles (skeptic, fact-checker) apply to debate turns only; the ballot prompt omits the role. The final writer is chosen by rule from the agreeing group and must keep the agreed position statement word for word as the headline; dissenters write their own one-line notes. _Why:_ A role that also governs the vote blocks unanimity in small councils. A free-hand synthesis can drift from what was agreed, and mixed-model judges may not be fair (Liang et al.).
- **Proving the agreement check before trusting it**: In phase 4, build a small fixture set of answer groups with known correct groupings (same answer in different words, different numbers, negations, partial agreement, multi-part answers, 'it depends') and score the clerk and ballot steps with the actual seated models on the GX10. _Why:_ No published measurement covers small local models partitioning free-form answers, and this step decides every Agreed badge. andybhall/llm-council-governance (MIT) shows the pattern of testing decision rules offline.

## Risks
- A wrong answer released as 'Agreed'. Models share errors (they agreed 60% of the time when both were wrong in Kim et al.) and defer to peers, so a 5-of-5 badge overstates reliability. Mitigate with the independent first-round tally, visible dissent and verified quotes.
- Clerk partition errors silently create or block consensus: merging answers that differ in a number or a condition, or splitting the same answer in two. This is the least-evidenced step in the design and it decides every outcome.
- With 3 or 4 seats the bar is unanimity, so many debates will run to the time limit and end 'No consensus' (my estimate from the independence model and from Kaesberg et al.). The last dissenter may also give in to pressure rather than to argument.
- A bad lesson is voted in by the same models that made the mistake, then read by every seat in every debate. If the council is allowed to rewrite the file when over budget, detail can collapse in one step.
- Text in a file reaches every seat at once, and llama-server currently treats special-token strings in that text as real control tokens. An instruction that gets written into council.md would persist across debates.
- Model-judged citation support is wrong roughly one time in four on the public benchmark. If 'citation does not support its claim' feeds learning automatically, it will generate spurious lessons.
- Two seats running the same model count as two votes toward 80% but are closer to one opinion, making agreement easier to reach and less meaningful.
- Constrained JSON is not shown to the model by llama.cpp and can lower reasoning quality if used for the main turns. Thinking-style models may also interact badly with grammars; this is untested here.
- Each round adds one clerk call and one ballot call per seat on top of the debate turns. On the 2-minute preset there may be time for only the independent round; I could not measure this.
- A skeptic role that persists into the ballot makes small councils unable to agree by construction.
- karpathy/llm-council carries no licence, so copying its code is not permitted by default even though it is the best-known reference.

## Open questions
- Which model acts as clerk: the strongest seated model, a rotating seat, or the small bubble model? How accurately does it partition answers on the GX10 with the models actually seated? Only a fixture test can answer this.
- How many rounds, including clerk and ballot calls, fit in 2, 5 and 10 minutes with 3 to 7 seats on the GX10?
- Does the owner want an early stop when no seat has changed its vote for 2 rounds, or should the debate always run to the time limit as the plan states?
- For 3 of 4 or 2 of 3 agreement, should the label be 'No consensus' as the plan says, or a distinct label such as 'Majority 3 of 4'?
- Should two seats running the same model count as two votes, or should the seat picker discourage it?
- For multi-part questions, should the council agree on the whole answer or part by part, releasing the agreed parts and marking the rest?
- Should accepted Lessons need the owner's OK, at least at first? The plan assumes an undo notice; the evidence on self-curated memory without ground truth argues for owner approval of Lessons, with preferences going straight in.
- Is the installed llama.cpp build affected by the special-token issue, which exact `response_format` nesting does it accept (the two llama.cpp docs show slightly different shapes), and do grammar-constrained calls work with the chosen models when thinking is on?
- Can a MiniCheck-class checker run under llama-server on the GX10 (arm64, CUDA), or does it need a separate Python process? Is its non-commercial licence acceptable for this personal tool?
- Does the Library hold only files the owner wrote, or also downloads, email attachments and web clippings? That sets how much weight the injection hygiene deserves.
- Does marking retrieved text as data reduce injection success on the small local models to be seated? The published figure is for GPT-family models only.

## Independent re-check (overrides the above)

- **K1a** [partly] Figures check out. Context the planner needs: the 4-model test ran Llama 3.1 8B, Mistral 7B, Gemma 2 9B and Qwen 2.5 7B through OpenRouter on MMLU-Pro Math (deliberate-then-vote 80.9% at N=136; best single model Qwen 2.5 7B 71.7% at N=847; plain majority vote 76.8%), so it is not a local-quantised or GB10 measurement, and its README says significance was not reached for most comparisons.
- **K1b** [refuted] Averages are right (0.7205 / 0.7691 / 0.7377 / 0.7112 / 0.7050, Decentralized MAD rows), but two details are wrong or missing. (1) Table 1 uses 5 copies of ONE model; the paper's 'heterogeneous' test is the same model with different personas, so no mixed-family council was measured. (2) It is not 'one task': at T=2 decentralised debate beat majority vote for Qwen2.5-7B on 4 of 7 tasks (MMLU Pro. Med. 0.8051 v 0.7941, Formal Logic 0.5556 v 0.5397, CommonsenseQA 0.8567 v 0.8300, HH-RLHF 0.4967 v 0.4867) and tied HellaSwag; the average gap comes from Arithmetics (0.76 v 0.99) and GSM8K (0.8867 v 0.94). For free-form output the authors say majority voting 'is not straightforward' and did not apply it.
- **K1c** [refuted] Quotes verified, with scope limits. Kaesberg's drop is on StrategyQA with three persona agents of one model; Weng's 33.9% to 44.4% is Llama3-70B's CR^T in a scripted conformity test (one subject agent, six peers), not open debate; Yao's '2-3 substantive exchanges' is an appendix recommendation, not a tested cap; Du's plateau after 4 rounds is on arithmetic only. Choi et al. predict flat, not falling, expected accuracy.
- **K1d** [partly] Verified at abstract level. Precision: Kim et al.'s 60% is 'on one leaderboard dataset'; Self-MoA's 6.6% is on AlpacaEval 2.0 (judged free-form) with 3.8% average elsewhere; Wynn's exact wording is 'The presence of a weaker agent disrupts the performance of the stronger agent'. No opened paper tests 3 to 7 different small local model families under a supermajority rule.
- **K2a** [partly] `json_schema` (completion endpoints), `response_format` (/chat/completions) and enum-to-grammar are verified, as is 'The JSON schema ... is not injected into the prompt'. But 'a ballot always parses' is wrong for llama-server: #19051 (closed not planned 2026-03-09) shows the server continuing unconstrained with HTTP 200 when grammar parsing fails; #29613 (fixed 2026-09-29 by PR #29615) shows a model-specific chat parser ignoring json_schema; #30256 (open, filed 2026-10-09) shows Gemma 4 with json_schema still emitting a thought channel with enable_thinking false and ending with empty content, the workaround being a raw `grammar`. Validate every ballot against the schema in code and retry.
- **K2b** [refuted] Verified. Extra evidence the original did not use: Kaesberg et al. Table 1 reports SBERT cosine similarity between final answers of 0.843 to 0.916 across all strategies, so answers to one question sit around ai-counsel's 0.85 threshold whether or not they agree. ai-counsel calls its 0.70 vote-merge threshold 'fixed and optimized' and gives no data.
- **K2c** [partly] Exact figures: 92.7% (TriviaQA) and 95.3% (CoQA) on 300 hand-labelled samples each, and 61% at sampling temperature 1.5 on 100 samples; the paper says 'the clusters might depend on the order in which the comparisons are made'. These are short QA answers, not sentence-length council positions.
- **K2d** [confirmed] 'Every accuracy figure' is overstated: Kaesberg et al. also score SQuAD 2.0 by F1, and Li et al. 2502.00674 (cited by the original under K1d) use AlpacaEval 2.0, a judged free-form benchmark. The claim itself holds.
- **K3a** [partly] 18 of 20 positive IBC values and the Qwen-32B on MMLU Professional Medicine figures (gap 0.608 to 0.024; Subversion down 64.3%, Correction down 14.9%) are verified. The missing fact is in Appendix J: under anonymisation 'accuracy remains largely unchanged' and the authors prove it 'cannot induce systematic accuracy improvements'. The paper removes self-versus-peer markers; it does not test showing model brand names.
- **K3b** [partly, disagrees] 'Confirmed' is too strong. Khan et al. tested verified verbatim quotes shown to a weaker judge who cannot read the text, with debaters assigned opposing answers (LLM judges 76% debate v 54% consultancy; humans 88% v 78%); it did not test file-and-page citations or a cooperative council in which every seat reads the files. What is supported is verified quotes: 'arguments-only settings result in lower judge accuracy'.
- **K3c** [partly] Verified at abstract level. ReConcile's 'up to 11.4%' is for the whole method against prior baselines, not for confidence weighting alone.
- **K3d** [partly] Verified. Scope: Smit's 'worst-performing protocol to the best-performing' is Multi-Persona on MedQA (about 15% on a 376-question USMLE subset), with CIAR showing the reverse; Yao's debates are mostly two debaters plus an optional judge; Weng's 'empowered' persona raised Llama3-70B's independence rate from 28.6% to 40.0%.
- **K3e** [partly] Figures verified (Deliberate then Synthesize 75.4% at N=142 v Deliberate then Vote 80.9% at N=136). Add Panickssery et al. 2404.13076: LLM evaluators recognise and favour their own generations, which bears on any seated model acting as clerk or final writer.
- **K4a** [partly] Verified: 25,338 stars on 2026-10-10, last push 2025-11-22, no LICENSE file, and the README says 'I'm not going to support it in any way'. Licences of the other repos were confirmed from their LICENSE files; MultiMind-AI has none.
- **K4b** [partly] Verified (PyPI 0.0.6, license_expression Apache-2.0, requires gradio>=4.0,<6.0; WEIPING defaults confidence_threshold 0.7 and consensus_rounds_max 5). Three more MIT projects exist: entropyvortex/roundtable (Next.js 15, 'Blind Round 1' on by default, consensus score = avg(confidence) - 0.5 * stddev(confidence)), jgabor/agora (CLI, `consensus_threshold` counts unique endorsements) and revoltz-dev/ai-debate (React, optional unanimity). None pairs a seated table with a supermajority on matched answers.
- **K5a** [partly] Verified. Scope: Gloaguen et al. study AGENTS.md-style files for coding agents, not a lessons file for question answering, and ACE's own table shows Dynamic Cheatsheet falling 3.7 points below baseline on finance when run online without ground-truth labels.
- **K5b** [partly] Quotes verified ('Claude may pick one arbitrarily'; 'target under 200 lines ... Longer files consume more context and reduce adherence'). The collapse example in the ACE paper is Dynamic Cheatsheet on AppWorld (18,282 to 122 tokens, 66.7 to 57.1, no-adaptation baseline 63.7). The plan (pages 9-10) already has a per-entry 'used N times' count, retirement of unused or contradicted entries, owner edit/pin/retire and versioned rollback, so the gaps are narrower than stated.
- **K6a** [confirmed] Khan et al.'s tool is not a raw exact match: it is 'a simple direct string match after normalisation', where normalisation strips punctuation and lower-cases both sides. No opened source measures how often small local models reproduce quotes verbatim, so the rate of false 'unverified' marks on the GX10 is unmeasured.
- **K6b** [partly] All five scores verified (balanced accuracy averaged over 11 datasets). Added facts: Granite Guardian 3.3 8B (76.5) is Apache-2.0 with an official GGUF repo, ibm-granite/granite-guardian-3.3-8b-GGUF, unlike CC BY-NC Bespoke-MiniCheck-7B; general 7-8B models score lower (Qwen2.5-7B-Instruct 72.8, Llama-3.1-8B-Instruct 70.3).
- **K7** [refuted] Verified, with dates: #24382 was closed as a duplicate on 2026-09-02; #28249 is open, labelled stale on 2026-10-03, with 1 of 3 tasks done; #26273 was closed not planned on 2026-09-12. The server README documents `/tokenize` `parse_special` (default true; 'When false special tokens are treated as plaintext') and a `/completion` prompt given as an array of strings and token ids, which is an exact alternative to string escaping.
- **K8** [partly] Table 2 figures verified (MMLU, Llama 3 8B, three persona agents, 5-turn cap): unanimity decided 59.50% in turn 1, but only 2.67% were undecided after turn 5, and its score (54.2 +/- 1.0) is not below majority (53.2 +/- 2.5). The Cornell paper (Bilinski and Chizik, on Argentine juries) cites US hung-jury rates of 2.1% to 3.0% federal and 6.2% state. So 'No consensus will be common with 3 and 4 seats' is the original's inference, not a finding. The 34% and 53% estimates are arithmetically right; the same assumption gives 24% for 4 of 4, 42% for 5 of 6 and 33% for 6 of 7 (my arithmetic).

### Objections to recommendations
- Ballot reliability: 'a grammar-constrained ballot always parses' is unsafe on llama-server. The GX10's llama.cpp build is unknown, each model family has its own chat parser, and issues #19051, #29613 and #30256 show schema requests returning unconstrained text, prose, or empty content with HTTP 200. The gateway must validate every ballot against the schema, retry, fall back to a raw `grammar` or `/completion`, and run a ballot self-test whenever a model is seated.
- 'Thinking off' has no universal per-request switch. `chat_template_kwargs: {"enable_thinking": false}` depends on the model's template and `--reasoning-budget 0` is a launch flag; #30256 reports neither stopped Gemma 4 reasoning under json_schema. Treat thinking control as a per-model capability to probe, not an assumption.
- Prompt-cache cost on one shared GPU (inference from the README: `cache_prompt` reuses only the common prefix). Dropping the role for the ballot, reshuffling labels per seat each round and removing own-text markers all change the prompt, so every seat may re-evaluate its whole context several times a round. Keep system text, council.md and passages first and put role and round material last; measure on the GX10.
- Call count against the time limit (estimate, no GB10 timings exist): each round adds one clerk call plus one ballot per seat, plus a clerk revision on any NONE, on top of the debate turns, which is 15 to 16 generations per round at 7 seats on one GPU. The 2-minute preset may fit only round 1. Time this in phase 3 or 4 before promising 2 to 3 rounds.
- The clerk is unspecified and is a single point of failure for every Agreed badge. The small bubble-summary model may be too weak, and a seated model favours its own generations (Panickssery et al.). A wrong merge produces a false agreement.
- The ballot as written lets a seat re-decide after seeing every position, which is an unreasoned conformity step, and small models favour particular option ids (Zheng et al., ICLR 2024). Phrase it as mapping the seat's own stated sentence to an id, have the clerk output its own mapping too, and flag any mismatch (my suggestion, untested).
- Anonymised labels buy less than implied and cost engine work. Choi et al. report accuracy 'largely unchanged', and they tested self-versus-peer markers, not model names. It changes the plan's 'answer each other by name', needs label-to-name rewriting in streamed text, and needs the owner's mid-debate messages that name a seat translated. A seat that did its own research will recognise its own position anyway (inference).
- Capping at 2 to 3 rounds changes an owner-visible rule: the plan stops on time or 80%, with a 10-minute preset that would go mostly unused. This needs the owner's decision. Kaesberg's data support the cap being practical (unanimity reached by turn 3 in 93.8% of cases, my sum of Table 2).
- Bespoke-MiniCheck-7B is CC BY-NC 4.0, adds about 4.7 GB plus another process in unified memory, and is unverified under llama-server. Granite Guardian 3.3 8B (Apache-2.0, official GGUF, 76.5) is the licence-clean alternative; simplest is to skip the second stage at first.
- The citation recommendation contradicts itself: the claim says 'hard gate', the pick says 'marks it verified or unverified'. Khan et al. only marked. Small models paraphrase and elide, so deleting unverified claims could gut answers; mark, do not delete. Special-token neutralisation must be applied to the same text the quote check matches against, or true quotes will fail.
- Neutralising 'each seated model's special-token strings' needs a token list per model, and the owner can download any GGUF, so it must be automatic. Reading it from GGUF tokenizer metadata is my unverified suggestion; the documented exact route is `/tokenize` with `parse_special: false` plus a token-array `/completion` prompt, which gives up chat-endpoint parsing.
- The council.md recommendations change the plan in ways the owner must approve: no debate in review (plan: 'the council then debates four questions'), lessons only from owner signals (plan also lists failed citation checks and vindicated dissents), and scope-filtered loading (plan: 'every seat reads council.md'). Rendering markdown from records also conflicts with the owner editing entries unless edits go through the records.
- The phase 4 fixture test cannot depend on the owner: a non-programmer cannot write or grade fixtures. It needs to ship as a built-in check with fixed pass marks and rerun automatically whenever a saved council's models change.
- The answer card is being asked to carry the vote, the first-round tally, a tie-break note, verified and unverified marks, 'support not confirmed' flags and a shared-model warning. For one non-technical reader this needs plain wording and detail on demand, or the Agreed signal gets buried.

### Missed by the first pass
- Choi et al. 2508.17536 never test different model families: Table 1 is 5 copies of one model and the 'heterogeneous' test is personas on the same model. Applying its result to a mixed-family council is an extrapolation.
- The same paper offers two cheap interventions that beat plain debate: MAD-Conformist (a seat whose answer matched the previous round's majority keeps it) and MAD-Follower (adopt the majority answer with 30% probability). Qwen2.5-7B at T=2 averaged 0.7625 and 0.7629 against 0.7332 for plain debate, still just under majority vote at 0.7691. Locking seats already in the leading group would also cut generations per round on the GX10 (inference).
- llama.cpp structured-output failure modes were not checked: #19051 fail-open on grammar errors (closed not planned), #20345 grammar inactive with thinking on (patched in March 2026, further reports to June 2026), #29613 a model parser ignoring json_schema (fixed by PR #29615), #30256 Gemma 4 thought channel under json_schema (open).
- Appendix J of Choi et al. 2510.07517: anonymisation leaves accuracy 'largely unchanged' (Qwen-7B, Qwen-32B, GPT-OSS-20B on four benchmarks). In four of five examined regressions the anonymised agent 'weighed peer responses uniformly and converged to an incorrect conclusion'.
- Option-id selection bias: Zheng et al. 2309.03882 (ICLR 2024 spotlight) show LLMs 'prefer to select specific option IDs as answers', which applies directly to an enum ballot with thinking off. Shuffling order per seat helps; asking twice in different orders and requiring the same pick is a cheap check (my suggestion).
- Almost all the debate evidence is closed-book question answering. The one document-grounded debate paper found is MADAM-RAG (Wang et al. 2504.13079: up to 11.40% on AmbigDocs and 15.80% on FaithEval with Llama3.3-70B). The council's seats share one retriever and file set, so their errors are correlated and the independence assumed in the K8 estimates is optimistic (inference).
- Kaesberg et al. (ACL 2025 Findings) support an independent first round directly: their All-Agents Drafting, where each agent drafts separately first, gains up to 3.3%, and the abstract says 'Increasing the number of agents improves performance, while more discussion rounds before voting reduce it'.
- Khan et al. also found quotes-only arguments gave 'much higher accuracy' than quotes plus arguments, since 'experts arguing for the incorrect answer can lie more easily' in prose. That favours showing other seats the verified quotes prominently.
- Three more MIT council projects with borrowable ideas: entropyvortex/roundtable (a brief showing 'where they split, who moved'; Blind Round 1 by default), jgabor/agora ('Typed control state, not response prose, authorizes halting'; evidence-status labels on claims) and revoltz-dev/ai-debate (React, optional unanimity).
- JSONSchemaBench (Geng et al. 2501.10868) benchmarks llama.cpp's constrained decoding among six frameworks on 10K real schemas. I read only the abstract, so its llama.cpp results are unverified, but it is the primary source for schema coverage limits.
- The plan's own open question, whether an accepted lesson waits for the owner's OK or goes in with an undo notice, was not addressed. ACE's finding that contexts degrade without ground-truth signals argues for owner OK at least at first (inference).
- None of the four review questions asks whether a lesson is still true or when it expires, although the plan's own example entry (L7) is about outdated figures. A review-by date or source-file link per entry would cover staleness (my suggestion).
