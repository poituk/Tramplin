import tempfile
import unittest
from pathlib import Path

from app.main import create_app
from app.models import Event, Opportunity, User


class SmokeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / 'test.db'
        outbox_dir = Path(self.temp_dir.name) / 'outbox'
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'WTF_CSRF_ENABLED': False,
            'MAIL_OUTBOX_DIR': str(outbox_dir),
            'BOT_API_TOKEN': 'test-bot-token',
            'REGISTRATION_NOTIFY_TO': 'admin@test.local, curator@test.local',
            'GITHUB_FETCH_ENABLED': False,
        })
        self.client = self.app.test_client()
        self.outbox_dir = outbox_dir

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_public_pages_render(self):
        for path in ['/', '/login', '/register', '/health']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_seeded_data_exists(self):
        with self.app.app_context():
            self.assertGreaterEqual(User.query.count(), 7)
            self.assertGreaterEqual(Opportunity.query.count(), 4)
            self.assertGreaterEqual(Event.query.count(), 2)

    def test_login_and_dashboard(self):
        response = self.client.post('/login', data={
            'email': 'student@tramplin.demo',
            'password': 'demo1234',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Алина'.encode('utf-8'), response.data)

    def test_catalog_search_filters_results(self):
        response = self.client.get('/?q=analytics&tab=events')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Analytics'.encode('utf-8'), response.data)

    def test_employer_registration_is_completed_immediately(self):
        response = self.client.post('/register', data={
            'role': 'employer',
            'display_name': 'Новый HR',
            'email': 'new.hr@example.com',
            'password': 'secret123',
            'city': 'Москва',
            'company_mode': 'create',
            'company_name': 'ООО Новая Компания',
            'inn': '7707083893',
            'website': 'https://new.example.com',
            'industry': 'IT',
            'office_address': 'Москва, Лесная, 7',
            'hr_title': 'Lead Recruiter',
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Регистрация завершена'.encode('utf-8'), response.data)

        with self.app.app_context():
            user = User.query.filter_by(email='new.hr@example.com').first()
            self.assertIsNotNone(user)
            self.assertTrue(user.is_active_account)
            self.assertIsNone(user.registration_flow)

        login_response = self.client.post('/login', data={
            'email': 'new.hr@example.com',
            'password': 'secret123',
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('Новый HR'.encode('utf-8'), login_response.data)

    def test_employer_dashboard_shows_hiring_and_event_boards(self):
        login_response = self.client.post('/login', data={
            'email': 'hr@techvision.demo',
            'password': 'demo1234',
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn('Найм по карточке'.encode('utf-8'), login_response.data)
        self.assertIn('Сохранить изменения'.encode('utf-8'), login_response.data)

        event_response = self.client.get('/dashboard?entity=event')
        self.assertEqual(event_response.status_code, 200)
        self.assertIn('Участники мероприятия'.encode('utf-8'), event_response.data)


if __name__ == '__main__':
    unittest.main()
