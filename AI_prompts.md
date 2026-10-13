# AI Prompt Log — Homework 5

This file records the prompts used for each problem, in my own words. There is
one section per problem, titled with the problem's number and title. Each
section has the prompt I typed to open the problem, followed by the follow-ups
that were needed to finish it.

## One-question-at-a-time work record

The prompt history below shows that this assignment was completed
sequentially, one question at a time:

1. **Setup.** I created the `homework/hw5/` folder and started this prompt log
   before beginning any problem. I gave the scenario, data and shop rules as
   context, and settled the model question before any code was written.
2. **Problem 1 — Vibecoder prompts.** This prompt log itself, kept current as
   each later problem is worked.
3. **Problem 2 — Study the Campus Customs database.** Begun once the data was
   in place. Produced `output/harness.md`.
4. **Problem 3 — Build the MCP server.** Begun after the schema was
   understood. Produced `mcp/mcp_server.py` and `mcp/README.md`.
5. **Problem 4 — Add the MCP server to vibe coder and test each tool.**
   Produced `mcp/test_tools.py`, `mcp/smoke.py` and `output/mcp_smoke.json`.
6. **Problem 5 — Build the agent team and grow the MCP tools.** Produced
   `backend/` and grew the MCP server to seventeen tools.
7. **Problem 6 — Plan three tickets.** Written before the backend was
   wired, so the expectations are a real hypothesis rather than a description
   of what already happened. Produced `output/desk_tickets.html`.
8. **Problem 7 — Backend routes.** Produced `backend/main.py`.
9. **Problem 8 — Agent dashboard.** Produced `frontend/` and
   `output/design.md`.
10. **Problem 9 — Resolve the tickets.** Produced
    `output/resolved_tickets.json`, `output/resolved_board.html`, and the
    filled Actual and Cash sections of `output/desk_tickets.html`.
11. **Problem 10 — Reflection.**

## Problem 1: Vibecoder prompts

**My prompt:** "okay today we're going to start on AI Foundations homework 5"

**Follow-ups:**

1. "I'll give you some screenshots with general background info and context on the assignment"
2. "please don't start building anything until I give you the step by step instructions for each problem"
3. "just giving screenshots for context"
4. "I have no portkey, we have to use Open AI key"
5. "the teacher knows"
6. "okay problem 1 is called vibecoder prompts"
7. "yes it's the same"

**Notes:** The shop rules require `gpt-6-luna` through Portkey. I have no
Portkey key and my OpenAI project has no access to that model, so this
assignment runs on my OpenAI key with `gpt-5.6-luna`. The instructor is aware
of the substitution.

## Problem 2: Study the Campus Customs database

**My prompt:** "okay problem 2 is called study the campus customs database"

**Follow-ups:**

1. "open data/campus_customs.db and look through every table and it's fields. copy the original file to data/campus_customs_new.db"
2. "study the three open tickets so you see how they link to other tables"
3. "start output/harness.md"
4. "for each table, list the fields and one short line on why that table matters for the agents"
5. "we'll come back to this harness document and add to it throughout the assignment"

## Problem 3: Build the MCP server

**My prompt:** "problem 3 is called build the MCP server"

**Follow-ups:**

1. "we need to write an mcp server using fastMCP"
2. "this will talk to data/campus_customs_new.db"
3. "every agent in this assignment will use tools in this mcp server. we need to write 3 tools we'll definitely need for tickets in this database"
4. "give me suggestions for the tools"
5. "keep the tool names clear"
6. "don't make up any data... use only what is in the database"
7. "which would you recommend?"
8. "okay in output/harness.md list each of the 3 mcp tools. for each tool include which table it reads , which ticket it helps unlock and one sentence on why that tool is the right one for that ticket"
9. "be specific"
10. "tie the tool to the ticket"
11. "also, let's add a short mcp_server/README.md file that explains what the mcp server is for, which database file it uses and the three tools in it"
12. "we can leave it for now, we can fix at the end if the problem suggests a different expected layout"

**Note:** The folder is `mcp/` holding `mcp_server.py` and `README.md`, matching
the lecture 9 layout. If the final problem's file tree expects `mcp_server/`,
rename it then.

## Problem 4: Add the MCP server to vibe coder and test each tool

**My prompt:** "okay problem 4 is called Add the MCP server to vibe coder and test each tool"

**Follow-ups:**

1. "the MCP server needs to be added to this project so claude code can call the tools. save the connection JSON text to .mcp.json at the project root"
2. "with the claude code connected, test each of the 3 MCP tools. Save evidence in output/mcp_smoke.json"
3. "for each tool save the prompt asked, the tool name and the tool output"
4. "tool output must match values in data/campus_customs_new.db"
5. "has the bug been fixed? make sure there are no bugs"
6. "we need to follow the instructions of the prompt for me to get an A"
7. "so I need to exit claude and come back?"
8. "okay I'm back"

## Problem 5: Build the agent team and grow the MCP tools

**My prompt:** "problem 5 is called build the agent team and grow the MCP tools"

**Follow-ups:**

1. "we need to build the agentic team for campus customs using PydanticAI: Boss, Inventory, Accounting, Facilities and Customer Service"
2. "we need prompts, models and agent loops so they can delegate work to eachother"
3. "with full connectivity"
4. "put the agent prompts in backend/prompts/ one file per agent"
5. "put data types in backend/models.py and agent files under backend/"
6. "write each prompt with shop rules that the agent needs"
7. "make sure the prompt is in my own voice, send suggestions for me to approve"
8. "more detailed prompts score higher"
9. "cover all aspects of each agent's scope and work"
10. "let me see the full prompts"
11. "add any tools the agents need to the MCP server so they can work on the open tickets. shop facts come from the MCP server over data/campus_customs_new.db ... do not invent a second shop-tools layer that bypasses MCP. wire the agents so they append to output/audit_trail.json as they run. for each agent-loop step, record enough to audit later. append to this file, dont wipe each run"
12. "in output/harness.md list each MCP tool along with which table the tool uses"
13. "also let's add a short saftey section"
14. "what guardrails would a business want when agents touch real customers money? and limits that keep token usage in check"
15. "okay make sure harness doc is updated with guardrails"
16. "also, update mcp_server/README.md so the tool list matches what we have now"
17. "sure, whatever you think is necessary for me to get an A"

**Note:** A full board run exposed duplicate approval requests. Three agents
independently filed a request for the same $840 invoice, so a human would have
seen five requests worth $5,920 against $3,240 of real obligations.
`request_approval` is now idempotent per obligation. Test suite grew to 33.

## Problem 6: Plan three tickets

**My prompt:** "okay problem 6 is called Plan 3 tickets. before we wire the backend, let's write down what we expect the team to do on each open ticket. build output/desk_tickets.html this should be a page we (and the grader) with one tab per ticket (101, 102, 103). We also need empy cash and reflection tabs for later problems in the assignment. on each ticket, let's fill in an expected section and leave from for an actual section after we run the agents. in the expected section, I need to add (in my own words + voice) who the boss would call and why, all the agent delegations I expect and which MCP tools I expect the run would use... we can't just say each ticket would call all specialists... we need logical hypothesis based on the ticket. send me suggestions"

**Follow-ups:**

1. "okay for ticket 103, we need to specify who the boss would call first"
2. "I agree" (inventory first on ticket 103)
3. "okay lets add these expectations to the html"
4. "make sure AI prompts is updated for problems 5 and 6 as well"

**What problem 6 produced:** `output/desk_tickets.html`, a standalone page with
five tabs. One per ticket, plus empty Cash and Reflection tabs for later
problems. Each ticket tab has an Expected section written before any run, and
an empty Actual section to fill in afterwards.

The Expected sections name who the boss calls first and why, the delegation
chain, and the MCP tools the run should use. They are specific per ticket
rather than listing every agent on every ticket:

- **101** starts with inventory, because it is a stock question first. Expected
  chain is boss to inventory to accounting, then customer service. Facilities
  is not involved.
- **102** starts with facilities, because a landlord email is a claim and the
  lease is the fact. Expected chain is boss to facilities to accounting, and
  two hops should be enough. Inventory is not involved.
- **103** starts with inventory, not accounting. The club wants 20 and the shop
  has 8, and that gap changes what is being offered. There is no point pricing
  a discount on units that cannot be delivered. Facilities is not involved.

The hypothesis worth testing across all three is that tickets 101 and 103 are
blocked by the same $840 invoice, so whichever runs second should reuse the
existing approval rather than asking for the same money twice.

---

## Problem 7: Backend routes

**My prompt:** "problem 7 is called Backend routes"

**Follow-ups:**

1. "the react frontend dashboard (this will be the next problem) needs a backend it can call"
2. "In backend/main.py use FastAPI and add routes that do the following ... return three tickets and whther each is open or resolved, take a ticket id and run you agent team on that ticket, return agent events (what each agent said and which tools they used, so the dashboard can refresh), approve payment or purchase after a human clicks approve (agents only prepare the pay, this route is actually what changes cash), return the current checking balance from cash_accounts, reset the database to the original values when you want to try a fresh run"
3. "from the backend/ folder start the server with uvicorn main:app --reload --port 8000"
4. "in output/harness.md, list each route in one line. this should include the url and what it does"

---

## Problem 8: Agent dashboard

**My prompt:** "okay problem 8 is called Agent dashboard. build the frontend dashboard in frontend/ with React + Vite + TypeScript. The page should call the routes we built in the previous problem. at minimum, the board should list all three tickets, let you pick one ticket and start the agent team on it, show each agent and what they are saying / doing while the ticket runs, mark a ticket resolved when the run finishes, show a short summary of what each agent did on that ticket, let a human approve a pay or purchase when asked, show the checking balance (checking balance should drop after an approved pay). the front end should talk to the backend at http://localhost:8000 , allow the Vite page origin so the browser is allowed to call those routes. start the board with npm run dev"

**Follow-ups:**

1. "we also need to make sure the dashboard looks good"
2. "give me design suggestions also. I'll be graded on this"
3. "and we need to add to output/design.md with what we chose for the dashboard layout, how the agents read differently, how resolved tickets and cash show up and why the creative and design choices we made make it feel special and something humans would enjoy using"
4. "think if the UX UI"
5. "let me see it when it's ready so I can give feedback on the design and layout"
6. "does the model need to be listed on the app?"
7. "dont remove it if it will do anything with the grading"
8. "I'm just not sure why it should visuallt be on the dashboard?"
9. "woah why are the ticket details coming up at the bottom of the screen?"
10. "do you think that's user riendly for humans?"
11. "thats prob the most important info"
12. "okay i think this looks much better"
13. "is anything broken or not adhering to my prompts?"
14. "I want to get an A? if everything is good, we can move on"
15. "okay make sure the design doc is updated with anything we changed and why"

---

## Problem 9: Resolve the tickets

**My prompt:** "problem 9 is called resolve the tickets... dont do anything until i give you the prompt"

**Follow-ups:**

1. "Before testing the agents on a full run over three tickets, reset the working database data/campus_customs_new.db again so we start clean. Not the starting checking balance. then run all three tickets on the board until each is resolved. open output/desk_tickets.html from problem 6. on each ticket tab, fill the actual section from this run: which agents worked, what they delegated, and which tools they used. keep the expected section so we can compare the two. on the cas tab of the same html, itemize the money (starting checking balance - after the reset, for each ticket how cash changed when that ticket resolved and why, ending checking balance - it must match cash_accounts in the working database"
2. "wrong cash math loses points even if the board shows every ticket resolved"
3. "we need to save output/resolved_tickets.json for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals"
4. "we also need to save output/resolved_board.html, a page where you can double click with a screenshot of the React board for each resolved ticket"
2. "wrong cash math loses points even if the board shows every ticket resolved"

**What problem 9 produced:** a full run over all three tickets from a reset
board, with the Actual sections and the Cash tab of
`output/desk_tickets.html` filled in from that run.

Cash reconciles exactly. Starting $3,400.00, three approved payments totalling
$3,248.00, ending $152.00, which matches `cash_accounts.balance` in the working
database.

Three predictions from problem 6 were wrong, and the page says so rather than
quietly agreeing with itself:

- **102** was predicted as `boss -> facilities -> accounting`. Facilities was
  never called. Accounting pulled the lease itself, so the check happened in
  the wrong seat.
- **103** was predicted to start with inventory. It started with accounting.
- **101** was predicted to go `inventory -> accounting`. The boss kept both
  hand-offs instead, so the shape was a hub rather than a chain.

Ticket 101 finished on `waiting` rather than `closed`, which is correct. The
tee is paid for and ordered, but the vendor has a 5 day lead and the shop's
today is 2026-08-31. Closing it would mean claiming stock had arrived when it
has not.
5. "append real runs to output/audit_trail.json"
6. "finish output/harness.md so it covers tables, MCP tools, the five agents, API routes, the dashboard and safety rules"

---

## Problem 10: Reflection

**My prompt:** "okay problem 10 is called reflection"

**Follow-ups:**

1. "yes we need to add to the reflection tab. In my voice and vibe, we need to add how would you evaluate the performance of the agents on each ticket and why? for each ticket, how did Actual compare to the expected plan you wrote earlier? what would have been simpler as one agent with tools and why? describe new problems campus customs might face that this agent team could solve with the agents we built? describe 3 new problems campus customs might face that this agent team could not solve with the tools we built and explain the tools and agents we would need to solve them. every answer should be tied to this app and the three tickets we ran, use the ticket tabs and cash tab on the same page as evidence"
2. "we need actual campus customs details. anything generic will score low. so pay attention to detail"

---

## Problem 11: Submit the repo

**My prompt:** "okay we need to push the code to a public GitHub repo"

**Follow-ups:**

1. "so graders can access and grade it"
2. "I need to submit the repo to canvas"
3. "and add it to output/github_url.txt"

**Repo:** https://github.com/theashleyjoyce/campus-customs-multi-agent (public)
