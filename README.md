# Tramplin

## Стек

- Python 3.11+
- Flask
- Flask-SQLAlchemy
- Flask-Login
- SQLite
- Leaflet
- Chart.js

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Открыть в браузере:

- `http://127.0.0.1:5000/`
- `http://127.0.0.1:5000/health`

## Тестовые профили для локальной проверки

- `student@tramplin.demo / demo1234`
- `designer@tramplin.demo / demo1234`
- `hr@techvision.demo / demo1234`
- `recruiter@techvision.demo / demo1234`
- `admin@tramplin.demo / demo1234`

## Переменные окружения

```bash
export SECRET_KEY='change-me'
export DATABASE_URL='sqlite:///absolute/path/to/tramplin.db'
export BOT_NAME='tramplin_verify_bot'
export BOT_API_TOKEN='change-this-bot-token'
export REGISTRATION_NOTIFY_TO='hr-admin@tramplin.local,curator@tramplin.local'
export MAIL_FROM='noreply@tramplin.local'
export MAIL_HOST=''
export MAIL_PORT='587'
export MAIL_USERNAME=''
export MAIL_PASSWORD=''
export MAIL_USE_TLS='true'
export MAIL_OUTBOX_DIR='app/mail_outbox'
```

Если `MAIL_HOST` пустой, письма не отправляются наружу, а сохраняются в папку outbox как `.eml`. Это удобно для локальной разработки и проверки пользовательских сценариев. Полный пример есть в `.env.example`. Для тестов можно передать конфиг напрямую в `create_app({...})`.

## Что внутри

- публичный каталог с отдельными вкладками для карьерных карточек и событий
- интерактивная карта с синхронизацией списка по текущему окну
- регистрация по ролям
- регистрация работодателя в один шаг без подтверждения по email
- кабинет студента с мэтчингом, канбаном, таймлайном и GitHub-блоком
- кабинет работодателя с вакансиями, событиями и обработкой кандидатов
- кабинет куратора с модерацией, аналитикой и управлением пользователями
- премодерация вакансий, событий и привязки HR к компании

## Тесты

```bash
python -m unittest discover -s tests -v
```

## Структура

```text
app/
  main.py
  models.py
  seed.py
  services.py
  static/
  templates/
docs/
scripts/
tests/
run.py
requirements.txt
```

## Новый сценарий регистрации работодателя

1. HR заполняет форму регистрации и указывает email, компанию и при желании Telegram username.
2. Система создаёт `RegistrationFlow` с одноразовым кодом подтверждения.
3. Пользователю уходит письмо с deep-link на бота и кодом.
4. Администраторам уходят уведомления о новой заявке.
5. Бот подтверждает код через HTTP endpoint `POST /api/bot/registration/<code>/confirm` с заголовком `X-Bot-Token`.
6. После подтверждения аккаунт работодателя активируется, а пользователю уходит финальное письмо.

Есть также страницы:
- `/registration/pending/<code>` — legacy-страница для старых flow подтверждения
- `/registration/status/<code>` — legacy JSON-статус для старых flow
- `/registration/resend/<code>` — legacy endpoint повторной отправки кода

### Пример интеграции бота

```bash
curl -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Bot-Token: change-this-bot-token' \
  -d '{"telegram_username":"hr_manager"}' \
  http://127.0.0.1:5000/api/bot/registration/PASTE_CODE_HERE/confirm
```
