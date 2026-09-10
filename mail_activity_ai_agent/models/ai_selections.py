# -*- coding: utf-8 -*-
# Constantes partagées entre mail.activity et le wizard mail.activity.schedule (le "Schedule
# Activity" ouvert depuis le chatter passe par ce wizard en Odoo 18, pas directement par le
# formulaire mail.activity — les deux ont donc besoin des mêmes champs/aides).
AI_MODEL_SELECTION = [
    ('', "Server default"),
    ('haiku', "Haiku — fastest & cheapest"),
    ('sonnet', "Sonnet — balanced (recommended)"),
    ('opus', "Opus — deepest reasoning"),
    ('fable', "Fable — newest, less proven yet"),
]
AI_MODEL_HELP = (
    "Which Claude model handles this task:\n"
    "• Server default — whatever the webhook server is configured to use.\n"
    "• Haiku — fastest and cheapest. Best for simple, well-defined tasks "
    "(classification, extraction, short factual answers).\n"
    "• Sonnet — balanced speed/quality. Recommended default for most tasks "
    "(analysis, everyday coding, drafting).\n"
    "• Opus — most capable for complex or ambiguous reasoning, deep analysis. "
    "Slower and more expensive: reserve for tasks that actually need it.\n"
    "• Fable — newest model family member. Use based on your own testing; its "
    "specific strengths are less established yet than Sonnet/Opus/Haiku."
)

AI_PERMISSION_MODE_SELECTION = [
    ('acceptEdits', "Accept edits automatically (recommended)"),
    ('default', "Ask for everything"),
    ('plan', "Plan only, no changes"),
    ('bypassPermissions', "No confirmation at all (risky)"),
]
AI_PERMISSION_MODE_HELP = (
    "How much the agent can do without asking you first:\n"
    "• Accept edits automatically — recommended. File edits run without confirmation, "
    "but shell commands and other sensitive actions still ask (you can step in via the "
    "remote session if needed).\n"
    "• Ask for everything — the agent pauses for your confirmation before each sensitive "
    "action. Safer but the session will need you to connect often.\n"
    "• Plan only — the agent reads and proposes a plan but makes no change at all.\n"
    "• No confirmation at all — fastest but the agent can run shell commands and edit "
    "files with zero oversight. Use only for directories/tasks you fully trust."
)

# Ligne que l'agent doit renvoyer, seule, quand sa tâche est entièrement terminée (plus aucune
# question en attente). Permet de distinguer une vraie fin de tâche d'une simple pause en
# attente de réponse utilisateur (le statut busy/idle seul ne fait pas cette distinction).
AI_AGENT_DONE_MARKER = 'AGENT_SESSION_DONE'
