# 🚀 Buildathon: Make Wednesdays Great Again

**Masters' Union · For AI Developers · Winner gets Rs. 25,000**

> **Every team must build in a fork of this repository.** Projects not built in a fork of this repo won't be judged.

| | |
|---|---|
| **Date** | Wednesday, 18 November 2026 |
| **Hacking** | **3:00 PM – 7:00 PM IST** (code freeze at 7:00 PM sharp) |
| **Venue** | CDS Audi, 8th floor |
| **Prize** | Rs. 25,000 to the winning team |
| **Register your fork** | 👉 **[https://forms.gle/ZJUYKwTYjsMsVB2b9](https://forms.gle/ZJUYKwTYjsMsVB2b9)** (**deadline 3:30 PM IST**) |
| **Final submission** | Your fork as it stands at **7:00 PM IST**. There's nothing else to submit. |

> 🤖 **Using an AI coding agent?** Point it at [`AGENTS.md`](AGENTS.md). It has the full event brief, tracks, judging and rules in a form agents can read directly. Claude Code loads it automatically through `CLAUDE.md`, and Codex reads `AGENTS.md` natively.

---

## 🎯 Pick one build track

| # | Track | Brief |
|---|---|---|
| **01** | **Build for the Physical World** | Make a real-world task easier, faster or more reliable. Show it in a realistic scenario. |
| **02** | **Build for AI Agents** | Find something an agent struggles with. Build the tool that fixes it, then demo the agent using it. |
| **03** | **Build in Your Area of Expertise** | Pick a field you know firsthand. Ship a working product that improves how people handle it today. |

## ⚖️ How you'll be judged (each criterion is ⅓ of your score)

| Criterion | The question judges ask |
|---|---|
| **Working product** | Does it do what you say it does? Show the core workflow in your demo. |
| **Problem insight** | Who faces this problem, and why does it happen? |
| **Depth of execution** | How well did you solve the hardest part of the build? |

---

## Why fork this repo?

Everyone starts from the same commit (the **genesis commit**) at the same time. Organizers can then check that:
- all code was written **during** the Buildathon and not brought in from an earlier project,
- teams commit steadily instead of pasting in one huge AI-generated dump at the end,
- every repo stays public and visible while you build.

The organizers track every fork automatically: commits, timing and activity. Read [RULES.md](RULES.md) before you write any code.

---

## ✅ Setup (about 5 minutes, do it at 3:00 PM)

**In short:** fork → register your fork in the form **by 3:30 PM** → build → push before 7:00 PM.

### 1. Fork this repo
Click **Fork** (top right). On the fork screen:
- **Owner:** one team member's personal account. Only **one fork per team**.
- **Repository name:** `buildathon-<team-name>`, for example `buildathon-byte-bandits`
- Click **Create fork**.

> ⚠️ Don't download a ZIP or copy the files into a new repo. **It has to be a real GitHub fork**, or the tracker can't see you.

### 2. Keep it public
Forks of a public repo are public. **Don't make it private, archive it, or delete it** until judging is over.

### 3. Add your teammates
In your fork: **Settings → Collaborators → Add people**. Add each teammate's GitHub account so their commits count toward the team.

### 4. Enable Actions
Open the **Actions** tab of your fork and click **"I understand my workflows, go ahead and enable them"**. This runs the automatic check on every push.

### 5. Make your registration commit (your first commit)
Fill in [`team.json`](team.json). `track` must be one of `physical-world`, `ai-agents` or `area-of-expertise`. Then:

```bash
git clone https://github.com/<your-username>/buildathon-<team-name>.git
cd buildathon-<team-name>
# edit team.json
git add team.json
git commit -m "register: <team name>"
git push
```

The **Hackathon check** in the Actions tab should go green ✅. If it's red, open the run to see what's wrong in `team.json`.

### 6. Register your fork (deadline: 3:30 PM IST)
👉 **[https://forms.gle/ZJUYKwTYjsMsVB2b9](https://forms.gle/ZJUYKwTYjsMsVB2b9)**

It's a 4-question Google Form: team name, fork link, track, team members. It connects your repo to the organizers' live tracker.

- Fill it in **once per team**, right after forking, and **no later than 3:30 PM IST**. **Teams that don't register can't be tracked.**
- Paste your **fork's** URL (`https://github.com/<you>/buildathon-<team-name>`), not this starter repo's.
- Need to change something? Use the **"Edit your response"** link on the confirmation page. Don't fill it in twice.
- **Final submission is automatic.** Whatever is pushed to your fork at 7:00 PM IST is what gets judged.

---

## 🛠 While you build (3:00 – 7:00 PM)

- Put your code anywhere in the repo (`app/`, `src/`, `frontend/`, `backend/`…). There's no required layout.
- **Commit early, commit often**, at least every 30 minutes of real work, with messages that say what changed.
- **Push regularly.** Commits you never push don't exist to the tracker.
- AI coding tools (Claude Code, Codex, Cursor, Copilot…) are **allowed and encouraged**. Keep `AGENTS.md` and `CLAUDE.md` in the repo; they keep your agent within the rules.
- Before 7:00 PM, replace the "Your project" section below with your project's README.

## 🧊 Code freeze: 7:00 PM IST

At 7:00 PM the tracker takes a snapshot of every fork. **Commits pushed after code freeze are ignored.** Judges look at your last commit before 7:00 PM.

## ❌ Things that get you flagged

- Rewriting history (`git push --force`, rebasing away the genesis commit, squashing everything into one commit)
- Commits dated before 3:00 PM
- One or two giant commits containing most of the project
- A repo that isn't a fork of this one, or that's private or deleted

See [RULES.md](RULES.md) for the full list.

---

## Your project

### Insights Buddy

**Reads seized phones into one case and answers an officer's questions with the exact records behind every line.**

- **Team:** cipher: Abhay Phalswal, Daksh Yadav, Sanskar Sharma
- **Track:** Build for the Physical World (`physical-world`)

#### The problem: who faces it and why it happens

An investigating officer with a seized phone. A forensic tool pulls everything out of it (chats, calls, photos, voice notes, places, documents), often lakhs of records, and then the officer reads it all by hand. It takes weeks, for four reasons:

1. **People don't spell.** The chats are in Hinglish. "paisa", "pese", "paise" and "पैसे" are one word, and an ordinary search finds only the spelling you typed.
2. **People don't say what they mean.** Gold bars are "biscuits", a bribe is "chai pani", and a contact is saved under a nickname.
3. **The answer is spread across phones.** Money leaves one phone and lands on another. A call is on one log and deleted from the other. Nobody can hold three phones in their head.
4. **The data can't leave the building.** Case material can't be pasted into a cloud chatbot, and an answer without proof is useless in a case file.

#### What we built: the core workflow

1. **Add the phones to a case.** Each export is read once into the case: records, people, money, conversations and a search index.
2. **Dashboard.** The case in plain words: who talks to whom, how much money moved, what was deleted, where the phones were together.
3. **Ask a question** in English or Hinglish, for example *"paisa kisne kisko bheja?"*. Every line of the answer carries numbered citations; clicking one opens the record, the phone it came from and the messages around it.
4. **Across phones.** Six checks done by code: money that left one phone and arrived on another, calls missing from one log, phones at the same place at the same time, both sides of the same chat (what one person deleted is still on the other phone), the same file on several phones, and how each phone saved the others.
5. **Search every spelling at once**, read chats drawn like the app they came from, save findings with notes, keep an audit log, apply a warrant limit, export.

It runs on one computer with no internet. The only data in this repository is made up: `ib/generate.py` writes three sample phones (about 20,000 records) for a sample case called "Operation Biscuit".

#### The hardest part: never saying something we can't point to

- **Code finds the evidence, and code checks every line.** An answer is built from records found by search, money and time, and any line that cites no record is dropped before the officer sees it. With no AI set up, the app still answers from the records alone; with a local model (any OpenAI-compatible server, set in `.env`), the model reads only the evidence code selected, and code checks what it wrote.
- **Cross-phone matching is exact, not guessed.** A payment is matched by amount, time and UPI reference across two phones' bank messages. A missing call is a call on one log with no partner on the other, on a day when that other log has calls.
- **One spelling for every way a word is written** (`ib/text.py`): Hinglish variants, Hindi script, and Indian amounts such as "dedh lakh".

`tests/test_smoke.py` checks the whole path on the sample phones: 9 checks, all passing.

#### How to run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

On Windows use `.venv\Scripts\pip` and `.venv\Scripts\python`. It opens http://127.0.0.1:8000; the sample login is shown on the login page. The first start creates the sample case and reads the three phones in a few seconds.

Run the checks with `.venv/bin/python tests/test_smoke.py`. To use a local AI model, copy `.env.example` to `.env`.

#### Demo (2 minutes)

1. Log in and open **Operation Biscuit (sample data)**: three phones, the numbers, the case in plain words.
2. **Ask** *"paisa kisne kisko bheja?"*, then click a citation: the bank SMS, its record number and the phone file it came from.
3. **Across phones:** Rs 50,000 left Phone 1 and arrived on Phone 2 two minutes later; a 4-minute call is missing from Phone 2's log; both phones were near the airport cargo terminal at 11:40 pm.
4. **Chats, both sides:** the 37 messages one person deleted, still on the other phone.
5. **Search** "biscuit", confirm it as a code word, save a finding.

#### What is not built

"Find by meaning" search, face grouping and the link board are not built. Photos are shown as cards with their extracted text, not as images. The AI path has been tested with a stand-in model only, not yet with a real one.

> **All rights reserved.** This repository is public only so the Buildathon organisers and judges can review it. No one may use or copy this code, its design or the product idea without written permission from its author, Abhay Phalswal. See [LICENSE](LICENSE).
