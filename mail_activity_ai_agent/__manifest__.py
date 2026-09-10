# mail_activity_ai_agent/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Mail Activity - AI Agent Session',
    'version': '18.0.1.0.0',
    'summary': 'Schedule an activity that dispatches a Claude Code agent session via webhook',
    'description': """
AI Agent Session activity type
===============================

Adds an "AI Agent Session" activity type to the chatter. When scheduled, it calls an
external webhook (Claude Code running on a personal server, configured per user) with
a prompt built from the record's data, its full chatter history and the activity
description. The agent works in the background; Odoo is notified via callback when it
needs the user's attention or when the task is complete.
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
        'views/mail_activity_type_views.xml',
        'views/mail_activity_views.xml',
        'views/mail_activity_schedule_views.xml',
        'data/mail_activity_type_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mail_activity_ai_agent/static/src/ai_agent_menu.js',
            'mail_activity_ai_agent/static/src/ai_agent_menu.xml',
            'mail_activity_ai_agent/static/src/ai_agent_menu.scss',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
}
