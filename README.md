# NexivoReach — AI B2B Sales Prospecting Agent

> **Turn products into prospects.**

NexivoReach is a professional SaaS platform for AI-powered B2B sales prospecting. Unlike simple chatbots or generic CRM dashboards, NexivoReach acts as a multi-step autonomous AI agent. It continuously discovers potential buyers, researches company websites and public signals, qualifies fit against catalog products, transparently explains recommendation scoring, and drafts personalized outreach with strict human approval boundaries.

---

## 🎯 Problem NexivoReach Solves

Many B2B manufacturers and exporters have high-quality products but lack a scalable, structured sales prospecting process. Manual prospecting requires hours of searching, website reading, buying signal detection, catalog matching, and drafting custom emails.

**NexivoReach automates the heavy lifting:**
1. **Understands Products**: Scrapes URLs, parses PDFs/CSVs, or accepts manual catalog entries.
2. **Defines Ideal Customers (ICP)**: Sets target industries, geographic markets, deal sizes, and custom buying signals.
3. **Discovers & Researches Buyers**: Executes real web research to find businesses matching your target buyer profile.
4. **Detects Buying Signals**: Identifies expansion news, new location launches, facility renovations, hiring, and product fit.
5. **Transparent Fit Scoring**: Provides a 100-point fit score with line-by-line evidence and reasoning.
6. **Personalized Outreach Engine**: Drafts customized outreach messages tied to verified company evidence.
7. **Human-in-the-Loop Control**: Requires human review and explicit approval before any message is sent.

---

## 🏗️ Architecture

NexivoReach follows an autonomous Agentic Workflow pattern:

```text
Goal Specification (ICP & Catalog)
            │
            ▼
    Agent Core (FastAPI)
  ┌──────────────────┐
  │  Observe State   │
  │        │         │
  │  Decide Action   │
  │        │         │
  │   Choose Tool    │ ◄───► Tools: WebSearch | SiteScraper | SignalDetector
  │        │         │              CatalogMatcher | ScoreCalculator
  │  Execute Tool    │
  │        │         │
  │  Inspect Result  │
  └────────┬─────────┘
           │
           ▼
    Score & Evidence ───► Personalized Outreach ───► Human Approval
```

---

## 🛠️ Technology Stack

- **Frontend**: React, TypeScript, Vite, Tailwind CSS, Lucide Icons
- **Backend**: Python 3.13, FastAPI, Uvicorn, SQLModel / SQLite (PostgreSQL compatible)
- **AI Providers**: Google Gemini API (Primary), Groq API (Secondary Fallback), with structural fallback heuristics
- **Data Parsing**: PyPDF, OpenPyXL, Pandas, Beautiful Soup 4

---

## 📋 Feature Status & Roadmap

| Feature | Status | Description |
| :--- | :---: | :--- |
| **Initial Setup & Architecture** | ✅ Completed | GitHub repo, modular FastAPI backend & Vite frontend scaffold |
| **Application Shell & Design System** | ✅ Completed | Professional SaaS design system (Linear/Attio inspired, zero AI tropes), responsive navigation tabs, and dark mode palette |
| **Business Onboarding** | ✅ Completed | Natural language business summary & AI profile extraction API |
| **Product Catalog Management** | ✅ Completed | Multi-source product import (URL scraper, PDF, CSV, Excel, Manual) & AI verification tagging |
| **Ideal Customer Profile (ICP)** | ✅ Completed | Target buyer personas, geographic markets, deal sizes & custom buying signal rules |
| **Autonomous Prospecting Agent** | 🚧 In progress | Multi-step agent workflow (`Observe -> Decide -> Tool -> Inspect`) |
| **Web Research Engine** | ⬜ Planned | Search & public site scraping with source attribution |
| **Transparent Prospect Scoring** | ⬜ Planned | Configurable 100-point scoring formula with evidence explanations |
| **Prospect Research Detail View** | ⬜ Planned | 94% fit banner, buying signals, product fit matrix, agent activity timeline |
| **Personalized Outreach Engine** | ⬜ Planned | AI personalized messaging based on verified company evidence |
| **Human Approval System** | ⬜ Planned | Explicit permission barrier for message dispatch |
| **Agent Operational Log** | ⬜ Planned | Full tool execution trace history and decision inspection |
| **Sales Command Dashboard** | ⬜ Planned | Pipeline board, priority leads, real-time agent metrics |

---

## ⚙️ Environment Variables

Create a `.env` file in the root / backend directory:

```env
# AI Providers
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here

# Database
DATABASE_URL=sqlite:///./nexivoreach.db

# Server Configuration
PORT=8000
HOST=0.0.0.0
```

---

## 🚀 How to Run Locally

### Prerequisites
- Node.js >= 18
- Python >= 3.10
- Git

### 1. Clone the repository
```bash
git clone https://github.com/ahmedtayyab/NexivoReach.git
cd NexivoReach
```

### 2. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 💡 Important Design Decisions

1. **No Fake Chatbot / No Hardcoded Pipelines**: The agent evaluates search results dynamically and invokes tools based on observation steps.
2. **Transparent AI Reasoning**: Every claim includes source links/excerpts. No black-box scores.
3. **Human-in-the-Loop Safety**: AI creates outreach drafts; humans approve before dispatch.
4. **Clean B2B Design System**: Modern, high-precision dark accent design system tailored for B2B SaaS users.

---

## 📄 License

MIT License. Designed for AI-powered B2B Sales Prospecting.
