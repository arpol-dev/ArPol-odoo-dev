# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ClaudeAgentController(http.Controller):
    """Reçoit les callbacks du webhook Claude Code (claude-console) pour les sessions lancées
    depuis le chatter ou une action serveur. Authentifié par un secret aléatoire généré par
    session (transmis en query string lors du lancement), pas par une session Odoo classique :
    l'appelant est un serveur externe, pas un navigateur."""

    @http.route('/claude_agent/callback', type='http', auth='public', methods=['POST'], csrf=False)
    def callback(self, **kwargs):
        session_id = request.httprequest.args.get('session_id', type=int)
        secret = request.httprequest.args.get('secret')

        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return self._json_response({'error': 'invalid JSON body'}, status=400)

        if not session_id or not secret:
            return self._json_response({'error': 'missing session_id/secret'}, status=400)

        session = request.env['ai.agent.session'].sudo().browse(session_id)
        if not (session.exists() and session.callback_secret and session.callback_secret == secret):
            _logger.warning("AI Agent callback: rejected (session_id=%s)", session_id)
            return self._json_response({'error': 'forbidden'}, status=403)
        try:
            session._handle_callback(payload.get('status'), conclusion=payload.get('conclusion'))
        except Exception:  # noqa: BLE001 - un souci ici ne doit jamais faire planter l'appelant
            _logger.exception("AI Agent callback: error handling session %s", session_id)
            return self._json_response({'error': 'internal error'}, status=500)
        return self._json_response({'ok': True})

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            status=status,
            headers=[('Content-Type', 'application/json')],
        )
