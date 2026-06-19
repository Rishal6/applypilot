# Product Decisions

## 1. Product Name

Use `ApplyPilot`, not a name tied to LinkedIn. This keeps the product extensible to other job sources and avoids unnecessary platform-brand dependency.

## 2. Local-First

Browser automation and session data stay on the user's machine. The SaaS should not require LinkedIn credentials.

## 3. Explicit Auto-Submit

Auto-submit is required for the paid product. The default workflow can still be review-first for trust, but users must be able to enable `auto-submit` with a daily limit and minimum score threshold.

## 4. BYOK Plus Managed AI

Users can bring OpenAI-compatible keys or use Ollama locally. Paid plans can later offer managed AI credits.

## 5. One Core

CLI, desktop, MCP, ChatGPT App, and SaaS should all use the same core models and storage contract.

## 6. Automate Last

The most defensible product value is good matching, daily workflow, and trusted execution. Full automation should reuse the same policy layer instead of living as scattered browser-script behavior.
