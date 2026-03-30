from __future__ import annotations

import json
from datetime import date, timedelta, datetime

from werkzeug.security import generate_password_hash

from .models import (
    Application,
    CompanyVerification,
    CuratorProfile,
    EmployerProfile,
    Event,
    EventRegistration,
    ModerationQueue,
    Opportunity,
    StudentProfile,
    Tag,
    User,
    db,
)
from .services import compute_match


SEED_TAGS = [
    ('Python', 'skill'), ('SQL', 'skill'), ('Docker', 'skill'), ('JavaScript', 'skill'),
    ('React', 'skill'), ('FastAPI', 'skill'), ('Go', 'skill'), ('Data Science', 'skill'),
    ('Machine Learning', 'skill'), ('PostgreSQL', 'skill'), ('Linux', 'skill'), ('Figma', 'skill'),
    ('Junior', 'level'), ('Intern', 'level'), ('Full-time', 'employment'), ('Part-time', 'employment'),
    ('Backend', 'skill'), ('Career', 'skill'), ('Networking', 'skill'), ('Product Design', 'skill'),
]


def seed_database() -> None:
    if User.query.first():
        return

    tags = {}
    for name, category in SEED_TAGS:
        tag = Tag(name=name, category=category)
        db.session.add(tag)
        tags[name] = tag

    student_user = User(
        email='student@tramplin.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='Алина Смирнова',
        role='student',
    )
    student_friend_user = User(
        email='designer@tramplin.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='Илья Рябов',
        role='student',
    )
    employer_user = User(
        email='hr@techvision.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='TechVision HR',
        role='employer',
    )
    recruiter_user = User(
        email='recruiter@techvision.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='TechVision Recruiter',
        role='employer',
    )
    analytics_user = User(
        email='analyst@tramplin.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='Мария Волкова',
        role='student',
    )
    mentor_user = User(
        email='mentor@tramplin.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='Никита Орлов',
        role='student',
    )
    curator_user = User(
        email='admin@tramplin.demo',
        password_hash=generate_password_hash('demo1234', method='pbkdf2:sha256', salt_length=16),
        display_name='Администратор платформы',
        role='curator',
    )
    db.session.add_all([student_user, student_friend_user, employer_user, recruiter_user, analytics_user, mentor_user, curator_user])
    db.session.flush()

    student = StudentProfile(
        user_id=student_user.id,
        full_name='Смирнова Алина Андреевна',
        university='МГТУ им. Баумана',
        graduation_year=2027,
        course='3 курс',
        city='Москва',
        summary='Backend-разработчик уровня Junior/Intern. Люблю системный дизайн, карты и продукты для EdTech.',
        github_url='https://github.com/alina-smirnova',
        portfolio_url='https://portfolio.tramplin.local/alina',
        privacy_mode='networking',
        active_search=True,
        radar_hard=82,
        radar_data=68,
        radar_soft=77,
        radar_leadership=61,
        gamification_points=1260,
        timeline_json=json.dumps([
            {'year': '2022', 'text': 'Поступление на ИУ7, первый pet-project на Python'},
            {'year': '2023', 'text': 'Победа в вузовском хакатоне по аналитике данных'},
            {'year': '2024', 'text': 'Курсовой проект: рекомендательная система вакансий'},
            {'year': '2025', 'text': 'Стажировка в лаборатории ML и публичные выступления'},
        ], ensure_ascii=False),
    )
    student.skills = [tags['Python'], tags['SQL'], tags['FastAPI'], tags['Linux'], tags['Junior']]

    student_friend = StudentProfile(
        user_id=student_friend_user.id,
        full_name='Рябов Илья Денисович',
        university='НИУ ВШЭ',
        graduation_year=2026,
        course='4 курс',
        city='Москва',
        summary='Product designer c сильным уклоном в UX-исследования и карьерные сообщества.',
        github_url='https://github.com/ilya-ryabov',
        portfolio_url='https://portfolio.tramplin.local/ilya',
        privacy_mode='networking',
        active_search=False,
        radar_hard=58,
        radar_data=49,
        radar_soft=86,
        radar_leadership=74,
        gamification_points=870,
        timeline_json=json.dumps([
            {'year': '2023', 'text': 'Запуск студенческого дизайн-клуба'},
            {'year': '2024', 'text': 'Стажировка по продуктовой аналитике и UX'},
        ], ensure_ascii=False),
    )
    student_friend.skills = [tags['Figma'], tags['Product Design'], tags['Career'], tags['Networking']]
    analytics_student = StudentProfile(
        user_id=analytics_user.id,
        full_name='Волкова Мария Сергеевна',
        university='ИТМО',
        graduation_year=2026,
        course='4 курс',
        city='Санкт-Петербург',
        summary='SQL и аналитика продукта, веду карьерные проекты и люблю live-мероприятия.',
        github_url='https://github.com/maria-volkova',
        portfolio_url='https://portfolio.tramplin.local/maria',
        privacy_mode='active',
        active_search=True,
        radar_hard=74,
        radar_data=88,
        radar_soft=72,
        radar_leadership=58,
        gamification_points=940,
        timeline_json=json.dumps([
            {'year': '2024', 'text': 'Портфолио SQL-кейсов и учебные аналитические дашборды'},
            {'year': '2025', 'text': 'Практика в fintech-команде и карьерные консультации'}
        ], ensure_ascii=False),
    )
    analytics_student.skills = [tags['SQL'], tags['Data Science'], tags['PostgreSQL'], tags['Career']]

    mentor_student = StudentProfile(
        user_id=mentor_user.id,
        full_name='Орлов Никита Павлович',
        university='УрФУ',
        graduation_year=2027,
        course='3 курс',
        city='Екатеринбург',
        summary='Python backend, Linux и pet-projects. Ищу менторство и стажировку.',
        github_url='https://github.com/nikita-orlov',
        portfolio_url='https://portfolio.tramplin.local/nikita',
        privacy_mode='active',
        active_search=True,
        radar_hard=79,
        radar_data=64,
        radar_soft=69,
        radar_leadership=55,
        gamification_points=1015,
        timeline_json=json.dumps([
            {'year': '2023', 'text': 'Собрал pet-project для автоматизации клуба разработчиков'},
            {'year': '2025', 'text': 'Призёр регионального хакатона по backend-разработке'}
        ], ensure_ascii=False),
    )
    mentor_student.skills = [tags['Python'], tags['Linux'], tags['Docker'], tags['Backend']]

    student.contacts.append(student_friend)
    student_friend.contacts.append(student)

    employer = EmployerProfile(
        user_id=employer_user.id,
        company_name='TechVision',
        legal_name='ООО «ТехВижн»',
        description='Продуктовая IT-компания, создающая цифровые сервисы для городской инфраструктуры, образования и HR Tech.',
        website='https://techvision.local',
        socials='https://t.me/techvision_careers',
        city='Москва',
        industry='HR Tech / Smart City',
        office_address='Москва, Пресненская наб., 10',
        cover_url='https://images.unsplash.com/photo-1497366754035-f200968a6e72?q=80&w=1200&auto=format&fit=crop',
        office_photo_url='https://images.unsplash.com/photo-1497366412874-3415097a27e7?q=80&w=1200&auto=format&fit=crop',
        verified_badge=True,
        company_inn='7707083893',
        hr_title='Lead HR Business Partner',
        hr_status='owner',
    )

    recruiter = EmployerProfile(
        user_id=recruiter_user.id,
        company_name='TechVision',
        legal_name='ООО «ТехВижн»',
        description='Командный HR-профиль компании для event и internship-направления.',
        website='https://techvision.local',
        socials='https://t.me/techvision_careers',
        city='Москва',
        industry='HR Tech / Smart City',
        office_address='Москва, Пресненская наб., 10',
        verified_badge=True,
        company_inn='7707083893',
        hr_title='Campus Recruiter',
        hr_status='approved',
    )

    verification = CompanyVerification(
        employer=employer,
        corporate_email='hr@techvision.demo',
        inn='7707083893',
        verification_level=2,
        legal_status='Подтверждено куратором',
        verified_at=datetime.now(),
    )
    recruiter_verification = CompanyVerification(
        employer=recruiter,
        corporate_email='recruiter@techvision.demo',
        inn='7707083893',
        verification_level=2,
        legal_status='Привязан к действующей компании',
        verified_at=datetime.now(),
    )

    curator = CuratorProfile(
        user_id=curator_user.id,
        title='Главный модератор',
        organization='Консорциум карьерных центров',
        is_super_admin=True,
    )

    db.session.add_all([student, student_friend, analytics_student, mentor_student, employer, recruiter, verification, recruiter_verification, curator])
    db.session.flush()

    opportunities = [
        Opportunity(
            employer_id=employer.id,
            title='Junior Python Backend Engineer',
            short_description='Разработка микросервисов карьерной платформы, интеграции с геоданными и ATS-модулем.',
            opportunity_type='vacancy',
            work_format='hybrid',
            city='Москва',
            address='Москва-Сити, Башня Федерация',
            latitude=55.7495,
            longitude=37.5379,
            salary_min=120000,
            salary_max=170000,
            employment_type='full-time',
            level='Junior',
            published_on=date.today() - timedelta(days=2),
            expires_on=date.today() + timedelta(days=30),
            moderation_status='approved',
        ),
        Opportunity(
            employer_id=employer.id,
            title='Стажировка Frontend React',
            short_description='Работа над публичной картой и личными кабинетами, фокус на UX и производительность.',
            opportunity_type='internship',
            work_format='office',
            city='Москва',
            address='Москва, ул. Льва Толстого, 16',
            latitude=55.7337,
            longitude=37.5884,
            salary_min=70000,
            salary_max=90000,
            employment_type='part-time',
            level='Intern',
            published_on=date.today() - timedelta(days=5),
            expires_on=date.today() + timedelta(days=20),
            moderation_status='approved',
        ),
        Opportunity(
            employer_id=employer.id,
            title='Blind Connection с Senior Backend Mentor',
            short_description='Анонимный запрос на 30-минутную менторскую встречу по backend-карьере.',
            opportunity_type='mentorship',
            work_format='remote',
            city='Москва',
            address='Удаленно',
            latitude=55.7512,
            longitude=37.6184,
            salary_min=0,
            salary_max=0,
            employment_type='mentorship',
            level='Intern',
            published_on=date.today() - timedelta(days=4),
            expires_on=date.today() + timedelta(days=40),
            moderation_status='approved',
        ),
        Opportunity(
            employer_id=recruiter.id,
            title='Data Analyst Internship',
            short_description='Аналитика рынка навыков, дашборды для кураторов, SQL и визуализация.',
            opportunity_type='internship',
            work_format='remote',
            city='Санкт-Петербург',
            address='Санкт-Петербург',
            latitude=59.9386,
            longitude=30.3141,
            salary_min=65000,
            salary_max=85000,
            employment_type='part-time',
            level='Intern',
            published_on=date.today() - timedelta(days=3),
            expires_on=date.today() + timedelta(days=25),
            moderation_status='approved',
        ),
    ]

    opportunities[0].tags = [tags['Python'], tags['SQL'], tags['Docker'], tags['FastAPI'], tags['Junior'], tags['Backend']]
    opportunities[1].tags = [tags['JavaScript'], tags['React'], tags['Figma'], tags['Intern']]
    opportunities[2].tags = [tags['Python'], tags['Linux'], tags['Intern'], tags['Backend']]
    opportunities[3].tags = [tags['SQL'], tags['Data Science'], tags['PostgreSQL'], tags['Intern']]
    db.session.add_all(opportunities)
    db.session.flush()

    events = [
        Event(
            employer_id=employer.id,
            title='Карьерный митап: Как пройти в Junior Backend',
            short_description='Открытая лекция, разбор резюме и сессия вопросов от команды найма TechVision.',
            event_format='offline',
            city='Москва',
            address='Москва, Ленинградский пр-т, 39',
            venue_name='Кампус TechVision Arena',
            latitude=55.7908,
            longitude=37.5449,
            starts_at=datetime.combine(date.today() + timedelta(days=7), datetime.min.time()).replace(hour=18, minute=30),
            ends_at=datetime.combine(date.today() + timedelta(days=7), datetime.min.time()).replace(hour=21, minute=0),
            registration_deadline=date.today() + timedelta(days=6),
            capacity=180,
            target_audience='Студенты backend-направления и junior-разработчики',
            speaker_name='Команда найма TechVision',
            registration_url='https://techvision.local/events/backend-meetup',
            contact_email='events@techvision.local',
            participation_cost='Бесплатно',
            moderation_status='approved',
        ),
        Event(
            employer_id=recruiter.id,
            title='Онлайн-день карьеры в Data & Analytics',
            short_description='Панель с аналитиками, воркшоп по SQL-портфолио и быстрые карьерные консультации.',
            event_format='online',
            city='Москва',
            address='Zoom / TechVision Live',
            venue_name='TechVision Live',
            latitude=55.7512,
            longitude=37.6184,
            starts_at=datetime.combine(date.today() + timedelta(days=11), datetime.min.time()).replace(hour=19, minute=0),
            ends_at=datetime.combine(date.today() + timedelta(days=11), datetime.min.time()).replace(hour=20, minute=30),
            registration_deadline=date.today() + timedelta(days=10),
            capacity=350,
            target_audience='Студенты аналитики, BI и DS',
            speaker_name='Data Harbor x TechVision',
            registration_url='https://techvision.local/events/data-day',
            contact_email='events@techvision.local',
            participation_cost='Бесплатно',
            moderation_status='approved',
        ),
    ]
    events[0].tags = [tags['Python'], tags['SQL'], tags['Career'], tags['Networking'], tags['Backend']]
    events[1].tags = [tags['SQL'], tags['Data Science'], tags['Career'], tags['Networking']]
    db.session.add_all(events)
    db.session.flush()

    applications = [
        Application(student_id=student.id, opportunity_id=opportunities[0].id, status='applied', note='Отправила резюме и GitHub'),
        Application(student_id=student.id, opportunity_id=opportunities[1].id, status='wishlist', note='Интересен frontend как второе направление'),
        Application(student_id=student.id, opportunity_id=opportunities[2].id, status='invited', note='Ментор согласился на анонимную встречу'),
        Application(student_id=analytics_student.id, opportunity_id=opportunities[3].id, status='applied', note='Готова к тестовому заданию по SQL'),
        Application(student_id=mentor_student.id, opportunity_id=opportunities[2].id, status='applied', note='Хочу созвон по backend-карьере и roadmap'),
        Application(student_id=mentor_student.id, opportunity_id=opportunities[0].id, status='reserve', note='Могу быстро пройти техническое интервью'),
    ]

    for application in applications:
        matched = compute_match(student, db.session.get(Opportunity, application.opportunity_id))
        application.match_score = matched['score']
        application.hr_private_note = 'Сильное портфолио, стоит пригласить' if application.match_score >= 80 else 'Нужно проверить пробелы по стеку'
        db.session.add(application)

    db.session.add_all([
        EventRegistration(
            student_id=student.id,
            event_id=events[0].id,
            status='registered',
            note='Хочу получить фидбек по резюме.',
        ),
        EventRegistration(
            student_id=analytics_student.id,
            event_id=events[1].id,
            status='registered',
            note='Интересен SQL-воркшоп и карьерная панель.',
        ),
        EventRegistration(
            student_id=mentor_student.id,
            event_id=events[0].id,
            status='waitlist',
            note='Если освободится место, подключусь офлайн.',
        ),
    ])

    moderation_items = [
        ModerationQueue(entity_type='company', entity_id=employer.id, title='Верификация TechVision', submitted_by='TechVision HR', status='approved'),
        ModerationQueue(entity_type='company', entity_id=recruiter.id, title='Привязка Campus Recruiter к TechVision', submitted_by='TechVision Recruiter', status='approved'),
        ModerationQueue(entity_type='opportunity', entity_id=opportunities[3].id, title='Data Analyst Internship', submitted_by='TechVision Recruiter', status='approved'),
        ModerationQueue(entity_type='event', entity_id=events[1].id, title='Онлайн-день карьеры в Data & Analytics', submitted_by='TechVision Recruiter', status='approved'),
    ]
    db.session.add_all(moderation_items)

    db.session.commit()
