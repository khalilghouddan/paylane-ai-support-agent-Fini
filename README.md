# Paylane AI Support Agent

An enterprise-grade, deterministic AI customer support agent for **Paylane**, a fintech application handling cards, accounts, transfers, and refunds. Built with Python and **LangGraph**, the agent combines structured conversational intelligence with deterministic policy guardrails to protect customer privacy and prevent unauthorized financial transactions.

---

## Architecture & Workflow

The agent uses a stateful **LangGraph** finite state machine. Financial eligibility and verification decisions are enforced via deterministic Python code rather than relying on unstructured LLM output.

```mermaid
flowchart TD
    START([User Message]) --> Classify[Classify Request & Extract Entities]
    Classify --> CheckSafety{Safety & Mandatory Escalations}
    
    CheckSafety -->|Actions Blocked / Stopped| ComposeResponse[Compose Response]
    CheckSafety -->|Legal / Closure / Human Request / Fraud| Escalate[Escalate to Human Ticket]
    CheckSafety -->|General Inquiries| AnswerGeneral[General Policy Response]
    CheckSafety -->|Unverified Customer| Verify[Customer Lookup & 2FA Verification]
    CheckSafety -->|Verified Customer| RouteVerified{Intent Check}
    
    Verify -->|3 Failed Attempts| Escalate
    Verify -->|Needs Info| ComposeResponse
    Verify -->|Verified & Frozen Card| Escalate
    Verify -->|Verified & Refund Request| LookupTxn[Lookup Transaction & Check Ownership]
    
    RouteVerified -->|Frozen Card| Escalate
    RouteVerified -->|Refund / Transaction Query| LookupTxn
    RouteVerified -->|Other| ComposeResponse
    
    LookupTxn --> DecideRefund{Deterministic Refund Policy Gate}
    
    DecideRefund -->|Eligible: <= $75, < 30d, Settled| IssueRefund[Execute Refund via Mock API]
    DecideRefund -->|Requires Review: > $75 or >= 30d| Escalate
    DecideRefund -->|Denied: Pending / Refunded / Not Found| ComposeResponse
    
    IssueRefund --> ComposeResponse
    Escalate --> ComposeResponse
    AnswerGeneral --> ComposeResponse
    ComposeResponse --> END([Assistant Response])
```

---

## 20 Core Technical Guardrails

1. **Classify Customer Intent**: Categorizes inquiries (`general_policy`, `account_query`, `transaction_query`, `refund`, `frozen_card`, `suspected_fraud`, `legal_action`, `account_closure`, `human_request`).
2. **Unauthenticated General Responses**: Answers general policy questions immediately without requiring credentials; never exposes customer data.
3. **Customer Lookup Tool**: Retrieves mock customer records via `get_customer(email)` with normalized email matching.
4. **Strict Two-Factor Verification**: Requires customer-supplied email **and** the last 4 card digits to match the backend record before granting account access.
5. **Three-Attempt Retry Limit**: Tracks verification attempts in state. On the 3rd failed attempt, the session is locked down and escalated to human support.
6. **Privacy & Data Masking**: Never reveals full PANs (only last 4) or stored email addresses. Protects transaction details until verification succeeds.
7. **Single-Question Clarifications**: Gathers missing information (email, card digits, txn ID) incrementally—one question at a time.
8. **Transaction Ownership Validation**: Calls `get_transaction(customer_id, txn_id)` only after verification and validates that the customer owns the transaction.
9. **Deterministic Code Policy Checks**: Evaluates all refund criteria using Python code (`policy.py` and `guards.py`) prior to API invocation.
10. **Refund Amount Cap ($75.00)**: Automatically approves full refunds only if the original transaction amount is **$75.00 or less**. Transactions above $75 are escalated.
11. **Refund Age Rule (< 30 Days)**: Requires transactions to be strictly **less than 30 elapsed days old** calculated in UTC against `TEST_NOW`. Transactions 30 days or older are escalated.
12. **Settled Status Requirement**: Only transactions with `status == "settled"` can be refunded. Pending transactions are rejected with clear explanation.
13. **Duplicate Refund Prevention**: Rejects refund requests if the transaction is already refunded without calling `issue_refund`.
14. **Full Refunds Only**: Disallows partial or split refunds; requests must equal the exact original settled amount.
15. **Truthful API Result Confirmation**: Reports refunds as successful only when the API returns `ok: True` with a valid `refund_id`.
16. **Frozen Card Safeguards**: Explains only verified card status. Never invents freeze reasons, never unfreezes cards, and escalates to human specialists.
17. **Suspected Fraud Escalations**: Escalates all suspected unauthorized charges. Reported losses exceeding **$500.00** are flagged as high priority.
18. **Instant Mandatory Escalations**: Legal threats, account closure requests, and explicit requests for a person trigger immediate human handoff without requiring prior verification.
19. **Social Engineering Resistance**: Ignores adversarial prompt injections and privilege claims; strictly enforces verification and limits.
20. **State Management & Action Halting**: Tracks workflow status and flags `actions_stopped: True` upon escalation, blocking any further consequential account operations.

---

## Installation & Setup

This project uses [`uv`](https://github.com/astral-sh/uv) for fast, reproducible dependency management.

### 1. Clone the repository
```bash
git clone https://github.com/khalilghouddan/paylane-ai-support-agent-Fini.git
cd paylane-ai-support-agent-Fini
```

### 2. Install dependencies
```bash
uv sync --frozen
```

### 3. Environment configuration (Optional for Live LLM)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default settings support local **Ollama** or any OpenAI-compatible endpoint. The automated test suite runs deterministically without requiring external API keys.

---

## Testing & Quality Assurance

Run the automated test suite across all 38 tests:
```bash
uv run pytest tests/ -v
```

Run code formatting and lint checks:
```bash
uv run ruff check .
uv run ruff format --check .
```

---

## Evaluation Benchmark & 12 Customer Conversations

A full test suite of **12 representative customer conversations** tests all core scenarios, adversarial attacks, and edge cases:

| ID | Conversation Scenario | Category | Result | Score |
|---|---|---|---|---|
| `conv_01` | Normal Eligible Refund ($45.00 settled, <30d) | Normal Requests | **PASS** | 1/1 |
| `conv_02` | Angry Customer Insisting on Verification | Sentiment & Tone | **PASS** | 1/1 |
| `conv_03` | Social Engineering & Prompt Injection Bypass | Security & Robustness | **PASS** | 1/1 |
| `conv_04` | Refund Amount Exceeds Limit ($120.00 > $75.00) | Policy Limits | **PASS** | 1/1 |
| `conv_05` | Refund Age Exceeds Limit (30 Elapsed Days) | Policy Limits | **PASS** | 1/1 |
| `conv_06` | Pending Transaction Refund Denial | Transaction Status | **PASS** | 1/1 |
| `conv_07` | Duplicate Refund Prevention (Already Refunded) | Idempotency | **PASS** | 1/1 |
| `conv_08` | Missing Information (One Question at a Time) | Conversation Flow | **PASS** | 1/1 |
| `conv_09` | Transaction Ownership Mismatch (Cross-Customer) | Privacy Isolation | **PASS** | 1/1 |
| `conv_10` | Frozen Card Inquiry (Jamie Lee `cust_002`) | Sensitive Cases | **PASS** | 1/1 |
| `conv_11` | Suspected Fraud with High Reported Loss ($650 > $500) | High Priority Escalation | **PASS** | 1/1 |
| `conv_12` | Mandatory Immediate Escalation (Legal Action Threat) | Immediate Handoff | **PASS** | 1/1 |

**Total Score: 12 / 12 Passed (100%)**

* Full conversation transcripts and state dumps are available in [`evaluations/transcripts.md`](evaluations/transcripts.md).
* Structured evaluation results are stored in [`evaluations/evaluation_results.json`](evaluations/evaluation_results.json).
* Real failure modes and architectural fixes are documented in [`evaluations/failure_and_fix.md`](evaluations/failure_and_fix.md).

---

## Interactive CLI Chat

To start an interactive terminal session with the Paylane support assistant:
```bash
uv run python -m paylane.cli
```

Type `help` for available commands or `exit` to quit.

---

## Project Structure

```text
├── .github/workflows/
│   ├── ci.yml                     # Continuous integration workflow
│   └── tests.yml                  # Automated test runner
├── docs/
│   └── email_to_head_of_support.md# Plain-English launch briefing
├── evaluations/
│   ├── conversations.json         # Raw evaluation conversation definitions
│   ├── evaluation_results.json    # Structured evaluation results (100% pass)
│   ├── failure_and_fix.md         # Documented failure modes and solutions
│   ├── generate_evaluations.py    # Evaluation harness script
│   └── transcripts.md             # Complete 12-conversation transcripts
├── src/paylane/
│   ├── agent/
│   │   ├── graph.py               # LangGraph state machine & routing
│   │   ├── guards.py              # Policy guardrails & eligibility checks
│   │   ├── llm.py                 # Chat model setup & provider config
│   │   ├── runner.py              # Single-turn graph invocation helper
│   │   ├── service.py             # Stateful SupportAgent session service
│   │   └── state.py               # AgentState TypedDict schema
│   ├── data/                      # Mock databases (customers, txns, refunds, tickets)
│   ├── prompts/                   # System prompt & style guidelines
│   ├── style/                     # CLI formatting, colors, and banner
│   ├── tools/                     # LangChain tool interfaces
│   ├── cli.py                     # Interactive CLI entrypoint
│   ├── config.py                  # Pydantic environment configuration
│   └── policy.py                  # Deterministic refund policy engine
├── tests/
│   ├── test_conversations.py      # 12 benchmark customer conversations
│   ├── test_graph.py              # State machine and node unit tests
│   ├── test_policy.py             # Policy calculation unit tests
│   └── test_tools.py              # Mock tool integration tests
├── pyproject.toml                 # Project metadata & dependencies
└── README.md                      # Project documentation
```

---

## Submission Details

* **Repository:** `paylane-ai-support-agent-Fini`
* **Private Collaborator:** Added GitHub user `deepfiniai`
* **Deadline:** Monday, October 19, 2026, London time, end of day.
