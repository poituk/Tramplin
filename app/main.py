from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .models import (
    Application,
    CompanyVerification,
    CuratorProfile,
    EmployerProfile,
    Event,
    EventRegistration,
    ModerationQueue,
    Opportunity,
    RegistrationFlow,
    StudentProfile,
    Tag,
    User,
    db,
)
from .seed import seed_database
from .registration_flow import (
    make_verification_code,
    normalize_recipients,
    notify_registration_confirmed,
    notify_registration_started,
)
from .services import (
    EVENT_STATUS_TITLES,
    FORMAT_LABELS,
    HR_STATUS_TITLES,
    STATUS_TITLES,
    TYPE_LABELS,
    analytics_payload,
    approved_company_members,
    available_event_seats,
    build_map_payload,
    build_public_catalog,
    can_auto_link_company,
    company_member_ids,
    company_team_members,
    compute_match,
    employer_activity_summary,
    employer_candidate_overview,
    employer_event_overview,
    extract_github_username,
    github_profile_payload,
    kanban_columns,
    recruitment_board_for_event,
    recruitment_board_for_opportunity,
    skill_gap_market_insights,
    timeline_items,
    verify_company,
)

BASE_DIR = Path(__file__).resolve().parent
ALLOWED_ROLES = {'student', 'employer', 'curator'}
APPLICATION_STATUSES = set(STATUS_TITLES) | {'reserve'}


def parse_datetime_local(value: str, fallback: datetime | None = None) -> datetime:
    if not value:
        return fallback or datetime.now()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return fallback or datetime.now()


def parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def parse_float(value: str | None, default: float) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def parse_tags_from_text(raw_value: str) -> list[Tag]:
    raw_tags = [part.strip() for part in raw_value.split(',') if part.strip()]
    tags = []
    for tag_name in raw_tags:
        tag = Tag.query.filter(Tag.name.ilike(tag_name)).first()
        if not tag:
            tag = Tag(name=tag_name, category='skill')
            db.session.add(tag)
            db.session.flush()
        tags.append(tag)
    return tags


def parse_timeline_text(raw_value: str) -> str:
    items = []
    for line in raw_value.splitlines():
        prepared = line.strip().lstrip('-').strip()
        if not prepared:
            continue
        if ':' in prepared:
            year, text = prepared.split(':', 1)
            items.append({'year': year.strip(), 'text': text.strip()})
        else:
            items.append({'year': str(date.today().year), 'text': prepared})
    return json_dumps(items)


def timeline_text(student: StudentProfile) -> str:
    return '\n'.join(f"{item.get('year', '')}: {item.get('text', '')}" for item in timeline_items(student))


def json_dumps(data) -> str:
    import json
    return json.dumps(data, ensure_ascii=False)


def find_item_by_id(items: list, item_id: int | None):
    if item_id is None:
        return items[0] if items else None
    for item in items:
        if item.id == item_id:
            return item
    return items[0] if items else None


def approved_opportunities():
    return Opportunity.query.filter_by(is_published=True, moderation_status='approved').filter(Opportunity.opportunity_type != 'event')


def approved_events():
    return Event.query.filter_by(is_published=True, moderation_status='approved')


def public_opportunity_catalog(selected_type: str = '', selected_format: str = '', selected_tag: str = '', min_salary: int = 0, search_query: str = ''):
    opportunity_query = approved_opportunities()

    if selected_type in {'vacancy', 'internship', 'mentorship'}:
        opportunity_query = opportunity_query.filter_by(opportunity_type=selected_type)

    if selected_format in {'office', 'hybrid', 'remote'}:
        opportunity_query = opportunity_query.filter_by(work_format=selected_format)

    opportunities = opportunity_query.all()

    if selected_tag:
        opportunities = [item for item in opportunities if selected_tag in [tag.name for tag in item.tags]]

    if search_query:
        normalized = search_query.casefold()
        opportunities = [
            item for item in opportunities
            if normalized in ' '.join([
                item.title,
                item.short_description,
                item.city,
                item.employer.company_name,
                ' '.join(tag.name for tag in item.tags),
            ]).casefold()
        ]

    return [item for item in opportunities if item.salary_max >= min_salary or item.salary_max == 0]


def public_event_catalog(selected_format: str = '', selected_tag: str = '', search_query: str = ''):
    event_query = approved_events()

    if selected_format in {'offline', 'online', 'hybrid'}:
        event_query = event_query.filter_by(event_format=selected_format)

    events = event_query.all()

    if selected_tag:
        events = [item for item in events if selected_tag in [tag.name for tag in item.tags]]

    if search_query:
        normalized = search_query.casefold()
        events = [
            item for item in events
            if normalized in ' '.join([
                item.title,
                item.short_description,
                item.city,
                item.venue_name,
                item.employer.company_name,
                ' '.join(tag.name for tag in item.tags),
            ]).casefold()
        ]

    return events


def migrate_legacy_events() -> None:
    legacy_events = Opportunity.query.filter_by(opportunity_type='event').all()
    if not legacy_events:
        return

    for legacy in legacy_events:
        migrated_event = Event.query.filter_by(title=legacy.title, employer_id=legacy.employer_id).first()
        if not migrated_event:
            starts_on = legacy.starts_on or legacy.expires_on or legacy.published_on or date.today()
            starts_at = datetime.combine(starts_on, time(18, 30))
            migrated_event = Event(
                employer_id=legacy.employer_id,
                title=legacy.title,
                short_description=legacy.short_description,
                event_format='online' if legacy.work_format == 'remote' else ('hybrid' if legacy.work_format == 'hybrid' else 'offline'),
                city=legacy.city,
                address=legacy.address,
                venue_name=legacy.address or legacy.city,
                latitude=legacy.latitude,
                longitude=legacy.longitude,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=2),
                registration_deadline=max(date.today(), starts_on - timedelta(days=1)),
                capacity=120,
                target_audience='Студенты и junior-специалисты',
                speaker_name=legacy.employer.company_name,
                registration_url=legacy.employer.website or '',
                contact_email=legacy.employer.user.email if legacy.employer and legacy.employer.user else '',
                participation_cost='Бесплатно',
                is_published=legacy.is_published,
                moderation_status=legacy.moderation_status,
            )
            migrated_event.tags = list(legacy.tags)
            db.session.add(migrated_event)
            db.session.flush()

        for item in ModerationQueue.query.filter_by(entity_type='opportunity', entity_id=legacy.id).all():
            item.entity_type = 'event'
            item.entity_id = migrated_event.id

        if legacy.applications:
            legacy.is_published = False
            legacy.moderation_status = 'archived'
        else:
            db.session.delete(legacy)

    db.session.commit()


def can_manage_company(profile: EmployerProfile) -> bool:
    return profile.hr_status in {'owner', 'approved'}


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder='templates', static_folder='static')
    default_db_path = BASE_DIR / 'tramplin.db'
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'tramplin-local-secret'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', f'sqlite:///{default_db_path}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        BOT_NAME=os.environ.get('BOT_NAME', 'tramplin_verify_bot').lstrip('@'),
        BOT_API_TOKEN=os.environ.get('BOT_API_TOKEN', 'change-this-bot-token'),
        REGISTRATION_NOTIFY_TO=os.environ.get('REGISTRATION_NOTIFY_TO', 'hr-admin@tramplin.local'),
        MAIL_FROM=os.environ.get('MAIL_FROM', 'noreply@tramplin.local'),
        MAIL_HOST=os.environ.get('MAIL_HOST', ''),
        MAIL_PORT=os.environ.get('MAIL_PORT', '587'),
        MAIL_USERNAME=os.environ.get('MAIL_USERNAME', ''),
        MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', ''),
        MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'true'),
        MAIL_OUTBOX_DIR=os.environ.get('MAIL_OUTBOX_DIR', str(BASE_DIR / 'mail_outbox')),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_globals():
        return {
            'today': date.today(),
            'status_titles': STATUS_TITLES,
            'event_status_titles': EVENT_STATUS_TITLES,
            'format_labels': FORMAT_LABELS,
            'type_labels': TYPE_LABELS,
            'hr_status_titles': HR_STATUS_TITLES,
            'registration_bot_name': app.config['BOT_NAME'],
        }

    def parse_checkbox(name: str) -> bool:
        return request.form.get(name) in {'1', 'true', 'on', 'yes'}

    def registration_status_label(flow: RegistrationFlow) -> str:
        labels = {
            'pending': 'ожидает подтверждения',
            'completed': 'подтверждено',
            'expired': 'истекло',
        }
        return labels.get(flow.status, flow.status)

    def admin_registration_recipients() -> list[str]:
        return normalize_recipients(app.config.get('REGISTRATION_NOTIFY_TO'))

    def complete_registration_flow(flow: RegistrationFlow, approval_source: str = 'email_code') -> None:
        now = datetime.now()
        if flow.status == 'completed':
            return

        flow.status = 'completed'
        flow.bot_confirmed_at = now
        flow.completed_at = now
        flow.notes = f'Регистрация подтверждена через {approval_source}.'

        user = flow.user
        user.is_active_account = True
        employer_profile = user.employer_profile
        if employer_profile and employer_profile.verification:
            verification = employer_profile.verification
            if 'email-коду' not in (verification.legal_status or '').casefold():
                base_status = verification.legal_status or 'На проверке'
                verification.legal_status = f'{base_status} · личность подтверждена по email-коду'
            if not verification.verified_at:
                verification.verified_at = now

        notify_registration_confirmed(
            app,
            user=user,
            flow=flow,
            company_name=employer_profile.company_name if employer_profile else user.display_name,
            admin_recipients=admin_registration_recipients(),
        )

    def ensure_profile_for_user(user: User) -> bool:
        changed = False
        if user.role == 'student' and not user.student_profile:
            db.session.add(StudentProfile(
                user_id=user.id,
                full_name=user.display_name,
                university='Не указан',
                graduation_year=date.today().year + 1,
                course='1 курс',
                city='Москва',
                summary='Новый участник платформы. Заполните навыки, ссылки и карьерные цели в настройках профиля.',
                timeline_json='[]',
            ))
            changed = True
        elif user.role == 'employer' and not user.employer_profile:
            company_name = f'Компания {user.display_name}'
            employer = EmployerProfile(
                user_id=user.id,
                company_name=company_name,
                legal_name=company_name,
                description='Профиль ожидает заполнения работодателем.',
                website='',
                socials='',
                city='Москва',
                industry='IT',
                office_address='—',
                company_inn='',
                hr_title='HR manager',
                hr_status='owner',
            )
            db.session.add(employer)
            db.session.flush()
            db.session.add(CompanyVerification(
                employer_id=employer.id,
                corporate_email=user.email,
                inn='',
                verification_level=0,
                legal_status='Требуется ручная проверка',
            ))
            changed = True
        elif user.role == 'curator' and not user.curator_profile:
            db.session.add(CuratorProfile(
                user_id=user.id,
                title='Куратор платформы',
                organization='Карьерный центр',
                is_super_admin=False,
            ))
            changed = True

        if changed:
            db.session.flush()
        return changed

    def profile_form_defaults(user: User) -> dict:
        if user.role == 'student' and user.student_profile:
            profile = user.student_profile
            return {
                'display_name': user.display_name,
                'full_name': profile.full_name,
                'university': profile.university,
                'graduation_year': profile.graduation_year,
                'course': profile.course,
                'city': profile.city,
                'summary': profile.summary,
                'github_url': profile.github_url or '',
                'portfolio_url': profile.portfolio_url or '',
                'privacy_mode': profile.privacy_mode,
                'active_search': profile.active_search,
                'radar_hard': profile.radar_hard,
                'radar_data': profile.radar_data,
                'radar_soft': profile.radar_soft,
                'radar_leadership': profile.radar_leadership,
                'skills': ', '.join(tag.name for tag in profile.skills if tag.category == 'skill'),
            }
        if user.role == 'employer' and user.employer_profile:
            profile = user.employer_profile
            verification = profile.verification
            return {
                'display_name': user.display_name,
                'company_name': profile.company_name,
                'legal_name': profile.legal_name,
                'company_description': profile.description,
                'website': profile.website or '',
                'socials': profile.socials or '',
                'city': profile.city,
                'industry': profile.industry,
                'office_address': profile.office_address or '',
                'cover_url': profile.cover_url or '',
                'office_photo_url': profile.office_photo_url or '',
                'inn': verification.inn if verification else '',
            }
        if user.role == 'curator' and user.curator_profile:
            profile = user.curator_profile
            return {
                'display_name': user.display_name,
                'curator_title': profile.title,
                'organization': profile.organization,
            }
        return {'display_name': user.display_name}

    def save_profile_settings(user: User) -> None:
        user.display_name = request.form.get('display_name', '').strip() or user.display_name

        if user.role == 'student' and user.student_profile:
            profile = user.student_profile
            profile.full_name = request.form.get('full_name', '').strip() or user.display_name
            user.display_name = profile.full_name
            profile.university = request.form.get('university', '').strip() or 'Не указан'
            profile.graduation_year = parse_int(request.form.get('graduation_year'), profile.graduation_year or date.today().year + 1)
            profile.course = request.form.get('course', '').strip() or '1 курс'
            profile.city = request.form.get('city', '').strip() or 'Москва'
            profile.summary = request.form.get('summary', '').strip() or profile.summary
            profile.github_url = request.form.get('github_url', '').strip() or None
            profile.portfolio_url = request.form.get('portfolio_url', '').strip() or None
            privacy_mode = request.form.get('privacy_mode', profile.privacy_mode or 'networking').strip()
            profile.privacy_mode = privacy_mode if privacy_mode in {'networking', 'contacts_only', 'incognito', 'public', 'private'} else 'networking'
            profile.active_search = parse_checkbox('active_search')
            profile.radar_hard = max(0, min(100, parse_int(request.form.get('radar_hard'), profile.radar_hard)))
            profile.radar_data = max(0, min(100, parse_int(request.form.get('radar_data'), profile.radar_data)))
            profile.radar_soft = max(0, min(100, parse_int(request.form.get('radar_soft'), profile.radar_soft)))
            profile.radar_leadership = max(0, min(100, parse_int(request.form.get('radar_leadership'), profile.radar_leadership)))
            skills_text = request.form.get('skills', '')
            if skills_text:
                profile.skills = parse_tags_from_text(skills_text)
            return

        if user.role == 'employer' and user.employer_profile:
            profile = user.employer_profile
            company_name = request.form.get('company_name', '').strip() or profile.company_name
            profile.company_name = company_name
            profile.legal_name = request.form.get('legal_name', '').strip() or company_name
            profile.description = request.form.get('company_description', '').strip() or profile.description
            profile.website = request.form.get('website', '').strip()
            profile.socials = request.form.get('socials', '').strip()
            profile.city = request.form.get('city', '').strip() or 'Москва'
            profile.industry = request.form.get('industry', '').strip() or profile.industry
            profile.office_address = request.form.get('office_address', '').strip() or profile.office_address
            profile.cover_url = request.form.get('cover_url', '').strip()
            profile.office_photo_url = request.form.get('office_photo_url', '').strip()
            new_inn = request.form.get('inn', '').strip()
            if new_inn:
                profile.company_inn = new_inn
            if profile.verification:
                if new_inn:
                    profile.verification.inn = new_inn
                profile.verification.corporate_email = user.email
            return

        if user.role == 'curator' and user.curator_profile:
            profile = user.curator_profile
            profile.title = request.form.get('curator_title', '').strip() or profile.title
            profile.organization = request.form.get('organization', '').strip() or profile.organization

    @app.route('/')
    def index():
        active_tab = request.args.get('tab', 'opportunities')
        if active_tab not in {'opportunities', 'events'}:
            active_tab = 'opportunities'

        selected_type = request.args.get('type', '')
        if selected_type not in {'', 'vacancy', 'internship', 'mentorship'}:
            selected_type = ''

        selected_format = request.args.get('format', '')
        if selected_format not in {'', 'office', 'hybrid', 'remote'}:
            selected_format = ''

        selected_event_format = request.args.get('event_format', '')
        if selected_event_format not in {'', 'offline', 'online', 'hybrid'}:
            selected_event_format = ''

        selected_tag = request.args.get('tag', '')
        search_query = request.args.get('q', '').strip()
        min_salary = parse_int(request.args.get('salary', '0'))

        opportunities = public_opportunity_catalog(
            selected_type=selected_type,
            selected_format=selected_format,
            selected_tag=selected_tag,
            min_salary=min_salary,
            search_query=search_query,
        )
        events = public_event_catalog(
            selected_format=selected_event_format,
            selected_tag=selected_tag,
            search_query=search_query,
        )

        opportunity_cards = build_public_catalog(opportunities, [])
        event_cards = build_public_catalog([], events)
        public_cards = opportunity_cards + event_cards

        tags = Tag.query.filter_by(category='skill').order_by(Tag.name.asc()).all()
        favorite_company_ids = []
        if current_user.is_authenticated and current_user.role == 'student':
            favorite_company_ids = [
                application.opportunity.employer_id
                for application in current_user.student_profile.applications
                if application.status == 'wishlist'
            ]

        return render_template(
            'index.html',
            active_tab=active_tab,
            opportunities=opportunities,
            events=events,
            public_cards=public_cards,
            opportunity_cards=opportunity_cards,
            event_cards=event_cards,
            opportunity_map_payload=build_map_payload(opportunity_cards),
            event_map_payload=build_map_payload(event_cards),
            tags=tags,
            selected_type=selected_type,
            selected_format=selected_format,
            selected_event_format=selected_event_format,
            selected_tag=selected_tag,
            search_query=search_query,
            min_salary=min_salary,
            favorite_company_ids=favorite_company_ids,
        )

    @app.route('/health')
    def healthcheck():
        return jsonify({
            'status': 'ok',
            'users': User.query.count(),
            'opportunities': Opportunity.query.count(),
            'events': Event.query.count(),
        })

    @app.route('/api/opportunities')
    def api_opportunities():
        tab = request.args.get('tab', 'all')
        selected_type = request.args.get('type', '')
        selected_format = request.args.get('format', '')
        selected_event_format = request.args.get('event_format', '')
        selected_tag = request.args.get('tag', '')
        search_query = request.args.get('q', '').strip()
        min_salary = parse_int(request.args.get('salary', '0'))

        if tab == 'events':
            cards = build_public_catalog([], public_event_catalog(selected_event_format, selected_tag, search_query))
        elif tab == 'opportunities':
            cards = build_public_catalog(
                public_opportunity_catalog(selected_type, selected_format, selected_tag, min_salary, search_query),
                [],
            )
        else:
            cards = build_public_catalog(
                public_opportunity_catalog(selected_type, selected_format, selected_tag, min_salary, search_query),
                public_event_catalog(selected_event_format, selected_tag, search_query),
            )
        return jsonify(build_map_payload(cards))

    @app.route('/opportunity/<int:opportunity_id>')
    def opportunity_detail(opportunity_id: int):
        opportunity = Opportunity.query.get_or_404(opportunity_id)
        match_info = None
        if current_user.is_authenticated and current_user.role == 'student':
            match_info = compute_match(current_user.student_profile, opportunity)
        return render_template('opportunity.html', opportunity=opportunity, match_info=match_info)

    @app.route('/event/<int:event_id>')
    def event_detail(event_id: int):
        event = Event.query.get_or_404(event_id)
        registration = None
        if current_user.is_authenticated and current_user.role == 'student':
            registration = EventRegistration.query.filter_by(
                student_id=current_user.student_profile.id,
                event_id=event.id,
            ).first()
        return render_template(
            'event.html',
            event=event,
            registration=registration,
            seats_left=available_event_seats(event),
        )

    @app.route('/apply/<int:opportunity_id>', methods=['POST'])
    @login_required
    def apply(opportunity_id: int):
        if current_user.role != 'student':
            flash('Отклик доступен только соискателям.', 'error')
            return redirect(url_for('opportunity_detail', opportunity_id=opportunity_id))
        opportunity = Opportunity.query.get_or_404(opportunity_id)
        existing = Application.query.filter_by(student_id=current_user.student_profile.id, opportunity_id=opportunity.id).first()
        status = request.form.get('status', 'applied')
        if existing:
            existing.status = status
        else:
            match_info = compute_match(current_user.student_profile, opportunity)
            db.session.add(Application(
                student_id=current_user.student_profile.id,
                opportunity_id=opportunity.id,
                status=status,
                note='Создано из карточки вакансии',
                match_score=match_info['score'],
            ))
        db.session.commit()
        flash('Статус успешно обновлён.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/event/register/<int:event_id>', methods=['POST'])
    @login_required
    def register_event(event_id: int):
        if current_user.role != 'student':
            flash('Регистрация доступна только соискателям.', 'error')
            return redirect(url_for('event_detail', event_id=event_id))

        event = Event.query.get_or_404(event_id)
        existing = EventRegistration.query.filter_by(
            student_id=current_user.student_profile.id,
            event_id=event.id,
        ).first()
        note = request.form.get('note', '').strip()

        status = 'registered'
        if not existing and event.capacity and available_event_seats(event) <= 0:
            status = 'waitlist'

        if existing:
            existing.note = note or existing.note
            if existing.status == 'cancelled':
                existing.status = status
        else:
            db.session.add(EventRegistration(
                student_id=current_user.student_profile.id,
                event_id=event.id,
                status=status,
                note=note,
            ))

        db.session.commit()
        flash('Регистрация на мероприятие обновлена.', 'success')
        return redirect(url_for('event_detail', event_id=event.id))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email'].strip().lower()
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password):
                if user.is_banned:
                    flash('Аккаунт заблокирован администратором.', 'error')
                    return redirect(url_for('login'))
                if not user.is_active_account:
                    if user.registration_flow and user.registration_flow.status != 'completed':
                        flash('Для входа сначала подтвердите регистрацию кодом из письма.', 'error')
                        return redirect(url_for('registration_pending', verification_code=user.registration_flow.verification_code))
                    flash('Аккаунт деактивирован.', 'error')
                    return redirect(url_for('login'))
                if ensure_profile_for_user(user):
                    db.session.commit()
                login_user(user)
                flash('Добро пожаловать в Трамплин.', 'success')
                return redirect(url_for('dashboard'))
            flash('Неверный логин или пароль.', 'error')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            role = request.form.get('role', '').strip()
            if role not in {'student', 'employer'}:
                flash('Выберите корректную роль.', 'error')
                return redirect(url_for('register'))

            email = request.form['email'].strip().lower()
            if User.query.filter_by(email=email).first():
                flash('Пользователь с таким email уже существует.', 'error')
                return redirect(url_for('register'))

            user = User(
                email=email,
                password_hash=generate_password_hash(request.form['password'], method='pbkdf2:sha256', salt_length=16),
                display_name=request.form['display_name'].strip(),
                role=role,
                is_active_account=True,
            )
            db.session.add(user)
            db.session.flush()

            if role == 'student':
                db.session.add(StudentProfile(
                    user_id=user.id,
                    full_name=request.form['display_name'].strip(),
                    university=request.form.get('university', 'Не указан'),
                    graduation_year=parse_int(request.form.get('graduation_year'), date.today().year + 1),
                    course=request.form.get('course', '1 курс'),
                    city=request.form.get('city', 'Москва'),
                    summary='Новый участник платформы. Заполните навыки, ссылки и карьерные цели в настройках профиля.',
                    timeline_json='[]',
                ))
                db.session.commit()
                flash('Регистрация завершена. Можно войти в систему.', 'success')
                return redirect(url_for('login'))

            company_mode = request.form.get('company_mode', 'create')
            company_name = request.form.get('company_name', 'Новая компания').strip() or 'Новая компания'
            inn = request.form.get('inn', '').strip()
            website = request.form.get('website', '').strip()
            hr_title = request.form.get('hr_title', 'HR manager').strip() or 'HR manager'
            existing_company = EmployerProfile.query.filter_by(company_inn=inn).order_by(EmployerProfile.id.asc()).first() if inn else None

            if company_mode == 'join' and existing_company:
                auto_linked = can_auto_link_company(existing_company, email, website)
                profile = EmployerProfile(
                    user_id=user.id,
                    company_name=existing_company.company_name,
                    legal_name=existing_company.legal_name,
                    description=existing_company.description,
                    website=existing_company.website,
                    socials=existing_company.socials,
                    city=existing_company.city,
                    industry=existing_company.industry,
                    office_address=existing_company.office_address,
                    cover_url=existing_company.cover_url,
                    office_photo_url=existing_company.office_photo_url,
                    verified_badge=existing_company.verified_badge and auto_linked,
                    company_inn=existing_company.company_inn,
                    hr_title=hr_title,
                    hr_status='approved' if auto_linked else 'pending',
                )
                db.session.add(profile)
                db.session.flush()
                verification_level = existing_company.verification.verification_level if existing_company.verification else 1
                legal_status = 'Привязан к действующей компании' if auto_linked else 'Ожидает подтверждения связи с компанией'
                db.session.add(CompanyVerification(
                    employer_id=profile.id,
                    corporate_email=email,
                    inn=inn,
                    verification_level=verification_level,
                    legal_status=legal_status,
                ))
                db.session.add(ModerationQueue(
                    entity_type='company',
                    entity_id=profile.id,
                    title=f'Привязка HR к компании {profile.company_name}',
                    submitted_by=user.display_name,
                    status='approved' if auto_linked else 'pending',
                ))
            else:
                verification_result = verify_company(email, inn)
                profile = EmployerProfile(
                    user_id=user.id,
                    company_name=company_name,
                    legal_name=verification_result['legal_name'] if verification_result['legal_name'] != 'Не найдено' else company_name,
                    description='Профиль ожидает заполнения работодателем.',
                    website=website,
                    socials='',
                    city=request.form.get('city', 'Москва'),
                    industry=request.form.get('industry', 'IT'),
                    office_address=request.form.get('office_address', '—'),
                    verified_badge=verification_result['verified'],
                    company_inn=inn,
                    hr_title=hr_title,
                    hr_status='owner',
                )
                db.session.add(profile)
                db.session.flush()
                db.session.add(CompanyVerification(
                    employer_id=profile.id,
                    corporate_email=email,
                    inn=inn,
                    verification_level=verification_result['level'],
                    legal_status=verification_result['status'],
                ))
                db.session.add(ModerationQueue(
                    entity_type='company',
                    entity_id=profile.id,
                    title=f'Регистрация работодателя {profile.company_name}',
                    submitted_by=user.display_name,
                    status='pending',
                ))

            db.session.commit()
            flash('Регистрация завершена. Можно войти в систему.', 'success')
            return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/registration/pending/<verification_code>')
    def registration_pending(verification_code: str):
        flow = RegistrationFlow.query.filter_by(verification_code=verification_code).first()
        if not flow:
            flash('Заявка на регистрацию не найдена.', 'error')
            return redirect(url_for('login'))
        return render_template(
            'registration_pending.html',
            flow=flow,
            status_label=registration_status_label(flow),
        )

    @app.route('/registration/verify/<verification_code>', methods=['POST'])
    def verify_registration_code(verification_code: str):
        flow = RegistrationFlow.query.filter_by(verification_code=verification_code).first()
        if not flow:
            flash('Заявка на регистрацию не найдена.', 'error')
            return redirect(url_for('login'))
        if flow.status == 'completed':
            flash('Регистрация уже подтверждена.', 'success')
            return redirect(url_for('registration_pending', verification_code=verification_code))

        submitted_code = request.form.get('email_code', '').strip()
        if not submitted_code:
            flash('Введите код из письма.', 'error')
            return redirect(url_for('registration_pending', verification_code=verification_code))
        if submitted_code != flow.verification_code:
            flash('Код не совпадает. Проверьте письмо и попробуйте ещё раз.', 'error')
            return redirect(url_for('registration_pending', verification_code=verification_code))

        complete_registration_flow(flow, approval_source='email_code')
        db.session.commit()
        flash('Регистрация подтверждена. Теперь можно войти в кабинет.', 'success')
        return redirect(url_for('login'))

    @app.route('/registration/status/<verification_code>')
    def registration_status(verification_code: str):
        flow = RegistrationFlow.query.filter_by(verification_code=verification_code).first()
        if not flow:
            return jsonify({'error': 'not_found'}), 404
        return jsonify({
            'status': flow.status,
            'status_label': registration_status_label(flow),
            'email': flow.contact_email,
            'completed_at': flow.completed_at.isoformat() if flow.completed_at else None,
        })

    @app.route('/registration/resend/<verification_code>', methods=['POST'])
    def resend_registration_email(verification_code: str):
        flow = RegistrationFlow.query.filter_by(verification_code=verification_code).first()
        if not flow:
            flash('Заявка на регистрацию не найдена.', 'error')
            return redirect(url_for('login'))
        if flow.status == 'completed':
            flash('Регистрация уже подтверждена.', 'success')
            return redirect(url_for('registration_pending', verification_code=verification_code))

        profile = flow.user.employer_profile
        notify_registration_started(
            app,
            user=flow.user,
            flow=flow,
            company_name=profile.company_name if profile else flow.user.display_name,
            admin_recipients=admin_registration_recipients(),
        )
        flow.applicant_email_sent_at = datetime.now()
        db.session.commit()
        flash('Письмо с кодом отправлено повторно.', 'success')
        return redirect(url_for('registration_pending', verification_code=verification_code))

    @app.route('/api/bot/registration/<verification_code>/confirm', methods=['POST'])
    def confirm_registration_from_bot(verification_code: str):
        token = request.headers.get('X-Bot-Token', '')
        if token != app.config['BOT_API_TOKEN']:
            return jsonify({'ok': False, 'error': 'forbidden'}), 403

        flow = RegistrationFlow.query.filter_by(verification_code=verification_code).first()
        if not flow:
            return jsonify({'ok': False, 'error': 'not_found'}), 404

        complete_registration_flow(flow, approval_source='integration')
        db.session.commit()
        return jsonify({
            'ok': True,
            'status': flow.status,
            'status_label': registration_status_label(flow),
            'user_email': flow.user.email,
        })

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Вы вышли из системы.', 'success')
        return redirect(url_for('index'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        if ensure_profile_for_user(current_user):
            db.session.commit()

        if current_user.role == 'student':
            student = current_user.student_profile
            applications = student.applications
            opportunities = approved_opportunities().all()
            recommendations = []
            for opportunity in opportunities[:4]:
                recommendations.append((opportunity, compute_match(student, opportunity)))
            return render_template(
                'dashboards/student.html',
                student=student,
                timeline=timeline_items(student),
                timeline_text_value=timeline_text(student),
                kanban=kanban_columns(applications),
                market_insights=skill_gap_market_insights(student, opportunities),
                recommendations=recommendations,
                event_registrations=sorted(student.event_registrations, key=lambda item: item.event.starts_at),
                suggested_tags=Tag.query.filter_by(category='skill').order_by(Tag.name.asc()).all(),
                github_profile=github_profile_payload(student),
            )

        if current_user.role == 'employer':
            employer = current_user.employer_profile
            member_ids = company_member_ids(employer)
            employer_opportunities = Opportunity.query.filter(Opportunity.employer_id.in_(member_ids)).order_by(Opportunity.created_at.desc()).all() if member_ids else []
            employer_events = Event.query.filter(Event.employer_id.in_(member_ids)).order_by(Event.created_at.desc()).all() if member_ids else []
            selected_entity = request.args.get('entity')
            if selected_entity not in {'opportunity', 'event'}:
                selected_entity = 'opportunity' if employer_opportunities else 'event'

            selected_item_id = request.args.get('item_id', type=int)
            selected_opportunity = find_item_by_id(employer_opportunities, selected_item_id) if selected_entity == 'opportunity' else None
            selected_event = find_item_by_id(employer_events, selected_item_id) if selected_entity == 'event' else None
            constructor_tab = request.args.get('constructor_tab', 'opportunity')
            if constructor_tab not in {'opportunity', 'event'}:
                constructor_tab = 'opportunity'

            return render_template(
                'dashboards/employer.html',
                employer=employer,
                verification=employer.verification,
                selected_entity=selected_entity,
                selected_opportunity=selected_opportunity,
                selected_event=selected_event,
                candidate_rows=employer_candidate_overview(selected_opportunity),
                event_rows=employer_event_overview(selected_event),
                candidate_board=recruitment_board_for_opportunity(selected_opportunity),
                event_board=recruitment_board_for_event(selected_event),
                hiring_summary=employer_activity_summary(employer_opportunities, employer_events),
                suggested_tags=Tag.query.filter_by(category='skill').order_by(Tag.name.asc()).all(),
                team_members=company_team_members(employer),
                employer_opportunities=employer_opportunities,
                employer_events=employer_events,
                constructor_tab=constructor_tab,
                can_manage_company=can_manage_company(employer),
            )

        curator = current_user.curator_profile
        opportunities = Opportunity.query.filter(Opportunity.opportunity_type != 'event').all()
        events = Event.query.all()
        return render_template(
            'dashboards/curator.html',
            curator=curator,
            moderation_items=ModerationQueue.query.order_by(ModerationQueue.created_at.desc()).all(),
            analytics=analytics_payload(opportunities, events),
            users=User.query.order_by(User.created_at.desc()).all(),
            employer_profiles=EmployerProfile.query.order_by(EmployerProfile.created_at.desc()).all(),
            manageable_opportunities=Opportunity.query.order_by(Opportunity.is_published.desc(), Opportunity.updated_at.desc()).all(),
        )

    @app.route('/student/profile', methods=['POST'])
    @login_required
    def update_student_profile():
        if current_user.role != 'student':
            return redirect(url_for('dashboard'))
        student = current_user.student_profile
        student.full_name = request.form.get('full_name', student.full_name).strip() or student.full_name
        current_user.display_name = request.form.get('display_name', current_user.display_name).strip() or current_user.display_name
        student.university = request.form.get('university', student.university).strip() or student.university
        student.course = request.form.get('course', student.course).strip() or student.course
        student.city = request.form.get('city', student.city).strip() or student.city
        student.graduation_year = parse_int(request.form.get('graduation_year'), student.graduation_year)
        student.summary = request.form.get('summary', student.summary).strip() or student.summary
        student.portfolio_url = request.form.get('portfolio_url', '').strip()
        student.privacy_mode = request.form.get('privacy_mode', student.privacy_mode)
        student.active_search = request.form.get('active_search') == 'on'
        skills_text = request.form.get('skills', '')
        student.skills = parse_tags_from_text(skills_text)
        timeline_value = request.form.get('timeline_text', '').strip()
        student.timeline_json = parse_timeline_text(timeline_value) if timeline_value else '[]'
        db.session.commit()
        flash('Профиль соискателя обновлён.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/student/profile/github', methods=['POST'])
    @login_required
    def connect_github():
        if current_user.role != 'student':
            return redirect(url_for('dashboard'))
        student = current_user.student_profile
        github_url = request.form.get('github_url', '').strip()
        username = extract_github_username(github_url)
        if not username:
            flash('Укажите корректную ссылку вида https://github.com/username.', 'error')
            return redirect(url_for('dashboard'))
        student.github_url = f'https://github.com/{username}'
        db.session.commit()
        flash(f'GitHub-профиль {username} успешно привязан.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/employer/create', methods=['POST'])
    @login_required
    def create_opportunity():
        if current_user.role != 'employer':
            return redirect(url_for('dashboard'))
        employer = current_user.employer_profile
        if not can_manage_company(employer):
            flash('Сначала дождитесь подтверждения привязки к компании от куратора.', 'error')
            return redirect(url_for('dashboard', constructor_tab='opportunity'))
        opportunity = Opportunity(
            employer_id=employer.id,
            title=request.form['title'],
            short_description=request.form['short_description'],
            opportunity_type=request.form['opportunity_type'],
            work_format=request.form['work_format'],
            city=request.form['city'],
            address=request.form['address'],
            latitude=parse_float(request.form.get('latitude'), 55.7512),
            longitude=parse_float(request.form.get('longitude'), 37.6184),
            salary_min=parse_int(request.form.get('salary_min', '0')),
            salary_max=parse_int(request.form.get('salary_max', '0')),
            employment_type=request.form.get('employment_type', 'full-time'),
            level=request.form.get('level', 'Intern'),
            published_on=date.today(),
            expires_on=date.today() + timedelta(days=30),
            moderation_status='pending',
            is_published=False,
        )
        opportunity.tags = parse_tags_from_text(request.form.get('tags', ''))
        db.session.add(opportunity)
        db.session.flush()
        db.session.add(ModerationQueue(
            entity_type='opportunity',
            entity_id=opportunity.id,
            title=opportunity.title,
            submitted_by=current_user.display_name,
        ))
        db.session.commit()
        flash('Карточка вакансии создана и отправлена на премодерацию.', 'success')
        return redirect(url_for('dashboard', entity='opportunity', item_id=opportunity.id, constructor_tab='opportunity'))

    @app.route('/employer/create-event', methods=['POST'])
    @login_required
    def create_event():
        if current_user.role != 'employer':
            return redirect(url_for('dashboard'))
        employer = current_user.employer_profile
        if not can_manage_company(employer):
            flash('Сначала дождитесь подтверждения привязки к компании от куратора.', 'error')
            return redirect(url_for('dashboard', constructor_tab='event'))
        starts_at = parse_datetime_local(
            request.form.get('starts_at', ''),
            fallback=datetime.combine(date.today() + timedelta(days=7), time(18, 0)),
        )
        ends_at = parse_datetime_local(
            request.form.get('ends_at', ''),
            fallback=starts_at + timedelta(hours=2),
        )
        event = Event(
            employer_id=employer.id,
            title=request.form['title'],
            short_description=request.form['short_description'],
            event_format=request.form['event_format'],
            city=request.form['city'],
            address=request.form.get('address', ''),
            venue_name=request.form['venue_name'],
            latitude=parse_float(request.form.get('latitude'), 55.7512),
            longitude=parse_float(request.form.get('longitude'), 37.6184),
            starts_at=starts_at,
            ends_at=ends_at,
            registration_deadline=date.fromisoformat(request.form.get('registration_deadline', date.today().isoformat())),
            capacity=parse_int(request.form.get('capacity', '0')),
            target_audience=request.form.get('target_audience', 'Студенты и выпускники'),
            speaker_name=request.form.get('speaker_name', 'Команда работодателя'),
            registration_url=request.form.get('registration_url', ''),
            contact_email=request.form.get('contact_email', employer.user.email),
            participation_cost=request.form.get('participation_cost', 'Бесплатно') or 'Бесплатно',
            moderation_status='pending',
            is_published=False,
        )
        event.tags = parse_tags_from_text(request.form.get('tags', ''))
        db.session.add(event)
        db.session.flush()
        db.session.add(ModerationQueue(
            entity_type='event',
            entity_id=event.id,
            title=event.title,
            submitted_by=current_user.display_name,
        ))
        db.session.commit()
        flash('Карточка мероприятия создана и отправлена на премодерацию.', 'success')
        return redirect(url_for('dashboard', entity='event', item_id=event.id, constructor_tab='event'))

    @app.route('/employer/application/<int:application_id>/status', methods=['POST'])
    @login_required
    def update_application_status(application_id: int):
        if current_user.role != 'employer':
            return redirect(url_for('dashboard'))
        application = Application.query.get_or_404(application_id)
        if application.opportunity.employer_id not in company_member_ids(current_user.employer_profile):
            flash('Недостаточно прав для управления этим откликом.', 'error')
            return redirect(url_for('dashboard'))
        application.status = request.form.get('status', application.status)
        application.hr_private_note = request.form.get('hr_private_note', application.hr_private_note).strip()
        db.session.commit()
        flash('Статус отклика обновлён.', 'success')
        return redirect(url_for('dashboard', entity='opportunity', item_id=application.opportunity_id))

    @app.route('/employer/application/<int:application_id>/update', methods=['POST'])
    @login_required
    def update_application(application_id: int):
        return update_application_status(application_id)

    @app.route('/employer/event-registration/<int:registration_id>/status', methods=['POST'])
    @login_required
    def update_event_registration_status(registration_id: int):
        if current_user.role != 'employer':
            return redirect(url_for('dashboard'))
        registration = EventRegistration.query.get_or_404(registration_id)
        if registration.event.employer_id not in company_member_ids(current_user.employer_profile):
            flash('Недостаточно прав для управления этой регистрацией.', 'error')
            return redirect(url_for('dashboard'))
        registration.status = request.form.get('status', registration.status)
        db.session.commit()
        flash('Статус участника обновлён.', 'success')
        return redirect(url_for('dashboard', entity='event', item_id=registration.event_id))

    @app.route('/curator/moderate/<int:item_id>', methods=['POST'])
    @login_required
    def moderate_item(item_id: int):
        if current_user.role != 'curator':
            return redirect(url_for('dashboard'))
        item = ModerationQueue.query.get_or_404(item_id)
        action = request.form.get('action')
        item.status = 'approved' if action == 'approve' else 'rejected'
        if action == 'reject':
            item.rejection_reason = request.form.get('reason', 'Не соответствует правилам платформы.')

        target_entity = None
        if item.entity_type == 'opportunity':
            target_entity = db.session.get(Opportunity, item.entity_id)
        elif item.entity_type == 'event':
            target_entity = db.session.get(Event, item.entity_id)
        elif item.entity_type == 'company':
            target_entity = db.session.get(EmployerProfile, item.entity_id)

        if isinstance(target_entity, Opportunity) or isinstance(target_entity, Event):
            target_entity.moderation_status = item.status
            target_entity.is_published = action == 'approve'
        elif isinstance(target_entity, EmployerProfile):
            if action == 'approve':
                if target_entity.hr_status != 'owner':
                    target_entity.hr_status = 'approved'
                if target_entity.verification:
                    target_entity.verification.legal_status = 'Подтверждено куратором'
                    target_entity.verification.verified_at = datetime.now()
                target_entity.verified_badge = True
            else:
                target_entity.hr_status = 'rejected'
                target_entity.verified_badge = False
                if target_entity.verification:
                    target_entity.verification.legal_status = 'Отклонено куратором'

        db.session.commit()
        flash('Статус модерации обновлён.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/profile/settings', methods=['GET', 'POST'])
    @login_required
    def profile_settings():
        if ensure_profile_for_user(current_user):
            db.session.commit()

        if request.method == 'POST':
            save_profile_settings(current_user)
            db.session.commit()
            flash('Профиль сохранён.', 'success')
            return redirect(url_for('profile_settings'))

        return render_template('profile_settings.html', form=profile_form_defaults(current_user))

    @app.route('/curator/opportunities/<int:opportunity_id>/visibility', methods=['POST'])
    @login_required
    def toggle_opportunity_visibility(opportunity_id: int):
        if current_user.role != 'curator':
            return redirect(url_for('dashboard'))

        opportunity = db.session.get(Opportunity, opportunity_id)
        if not opportunity:
            flash('Вакансия не найдена.', 'error')
            return redirect(url_for('dashboard'))

        action = request.form.get('action', 'hide')
        if action == 'publish':
            if opportunity.moderation_status != 'approved':
                flash('Нельзя публиковать карточку без одобрения.', 'error')
                return redirect(url_for('dashboard'))
            opportunity.is_published = True
            flash('Карточка снова опубликована.', 'success')
        else:
            opportunity.is_published = False
            flash('Карточка снята с публикации.', 'success')

        db.session.commit()
        return redirect(url_for('dashboard'))

    @app.route('/curator/users/<int:user_id>/toggle-ban', methods=['POST'])
    @login_required
    def toggle_user_ban(user_id: int):
        if current_user.role != 'curator':
            return redirect(url_for('dashboard'))

        user = db.session.get(User, user_id)
        if not user:
            flash('Пользователь не найден.', 'error')
            return redirect(url_for('dashboard'))
        if user.id == current_user.id:
            flash('Нельзя заблокировать самого себя.', 'error')
            return redirect(url_for('dashboard'))

        action = request.form.get('action', 'ban')
        user.is_banned = action == 'ban'
        db.session.commit()
        flash('Статус пользователя обновлён.', 'success')
        return redirect(url_for('dashboard'))

    @app.route('/curator/users/<int:user_id>/role', methods=['POST'])
    @login_required
    def update_user_role(user_id: int):
        if current_user.role != 'curator':
            return redirect(url_for('dashboard'))

        user = db.session.get(User, user_id)
        if not user:
            flash('Пользователь не найден.', 'error')
            return redirect(url_for('dashboard'))
        if user.id == current_user.id:
            flash('Нельзя менять роль текущего администратора через этот экран.', 'error')
            return redirect(url_for('dashboard'))

        new_role = request.form.get('role', '').strip()
        if new_role not in ALLOWED_ROLES:
            flash('Некорректная роль.', 'error')
            return redirect(url_for('dashboard'))

        user.role = new_role
        ensure_profile_for_user(user)
        db.session.commit()
        flash('Роль пользователя обновлена.', 'success')
        return redirect(url_for('dashboard'))

    with app.app_context():
        db.create_all()
        seed_database()
        migrate_legacy_events()

    return app


if __name__ == '__main__':
    create_app().run(debug=True)
