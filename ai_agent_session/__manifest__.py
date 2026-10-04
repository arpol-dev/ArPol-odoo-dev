# ai_agent_session/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'AI Agent Session',
    'version': '18.0.2.0.0',
    'summary': 'Launch a Claude Code agent session from the chatter or a server action, via webhook',
    'description': """
AI Agent Session
================

Adds an "AI Agent" button next to "Activities" in every chatter, and a "Launch AI Agent
Session" server action type. Both call an external webhook (Claude Code running on a personal
server, configured per user) with a prompt built from the record's data, its full chatter
history and the request typed by the user. The agent works in the background; the conclusion
(or its question) is posted as an internal note on the record, and a systray menu tracks the
sessions.
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
        'security/security.xml',
        'views/res_users_views.xml',
        'views/ai_agent_session_wizard_views.xml',
        'views/ir_actions_server_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_agent_session/static/src/ai_agent_menu.js',
            'ai_agent_session/static/src/ai_agent_menu.xml',
            'ai_agent_session/static/src/ai_agent_menu.scss',
            'ai_agent_session/static/src/chatter_ai_agent.js',
            'ai_agent_session/static/src/chatter_ai_agent.xml',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
}
