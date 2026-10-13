# Dashboard design

Notes on how the Campus Customs dashboard is built and why it is built that
way. The job of this page is to let a person watch five agents work and step in
when money is involved. Everything below follows from that.

## The layout

Three columns under a status bar.

```
┌──────────────────────────────────────────────────────────────┐
│  Campus Customs            CHECKING  SHOP DATE  MODEL  RESET │
├───────────────┬──────────────────────────────┬───────────────┤
│  THE BOARD    │  LIVE AGENT ACTIVITY         │  THE TEAM     │
│               │                              │               │
│  #101 ticket  │  Boss      read the ticket   │  ● Boss       │
│  #102 ticket  │  Inventory called check_stock│  ● Inventory  │
│  #103 ticket  │  Boss      asked Accounting  │  ● Accounting │
│               │                              │  ● Facilities │
│               │  What each agent did         │  ● Customer   │
│               │  [summary cards]             │               │
│               │                              │  WAITING ON   │
│               │                              │  YOU          │
│               │                              │  [$840 card]  │
└───────────────┴──────────────────────────────┴───────────────┘
```

The middle column is the widest and it holds the live feed. That is deliberate.
The assignment is about watching a team work, so the watching is the centre of
the page and everything else is support.

The left column is the board. Three tickets, each a card you can click, each
with its own run button. You never have to go looking for the thing that starts
a run.

The right column is the people and the decisions. The team at the top so you
can see who is busy, the approval queue underneath so money requests land in
the same place your eye already is.

The top bar carries the four things you want at a glance and never want to
scroll for: the balance, the shop date, the model, and a reset.

## How the agents read differently

Five agents in one feed could easily turn into a wall of identical text. Three
things stop that.

**Each agent has its own colour.** Boss is pink, Inventory green, Accounting
amber, Facilities purple, Customer Service blue. That same colour is used three
times: the dot in the roster, the name in the feed, and the dot on the summary
card. You can follow one agent down the page by colour alone, without reading.

**Names are right-aligned in a fixed column.** The feed is a two column grid
with the agent name on the left at a set width. That gives you a clean vertical
edge to scan, so a glance tells you who is talking before you read what they
said.

**Agents speak in sentences, not JSON.** The backend sends audit steps. The
page turns each one into a line a person can read. "Inventory called
check_stock". "Boss asked Accounting: can we cover an $840 invoice". Tool names
still appear, as small chips under the sentence, so the detail is there without
being the main event.

The lines are also styled by what kind of thing happened. A delegation is
italic, because one agent handing work to another is the interesting moment. A
final answer is bold. A refusal or error is red. You can tell the shape of a
run from six feet away.

## How a resolved ticket shows up

A ticket that has been worked changes in four ways at once, because one signal
is easy to miss.

- The left rail of the card turns green
- The card background picks up a soft green wash
- The status chip changes and grows a tick
- The button changes from "Run the team" to "Run again"

While a run is going the rail is amber and the chip says "running", so there
are three clear states rather than two: untouched, in progress, done.

Above the summary cards there is a second confirmation, the heading "What each
agent did on ticket #101" with a resolved chip beside it. By then you have been
told the same thing in two places, which is about right for the one outcome the
page exists to produce.

## How cash shows up

The balance is the biggest number in the top bar, bigger than the shop date and
the model next to it. It sits in a lighter tile so it reads as the primary
figure.

When it changes it does not just quietly update. The tile flashes amber, the
number scales up briefly, then settles. The whole thing takes 1.6 seconds. This
matters because "the balance drops after an approved payment" is the single
most important cause and effect on the page, and a number that silently changes
while you are looking somewhere else is a missed moment.

Underneath the balance a second line appears once anything has been spent,
reading "$840.00 paid out". The shop has no income, so the only direction this
number goes is up, and showing it next to the balance makes the one way nature
of the money obvious.

Further down the right column there is a Money Out list, one row per payment,
each showing the amount, what it settled and who approved it. That is the
audit view. The top bar is the glance view. Same facts, two depths.

## Approvals

The approval card is the one piece of the page designed to interrupt you.

It is warm cream against a page of cool greys and blues, it has an amber left
rail, and the amount is set large. It animates in rather than appearing. It sits
under a heading that says "Waiting on you" rather than "Approvals", because the
first is a request and the second is a filing cabinet.

Two buttons, approve and deny, both full width, side by side. No dropdown, no
confirm dialog. A human looked at a number and made a call, and the interface
should take about as long as that did.

When there is nothing pending the space does not go empty. It says "Nothing to
approve. Agents prepare payments, they never make them." That sentence is doing
real work. It tells a first time visitor the most important rule of the system
at the moment they are most likely to wonder about it.

That sentence also has to be true, and at one point it was not quite. The
payment tool originally accepted any non-empty name in its approver field, so a
payment could go through without a human ever clicking this button. The
dashboard route caught it, but the tool underneath did not. It is fixed now:
the tool requires an approval record that a person actually decided, matched on
what is being paid and which bill. A name on its own is refused, and so is a
name against a request still sitting on pending.

That matters for the interface and not only for the backend. This button is the
only path to spending money in the entire system, so the copy next to it is a
promise about how the whole thing behaves. It should not be a promise the
plumbing can quietly break.

## The decision record

The notes on a ticket are the outcome of a run. They say what the team decided
and why, which makes them the most important text on the page.

The first version put them in a sticky bar at the bottom of the window. That
was wrong twice over. It was the least readable spot on the page, and because
the backend appends a note for every decision, the bar grew to 2,550 pixels
tall holding 1,300 characters. A sticky footer taller than the screen.

Now the record sits at the top of the middle column, where the eye lands after
clicking a ticket. The notes field stores entries separated by a pipe, so the
page splits on that and numbers them. A run that produced three decisions reads
as three decisions. The original customer request is styled differently from
the rest, because it is the ask rather than something the team concluded.

The card takes a green rail once the ticket is settled, matching the ticket
card on the left, so the two agree at a glance.

## Small things that make it feel considered

**The empty feed teaches.** Before the first run it does not sit blank. It says
what is about to happen and in what order. A new person can read it and know
what they are about to watch.

**Lines slide in.** Each new feed line animates up by four pixels over about a
fifth of a second. Barely visible on its own, but it makes a run feel like
something happening rather than a list refreshing.

**The working dot pulses.** An agent that is thinking has a dot with a soft
expanding ring. An idle agent is grey. A finished agent is solid colour on a
pale green row. You can answer "who is busy" without reading a word.

**The feed auto scrolls, the page does not jump.** New lines scroll the feed
container, not the window, so reading the summary while a run continues does
not yank you around.

**Numbers are tabular.** Balances, amounts and ticket ids all use tabular
figures so columns of money line up and do not jitter as they change.

**Polling stops during a run.** While the stream is open the page does not also
poll in the background. The stream is the truth, and two sources would fight.

## What changed after the first build, and why

Three things moved after the dashboard was first working. Each is here because
the reasoning is more useful than the result.

### The ticket detail moved out of a sticky footer

The first version pinned the selected ticket's notes to the bottom of the
window. It looked tidy with one short note on it. The problem is that the
backend appends a note for every decision the team makes, so after a real run
that bar held 1,300 characters and measured 2,550 pixels tall. A sticky footer
taller than the screen.

Worse, it buried the single most valuable text on the page. Those notes are the
decision record. They say what the team concluded and why, which is the whole
output of a run.

It is now a card at the top of the middle column, where the eye lands after
clicking a ticket, and the entries are split and numbered instead of running
together. Covered in full under The decision record above.

The lesson worth keeping: a layout that works with placeholder data can fail
completely with real data. The footer was fine until the system actually did
something.

### The model tile stayed, and that was a deliberate call

There was a question about whether `gpt-5.6-luna` belongs in the status bar at
all. On pure design logic it does not. A stat tile should hold something you
act on. The balance tells you whether you can approve a payment. The shop date
tells you what counts as overdue. The model tells you nothing you would use
while working a ticket, and at equal visual weight it flattens the hierarchy
around the number that actually matters.

It stayed anyway, for two reasons. Someone opening the app cold can see what it
is running on without digging through `config.py`, which is worth something for
a demo. And this project runs on a substituted model, documented in the README
and in `backend/config.py`, so showing it openly is more honest than tucking it
away for the sake of a cleaner bar.

Design is not the only input. Being straightforward about what the system is
running won out over visual tidiness.

### The approval button became a real guarantee

Described under Approvals above. The short version is that the interface was
making a promise the plumbing could break, and the plumbing was fixed rather
than the copy softened.

## Why it feels like something a person would use

The page is built around one honest idea, which is that this system does work
on its own right up until money is involved, and then it stops and waits for
you.

So the layout gives the agents the biggest column and lets you watch them. It
gives you a colour coded cast rather than a log. It makes the moment they stop
and ask for money look and feel different from everything else on the screen.
And it makes the consequence of your decision, the balance falling, impossible
to miss.

It does not try to look like an enterprise console, with dense tables and
twelve filters. It looks like a shop counter with a board on it. That suits a
small Yale apparel shop staffed by five agents, and it keeps the attention on
the thing worth watching, which is a team of agents figuring out that one
unpaid invoice is blocking two separate customers.
