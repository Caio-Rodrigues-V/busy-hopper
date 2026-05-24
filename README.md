# AI Agent Orchestrator Control Plane

A multi-agent autonomous corporate orchestrator control plane featuring hierarchical organizational structure, strict multi-tenant boundaries, Fernet credentials encryption, real-time live execution tracing, heartbeats scheduler, cost control budget locks, and an interactive dashboard.

## Key Concepts

- **Company (Multi-Tenant)**: Renders strict data boundaries. Each company has a custom natural language mission statement that informs all subordinate tasks.
- **Hierarchical Org Chart**: Agents report to bosses in a tree line (CEO Sophia -> Manager Marcus -> Worker DevBot). Allowed tools are constrained by the principle of least privilege.
- **Execution Run Traces**: Individual task checkouts are tracked step-by-step. Inputs, outputs, tool invocations, token usage, and latency metrics are captured in an append-only ledger.
- **Governance Gateways**: Governed actions (e.g. bash commands, Meta Ads campaigns deployment) automatically pause the agent loop and raise an approval ticket for human board decision before resuming execution.
- **Cost Hard-Stops**: Agents and companies have strict monthly cost thresholds. Reaching them automatically pauses execution and triggers budget alerts.
- **Meta Ads Orchestrator**: A dedicated sidebar section to configure Meta Ads connection settings (Token, Ad Account, Page, Pixel) and manually deploy simulated campaigns or track campaigns deployed autonomously by agents.
- **Agent Workspace Gallery & SVG Creative Tool**: Clicking on any agent inside the Org Chart opens their workspace profile, listing files (copies, banners, HTML pages) generated during their runs. Features an inline copy reader and vector SVG banner viewer. Agents can use the `generate_image_asset` tool to compose styled ad creatives natively.
- **Guarded WebSockets**: Connections to the real-time stream are fully authenticated using JWT tokens and checked against database company ownership records to prevent unauthorized eavesdropping.

---

## Getting Started

### 1. Backend Setup

Prerequisites: Python 3.11 or 3.12.

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. Install packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file based on `.env.example` (or use the populated defaults for local testing):
   ```
   SECRET_KEY=super_secret_jwt_key_for_local_dev_change_me_in_production_12345
   ENCRYPTION_KEY=8lqWc_wA-p5HcrgC5lV4TfV3r4f7h9L3t9u3j2m1G4c=
   DATABASE_URL=sqlite+aiosqlite:///./orchestrator.db
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

5. Execute database migrations:
   ```bash
   alembic -c alembic.ini upgrade head
   ```

6. Seed default company data (Admin: `admin@autonomous.corp` | Password: `password123`):
   ```bash
   python app/database_prepop.py
   ```

7. Launch development server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

---

### 2. Frontend Setup

Prerequisites: Node.js 18+.

1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```

2. Install node packages:
   ```bash
   npm install
   ```

3. Launch Vite development server:
   ```bash
   npm run dev
   ```
   By default, it launches at `http://localhost:5173`.

---

## Running Verification Tests

To execute backend unit tests:
```bash
cd backend
pytest tests/
```
All core encryption functions, password hashers, JWT authenticators, and token rate calculators are validated.
