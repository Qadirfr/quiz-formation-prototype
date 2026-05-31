-- Supabase / PostgreSQL schema for the future online version.
-- Run this in Supabase SQL Editor when moving away from local SQLite.
-- This schema mirrors the current prototype tables as closely as possible.

create table if not exists learners (
    id bigserial primary key,
    name text not null,
    email text not null unique,
    group_name text,
    created_at timestamptz not null default now()
);

create table if not exists saved_quizzes (
    id bigserial primary key,
    title text not null,
    module text,
    difficulty text,
    question_count integer not null default 0,
    quiz_json jsonb not null,
    source_preview text,
    created_at timestamptz not null default now()
);

create table if not exists quiz_attempts (
    id bigserial primary key,
    learner_id bigint not null references learners(id) on delete cascade,
    quiz_id bigint,
    quiz_title text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    score numeric not null default 0,
    max_score numeric not null default 0,
    percentage numeric not null default 0,
    recommended_level text,
    manual_count integer not null default 0
);

create table if not exists learner_answers (
    id bigserial primary key,
    attempt_id bigint not null references quiz_attempts(id) on delete cascade,
    question_index integer not null,
    question_type text,
    question_text text,
    user_answer_json jsonb,
    correct_answer_json jsonb,
    is_correct boolean,
    score numeric not null default 0,
    domain text,
    subdomain text,
    learning_objective text,
    concept_evaluated text,
    cognitive_level text,
    competency text,
    explanation text,
    selected_feedback text,
    correct_feedback text,
    remediation text,
    created_at timestamptz not null default now()
);

create table if not exists question_bank (
    id bigserial primary key,
    question_hash text not null unique,
    source_quiz_id bigint,
    source_quiz_title text,
    question_type text,
    domain text,
    subdomain text,
    difficulty text,
    cognitive_level text,
    competency text,
    concept_evaluated text,
    question_text text not null,
    question_json jsonb not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists training_sessions (
    id bigserial primary key,
    title text not null,
    access_code text not null unique,
    mode text not null default 'directed',
    source text,
    status text not null default 'waiting',
    current_question_index integer not null default 0,
    show_correction boolean not null default false,
    questions_json jsonb not null,
    created_at timestamptz not null default now(),
    closed_at timestamptz
);

create table if not exists session_participants (
    id bigserial primary key,
    session_id bigint not null references training_sessions(id) on delete cascade,
    learner_id bigint not null references learners(id) on delete cascade,
    joined_at timestamptz not null default now(),
    unique(session_id, learner_id)
);

create table if not exists session_answers (
    id bigserial primary key,
    session_id bigint not null references training_sessions(id) on delete cascade,
    participant_id bigint not null references session_participants(id) on delete cascade,
    learner_id bigint not null references learners(id) on delete cascade,
    question_index integer not null,
    question_type text,
    question_text text,
    user_answer_json jsonb,
    correct_answer_json jsonb,
    is_correct boolean,
    score numeric not null default 0,
    selected_feedback text,
    correct_feedback text,
    answered_at timestamptz not null default now(),
    unique(session_id, participant_id, question_index)
);

create index if not exists idx_learners_email on learners(email);
create index if not exists idx_quiz_attempts_learner_id on quiz_attempts(learner_id);
create index if not exists idx_learner_answers_attempt_id on learner_answers(attempt_id);
create index if not exists idx_question_bank_domain on question_bank(domain);
create index if not exists idx_question_bank_active on question_bank(is_active);
create index if not exists idx_training_sessions_access_code on training_sessions(access_code);
create index if not exists idx_session_answers_session_question on session_answers(session_id, question_index);

-- Important security note:
-- For a first server-side Streamlit deployment, keep Supabase Row Level Security disabled
-- or use service-side credentials only. For a public multi-tenant SaaS version, design proper RLS policies.
