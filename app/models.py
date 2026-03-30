from __future__ import annotations

from datetime import datetime, date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

opportunity_tags = db.Table(
    'opportunity_tags',
    db.Column('opportunity_id', db.Integer, db.ForeignKey('opportunity.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True),
)

event_tags = db.Table(
    'event_tags',
    db.Column('event_id', db.Integer, db.ForeignKey('event.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True),
)

student_tags = db.Table(
    'student_tags',
    db.Column('student_profile_id', db.Integer, db.ForeignKey('student_profile.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True),
)

contact_links = db.Table(
    'contact_links',
    db.Column('student_id', db.Integer, db.ForeignKey('student_profile.id'), primary_key=True),
    db.Column('contact_id', db.Integer, db.ForeignKey('student_profile.id'), primary_key=True),
)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class User(UserMixin, TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(30), nullable=False)  # student, employer, curator
    is_active_account = db.Column(db.Boolean, default=True)
    is_banned = db.Column(db.Boolean, default=False)

    student_profile = db.relationship('StudentProfile', back_populates='user', uselist=False)
    employer_profile = db.relationship('EmployerProfile', back_populates='user', uselist=False)
    curator_profile = db.relationship('CuratorProfile', back_populates='user', uselist=False)
    registration_flow = db.relationship('RegistrationFlow', back_populates='user', uselist=False, cascade='all, delete-orphan')


class Tag(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    category = db.Column(db.String(40), nullable=False, default='skill')


class StudentProfile(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    full_name = db.Column(db.String(180), nullable=False)
    university = db.Column(db.String(180), nullable=False)
    graduation_year = db.Column(db.Integer, nullable=False)
    course = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    github_url = db.Column(db.String(255))
    portfolio_url = db.Column(db.String(255))
    privacy_mode = db.Column(db.String(30), default='networking')
    active_search = db.Column(db.Boolean, default=True)
    radar_hard = db.Column(db.Integer, default=70)
    radar_data = db.Column(db.Integer, default=60)
    radar_soft = db.Column(db.Integer, default=75)
    radar_leadership = db.Column(db.Integer, default=55)
    gamification_points = db.Column(db.Integer, default=0)
    timeline_json = db.Column(db.Text, nullable=False, default='[]')

    user = db.relationship('User', back_populates='student_profile')
    skills = db.relationship('Tag', secondary=student_tags, lazy='joined')
    applications = db.relationship('Application', back_populates='student', cascade='all, delete-orphan')
    event_registrations = db.relationship('EventRegistration', back_populates='student', cascade='all, delete-orphan')
    contacts = db.relationship(
        'StudentProfile',
        secondary=contact_links,
        primaryjoin=id == contact_links.c.student_id,
        secondaryjoin=id == contact_links.c.contact_id,
        lazy='joined',
    )


class EmployerProfile(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    company_name = db.Column(db.String(180), nullable=False)
    legal_name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    website = db.Column(db.String(255))
    socials = db.Column(db.String(255))
    city = db.Column(db.String(80), nullable=False)
    industry = db.Column(db.String(120), nullable=False)
    office_address = db.Column(db.String(255))
    cover_url = db.Column(db.String(255))
    office_photo_url = db.Column(db.String(255))
    verified_badge = db.Column(db.Boolean, default=False)
    company_inn = db.Column(db.String(12), default='')
    hr_title = db.Column(db.String(120), default='HR manager')
    hr_status = db.Column(db.String(30), default='owner')

    user = db.relationship('User', back_populates='employer_profile')
    opportunities = db.relationship('Opportunity', back_populates='employer', cascade='all, delete-orphan')
    events = db.relationship('Event', back_populates='employer', cascade='all, delete-orphan')
    verification = db.relationship('CompanyVerification', back_populates='employer', uselist=False)


class CuratorProfile(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    title = db.Column(db.String(120), nullable=False)
    organization = db.Column(db.String(180), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False)

    user = db.relationship('User', back_populates='curator_profile')


class Opportunity(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('employer_profile.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    opportunity_type = db.Column(db.String(30), nullable=False)
    work_format = db.Column(db.String(30), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    address = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    salary_min = db.Column(db.Integer, default=0)
    salary_max = db.Column(db.Integer, default=0)
    employment_type = db.Column(db.String(40), default='full-time')
    level = db.Column(db.String(40), default='Intern')
    published_on = db.Column(db.Date, default=date.today)
    expires_on = db.Column(db.Date)
    starts_on = db.Column(db.Date)
    is_published = db.Column(db.Boolean, default=True)
    moderation_status = db.Column(db.String(30), default='approved')

    employer = db.relationship('EmployerProfile', back_populates='opportunities')
    tags = db.relationship('Tag', secondary=opportunity_tags, lazy='joined')
    applications = db.relationship('Application', back_populates='opportunity', cascade='all, delete-orphan')


class Event(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('employer_profile.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    event_format = db.Column(db.String(30), nullable=False, default='offline')
    city = db.Column(db.String(80), nullable=False)
    address = db.Column(db.String(255))
    venue_name = db.Column(db.String(180), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    registration_deadline = db.Column(db.Date, nullable=False)
    capacity = db.Column(db.Integer, default=0)
    target_audience = db.Column(db.String(180), nullable=False, default='Студенты и выпускники')
    speaker_name = db.Column(db.String(180), nullable=False, default='Команда работодателя')
    registration_url = db.Column(db.String(255))
    contact_email = db.Column(db.String(255))
    participation_cost = db.Column(db.String(80), nullable=False, default='Бесплатно')
    is_published = db.Column(db.Boolean, default=True)
    moderation_status = db.Column(db.String(30), default='approved')

    employer = db.relationship('EmployerProfile', back_populates='events')
    tags = db.relationship('Tag', secondary=event_tags, lazy='joined')
    registrations = db.relationship('EventRegistration', back_populates='event', cascade='all, delete-orphan')


class Application(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_profile.id'), nullable=False)
    opportunity_id = db.Column(db.Integer, db.ForeignKey('opportunity.id'), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='wishlist')
    match_score = db.Column(db.Integer, default=0)
    note = db.Column(db.Text, default='')
    hr_private_note = db.Column(db.Text, default='')

    student = db.relationship('StudentProfile', back_populates='applications')
    opportunity = db.relationship('Opportunity', back_populates='applications')


class EventRegistration(TimestampMixin, db.Model):
    __table_args__ = (
        db.UniqueConstraint('student_id', 'event_id', name='uq_student_event_registration'),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student_profile.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='registered')
    note = db.Column(db.Text, default='')

    student = db.relationship('StudentProfile', back_populates='event_registrations')
    event = db.relationship('Event', back_populates='registrations')


class CompanyVerification(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey('employer_profile.id'), nullable=False, unique=True)
    corporate_email = db.Column(db.String(255), nullable=False)
    inn = db.Column(db.String(12), nullable=False)
    verification_level = db.Column(db.Integer, default=1)
    legal_status = db.Column(db.String(80), default='На проверке')
    verified_at = db.Column(db.DateTime)

    employer = db.relationship('EmployerProfile', back_populates='verification')


class RegistrationFlow(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    contact_email = db.Column(db.String(255), nullable=False)
    flow_type = db.Column(db.String(40), nullable=False, default='telegram_bot_email')
    verification_code = db.Column(db.String(64), nullable=False, unique=True, index=True)
    telegram_username = db.Column(db.String(120))
    bot_name = db.Column(db.String(120), nullable=False, default='tramplin_verify_bot')
    status = db.Column(db.String(30), nullable=False, default='pending')
    applicant_email_sent_at = db.Column(db.DateTime)
    admin_email_sent_at = db.Column(db.DateTime)
    bot_confirmed_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text, default='')

    user = db.relationship('User', back_populates='registration_flow')


class ModerationQueue(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(180), nullable=False)
    submitted_by = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(30), default='pending')
    rejection_reason = db.Column(db.Text, default='')
