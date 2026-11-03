# -*- coding: utf-8 -*-
# Constantes partagées entre le wizard du chatter (ai.agent.session.wizard) et l'action serveur
# (ir.actions.server) : mêmes options, mêmes aides.
AI_AGENT_PERMISSION_DEFAULT = 'allow'
AI_AGENT_PERMISSION_SELECTION = [
    ('allow', "Allow — run without asking"),
    ('ask', "Ask — pause for confirmation in IArPol"),
    ('deny', "Deny — refuse every action"),
]
AI_AGENT_PERMISSION_HELP = (
    "What the agent may do without asking first:\n"
    "• Allow — default. Commands and file changes run without confirmation.\n"
    "• Ask — the session waits for an answer in IArPol before each sensitive action.\n"
    "• Deny — the agent can read and reason, but every action is refused."
)
AI_AGENT_MODEL_HELP = (
    "Model that handles the task. The list comes from the AI Agent server: use the "
    "Synchronize button in your AI Agent preferences when it changes. Empty = the server's default."
)
