-- Durable state for staged, background evaluation batches.
-- Run this migration in the Supabase SQL editor before enabling batch uploads.

create extension if not exists pgcrypto;

create table if not exists public.evaluation_batches (
    id uuid primary key default gen_random_uuid(),
    owner_email text,
    guest_token_hash text,
    requester_ip_hash text not null,
    question_path text not null,
    question_filename text not null,
    question_uploaded boolean not null default false,
    answer_key_path text,
    answer_key_filename text,
    answer_key_uploaded boolean not null default false,
    total_sheets integer not null check (total_sheets between 1 and 60),
    status text not null default 'draft' check (
        status in ('draft', 'queued', 'processing', 'completed', 'partial', 'failed')
    ),
    completed_count integer not null default 0,
    failed_count integer not null default 0,
    last_error text,
    worker_id text,
    claim_token text,
    heartbeat_at timestamptz,
    lease_expires_at timestamptz,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    constraint evaluation_batches_owner_check check (
        (owner_email is not null) <> (guest_token_hash is not null)
    ),
    constraint evaluation_batches_counts_check check (
        completed_count >= 0 and failed_count >= 0
    )
);

create table if not exists public.batch_evaluations (
    id uuid primary key default gen_random_uuid(),
    batch_id uuid not null references public.evaluation_batches(id) on delete cascade,
    client_file_id text not null,
    answer_path text not null,
    answer_filename text not null,
    uploaded boolean not null default false,
    status text not null default 'pending' check (
        status in ('pending', 'processing', 'completed', 'failed')
    ),
    attempts integer not null default 0,
    score integer,
    max_marks integer,
    feedback text,
    question_text text,
    student_answer text,
    answer_key text,
    answer_visibility jsonb not null default '[]'::jsonb,
    failure_message text,
    claim_token text,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    updated_at timestamptz not null default now(),
    constraint batch_evaluations_attempts_check check (attempts >= 0),
    constraint batch_evaluations_max_marks_check check (max_marks is null or max_marks > 0),
    constraint batch_evaluations_score_check check (
        score is null or (max_marks is not null and score between 0 and max_marks)
    ),
    unique (batch_id, client_file_id)
);

create index if not exists evaluation_batches_owner_created_idx
    on public.evaluation_batches (owner_email, created_at desc);
create index if not exists evaluation_batches_queue_idx
    on public.evaluation_batches (status, created_at);
create index if not exists evaluation_batches_requester_idx
    on public.evaluation_batches (requester_ip_hash, created_at desc);
create index if not exists batch_evaluations_batch_created_idx
    on public.batch_evaluations (batch_id, created_at);

create or replace function public.set_batch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists evaluation_batches_updated_at on public.evaluation_batches;
create trigger evaluation_batches_updated_at
before update on public.evaluation_batches
for each row execute function public.set_batch_updated_at();

drop trigger if exists batch_evaluations_updated_at on public.batch_evaluations;
create trigger batch_evaluations_updated_at
before update on public.batch_evaluations
for each row execute function public.set_batch_updated_at();

-- The web process and worker use the server-only Supabase key. No browser role
-- is granted access to these tables because guest access is checked by Flask.
alter table public.evaluation_batches enable row level security;
alter table public.batch_evaluations enable row level security;

insert into storage.buckets (id, name, public)
values ('evaluation-batches', 'evaluation-batches', false)
on conflict (id) do update set public = false;

create or replace function public.claim_evaluation_batch(
    p_worker_id text,
    p_lease_seconds integer default 900
)
returns setof public.evaluation_batches
language plpgsql
security definer
set search_path = public
as $$
declare
    claimed_batch_id uuid;
    new_claim_token text;
begin
    select b.id
    into claimed_batch_id
    from public.evaluation_batches as b
    where b.status = 'queued'
       or (
           b.status = 'processing'
           and coalesce(b.lease_expires_at, to_timestamp(0)) < now()
       )
    order by b.created_at
    for update skip locked
    limit 1;

    if not found then
        return;
    end if;

    new_claim_token := gen_random_uuid()::text;
    update public.evaluation_batches as b
    set status = 'processing',
        worker_id = p_worker_id,
        claim_token = new_claim_token,
        started_at = coalesce(b.started_at, now()),
        heartbeat_at = now(),
        lease_expires_at = now() + make_interval(secs => greatest(p_lease_seconds, 60)),
        last_error = null
    where b.id = claimed_batch_id;

    -- A restarted worker may inherit rows left in processing. Give every
    -- unfinished row the new fence before the worker starts evaluating.
    update public.batch_evaluations as e
    set status = 'pending',
        claim_token = new_claim_token,
        started_at = null,
        updated_at = now()
    where e.batch_id = claimed_batch_id
      and e.status in ('pending', 'processing');

    return query
    select b.*
    from public.evaluation_batches as b
    where b.id = claimed_batch_id;
end;
$$;

revoke execute on function public.claim_evaluation_batch(text, integer) from public, anon, authenticated;
grant execute on function public.claim_evaluation_batch(text, integer) to service_role;
