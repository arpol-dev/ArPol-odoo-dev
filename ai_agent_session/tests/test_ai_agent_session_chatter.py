# -*- coding: utf-8 -*-
import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

SESSION_REQUESTS = 'odoo.addons.ai_agent_session.models.ai_agent_session.requests'


def _response(data):
    response = MagicMock()
    response.json.return_value = data
    return response


class AiAgentChatterCommon:
    def _setup_user_and_record(self):
        self.env.user.sudo().write({
            'claude_webhook_url': 'https://webhook.example.com',
            'claude_webhook_token': 'tok',
            'claude_webhook_cwd': '/work',
        })
        self.partner = self.env['res.partner'].create({'name': 'Chatter Target'})

    def _launch(self, **kwargs):
        wizard = self.env['ai.agent.session.wizard'].create({
            'res_model': 'res.partner',
            'res_id': self.partner.id,
            'request': 'Summarize this contact',
            **kwargs,
        })
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.post.return_value = _response({'name': 'ccm-1', 'remoteControlUrl': 'https://rc'})
            wizard.action_launch()
        session = self.env['ai.agent.session'].search([('res_id', '=', self.partner.id)])
        return session, requests_mock.post.call_args


@tagged('post_install', '-at_install')
class TestAiAgentSessionChatter(AiAgentChatterCommon, TransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_user_and_record()

    def test_wizard_defaults(self):
        wizard = self.env['ai.agent.session.wizard'].new({})
        self.assertEqual(wizard.ai_permission_mode, 'auto')
        self.assertEqual(wizard.ai_model, 'sonnet')

    def test_launch_calls_webhook_and_tracks_session(self):
        session, call = self._launch()
        payload = call.kwargs['json']
        self.assertEqual(session.status, 'running')
        self.assertEqual(session.session_name, 'ccm-1')
        self.assertEqual(payload['permissionMode'], 'auto')
        self.assertEqual(payload['cwd'], '/work')
        self.assertIn('Summarize this contact', payload['prompt'])
        self.assertIn('Chatter Target', payload['prompt'])
        self.assertIn('an Odoo record', payload['prompt'])
        self.assertIn(f'session_id={session.id}&secret={session.callback_secret}', payload['callbackUrl'])
        self.assertEqual(call.kwargs['headers'], {'X-Webhook-Token': 'tok'})

    def test_launch_without_webhook_config(self):
        self.env.user.sudo().claude_webhook_url = False
        with self.assertRaises(UserError):
            self._launch()

    def test_task_done_posts_note_and_closes(self):
        session, __ = self._launch()
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.get.return_value = _response({'text': 'full log'})
            session._handle_callback('task_done', conclusion='All good')
            requests_mock.delete.assert_called_once()
        self.assertEqual((session.status, session.conclusion), ('done', 'All good'))
        message = self.partner.message_ids[0]
        self.assertIn('All good', message.body)
        self.assertEqual(message.attachment_ids.name, 'session_log.txt')
        self.assertEqual(message.subtype_id, self.env.ref('mail.mt_note'))
        # Un second callback (dédoublonnage) ne repost rien.
        count = len(self.partner.message_ids)
        session._handle_callback('task_done', conclusion='again')
        self.assertEqual(len(self.partner.message_ids), count)

    def _wait_for_answer(self, session):
        with patch(SESSION_REQUESTS) as requests_mock:
            session._handle_callback('needs_input', conclusion='Which company?')
        return requests_mock

    def test_needs_input_posts_question_and_keeps_session_alive(self):
        session, __ = self._launch()
        requests_mock = self._wait_for_answer(session)
        self.assertEqual(session.status, 'needs_attention')
        self.assertIn('Which company?', self.partner.message_ids[0].body)
        # La session reste vivante : on doit pouvoir lui répondre.
        requests_mock.delete.assert_not_called()

    def test_reply_sends_message_and_resumes(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.post.return_value = _response({'ok': True})
            self.env['ai.agent.session.reply'].create({
                'session_id': session.id, 'answer': 'Company A',
            }).action_send()
        call = requests_mock.post.call_args
        self.assertEqual(call.args[0], 'https://webhook.example.com/api/webhook/sessions/ccm-1/message')
        self.assertEqual(call.kwargs['json'], {'text': 'Company A'})
        self.assertEqual(session.status, 'running')

    def test_reply_requires_a_waiting_session(self):
        session, __ = self._launch()
        with self.assertRaises(UserError), patch(SESSION_REQUESTS):
            session.action_reply('too early')

    def test_reply_when_session_is_gone(self):
        # 400 : session retirée du suivi (arrêtée par DELETE) ; 404 : disparue de `claude agents`.
        for status_code in (400, 404):
            session, __ = self._launch()
            self._wait_for_answer(session)
            with patch(SESSION_REQUESTS) as requests_mock:
                requests_mock.post.return_value = MagicMock(status_code=status_code)
                self.assertFalse(session.action_reply('hello?'))
            self.assertEqual(session.status, 'cancelled')
            self.assertIn('no longer exists', session.conclusion)
            session.unlink()

    def test_reply_wizard_warns_when_session_is_gone(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.post.return_value = MagicMock(status_code=400)
            action = self.env['ai.agent.session.reply'].create({
                'session_id': session.id, 'answer': 'hello?',
            }).action_send()
        self.assertEqual(action['params']['type'], 'warning')

    def test_reply_network_failure_is_a_clear_error(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        with self.assertRaises(UserError), patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.RequestException = ConnectionError
            requests_mock.post.side_effect = ConnectionError('boom')
            session.action_reply('hello?')
        self.assertEqual(session.status, 'needs_attention')

    def test_task_done_after_waiting_closes_and_stops_session(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.get.return_value = _response({'text': 'log'})
            session._handle_callback('task_done', conclusion='Finished anyway')
            requests_mock.delete.assert_called_once()
        self.assertEqual(session.status, 'done')

    def test_idle_heuristic_ignored_while_waiting(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        count = len(self.partner.message_ids)
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.get.return_value = _response({'text': 'something'})
            session._handle_callback('idle')
        self.assertEqual(len(self.partner.message_ids), count)

    def test_dismissing_a_waiting_session_stops_it(self):
        session, __ = self._launch()
        self._wait_for_answer(session)
        with patch(SESSION_REQUESTS) as requests_mock:
            session.action_dismiss()
            requests_mock.delete.assert_called_once()
        self.assertEqual((session.status, session.is_dismissed), ('cancelled', True))

    def test_systray_links_live_sessions_to_iassistant(self):
        session, __ = self._launch()
        data = self.env['ai.agent.session'].get_systray_data()['sessions'][0]
        self.assertEqual(data['session_url'], 'https://webhook.example.com/s/ccm-1')
        self._wait_for_answer(session)
        data = self.env['ai.agent.session'].get_systray_data()['sessions'][0]
        self.assertEqual(data['session_url'], 'https://webhook.example.com/s/ccm-1')
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.get.return_value = _response({'text': 'log'})
            session._handle_callback('task_done', conclusion='ok')
        data = self.env['ai.agent.session'].get_systray_data()['sessions'][0]
        self.assertFalse(data['session_url'])

    def test_prompt_tells_the_agent_the_session_stays_open(self):
        __, call = self._launch()
        prompt = call.kwargs['json']['prompt']
        self.assertIn('his answer will reach you as a new message', prompt)
        self.assertNotIn('automatically terminated', prompt)

    def test_server_action_launches_session_for_configured_user(self):
        other = self.env['res.users'].create({
            'name': 'Agent Owner', 'login': 'agent_owner',
            'claude_webhook_url': 'https://other.example.com', 'claude_webhook_token': 'other-tok',
        })
        action = self.env['ir.actions.server'].create({
            'name': 'Ask AI',
            'model_id': self.env['ir.model']._get_id('res.partner'),
            'state': 'ai_agent',
            'ai_agent_user_id': other.id,
            'ai_agent_request': 'Check this partner',
            'ai_agent_title': 'Partner check',
        })
        self.assertEqual(action.ai_agent_permission_mode, 'auto')
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.post.return_value = _response({'name': 'ccm-2'})
            action.with_context(active_model='res.partner', active_id=self.partner.id,
                                active_ids=[self.partner.id]).run()
        session = self.env['ai.agent.session'].search([('res_id', '=', self.partner.id)])
        self.assertEqual((session.user_id, session.name, session.status), (other, 'Partner check', 'running'))
        call = requests_mock.post.call_args
        self.assertTrue(call.args[0].startswith('https://other.example.com'))
        self.assertEqual(call.kwargs['headers'], {'X-Webhook-Token': 'other-tok'})
        self.assertIn('Check this partner', call.kwargs['json']['prompt'])


@tagged('post_install', '-at_install')
class TestAiAgentSessionChatterCallback(AiAgentChatterCommon, HttpCase):

    def test_callback_route_authenticates_by_session_secret(self):
        self._setup_user_and_record()
        session, __ = self._launch()
        url = f'/claude_agent/callback?session_id={session.id}'
        body = json.dumps({'status': 'task_done', 'conclusion': 'Done'})
        bad = self.url_open(f'{url}&secret=wrong', data=body, headers={'Content-Type': 'application/json'})
        self.assertEqual(bad.status_code, 403)
        with patch(SESSION_REQUESTS) as requests_mock:
            requests_mock.get.return_value = _response({'text': 'log'})
            good = self.url_open(
                f'{url}&secret={session.callback_secret}', data=body,
                headers={'Content-Type': 'application/json'},
            )
        self.assertEqual(good.status_code, 200)
        session.invalidate_recordset()
        self.assertEqual(session.status, 'done')
