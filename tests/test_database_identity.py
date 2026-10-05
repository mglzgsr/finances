import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import database


class DatabaseIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name) / 'finance.db')
        self.db = patch.object(database, 'DB_PATH', self.db_path)
        self.db.start()
        database.init_db()

    def tearDown(self):
        self.db.stop()
        self.temp.cleanup()

    def test_reconnection_keeps_account_identity_balance_and_history(self):
        first = database.create_account('old-name', 'Original', connection_id='HSBC',
                                        truelayer_account_id='stable-id', source='truelayer')
        database.update_account_balance('old-name', 123)
        database.save_transactions([dict(date='2026-10-01', description='Example',
            tx_type='DEBIT', is_debit=True, amount=10, balance=None,
            category='Otros', bank='old-name', hash='unique')])
        second = database.create_account('new-name', 'New name', connection_id='HSBC',
                                         truelayer_account_id='stable-id', source='truelayer')
        self.assertEqual(first, second)
        self.assertEqual(len(database.get_all_accounts()), 1)
        account = database.get_account_by_truelayer_id('stable-id')
        self.assertEqual(account['slug'], 'old-name')
        self.assertEqual(account['display_name'], 'New name')
        self.assertEqual(account['current_balance'], 123)
        self.assertIsNone(database.get_account('new-name'))
        self.assertEqual(database.get_transactions(bank='old-name')['total'], 1)

    def test_manual_accounts_and_slug_updates_still_work(self):
        first = database.create_account('manual-one', 'One')
        database.create_account('manual-two', 'Two')
        self.assertEqual(database.create_account('manual-one', 'Updated'), first)
        self.assertEqual(len(database.get_all_accounts()), 2)

    def test_unique_index_enforces_external_identity(self):
        database.create_account('one', 'One', truelayer_account_id='same')
        with database.get_conn() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO accounts (slug, display_name, truelayer_account_id) VALUES ('two', 'Two', 'same')")

    def test_refresh_expiry_saved_and_updated(self):
        before = datetime.utcnow()
        database.save_connection('HSBC', 'access', 'refresh', 3600)
        expiry = datetime.fromisoformat(database.get_connection('HSBC')['refresh_expires_at'])
        self.assertGreaterEqual(expiry, before + timedelta(days=90))
        self.assertLessEqual(expiry, datetime.utcnow() + timedelta(days=90))
        with database.get_conn() as conn:
            conn.execute("UPDATE bank_connections SET refresh_expires_at='2000-01-01' WHERE bank='HSBC'")
        database.save_connection('HSBC', 'new-access', 'new-refresh', 3600)
        connection = database.get_connection('HSBC')
        self.assertEqual(connection['refresh_token'], 'new-refresh')
        self.assertEqual(database.get_all_connections()[0]['refresh_expires_at'], connection['refresh_expires_at'])
        self.assertNotEqual(connection['refresh_expires_at'], '2000-01-01')

    def test_duplicate_accounts_migrate_without_deleting_transactions(self):
        original = database.create_account('original', 'Original', truelayer_account_id='stable')
        with database.get_conn() as conn:
            conn.execute('DROP INDEX idx_accounts_truelayer_account_id')
            duplicate = conn.execute("INSERT INTO accounts (slug, display_name, truelayer_account_id, current_balance, last_sync) VALUES ('renamed', 'Renamed', 'stable', 42, '2026-10-05')").lastrowid
            conn.execute("INSERT INTO transactions (date, description, is_debit, amount, category, bank, hash, account_id) VALUES ('2026-10-05', 'Example', 1, 10, 'Otros', 'renamed', 'unique', ?)", (duplicate,))
        database.init_db()
        database.init_db()
        self.assertEqual(len(database.get_all_accounts()), 1)
        self.assertEqual(database.get_account('original')['current_balance'], 42)
        self.assertFalse(database.get_account('renamed')['is_active'])
        with database.get_conn() as conn:
            self.assertEqual(conn.execute('SELECT bank, account_id FROM transactions').fetchall(), [('original', original)])
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM accounts').fetchone()[0], 2)

    def test_existing_schema_migrates_idempotently(self):
        with database.get_conn() as conn:
            conn.execute('DROP INDEX idx_accounts_truelayer_account_id')
            conn.execute('ALTER TABLE bank_connections DROP COLUMN refresh_expires_at')
            conn.execute("INSERT INTO bank_connections (bank, access_token, refresh_token, expires_at, connected_at) VALUES ('HSBC', 'a', 'r', '2026-10-01', '2026-10-01')")
        database.init_db()
        database.init_db()
        self.assertIsNone(database.get_connection('HSBC')['refresh_expires_at'])
        self.test_unique_index_enforces_external_identity()


if __name__ == '__main__':
    unittest.main()
