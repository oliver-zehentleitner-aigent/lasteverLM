# Scope

## The MVP is grounded question answering over uploaded documents, nothing more

**Id:** d7adc698-ffa5-4edf-a031-59a2aacf4f1e
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** planning conversation, 2026-10-12
**Revisit when:** the MVP is deployed and stable

The first release does exactly this: create a notebook, add sources
(PDF, plain text, URL), ask questions, get answers that cite the source
passages they rest on, keep the conversation per notebook. The layout is
the three-pane NotebookLM shape (sources, chat, notes) and must be
efficient and thought through, but it is not polished beyond that.

**Reason:** the project is a time-boxed portfolio piece. What it has to
show is that a vague brief turns into a stable, deployed system with a
clear architecture and a visible decision trail. Every feature beyond the
core costs time that would otherwise go into stability and the
decision trail, and adds nothing to what the project demonstrates.

**Deliberately left out:** audio overviews and other generated media,
mind maps, sharing between users, horizontal scaling, UI polish past a
clean layout. Each of these is a NotebookLM feature a reader might
expect; none of them is a precondition for the core loop, and the audio
overview in particular is expensive in both effort and API cost. They
are candidates for later, not forgotten.

## Time budget

**Id:** a835376b-16d6-4c47-8f78-f5090170f032
**Type:** constraint
**Status:** open
**Evidence:** unknown
**Source:** planning conversation, 2026-10-12

No deadline is fixed yet. The working assumption is a short, self-set
window, because a tight time box matches the MVP message and keeps the
scope above honest. Once set, the date goes here.
