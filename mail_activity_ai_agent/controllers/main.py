# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class ClaudeAgentController(http.Controller):
    """Reçoit les callbacks du webhook Claude Code (claude-console) pour les sessions
    déclenchées depuis une activité mail.activity. Authentifié par un secret aléatoire
    généré par activité (transmis en query string lors du déclenchement), pas par une
    session Odoo classique : l'appelant est un serveur externe, pas un navigateur."""

    @http.route('/claude_agent/callback', type='http', auth='public', methods=['POST'], csrf=False)
    def callback(self, **kwargs):
        activity_id = request.httprequest.args.get('activity_id', type=int)
        secret = request.httprequest.args.get('secret')

        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return self._json_response({'error': 'invalid JSON body'}, status=400)

        if not activity_id or not secret:
            return self._json_response({'error': 'missing activity_id/secret'}, status=400)

        status = payload.get('status')
        session_name = payload.get('name')
        conclusion = payload.get('conclusion')

        activity = request.env['mail.activity'].sudo().browse(activity_id)
        if activity.exists() and activity.ai_callback_secret and activity.ai_callback_secret == secret:
            try:
                activity._ai_agent_handle_callback(status, session_name, conclusion=conclusion)
            except Exception:  # noqa: BLE001 - un souci ici ne doit jamais faire planter l'appelant
                _logger.exception("AI Agent callback: error handling activity %s", activity_id)
                return self._json_response({'error': 'internal error'}, status=500)
            return self._json_response({'ok': True})

        # L'activité n'existe plus (annulée entretemps, ou disparue hors flux normal) : avant de
        # rejeter, chercher la trace de suivi correspondante — elle survit à la suppression de
        # l'activité (voir ai_agent_session.py) et porte sa propre copie du secret, justement pour
        # absorber ce cas plutôt que de laisser un callback tardif se perdre en 403.
        session = request.env['ai.agent.session'].sudo().search([
            ('source_activity_id', '=', activity_id),
            ('callback_secret', '=', secret),
        ], limit=1)
        if not session:
            _logger.warning("AI Agent callback: rejected (activity_id=%s)", activity_id)
            return self._json_response({'error': 'forbidden'}, status=403)

        try:
            session._handle_late_callback(status, conclusion)
        except Exception:  # noqa: BLE001 - un souci ici ne doit jamais faire planter l'appelant
            _logger.exception("AI Agent callback: error handling late session %s", session.id)
            return self._json_response({'error': 'internal error'}, status=500)

        return self._json_response({'ok': True})

    def _json_response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            status=status,
            headers=[('Content-Type', 'application/json')],
        )
