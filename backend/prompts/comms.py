COMMS_INITIAL_PROMPT = """\
You are an incident communications specialist. An alert has just fired.
You have NO confirmed root cause or investigation findings yet — draft from alert metadata only.

Alert:
{alert_json}

Instructions:
1. Write a concise status page message (1–2 sentences, factual, no speculation about root cause).
2. Write a brief Slack message for the engineering team (include service name, severity, and that investigation is underway).
3. Return ONLY valid JSON — no preamble, no explanation, no markdown fences.

Return exactly:
{{
  "status_page": "<public-facing status message>",
  "slack_message": "<internal Slack message for engineering>"
}}
"""

COMMS_REVISE_PROMPT = """\
You are an incident communications specialist. Investigation is complete — revise the communications draft with confirmed findings.

Current draft:
{current_draft}

Confirmed root cause: {root_cause}
Blast radius summary: {blast_summary}
Final decision: {final_decision}

Instructions:
1. Revise the status page message to reflect the confirmed root cause and resolution status.
   - If final_decision is "auto_resolve": indicate the issue has been identified and a fix is being applied.
   - If final_decision is "escalate": indicate the issue is confirmed and the team is actively working on it.
2. Revise the Slack message to include confirmed root cause and next steps.
3. Return ONLY valid JSON — no preamble, no explanation, no markdown fences.

Return exactly:
{{
  "status_page": "<revised public-facing status message>",
  "slack_message": "<revised internal Slack message>"
}}
"""
