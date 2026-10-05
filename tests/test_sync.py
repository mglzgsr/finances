import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

import database
import main
import open_banking as ob


def provider_response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request('GET', 'https://api.truelayer.com/data/v1/accounts'))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = patch.object(database, 'DB_PATH', str(Path(self.temp.name) / 'test.db'))
        self.db.start()
        database.init_db()
        database.save_connection('test', 'fake-access', 'fake-refresh', 3600)
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        self.db.stop()
        self.temp.cleanup()

    def test_discovery_failure_does_not_mark_sync_successful(self):
        with patch.object(ob.httpx, 'get', return_value=provider_response(401, {})):
            response = self.client.post('/api/sync?bank=test')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail']['code'], 'reconnect_required')
        self.assertIsNone(database.get_connection('test')['last_sync'])

    def test_expired_refresh_requires_reconnection(self):
        database.save_connection('test', 'fake-access', 'fake-refresh', -1)
        with patch.object(ob.httpx, 'post', return_value=provider_response(400, {'error': 'invalid_grant'})):
            response = self.client.post('/api/sync?bank=test')
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(database.get_connection('test')['last_sync'])

    def test_empty_discovery_does_not_mark_sync_successful(self):
        with patch.object(ob.httpx, 'get', return_value=provider_response(200, {'results': []})):
            response = self.client.post('/api/sync?bank=test')
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(database.get_connection('test')['last_sync'])

    def test_card_transaction_failure_is_not_empty_success(self):
        with patch.object(ob.httpx, 'get', return_value=provider_response(500, {})):
            with self.assertRaises(httpx.HTTPStatusError):
                ob.fetch_card_transactions('fake-access', 'card')

    def test_only_unsupported_discovery_returns_empty(self):
        for fetch in (ob.fetch_accounts, ob.fetch_cards):
            with patch.object(ob.httpx, 'get', return_value=provider_response(501, {})):
                self.assertEqual(fetch('fake-access'), [])
            with patch.object(ob.httpx, 'get', return_value=provider_response(403, {})):
                with self.assertRaises(httpx.HTTPStatusError):
                    fetch('fake-access')

    def test_available_balance_without_current(self):
        with patch.object(ob.httpx, 'get', return_value=provider_response(200, {'results': [{'available': 12.5}]})):
            self.assertEqual(ob.fetch_balance('fake-access', 'account'), 12.5)

    def test_successful_card_only_sync_and_repeat(self):
        card = {'account_id': 'card', 'display_name': 'Card', 'currency': 'GBP'}
        tx = {'transaction_id': 'one', 'timestamp': '2026-10-04T12:00:00Z', 'amount': -10, 'description': 'Test'}
        with patch.object(ob, 'fetch_accounts', return_value=[]), patch.object(ob, 'fetch_cards', return_value=[card]), patch.object(ob, 'fetch_card_transactions', return_value=[tx]), patch.object(ob, 'fetch_card_balance', return_value=10):
            first = self.client.post('/api/sync?bank=test')
            second = self.client.post('/api/sync?bank=test')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['new'], 1)
        self.assertEqual(second.json()['new'], 0)
        self.assertEqual(second.json()['skipped'], 1)
        self.assertIsNotNone(database.get_connection('test')['last_sync'])

    def test_renamed_card_sync_uses_existing_slug(self):
        database.create_account('original-card', 'Original', source='truelayer',
                                connection_id='test', truelayer_account_id='card')
        card = {'account_id': 'card', 'display_name': 'Renamed', 'currency': 'GBP'}
        tx = {'transaction_id': 'one', 'timestamp': '2026-10-04T12:00:00Z',
              'amount': -10, 'description': 'Test'}
        with patch.object(ob, 'fetch_accounts', return_value=[]), patch.object(ob, 'fetch_cards', return_value=[card]), patch.object(ob, 'fetch_card_transactions', return_value=[tx]), patch.object(ob, 'fetch_card_balance', return_value=10):
            response = self.client.post('/api/sync?bank=test')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(database.get_all_accounts()), 1)
        self.assertEqual(database.get_transactions(bank='original-card')['total'], 1)
        self.assertEqual(database.get_account('original-card')['current_balance'], 10)

    def test_network_failure_is_actionable(self):
        with patch.object(ob, 'fetch_accounts', side_effect=httpx.ConnectError('offline')):
            response = self.client.post('/api/sync?bank=test')
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(database.get_connection('test')['last_sync'])


if __name__ == '__main__':
    unittest.main()
