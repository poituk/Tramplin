from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app, has_app_context

from .models import Application, EmployerProfile, Event, EventRegistration, Opportunity, StudentProfile


FAKE_FNS_REGISTRY = {
    '7707083893': {
        'legal_name': 'ООО «ТехВижн»',
        'registered_at': '2018-04-12',
        'status': 'Действующее',
    },
    '7715964180': {
        'legal_name': 'АО «Data Harbor Labs»',
        'registered_at': '2016-09-20',
        'status': 'Действующее',
    },
}

TYPE_COLORS = {
    'vacancy': '#3b82f6',
    'internship': '#10b981',
    'event': '#ef4444',
    'mentorship': '#8b5cf6',
}

TYPE_LABELS = {
    'vacancy': 'Вакансия',
    'internship': 'Стажировка',
    'event': 'Мероприятие',
    'mentorship': 'Менторство',
}

FORMAT_LABELS = {
    'office': 'Офис',
    'hybrid': 'Гибрид',
    'remote': 'Удаленно',
    'offline': 'Оффлайн',
    'online': 'Онлайн',
}

EVENT_STATUS_TITLES = {
    'registered': 'Новая регистрация',
    'approved': 'Одобрен',
    'waitlist': 'Лист ожидания',
    'attended': 'Посетил',
    'rejected': 'Отклонен',
    'cancelled': 'Отменил',
}

STATUS_TITLES = {
    'wishlist': 'Интересуется',
    'applied': 'Откликнулся',
    'invited': 'Собеседование',
    'approved': 'Одобрен',
    'offer': 'Оффер',
    'rejected': 'Отказ',
    'reserve': 'Резерв',
}

HR_STATUS_TITLES = {
    'owner': 'Владелец компании',
    'approved': 'Подтвержденный HR',
    'pending': 'Ожидает подтверждения',
    'rejected': 'Отклонен',
}

APPLICATION_BOARD_ORDER = ['applied', 'invited', 'approved', 'offer', 'reserve', 'rejected', 'wishlist']
EVENT_BOARD_ORDER = ['registered', 'approved', 'attended', 'waitlist', 'rejected', 'cancelled']


def compute_match(student: StudentProfile, opportunity: Opportunity) -> dict:
    student_skills = {tag.name.lower() for tag in student.skills}
    opportunity_skills = {tag.name.lower() for tag in opportunity.tags}
    overlap = student_skills & opportunity_skills
    missing = opportunity_skills - student_skills

    skill_component = (len(overlap) / max(len(opportunity_skills), 1)) * 70
    city_component = 10 if student.city == opportunity.city else 5
    active_search_component = 10 if student.active_search else 4
    portfolio_component = 10 if student.github_url else 4
    score = round(skill_component + city_component + active_search_component + portfolio_component)
    score = max(35, min(99, score))

    recommendations = []
    if missing:
        top_missing = sorted(missing)[:3]
        recommendations.append(
            f"Изучите {', '.join(top_missing)} — это даст быстрый рост релевантности."
        )
    if not student.github_url:
        recommendations.append('Добавьте GitHub или GitLab, чтобы усилить доверие работодателей.')
    if student.privacy_mode == 'incognito':
        recommendations.append('Переключите режим на «Активный поиск», чтобы повысить видимость профиля.')

    potential = min(99, score + 17 if missing else score + 8)
    return {
        'score': score,
        'missing_skills': sorted(missing),
        'overlap': sorted(overlap),
        'recommendations': recommendations,
        'potential_score': potential,
    }


def skill_gap_market_insights(student: StudentProfile, opportunities: list[Opportunity]) -> list[str]:
    market_counter = Counter()
    student_skills = {tag.name.lower() for tag in student.skills}
    for opportunity in opportunities:
        market_counter.update(tag.name for tag in opportunity.tags)
    insights = []
    for skill, count in market_counter.most_common(4):
        if skill.lower() not in student_skills:
            insights.append(
                f'В {count} релевантных возможностях требуется {skill}, а у вас этот навык не отмечен.'
            )
    if not insights:
        insights.append('Ваш стек уже перекрывает основную часть рынка. Усильте портфолио и кейсы.')
    return insights


def verify_company(corporate_email: str, inn: str) -> dict:
    level = 1 if corporate_email and not corporate_email.endswith(('gmail.com', 'yandex.ru', 'mail.ru', 'hotmail.com')) else 0
    registry = FAKE_FNS_REGISTRY.get(inn)
    if registry:
        return {
            'level': 2 if level else 1,
            'verified': bool(level),
            'legal_name': registry['legal_name'],
            'registered_at': registry['registered_at'],
            'status': registry['status'],
            'checked_at': datetime.now().isoformat(timespec='seconds'),
        }
    return {
        'level': level,
        'verified': False,
        'legal_name': 'Не найдено',
        'registered_at': '—',
        'status': 'Требуется ручная проверка',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
    }


def opportunity_salary_label(opportunity: Opportunity) -> str:
    if opportunity.salary_max:
        return f"{opportunity.salary_min:,}–{opportunity.salary_max:,} ₽".replace(',', ' ')
    return 'Без оплаты / карьерная активность'


def event_schedule_label(event: Event) -> str:
    starts = event.starts_at.strftime('%d.%m %H:%M')
    ends = event.ends_at.strftime('%H:%M')
    return f'{starts}–{ends}'


def available_event_seats(event: Event) -> int:
    if not event.capacity:
        return 0
    active_statuses = {'registered', 'approved', 'attended'}
    occupied = sum(1 for reg in event.registrations if reg.status in active_statuses)
    return max(event.capacity - occupied, 0)


def serialize_opportunity(item: Opportunity) -> dict:
    return {
        'id': f'opportunity-{item.id}',
        'entity_type': 'opportunity',
        'entity_id': item.id,
        'title': item.title,
        'company': item.employer.company_name,
        'company_id': item.employer_id,
        'type': item.opportunity_type,
        'type_label': TYPE_LABELS.get(item.opportunity_type, item.opportunity_type),
        'format': item.work_format,
        'format_label': FORMAT_LABELS.get(item.work_format, item.work_format),
        'city': item.city,
        'address': item.address,
        'lat': item.latitude,
        'lng': item.longitude,
        'salary': opportunity_salary_label(item),
        'meta_line': opportunity_salary_label(item),
        'color': TYPE_COLORS.get(item.opportunity_type, '#3b82f6'),
        'tags': [tag.name for tag in item.tags],
        'url': f'/opportunity/{item.id}',
        'short_description': item.short_description,
    }


def serialize_event(event: Event) -> dict:
    return {
        'id': f'event-{event.id}',
        'entity_type': 'event',
        'entity_id': event.id,
        'title': event.title,
        'company': event.employer.company_name,
        'company_id': event.employer_id,
        'type': 'event',
        'type_label': TYPE_LABELS['event'],
        'format': event.event_format,
        'format_label': FORMAT_LABELS.get(event.event_format, event.event_format),
        'city': event.city,
        'address': event.address,
        'lat': event.latitude,
        'lng': event.longitude,
        'salary': event_schedule_label(event),
        'meta_line': f"{event_schedule_label(event)} · {event.participation_cost}",
        'color': TYPE_COLORS['event'],
        'tags': [tag.name for tag in event.tags],
        'url': f'/event/{event.id}',
        'short_description': event.short_description,
    }


def build_public_catalog(opportunities: list[Opportunity], events: list[Event]) -> list[dict]:
    cards = [serialize_opportunity(item) for item in opportunities] + [serialize_event(item) for item in events]
    cards.sort(key=lambda item: (item['type'] != 'event', item['city'], item['title']))
    return cards


def build_map_payload(cards: list[dict]) -> list[dict]:
    result = []
    for item in cards:
        result.append({
            'id': item['id'],
            'title': item['title'],
            'company': item['company'],
            'type': item['type'],
            'format': item['format_label'],
            'city': item['city'],
            'address': item['address'],
            'lat': item['lat'],
            'lng': item['lng'],
            'salary': item['meta_line'],
            'color': item['color'],
            'tags': item['tags'],
            'url': item['url'],
        })
    return result


def timeline_items(student: StudentProfile) -> list[dict]:
    try:
        return json.loads(student.timeline_json)
    except json.JSONDecodeError:
        return []


def kanban_columns(applications: list[Application]) -> dict:
    columns = defaultdict(list)
    for application in applications:
        columns[application.status].append(application)
    return columns


def _application_card(application: Application) -> dict:
    student = application.student
    return {
        'application': application,
        'student': student,
        'name': student.full_name,
        'city': student.city,
        'university': student.university,
        'course': student.course,
        'summary': student.summary,
        'match_score': application.match_score,
        'status_key': application.status,
        'status_label': STATUS_TITLES.get(application.status, application.status),
        'note': application.hr_private_note or application.note or 'Без заметок',
        'skills': [tag.name for tag in student.skills[:4]],
        'profile_url': student.github_url or student.portfolio_url or '',
        'updated_at': application.updated_at,
    }


def _event_card(registration: EventRegistration) -> dict:
    student = registration.student
    return {
        'registration': registration,
        'student': student,
        'name': student.full_name,
        'city': student.city,
        'university': student.university,
        'course': student.course,
        'summary': student.summary,
        'status_key': registration.status,
        'status_label': EVENT_STATUS_TITLES.get(registration.status, registration.status),
        'note': registration.note or 'Без комментария',
        'skills': [tag.name for tag in student.skills[:4]],
        'profile_url': student.github_url or student.portfolio_url or '',
        'created_at': registration.created_at,
    }


def recruitment_board_for_opportunity(opportunity: Opportunity | None) -> list[dict]:
    if not opportunity:
        return []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for application in sorted(opportunity.applications, key=lambda item: (item.status, -item.match_score, item.created_at)):
        grouped[application.status].append(_application_card(application))

    board = []
    for status in APPLICATION_BOARD_ORDER:
        cards = sorted(grouped.get(status, []), key=lambda item: (-item['match_score'], item['name']))
        board.append({
            'key': status,
            'title': STATUS_TITLES.get(status, status),
            'count': len(cards),
            'cards': cards,
        })
    return board


def recruitment_board_for_event(event: Event | None) -> list[dict]:
    if not event:
        return []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for registration in sorted(event.registrations, key=lambda item: (item.status, item.created_at)):
        grouped[registration.status].append(_event_card(registration))

    board = []
    for status in EVENT_BOARD_ORDER:
        cards = sorted(grouped.get(status, []), key=lambda item: (item['city'], item['name']))
        board.append({
            'key': status,
            'title': EVENT_STATUS_TITLES.get(status, status),
            'count': len(cards),
            'cards': cards,
        })
    return board


def employer_candidate_overview(opportunity: Opportunity | None) -> list[dict]:
    if not opportunity:
        return []
    ordered = sorted(opportunity.applications, key=lambda x: x.match_score, reverse=True)
    return [
        {
            'application': app,
            'student': app.student,
            'status': STATUS_TITLES.get(app.status, app.status),
            'match_score': app.match_score,
            'note': app.hr_private_note or 'Без заметок',
        }
        for app in ordered
    ]


def employer_event_overview(event: Event | None) -> list[dict]:
    if not event:
        return []
    ordered = sorted(event.registrations, key=lambda x: x.created_at, reverse=True)
    return [
        {
            'registration': registration,
            'student': registration.student,
            'status': EVENT_STATUS_TITLES.get(registration.status, registration.status),
            'note': registration.note or 'Без заметок',
            'created_at': registration.created_at,
        }
        for registration in ordered
    ]


def employer_activity_summary(opportunities: list[Opportunity], events: list[Event]) -> dict:
    applications = [application for opportunity in opportunities for application in opportunity.applications]
    registrations = [registration for event in events for registration in event.registrations]
    active_hiring = sum(1 for item in applications if item.status in {'applied', 'invited', 'approved', 'offer'})
    approved_people = sum(1 for item in applications if item.status in {'approved', 'offer'})
    approved_events = sum(1 for item in registrations if item.status in {'approved', 'attended'})
    unique_cities = sorted({item.student.city for item in applications} | {item.student.city for item in registrations})
    return {
        'applications_total': len(applications),
        'registrations_total': len(registrations),
        'active_hiring': active_hiring,
        'approved_people': approved_people,
        'approved_events': approved_events,
        'unique_cities': unique_cities,
    }


def analytics_payload(opportunities: list[Opportunity], events: list[Event]) -> dict:
    by_type = Counter(item.opportunity_type for item in opportunities)
    by_type['event'] = len(events)
    by_city = Counter(item.city for item in opportunities)
    by_city.update(item.city for item in events)
    by_skill = Counter()
    for item in opportunities:
        by_skill.update(tag.name for tag in item.tags)
    for item in events:
        by_skill.update(tag.name for tag in item.tags)
    return {
        'by_type': dict(by_type),
        'by_city': dict(by_city),
        'top_skills': dict(by_skill.most_common(8)),
    }


def normalize_domain(value: str | None) -> str:
    if not value:
        return ''
    cleaned = value.strip().lower()
    if '@' in cleaned and '://' not in cleaned:
        return cleaned.split('@')[-1]
    if '://' not in cleaned:
        cleaned = f'https://{cleaned}'
    parsed = urlparse(cleaned)
    host = parsed.netloc.lower().replace('www.', '')
    return host


def company_team_members(profile: EmployerProfile) -> list[EmployerProfile]:
    if not profile.company_inn:
        return [profile]
    return EmployerProfile.query.filter_by(company_inn=profile.company_inn).order_by(EmployerProfile.hr_status.desc(), EmployerProfile.created_at.asc()).all()


def approved_company_members(profile: EmployerProfile) -> list[EmployerProfile]:
    return [member for member in company_team_members(profile) if member.hr_status in {'owner', 'approved'}]


def company_member_ids(profile: EmployerProfile) -> list[int]:
    return [member.id for member in approved_company_members(profile)]


def can_auto_link_company(existing_profile: EmployerProfile | None, work_email: str, website: str) -> bool:
    if not existing_profile:
        return False
    email_domain = normalize_domain(work_email)
    known_domains = {normalize_domain(existing_profile.website)}
    if existing_profile.verification:
        known_domains.add(normalize_domain(existing_profile.verification.corporate_email))
    known_domains.add(normalize_domain(website))
    return bool(email_domain and email_domain in known_domains)


def extract_github_username(github_url: str | None) -> str:
    if not github_url:
        return ''
    value = github_url.strip()
    if not value:
        return ''
    if 'github.com' not in value:
        return ''
    path = urlparse(value if '://' in value else f'https://{value}').path.strip('/')
    if not path:
        return ''
    return path.split('/')[0]


def _github_headers() -> dict:
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'tramplin-app',
    }
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


@lru_cache(maxsize=128)
def _github_json(url: str):
    request = Request(url, headers=_github_headers())
    with urlopen(request, timeout=4) as response:
        return json.loads(response.read().decode('utf-8'))


def _github_fetch_enabled() -> bool:
    if has_app_context():
        return current_app.config.get('GITHUB_FETCH_ENABLED', True)
    return True


def github_profile_payload(student: StudentProfile) -> dict | None:
    username = extract_github_username(student.github_url)
    if not username:
        return None

    payload = {
        'username': username,
        'profile_url': student.github_url,
        'repo_cards': [],
        'summary': 'Профиль подключен.',
        'sync_label': 'GitHub подключен',
    }

    if not _github_fetch_enabled():
        payload['sync_label'] = 'GitHub подключен без онлайн-синхронизации'
        return payload

    try:
        profile = _github_json(f'https://api.github.com/users/{username}')
        repositories = _github_json(
            f'https://api.github.com/users/{username}/repos?sort=updated&per_page=12&type=owner'
        )
    except (HTTPError, URLError, TimeoutError, ValueError):
        payload['sync_label'] = 'GitHub подключен, репозитории не загрузились'
        return payload

    real_repositories = [repo for repo in repositories if not repo.get('fork') and not repo.get('private')]
    real_repositories.sort(
        key=lambda repo: (
            int(repo.get('stargazers_count') or 0),
            int(repo.get('forks_count') or 0),
            repo.get('updated_at') or '',
        ),
        reverse=True,
    )

    payload['summary'] = profile.get('bio') or 'Публичный GitHub-профиль подключен.'
    payload['sync_label'] = 'GitHub синхронизирован'
    payload['avatar_url'] = profile.get('avatar_url') or ''
    payload['repo_cards'] = [
        {
            'name': repo.get('full_name') or repo.get('name') or username,
            'description': repo.get('description') or 'Описание не заполнено.',
            'stars': int(repo.get('stargazers_count') or 0),
            'language': repo.get('language') or '—',
            'url': repo.get('html_url') or student.github_url,
        }
        for repo in real_repositories[:3]
    ]
    return payload
