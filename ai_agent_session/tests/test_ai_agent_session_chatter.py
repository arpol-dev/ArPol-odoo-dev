# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import requests

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

LAUNCHER_REQUEST = 'odoo.addons.ai_agent_session.models.ai_agent_launcher.requests.request'


def _response(data):
    response = MagicMock()
    response.json.return_value = data
    return response


@tagged('post_install', '-at_install')
class TestAiAgentSession(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.sudo().write({
            'claude_webhook_url': 'https://webhook.example.com',
            'claude_webhook_token': 'tok',
            'claude_webhook_cwd': '/work',
        })
        self.partner = self.env['res.partner'].create({'name': 'Chatter Target'})

    def _launch(self, webhook_reply=None, **kwargs):
        wizard = self.env['ai.agent.session.wizard'].create({
            'res_model': 'res.partner',
            'res_id': self.partner.id,
            'request': 'Summarize this contact',
            **kwargs,
        })
        with patch(LAUNCHER_REQUEST) as request_mock:
            request_mock.return_value = _response(webhook_reply or {'name': 'ses_abc123', 'label': 'x'})
            wizard.action_launch()
        return request_mock.call_args

    def _notes(self):
        return self.partner.message_ids.filtered(lambda m: 'AI Agent session launched' in (m.body or ''))

    def test_wizard_defaults_to_allow(self):
        wizard = self.env['ai.agent.session.wizard'].new({})
        self.assertEqual(wizard.ai_permission, 'allow')
        self.assertFalse(wizard.ai_model_id)

    def test_launch_posts_session_to_webhook(self):
        call = self._launch(summary='Contact review')
        args, kwargs = call.args, call.kwargs
        self.assertEqual(args[0], 'POST')
        self.assertEqual(args[1], 'https://webhook.example.com/api/webhook/sessions')
        self.assertEqual(kwargs['headers'], {'X-Webhook-Token': 'tok'})
        payload = kwargs['json']
        self.assertEqual(payload['cwd'], '/work')
        self.assertEqual(payload['label'], 'Contact review')
        self.assertEqual(payload['permission'], 'allow')
        self.assertIsNone(payload['model'])
        self.assertTrue(payload['idempotencyKey'].startswith('odoo-ai-agent-'))
        self.assertIn('Summarize this contact', payload['prompt'])
        self.assertIn('Chatter Target', payload['prompt'])
        self.assertNotIn('AGENT_SESSION_DONE', payload['prompt'])

    def test_launch_posts_internal_note_with_session_reference(self):
        self._launch(webhook_reply={'name': 'ses_abc123', 'label': 'x', 'openUrl': 'https://iarpol.arpol.fr/open/ses_abc123'})
        notes = self._notes()
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes.subtype_id.internal)
        self.assertIn('ses_abc123', notes.body)
        self.assertIn('server default', notes.body)
        self.assertIn('Allow', notes.body)
        self.assertIn('Summarize this contact', notes.body)
        self.assertIn('https://iarpol.arpol.fr/open/ses_abc123', notes.body)

    def test_launch_sends_selected_model_and_permission(self):
        model = self.env['ai.agent.model'].create({'code': 'anthropic/claude-sonnet-5', 'name': 'Sonnet 5'})
        call = self._launch(ai_model_id=model.id, ai_permission='ask')
        payload = call.kwargs['json']
        self.assertEqual(payload['model'], 'anthropic/claude-sonnet-5')
        self.assertEqual(payload['permission'], 'ask')
        self.assertIn('anthropic/claude-sonnet-5', self._notes().body)

    def test_missing_webhook_configuration_raises_and_posts_nothing(self):
        self.env.user.sudo().write({'claude_webhook_url': False})
        with self.assertRaises(UserError):
            self._launch()
        self.assertFalse(self._notes())

    def test_missing_working_directory_raises(self):
        self.env.user.sudo().write({'claude_webhook_cwd': False})
        with self.assertRaises(UserError):
            self._launch()

    def test_unreachable_webhook_raises_and_posts_nothing(self):
        wizard = self.env['ai.agent.session.wizard'].create({
            'res_model': 'res.partner', 'res_id': self.partner.id, 'request': 'Ping',
        })
        with patch(LAUNCHER_REQUEST, side_effect=requests.ConnectionError('down')):
            with self.assertRaises(UserError):
                wizard.action_launch()
        self.assertFalse(self._notes())

    def test_webhook_refusal_raises_and_posts_nothing(self):
        wizard = self.env['ai.agent.session.wizard'].create({
            'res_model': 'res.partner', 'res_id': self.partner.id, 'request': 'Ping',
        })
        reply = _response({})
        reply.raise_for_status.side_effect = requests.HTTPError('403')
        with patch(LAUNCHER_REQUEST, return_value=reply):
            with self.assertRaises(UserError):
                wizard.action_launch()
        self.assertFalse(self._notes())

    def test_server_action_launches_for_its_record(self):
        action = self.env['ir.actions.server'].create({
            'name': 'AI test',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'ai_agent',
            'ai_agent_user_id': self.env.user.id,
            'ai_agent_request': 'Check this partner',
            'ai_agent_permission': 'deny',
        })
        with patch(LAUNCHER_REQUEST) as request_mock:
            request_mock.return_value = _response({'name': 'ses_action1'})
            action._run_action_ai_agent({'record': self.partner})
        self.assertEqual(request_mock.call_args.kwargs['json']['permission'], 'deny')
        self.assertIn('ses_action1', self._notes().body)


@tagged('post_install', '-at_install')
class TestAiAgentModelSync(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.sudo().write({
            'claude_webhook_url': 'https://webhook.example.com',
            'claude_webhook_token': 'tok',
        })

    def _sync(self, models):
        with patch(LAUNCHER_REQUEST) as request_mock:
            request_mock.return_value = _response({'models': models})
            return self.env.user.action_sync_ai_agent_models(), request_mock

    def test_sync_creates_then_deactivates_missing_models(self):
        first = [
            {'id': 'anthropic/claude-sonnet-5', 'name': 'Sonnet 5', 'provider': 'anthropic', 'variants': ['high'], 'status': 'active'},
            {'id': 'opencode/flint', 'name': 'Flint', 'provider': 'opencode', 'variants': [], 'status': 'beta'},
        ]
        result, request_mock = self._sync(first)
        self.assertEqual(request_mock.call_args.args[0], 'GET')
        self.assertEqual(request_mock.call_args.args[1], 'https://webhook.example.com/api/webhook/models')
        self.assertIn('2 AI Agent models synchronized', result['params']['message'])
        Model = self.env['ai.agent.model']
        self.assertEqual(Model.search_count([('active', '=', True)]), 2)
        self.assertEqual(Model.search([('code', '=', 'anthropic/claude-sonnet-5')]).variants, 'high')

        self._sync([{'id': 'anthropic/claude-sonnet-5', 'name': 'Sonnet 5 bis', 'provider': 'anthropic', 'variants': [], 'status': 'active'}])
        self.assertEqual(Model.search_count([('code', '=', 'anthropic/claude-sonnet-5')]), 1)
        self.assertEqual(Model.search([('code', '=', 'anthropic/claude-sonnet-5')]).name, 'Sonnet 5 bis')
        self.assertFalse(Model.search([('code', '=', 'opencode/flint')]).active)

    def test_sync_ignores_duplicates(self):
        dupes = [{'id': 'anthropic/x', 'name': 'X'}, {'id': 'anthropic/x', 'name': 'X'}]
        self._sync(dupes)
        self.assertEqual(self.env['ai.agent.model'].search_count([('code', '=', 'anthropic/x')]), 1)

@tagged('post_install', '-at_install')
class TestAiAgentDefaultModel(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.sudo().write({
            'claude_webhook_url': 'https://webhook.example.com',
            'claude_webhook_token': 'tok',
            'claude_webhook_cwd': '/work',
        })
        self.partner = self.env['res.partner'].create({'name': 'Default Target'})
        self.model = self.env['ai.agent.model'].create({'code': 'anthropic/haiku-test', 'name': 'Haiku test'})

    def test_wizard_preselects_user_default_model(self):
        self.env.user.sudo().ai_agent_default_model_id = self.model
        wizard = self.env['ai.agent.session.wizard'].new({})
        self.assertEqual(wizard.ai_model_id, self.model)

    def test_wizard_without_default_model_is_empty(self):
        wizard = self.env['ai.agent.session.wizard'].new({})
        self.assertFalse(wizard.ai_model_id)

    def test_server_action_falls_back_to_user_default_model(self):
        self.env.user.sudo().ai_agent_default_model_id = self.model
        action = self.env['ir.actions.server'].create({
            'name': 'AI default',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'ai_agent',
            'ai_agent_user_id': self.env.user.id,
            'ai_agent_request': 'Check default',
        })
        with patch(LAUNCHER_REQUEST) as request_mock:
            request_mock.return_value = _response({'name': 'ses_default'})
            action._run_action_ai_agent({'record': self.partner})
        self.assertEqual(request_mock.call_args.kwargs['json']['model'], 'anthropic/haiku-test')

    def test_models_list_action_and_sync_button(self):
        action = self.env.ref('ai_agent_session.ai_agent_model_action')
        self.assertEqual(action.res_model, 'ai.agent.model')
        with patch(LAUNCHER_REQUEST) as request_mock:
            request_mock.return_value = _response({'models': [{'id': 'opencode/x', 'name': 'X'}]})
            self.env['ai.agent.model'].action_sync_from_server()
        self.assertTrue(self.env['ai.agent.model'].search([('code', '=', 'opencode/x')]))
