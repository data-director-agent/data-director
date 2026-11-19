# UI best practice for an agentic research-data assistant

*Prepared 21 October 2026 for the Data Director reference implementation ("Workbench")*

## Scope and assumption

"An app like this" is read here as an AI agent that helps researchers prepare, document and deposit FAIR research data, with a human reviewing and approving what it does. No single body of guidance covers that combination, so this document synthesises four strands:

1. human-in-the-loop (HITL) design for agents,
2. trust calibration and transparency,
3. research-data deposit usability, and
4. accessibility for AI chat interfaces.

Sections are tagged with a source-quality note where it matters. Anything marked **[my synthesis]** is an inference for Data Director rather than something a source says.

## Summary

- **Chat alone is a poor interface for agents that act.** Several practitioners argue agents need visible plans, approval points, activity logs and undo, not just a text box. This is an opinion-led claim, but it is consistent with the more rigorous guidance below.
- **Treat oversight as a control-design problem, not an "Approve" button.** Approving everything produces rubber-stamping. Spend human attention on uncertain, unusual, consequential or irreversible steps.
- **Show the resolved action, not a description of it.** An approval screen that hides what will actually happen is not meaningful oversight.
- **Transparency has to be designed to calibrate trust, not to maximise it.** Provenance, uncertainty cues and honest limits help. Fluent explanations alone can mislead.
- **Researchers find deposit forms hard, mainly because of metadata.** An assistant's biggest UI win is reducing that burden without hiding what is being recorded.
- **Accessibility needs engineering judgement.** WCAG 2.2 does not directly address streamed AI output, so a standard audit will under-report problems.

## 1. Go beyond the chat box

A recent practitioner piece argues that chat is the wrong default for agents: a text box suits asking, but is poor for watching, checking and undoing work ([Towards AI, Sept 2026](https://pub.towardsai.net/designing-for-ai-agents-8-ux-patterns-that-build-trust-in-2026-713a0c926933)). The same piece lists plans, approvals, logs and undo as the missing pieces. Note that this is a Medium opinion article by a student designer, and only its introduction was readable (member-only), so treat it as a pointer rather than evidence.

Microsoft's research guidelines make a related point from the human-AI interaction literature: make clear what the system can do and how well it can do it (guidelines 1 and 2), and let users efficiently correct it when it is wrong (guideline 9) ([Microsoft Research](https://www.microsoft.com/en-us/research/blog/guidelines-for-human-ai-interaction-design/)).

**Practical implication [my synthesis]:** use chat for intent and clarification, but give the work itself a structured surface: a plan or task view, a diff of proposed metadata changes, an activity log, and a way to roll back.

## 2. Design oversight by risk, and avoid approval fatigue

Consistent themes across the HITL sources:

- **Oversight should not be everywhere.** One design practice argues human attention should be concentrated on consequential, uncertain, unusual or irreversible actions, with medium-risk work using a review window or queued approval ([The Skins Factory](https://www.theskinsfactory.com/uiux-design-questions-answers/how-do-you-design-human-in-the-loop-ai-without-creating-approval-fatigue)).
- **Classify actions by risk and match oversight to it.** Coding agents are the usual example: they run safe reads autonomously but ask before potentially destructive commands ([Codemia](https://codemia.io/courses/introduction_to_agentic_ai/human_in_the_loop_design)).
- **Approval fatigue turns oversight into rubber-stamping.** One article frames HITL as a control-design problem and recommends the agent restate its interpreted scope before it starts ([Level Up Coding](https://levelup.gitconnected.com/beyond-approval-designing-human-in-the-loop-control-for-agentic-ai-7b97834bd5ba)).
- **Four common patterns:** interrupt-and-resume, human-as-a-tool, approval flows, and fallback escalation ([Dataiku](https://www.dataiku.com/blog/human-in-the-loop-ai-agents)). Another source distinguishes approval, input (the agent lacks data) and escalation (the agent is stuck) ([Understanding Data](https://understandingdata.com/posts/human-in-the-loop-patterns/)).
- **Go beyond approve/reject.** Variants include scoped approval, dry-run preview, and approving the agent's plan before execution ([Kunal Ganglani](https://www.kunalganglani.com/blog/tool-approval-patterns-ai-agents)).
- **Design for scepticism, not blind trust.** One article suggests techniques to counter reviewer bias, such as asking the reviewer to select a reason for approval ([Zartis](https://www.zartis.com/human-in-the-loop-ui-patterns-designing-intentional-friction-for-safer-ai-products/)).

Source quality: these are practitioner and vendor blogs. They agree with each other, but none presents controlled evidence on approval fatigue.

**Practical implication [my synthesis]:** for Data Director, a policy/review gate with risk tiers maps naturally onto these patterns. Low-risk lookups (for example vocabulary suggestions) can be shown inline. Anything that writes to a repository, asserts a licence, or touches sensitive-data handling should require explicit, specific review.

## 3. Show the resolved action and its provenance

- The principle from agent-approval writing is blunt: if the approval UI does not show the *resolved* action, it is not human-in-the-loop ([Kunal Ganglani](https://www.kunalganglani.com/blog/tool-approval-patterns-ai-agents)).
- A description of the AG-UI protocol says a client should make clear which agent is acting, what action is pending, what data is being shown, and whether an approval changes external state ([Promptmetheus](https://promptmetheus.com/resources/llm-knowledge-base/agent-user-interaction-protocol-ag-ui)).
- For trust, practitioner guidance puts provenance (citations or a source browser), explicit capability limits, and human checkpoints for irreversible actions first ([AI UX Playground](https://aiuxplayground.com/ai-trust-design)).

**Practical implication [my synthesis]:** every suggestion (a vocabulary term, licence, metadata field) should link to the evidence it was drawn from, and every approval should show exactly what will be written, where.

## 4. Calibrate trust rather than maximise it

- A 2026 paper argues trust in chatbots should be treated as a calibration problem, and that interpretability affordances such as source citations and uncertainty cues make evaluation possible ([PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13593748/)). It also notes that chatbots have produced fabricated but convincingly formatted evidence, including citations.
- Older human-factors work on robot interfaces found that more agent transparency improved operator performance and trust calibration, but only to a degree. Adding uncertainty information did not raise trust further, and workload did not necessarily rise ([Chen et al., 2017](https://stars.library.ucf.edu/scopus2015/7040)). This is a different domain (robot supervision), so it is suggestive for our purposes, not conclusive.
- A practitioner article warns that showing reasoning can backfire, because a fluent explanation reads as competence ([p0stman](https://p0stman.com/agent-ux/calibrated-confidence)). This is a vendor blog and I could not check the underlying studies it refers to, so treat it as **unsubstantiated** for now.
- A conversational-agent paper proposes that agents should sometimes *reduce* user trust where appropriate, to avoid excessive reliance ([Dubiel et al., CUI 2022](https://pureportal.strath.ac.uk/en/publications/conversational-agents-trust-calibration/)).

**Practical implication [my synthesis]:** prefer evidence panels and explicit "could not ground this" states over long narrative explanations. A grounding check that fails should be visibly different from a pass.

## 5. Design for being wrong

Microsoft's guidelines group several behaviours under "when wrong": efficient dismissal, efficient correction, scoping services when in doubt (disambiguate or degrade gracefully), and explaining why the system did what it did ([Microsoft Research](https://www.microsoft.com/en-us/research/blog/guidelines-for-human-ai-interaction-design/)). HITL sources add that an agent should route to a human when it has missing data or conflicting signals instead of guessing ([Level Up Coding](https://levelup.gitconnected.com/beyond-approval-designing-human-in-the-loop-control-for-agentic-ai-7b97834bd5ba)).

The same guidelines cover the longer term: granular feedback, global controls, and notifying users when capabilities change (guidelines 15, 17 and 18). The authors stress these are prompts for design discussion, not a checklist.

**Practical implication [my synthesis]:** abstain and refer outcomes should be first-class screens with a clear next step, not error messages. Capture structured corrections, and tell users when the agent's behaviour or model changes between sessions.

## 6. Research-data deposit usability

Evidence here is thinner than for generic AI UX, and I could only reach summaries.

- A usability study of the Texas Data Repository found first-time depositors often found adding or editing metadata overwhelming, and had to shift from thinking as a data creator to thinking as a data curator ([Journal of eScience Librarianship, 2022](https://publishing.escholarship.umassmed.edu/jeslib/article/id/435); abstract and summary only, as the full page was blocked). The authors suggest the findings apply to any self-deposit model.
- Jisc's UX specialist framed the tension directly: repositories want robust, rich, accurate metadata, but not at the expense of usability, and making metadata visible gives it purpose and drives engagement ([Jisc/RDA slides, 2019](https://archive.rd-alliance.org/sites/default/files/2019-10-24_Davey_Tom.pdf)).
- Earlier repository-usability reviews note that deposit interfaces are under-studied, and report experiments with minimal manual metadata plus automatic metadata ([DepositMO review](https://blog.soton.ac.uk/depositmo/2012/01/24/repository-usability-review-1-designing-for-metadata)).
- Several university repositories have run task-based usability tests with the think-aloud method, and the Samvera community collects the write-ups ([Samvera](https://samvera.atlassian.net/wiki/spaces/samvera/pages/405211845/UI+Usability+Studies+Tests)). The Alberta testing found consistent barriers across library staff and faculty/graduate participants.

**Practical implication [my synthesis]:** the agent's main UI job is to move the researcher from "filling in a form" to "reviewing proposed metadata". Show what was inferred and from where, keep the curator-mindset shift gentle (plain language, examples), and test with real depositors using the same task-based, think-aloud approach. This also fits the planned hands-on evaluation workshop.

## 7. Accessibility

- A chat interface must still meet WCAG 2.2 AA: keyboard operation, focus management, live regions, contrast, and use at 400% zoom without horizontal scrolling ([EZUD](https://ezud.com/building-accessible-ai-chatbots/)).
- One engineering article argues WCAG 2.2 has no success criterion specifically for streaming content, so conformance audits alone give a misleading picture. It recommends `aria-live="polite"` with `aria-atomic="false"` for dynamic content, structured output over streaming prose where possible, and testing the container rather than the content ([Tian Pan](https://tianpan.co/blog/2026-04-17-ai-accessibility-streaming-screen-readers)). This is a single-author blog, but the underlying point that SC 4.1.3 (status messages) was written with simpler cases in mind is plausible.
- A real-world UK example: the University of Westminster's accessibility statement for its AI chatbot lists failures against a long run of WCAG 2.2 criteria, including keyboard operation, focus order, status messages and reflow ([Westminster](https://www.westminster.ac.uk/about-us/our-university/corporate-information/policies-and-documents-a-z/accessibility-statements-for-university-websites/learnwise-liby-ai-chatbot-accessibility-statement)). It is a useful list of what to test, and a reminder that public-sector accessibility regulations apply.
- Guidance on AI-platform accessibility adds that a chat window must expose message order and generation state, and long operations need remaining time and a way to cancel or extend ([Gravitee](https://www.gravitee.io/corpus/gen-1980/human-computer-interaction/accessibility-for-ai-interfaces.html)). Treat this vendor source with care.

**Practical implication [my synthesis]:** test with real screen readers on long-running, multi-step agent runs, not only on a single reply. Prefer discrete status updates and structured results over token-by-token streaming where users need to act on the output.

## 8. Protocol layer: AG-UI

AG-UI is an open, event-based protocol that standardises how agent state, messages, tool events and user interactions flow between an agent backend and a frontend ([AG-UI docs](https://docs.ag-ui.com/introduction.md)). It sits alongside MCP (agents to tools) and A2A (agents to agents), and addresses where a user can see progress, steer work or approve actions ([Promptmetheus](https://promptmetheus.com/resources/llm-knowledge-base/agent-user-interaction-protocol-ag-ui)). It is separate from A2UI, a generative-UI specification for agent-delivered widgets ([AG-UI overview](https://docs.copilotkit.ai/ag-ui/introduction)).

Caveats from the sources: AG-UI handles interruption and cancellation, but its security treatment (for example strict schema validation of every state update) comes from a third-party threat analysis, not the specification itself ([Ken Huang](https://kenhuangus.substack.com/p/ag-ui-and-a2ui-protocols-explained)). The protocol standardises transport, not the design of the review experience. **[my synthesis]:** the policy and review decisions remain the project's own.

## 9. Checklist for Data Director's UI

All items are **[my synthesis]** from the sources above.

1. **Structure the work.** Plan view, progress, activity log, undo or rollback. Chat for intent only.
2. **Tier the oversight.** Define which actions run freely, which queue for review, and which require explicit approval. Record the tiering in the specification.
3. **Show the resolved action.** What will be written, to which repository or record, with a preview or dry run.
4. **Attach evidence to every suggestion.** Source link, retrieval context, and a visible "not grounded" state.
5. **Make abstain and refer outcomes real screens.** Clear reason, clear next step, easy handover to a human data steward.
6. **Support correction.** One-step edit or dismiss, and structured feedback capture (with consent).
7. **Reduce metadata burden visibly.** Pre-fill, explain, and let researchers see how metadata will be used.
8. **Resist approval fatigue.** Batch low-risk items, ask for a reason on high-risk approvals, and monitor how often reviewers approve without edits.
9. **Declare capability and limits upfront.** What the agent can and cannot do, and how reliable it is.
10. **Build accessibility in from the start.** Keyboard and focus model, live-region strategy for long runs, 400% zoom, and testing with assistive technology users.
11. **Test with depositors.** Task-based, think-aloud sessions with researchers who have never used the tool.

## 10. Evidence gaps

- No source gives controlled evidence on how often reviewers approve agent actions without checking, or which interface patterns reduce this.
- Evidence on explanation backfire comes from a vendor blog; it needs checking against primary studies before it drives design.
- Research-deposit usability studies are mostly small, single-institution and several years old, and I could not read two of them in full.
- Accessibility guidance for streamed AI output rests on engineering opinion, not a standard.
- Nothing found addresses the specific combination of research data, FAIR metadata and an agent. This is a gap the project could usefully fill with its own evaluation.

## Sources

- [Guidelines for human-AI interaction design, Microsoft Research](https://www.microsoft.com/en-us/research/blog/guidelines-for-human-ai-interaction-design/)
- [Beyond Approval: Designing Human-in-the-Loop Control for Agentic AI](https://levelup.gitconnected.com/beyond-approval-designing-human-in-the-loop-control-for-agentic-ai-7b97834bd5ba)
- [Human-in-the-Loop Design, Codemia](https://codemia.io/courses/introduction_to_agentic_ai/human_in_the_loop_design)
- [Human-in-the-loop AI agents: design patterns, Dataiku](https://www.dataiku.com/blog/human-in-the-loop-ai-agents)
- [Human-in-the-Loop UI Patterns, Zartis](https://www.zartis.com/human-in-the-loop-ui-patterns-designing-intentional-friction-for-safer-ai-products/)
- [Human-in-the-Loop Patterns, Understanding Data](https://understandingdata.com/posts/human-in-the-loop-patterns/)
- [Human-in-the-loop AI without approval fatigue, The Skins Factory](https://www.theskinsfactory.com/uiux-design-questions-answers/how-do-you-design-human-in-the-loop-ai-without-creating-approval-fatigue)
- [10 HITL Tool Approval Patterns for AI Agents](https://www.kunalganglani.com/blog/tool-approval-patterns-ai-agents)
- [Designing for AI Agents: 8 UX Patterns, Towards AI](https://pub.towardsai.net/designing-for-ai-agents-8-ux-patterns-that-build-trust-in-2026-713a0c926933)
- [AG-UI documentation](https://docs.ag-ui.com/introduction.md) and [overview](https://docs.copilotkit.ai/ag-ui/introduction)
- [AG-UI, Promptmetheus](https://promptmetheus.com/resources/llm-knowledge-base/agent-user-interaction-protocol-ag-ui)
- [AG-UI and A2UI explained, Ken Huang](https://kenhuangus.substack.com/p/ag-ui-and-a2ui-protocols-explained)
- [Why we believe chatbots: trust calibration as a design problem, PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13593748/)
- [Effects of Agent Transparency on Human-Autonomy Teaming Effectiveness](https://stars.library.ucf.edu/scopus2015/7040)
- [Conversational agents trust calibration, Dubiel et al.](https://pureportal.strath.ac.uk/en/publications/conversational-agents-trust-calibration/)
- [Calibrated confidence, p0stman](https://p0stman.com/agent-ux/calibrated-confidence)
- [AI trust design, AI UX Playground](https://aiuxplayground.com/ai-trust-design)
- [Depositing Data: A Usability Study of the Texas Data Repository](https://publishing.escholarship.umassmed.edu/jeslib/article/id/435)
- [Mixed licence and access: a UX challenge, Jisc (RDA)](https://archive.rd-alliance.org/sites/default/files/2019-10-24_Davey_Tom.pdf)
- [Repository usability review 1, DepositMO](https://blog.soton.ac.uk/depositmo/2012/01/24/repository-usability-review-1-designing-for-metadata)
- [UI Usability Studies/Tests, Samvera](https://samvera.atlassian.net/wiki/spaces/samvera/pages/405211845/UI+Usability+Studies+Tests)
- [Building Accessible AI Chatbots, EZUD](https://ezud.com/building-accessible-ai-chatbots/)
- [The Accessibility Gap in AI Interfaces, Tian Pan](https://tianpan.co/blog/2026-04-17-ai-accessibility-streaming-screen-readers)
- [Learnwise Liby AI Chatbot accessibility statement, University of Westminster](https://www.westminster.ac.uk/about-us/our-university/corporate-information/policies-and-documents-a-z/accessibility-statements-for-university-websites/learnwise-liby-ai-chatbot-accessibility-statement)
- [Accessibility for AI Interfaces, Gravitee](https://www.gravitee.io/corpus/gen-1980/human-computer-interaction/accessibility-for-ai-interfaces.html)
