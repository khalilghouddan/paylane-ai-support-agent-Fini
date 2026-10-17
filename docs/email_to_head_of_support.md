# Briefing to Paylane Head of Support: AI Support Agent Readiness Review

**To:** Head of Customer Support, Paylane (<support-leadership@paylane.internal>)  
**From:** Antigravity AI Engineering Team (<engineering@paylane.internal>)  
**Date:** October 17, 2026  
**Subject:** Paylane AI Support Agent — Architecture, Policy Safeguards, Capabilities, Limitations & Launch Readiness  

---

Dear Head of Support,

We are pleased to present the initial release of the **Paylane AI Support Agent**, an automated customer support solution built with Python and LangGraph. The agent is designed to streamline front-line card, transaction, and refund inquiries while maintaining strict compliance, fraud prevention, and customer data privacy standards.

Below is an executive overview of the agent's capabilities, deterministic safety rules, operational limitations, and key business questions we recommend aligning on before production rollout.

---

### 1. Key Capabilities

* **Unauthenticated Policy Inquiries:**  
  The agent can immediately answer general policy questions (such as refund timelines, eligibility windows, and operating hours) without requiring credentials, while never disclosing sensitive account details.
* **Deterministic Two-Factor Customer Verification:**  
  Prior to revealing account balances, transaction history, or executing any account action, the agent requires both the customer-supplied email address and the last four digits of their card to match our backend record. Verification state is controlled by Python code, never by language model judgment.
* **Automated Full Refunds:**  
  The agent can autonomously evaluate and issue full refunds for settled transactions meeting all of the following criteria:
  * Belong to the verified customer.
  * Transaction status is strictly `settled`.
  * Original transaction amount is **$75.00 or less**.
  * Transaction age is strictly **less than 30 elapsed days** in UTC.
  * Has not been previously refunded.
* **Progressive Multi-Turn Clarification:**  
  When details (such as transaction IDs or card digits) are missing, the agent asks concise, warm, clarifying questions one at a time.
* **Structured Human Handoff & Ticketing:**  
  Whenever an issue exceeds automatic policy boundaries, the agent generates a structured support ticket with an appropriate urgency level (including high-priority routing for reported fraud losses exceeding $500.00).

---

### 2. Operational Guardrails & Limitations

To protect Paylane and its customers, strict boundaries are enforced at the code level:

* **No Partial or Split Refunds:**  
  The agent does not support partial refunds (e.g., refunding $20 of a $45 transaction) or splitting transactions across requests. The requested amount must equal the exact original settled amount.
* **No Refunds for Pending Charges:**  
  Transactions currently in `pending` status cannot be refunded. The agent clearly explains that the charge has not yet settled, without fabricating an arrival date or promising bank clearing timelines.
* **Zero Duplicate Refunds:**  
  Transactions with a status of `refunded` or an existing record in our refund ledger are rejected immediately without calling the refund API.
* **Frozen Cards Protection:**  
  When an account or card is marked `frozen`, the agent only confirms the verified status. It never speculates on or invents why the freeze occurred, never attempts to unfreeze the card, and immediately routes the case to human card security specialists.
* **Three-Attempt Verification Lockout:**  
  If a user fails verification three times within a session, the conversation is locked down (`actions_stopped: True`), an escalation ticket is filed, and all further consequential account actions are halted.
* **Mandatory Immediate Escalation:**  
  Any mention of legal action (lawyers, lawsuits, CFPB complaints), requests for account closure, or explicit demands to speak with a human agent bypass verification and trigger an immediate ticket creation. Once escalated, the agent halts all further actions for that issue.
* **PII & Data Masking:**  
  The agent never exposes stored email addresses on file or full card Primary Account Numbers (PANs). Only the last 4 digits are ever referenced.

---

### 3. Questions to Align on Before Production Launch

Before opening this agent to 100% of live customer traffic, we recommend discussing the following operational and product questions:

1. **Authorization Voids vs. Settled Refunds:**  
   Currently, pending authorizations cannot be refunded and customers are asked to wait until settlement. Would customer support prefer a distinct "void authorization" workflow for pending authorizations that cancels the pending hold before settlement?
2. **Post-Lockout Re-Authentication Pathway:**  
   When a user fails verification 3 times, their session is permanently locked out and handed to a human. What self-service unlock or re-authentication flow (such as magic link email or in-app biometric challenge) should we establish to reduce agent ticket load?
3. **Escalation Notification & Webhooks:**  
   When the agent generates tickets (normal or high priority), what ticketing system integration (e.g., Zendesk, ServiceNow, or Jira Service Management) should receive the real-time webhook payloads, and which on-call queue monitors fraud losses > $500?
4. **Discretionary Human Override Tooling:**  
   For transactions between $75.01 and $250.00 or transactions between 30 and 60 days old, what guidelines will human tier-1 agents use to approve manual exceptions?
5. **Multi-Currency Support:**  
   The current rule enforces a flat $75.00 limit. If Paylane expands into GBP (€/£) or other currencies, should the limit dynamically convert via daily FX rates or follow local statutory caps?

---

### 4. Summary & Verification

The agent has undergone a suite of **38 automated unit, policy, and multi-turn conversation tests**, achieving a **100% pass rate**. Transcripts of all 12 benchmark customer scenarios (including angry users, prompt injection attacks, and fraud edge cases) are available in `evaluations/transcripts.md`.

We look forward to reviewing these findings with you and scheduling our staging deployment.

Warm regards,  
**Antigravity AI Engineering Team**  
*Paylane Core Infrastructure & Agentic Systems*
