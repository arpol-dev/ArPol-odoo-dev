# ai_agent_session/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'AI Agent Session',
    'version': '18.0.3.0.0',
    'summary': 'Launch an OpenCode session on the IArPol server from the chatter or a server action',
    'description': """
AI Agent Session
================

Adds an "AI Agent" button next to "Activities" in every chatter, and a "Launch AI Agent
Session" server action type. Both call the IArPol webhook, which creates an OpenCode session
on the server with a prompt built from the record's data, its chatter history and the request
typed by the user. The session is then managed in IArPol: Odoo does not follow it. A chatter
note records the session reference, the model and the permissions.

The list of available models is synchronized from the same server (AI Agent preferences).
""",
    'author': 'Armand Polmard',
    'website': 'https://arpol.fr',
    'category': 'Discuss',
    'depends': ['mail'],
    'external_dependencies': {
        'python': ['requests'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/ai_agent_session_wizard_views.xml',
        'views/ir_actions_server_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_agent_session/static/src/chatter_ai_agent.js',
            'ai_agent_session/static/src/chatter_ai_agent.xml',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
}
