--
-- PostgreSQL database dump
--

\restrict P6EdF1tqrKdR81IHsqwREd9WMa6ljgMm1FcfgvAd4xThsV0MmdZNR4mcVKoOPTs

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: attendance_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.attendance_status AS ENUM (
    'present',
    'absent',
    'half_day',
    'leave',
    'holiday',
    'weekend'
);


ALTER TYPE public.attendance_status OWNER TO wms;

--
-- Name: calendar_event_type; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.calendar_event_type AS ENUM (
    'holiday',
    'event',
    'cdc_holiday',
    'natural_hazard',
    'working_day'
);


ALTER TYPE public.calendar_event_type OWNER TO wms;

--
-- Name: day_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.day_status AS ENUM (
    'on_duty',
    'half_day',
    'on_leave',
    'wfh',
    'permission',
    'comp_off',
    'office'
);


ALTER TYPE public.day_status OWNER TO wms;

--
-- Name: deliverable_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.deliverable_status AS ENUM (
    'pending',
    'in_progress',
    'completed'
);


ALTER TYPE public.deliverable_status OWNER TO wms;

--
-- Name: employee_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.employee_status AS ENUM (
    'active',
    'on_leave',
    'exited'
);


ALTER TYPE public.employee_status OWNER TO wms;

--
-- Name: export_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.export_status AS ENUM (
    'pending',
    'running',
    'success',
    'failed'
);


ALTER TYPE public.export_status OWNER TO wms;

--
-- Name: export_type; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.export_type AS ENUM (
    'attendance',
    'project',
    'employee',
    'project_mandays'
);


ALTER TYPE public.export_type OWNER TO wms;

--
-- Name: leave_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.leave_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'cancelled'
);


ALTER TYPE public.leave_status OWNER TO wms;

--
-- Name: leave_type; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.leave_type AS ENUM (
    'casual',
    'sick',
    'annual',
    'comp_off',
    'unpaid',
    'other'
);


ALTER TYPE public.leave_type OWNER TO wms;

--
-- Name: project_member_role; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.project_member_role AS ENUM (
    'lead',
    'member',
    'team_lead',
    'contributor',
    'qc'
);


ALTER TYPE public.project_member_role OWNER TO wms;

--
-- Name: project_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.project_status AS ENUM (
    'planning',
    'active',
    'on_hold',
    'completed',
    'archived'
);


ALTER TYPE public.project_status OWNER TO wms;

--
-- Name: task_priority; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.task_priority AS ENUM (
    'low',
    'medium',
    'high'
);


ALTER TYPE public.task_priority OWNER TO wms;

--
-- Name: task_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.task_status AS ENUM (
    'open',
    'in_progress',
    'completed',
    'cancelled'
);


ALTER TYPE public.task_status OWNER TO wms;

--
-- Name: user_role; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.user_role AS ENUM (
    'admin',
    'manager',
    'employee',
    'viewer',
    'project_manager'
);


ALTER TYPE public.user_role OWNER TO wms;

--
-- Name: work_location; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.work_location AS ENUM (
    'hyderabad',
    'chennai',
    'qatar'
);


ALTER TYPE public.work_location OWNER TO wms;

--
-- Name: work_report_status; Type: TYPE; Schema: public; Owner: wms
--

CREATE TYPE public.work_report_status AS ENUM (
    'draft',
    'submitted',
    'approved',
    'rejected',
    'granted'
);


ALTER TYPE public.work_report_status OWNER TO wms;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_master; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.activity_master (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    parent_id uuid,
    code text,
    name text NOT NULL,
    level character varying(20) NOT NULL,
    benchmark_type character varying(20),
    benchmark_value numeric(10,2),
    benchmark_period_days integer,
    benchmark_unit_note text,
    benchmark_remarks text,
    relevant_count_field character varying(20),
    is_active boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT activity_master_benchmark_type_valid CHECK (((benchmark_type IS NULL) OR ((benchmark_type)::text = ANY ((ARRAY['NUMERIC'::character varying, 'TASK_BASED'::character varying])::text[])))),
    CONSTRAINT activity_master_level_valid CHECK (((level)::text = ANY ((ARRAY['activity'::character varying, 'sub_activity'::character varying])::text[]))),
    CONSTRAINT activity_master_no_self_parent CHECK (((parent_id IS NULL) OR (parent_id <> id))),
    CONSTRAINT activity_master_numeric_requires_count_field CHECK ((((benchmark_type)::text <> 'NUMERIC'::text) OR (relevant_count_field IS NOT NULL))),
    CONSTRAINT activity_master_numeric_requires_value CHECK ((((benchmark_type)::text <> 'NUMERIC'::text) OR (benchmark_value IS NOT NULL))),
    CONSTRAINT activity_master_relevant_count_field_valid CHECK (((relevant_count_field IS NULL) OR ((relevant_count_field)::text = ANY ((ARRAY['tags'::character varying, 'docs'::character varying, 'bom'::character varying, 'spares'::character varying])::text[]))))
);


ALTER TABLE public.activity_master OWNER TO wms;

--
-- Name: activity_types; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.activity_types (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(10),
    name character varying(200) NOT NULL,
    category character varying(30) DEFAULT 'GENERAL'::character varying NOT NULL,
    requires_project boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    group_name text
);


ALTER TABLE public.activity_types OWNER TO wms;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO wms;

--
-- Name: attendance_records; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.attendance_records (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id uuid NOT NULL,
    attendance_date date NOT NULL,
    check_in_at timestamp with time zone,
    check_out_at timestamp with time zone,
    total_minutes integer DEFAULT 0 NOT NULL,
    overtime_minutes integer DEFAULT 0 NOT NULL,
    status public.attendance_status NOT NULL,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attendance_minutes_nonneg CHECK (((total_minutes >= 0) AND (overtime_minutes >= 0))),
    CONSTRAINT attendance_out_after_in CHECK (((check_out_at IS NULL) OR (check_in_at IS NULL) OR (check_out_at >= check_in_at)))
);


ALTER TABLE public.attendance_records OWNER TO wms;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.audit_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    actor_user_id uuid,
    actor_email character varying(320),
    actor_role character varying(50),
    action character varying(100) NOT NULL,
    entity_type character varying(100),
    entity_id uuid,
    status character varying(20) DEFAULT 'success'::character varying NOT NULL,
    ip_address character varying(45),
    user_agent text,
    details jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public.audit_logs OWNER TO wms;

--
-- Name: company_calendar_events; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.company_calendar_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    event_date date NOT NULL,
    title character varying(200) NOT NULL,
    event_type public.calendar_event_type DEFAULT 'holiday'::public.calendar_event_type NOT NULL,
    description text,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.company_calendar_events OWNER TO wms;

--
-- Name: daily_work_reports; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.daily_work_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id uuid NOT NULL,
    report_date date NOT NULL,
    status public.work_report_status DEFAULT 'draft'::public.work_report_status NOT NULL,
    summary text,
    total_minutes integer DEFAULT 0 NOT NULL,
    submitted_at timestamp with time zone,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    review_note text,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    day_status public.day_status,
    location public.work_location,
    remarks text,
    query_text text,
    well_head_no text,
    pm_plant text,
    task_list_count integer DEFAULT 0,
    task_list_op_count integer DEFAULT 0,
    maintenance_item_count integer DEFAULT 0,
    maintenance_plan_count integer DEFAULT 0,
    edit_requested_at timestamp with time zone,
    edit_request_note text,
    CONSTRAINT work_reports_total_minutes_range CHECK (((total_minutes >= 0) AND (total_minutes <= 1440)))
);


ALTER TABLE public.daily_work_reports OWNER TO wms;

--
-- Name: employees; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.employees (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    employee_code text NOT NULL,
    first_name text NOT NULL,
    last_name text NOT NULL,
    work_email public.citext,
    phone text,
    department text,
    designation text,
    manager_id uuid,
    date_of_joining date,
    status public.employee_status DEFAULT 'active'::public.employee_status NOT NULL,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    office_id uuid,
    reporting_pm_id uuid,
    personal_email public.citext,
    CONSTRAINT employees_no_self_manager CHECK (((manager_id IS NULL) OR (manager_id <> id)))
);


ALTER TABLE public.employees OWNER TO wms;

--
-- Name: export_jobs; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.export_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    requested_by uuid NOT NULL,
    export_type public.export_type NOT NULL,
    status public.export_status DEFAULT 'pending'::public.export_status NOT NULL,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    filename text,
    file_data bytea,
    row_count integer,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


ALTER TABLE public.export_jobs OWNER TO wms;

--
-- Name: job_codes; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.job_codes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(30) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.job_codes OWNER TO wms;

--
-- Name: leave_requests; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.leave_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employee_id uuid NOT NULL,
    leave_type public.leave_type NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    reason text,
    status public.leave_status DEFAULT 'pending'::public.leave_status NOT NULL,
    manager_id uuid,
    manager_comment text,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT leave_dates_order CHECK ((end_date >= start_date))
);


ALTER TABLE public.leave_requests OWNER TO wms;

--
-- Name: maintenance_plants; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.maintenance_plants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code text NOT NULL,
    description text,
    planning_plant_id uuid NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.maintenance_plants OWNER TO wms;

--
-- Name: notifications; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    type character varying(100) NOT NULL,
    title character varying(300) NOT NULL,
    message text NOT NULL,
    entity_type character varying(100),
    entity_id uuid,
    is_read boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    target_url text,
    severity character varying(20) DEFAULT 'INFO'::character varying NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT notifications_severity_valid CHECK (((severity)::text = ANY ((ARRAY['INFO'::character varying, 'WARNING'::character varying, 'CRITICAL'::character varying])::text[])))
);


ALTER TABLE public.notifications OWNER TO wms;

--
-- Name: offices; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.offices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying NOT NULL,
    timezone character varying NOT NULL,
    shift_start time without time zone NOT NULL,
    shift_end time without time zone NOT NULL,
    break_minutes integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.offices OWNER TO wms;

--
-- Name: planning_plants; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.planning_plants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code text NOT NULL,
    description text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.planning_plants OWNER TO wms;

--
-- Name: project_activities; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_activities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    activity_type_id uuid,
    activity_type_name text,
    title text NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    assigned_to_id uuid,
    assigned_to_name text,
    target_date date,
    closed_date date,
    remarks text,
    sort_order integer DEFAULT 0 NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT project_activities_status_valid CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'in_progress'::character varying, 'closed'::character varying])::text[])))
);


ALTER TABLE public.project_activities OWNER TO wms;

--
-- Name: project_deliverables; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_deliverables (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    target_date date,
    owner_employee_id uuid,
    status public.deliverable_status DEFAULT 'pending'::public.deliverable_status NOT NULL,
    completion_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_deliverables OWNER TO wms;

--
-- Name: project_managers; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_managers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    user_id uuid NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_managers OWNER TO wms;

--
-- Name: project_members; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_members (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    role public.project_member_role DEFAULT 'member'::public.project_member_role NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_members OWNER TO wms;

--
-- Name: project_planned_date_changes; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_planned_date_changes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    old_date date,
    new_date date,
    changed_by uuid NOT NULL,
    reason text NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_planned_date_changes OWNER TO wms;

--
-- Name: project_submission_items; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_submission_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    submission_id uuid NOT NULL,
    activity_type_id uuid,
    activity_label text NOT NULL,
    quantity integer NOT NULL,
    unit text NOT NULL,
    CONSTRAINT project_submission_items_qty_pos CHECK ((quantity > 0))
);


ALTER TABLE public.project_submission_items OWNER TO wms;

--
-- Name: project_submissions; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    submission_date date NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    notes text,
    submitted_by uuid NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    review_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT project_submissions_period_order CHECK ((period_end >= period_start))
);


ALTER TABLE public.project_submissions OWNER TO wms;

--
-- Name: project_timeline_events; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.project_timeline_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    event_type character varying(50) NOT NULL,
    actor_id uuid,
    actor_name text,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.project_timeline_events OWNER TO wms;

--
-- Name: projects; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code text NOT NULL,
    name text NOT NULL,
    client text,
    description text,
    status public.project_status DEFAULT 'planning'::public.project_status NOT NULL,
    start_date date,
    planned_completion_date date,
    created_by uuid,
    updated_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    job_code_id uuid,
    actual_completion_date date,
    maintenance_plant_id uuid,
    CONSTRAINT projects_dates CHECK (((planned_completion_date IS NULL) OR (start_date IS NULL) OR (planned_completion_date >= start_date)))
);


ALTER TABLE public.projects OWNER TO wms;

--
-- Name: tasks; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    title text NOT NULL,
    description text,
    assigned_to_employee_id uuid NOT NULL,
    assigned_by_employee_id uuid NOT NULL,
    status public.task_status DEFAULT 'open'::public.task_status NOT NULL,
    priority public.task_priority DEFAULT 'medium'::public.task_priority NOT NULL,
    due_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    project_id uuid
);


ALTER TABLE public.tasks OWNER TO wms;

--
-- Name: users; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email public.citext NOT NULL,
    password_hash character varying NOT NULL,
    role public.user_role DEFAULT 'employee'::public.user_role NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT users_email_format CHECK ((email OPERATOR(public.~*) '^[^@\s]+@[^@\s]+\.[^@\s]+$'::public.citext))
);


ALTER TABLE public.users OWNER TO wms;

--
-- Name: work_report_tasks; Type: TABLE; Schema: public; Owner: wms
--

CREATE TABLE public.work_report_tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    report_id uuid NOT NULL,
    project_id uuid NOT NULL,
    description text NOT NULL,
    minutes_spent integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    activity_type text,
    tags_count integer DEFAULT 0 NOT NULL,
    docs_count integer DEFAULT 0 NOT NULL,
    bom_count integer DEFAULT 0 NOT NULL,
    spares_count integer DEFAULT 0 NOT NULL,
    project_name text,
    project_code text,
    project_job_code_code text,
    task_id uuid,
    task_title text,
    task_minutes_spent integer,
    sub_activity_id uuid,
    sub_activity_name text,
    activity_name text,
    benchmark_value_snapshot numeric(10,2),
    benchmark_period_days_snapshot integer,
    benchmark_type_snapshot character varying(20),
    deficit numeric(10,2),
    productivity_pct numeric(6,2),
    completed_date date,
    relevant_count_field_snapshot character varying(20),
    started_date date,
    due_date date,
    is_completed boolean DEFAULT false NOT NULL,
    maintenance_plant_id uuid,
    maintenance_plant_code text,
    maintenance_plant_description text,
    planning_plant_code text,
    planning_plant_description text,
    CONSTRAINT work_report_tasks_minutes_range CHECK (((minutes_spent IS NULL) OR ((minutes_spent >= 0) AND (minutes_spent <= 1440))))
);


ALTER TABLE public.work_report_tasks OWNER TO wms;

--
-- Data for Name: activity_master; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.activity_master (id, parent_id, code, name, level, benchmark_type, benchmark_value, benchmark_period_days, benchmark_unit_note, benchmark_remarks, relevant_count_field, is_active, sort_order, created_by, created_at, updated_at) FROM stdin;
e8028f2a-beb1-47a2-8e22-f179324d82f6	0085ae9c-a74d-446d-b18a-7e18572eb8b2	\N	LEAVE	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
239b13ab-aa86-4d45-9e1a-74c26b00b238	9946150a-426f-4419-9d2e-428e090bcc90	\N	COMPANY HOLIDAY	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8efdb746-307f-4724-8dc7-56f603e67f22	\N	\N	WORK FROM HOME	activity	\N	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
5730596b-0e42-4a57-8cfc-52987b98652b	8efdb746-307f-4724-8dc7-56f603e67f22	\N	WORK FROM HOME	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
71250629-5c09-4f15-8ad4-e4653ccf3ab7	\N	\N	WEEK OFF	activity	\N	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
fc671d14-8c49-4b69-83e6-89c5b8fb20e6	71250629-5c09-4f15-8ad4-e4653ccf3ab7	\N	WEEK OFF	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
2175d74b-ae4e-4bf2-8033-3492a8ccbcad	\N	\N	WORK AT OFFICE	activity	\N	\N	\N	\N	\N	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a5e197af-63e0-4c10-96f3-c9e66011242e	2175d74b-ae4e-4bf2-8033-3492a8ccbcad	\N	WORK AT OFFICE	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f8ae5d1b-9194-4f1e-8536-1268eb4e2e10	\N	\N	COMP-OFF	activity	\N	\N	\N	\N	\N	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a349d0bd-7662-456b-a969-ee61c4e4bd9e	f8ae5d1b-9194-4f1e-8536-1268eb4e2e10	\N	COMP-OFF	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
be647660-2037-4b4f-b743-fc901fca38cb	\N	\N	OVERTIME HOURS-COMPENSATION	activity	\N	\N	\N	\N	\N	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
68015cdb-50ef-4539-afbd-d16cdd972f8e	be647660-2037-4b4f-b743-fc901fca38cb	\N	OVERTIME HOURS-COMPENSATION	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
69af779f-a36e-4b37-a896-d333f99c7e98	\N	\N	OVERTIME HOURS-SALARY	activity	\N	\N	\N	\N	\N	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0e6b2df9-10a6-41dd-b069-6cb1efd88bc3	69af779f-a36e-4b37-a896-d333f99c7e98	\N	OVERTIME HOURS-SALARY	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a635c89a-0c60-42c2-99ae-ddb82794f543	\N	\N	PERMISSION	activity	\N	\N	\N	\N	\N	\N	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
74cf8e53-efa7-419a-834e-b307eb9e92a7	a635c89a-0c60-42c2-99ae-ddb82794f543	\N	PERMISSION-FIRST HALF 1HR	sub_activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
fe540533-14ed-4ccb-b704-3dcb74b34e7d	a635c89a-0c60-42c2-99ae-ddb82794f543	\N	PERMISSION-SECOND HALF 1HR	sub_activity	\N	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
336a1f06-f115-49a3-9310-d03fc615731a	a635c89a-0c60-42c2-99ae-ddb82794f543	\N	PERMISSION-FIRST HALF 2HR	sub_activity	\N	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f89834d8-c52c-4f85-a10a-0389e78d0bf0	a635c89a-0c60-42c2-99ae-ddb82794f543	\N	PERMISSION-SECOND HALF 2HR	sub_activity	\N	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	\N	PROJECT MEETING	activity	\N	\N	\N	\N	\N	\N	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
de0cad92-b14e-40af-9e75-90f24413c268	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-FMTL	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d935a641-1265-48b3-9689-bf49d84d0a71	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-MTL	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
37566e00-a56a-4d50-8025-a1b7cb017420	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-DOC	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
26e3a54d-1228-49fa-81ed-9c6a3a50a0a6	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-BOM	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ebe5a79c-b602-4228-92a0-c6ee4630eedc	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-HIEARCHY	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
230d41d2-4863-4f28-b98c-f77ea9e4dfc8	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-FLOC/EQPT-IDB(PMEQM)	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
4a44d85c-f369-44c3-921e-b654e07e2eb2	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-INITIAL IDB	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
3fbb551f-c766-422f-8658-d4739a3245b4	c9d95f7d-6c44-4766-8193-385d6f7511bf	\N	PROJECT MEETING-WEEKLY/BIWEEKLY	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
44f3d905-5443-46ae-877a-3e04e107ec34	\N	\N	TAG ESTIMATION	activity	\N	\N	\N	\N	\N	\N	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
3b9d0c63-2761-4116-834a-41b402faff97	44f3d905-5443-46ae-877a-3e04e107ec34	\N	TAG ESTIMATION-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
11c9a232-5e85-49a6-a0e8-b4616a05563a	44f3d905-5443-46ae-877a-3e04e107ec34	\N	TAG ESTIMATION-DATA POPULATION	sub_activity	\N	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f1cd503f-e4d4-49e0-ba9e-bbf5a232830a	44f3d905-5443-46ae-877a-3e04e107ec34	\N	TAG ESTIMATION-REWORK	sub_activity	\N	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
4c4174d6-ab12-48b7-9149-26aa3b3ff4d5	44f3d905-5443-46ae-877a-3e04e107ec34	\N	TAG ESTIMATION-QC	sub_activity	\N	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	\N	DEMOLITION	activity	\N	\N	\N	\N	\N	\N	t	11	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8f513dd8-bff6-4cd3-a5f1-c29e7cf6f499	e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	DEMOLITION-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
1f857767-2b93-4ff0-8b1f-888b4df52e07	e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	DEMOLITION-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
c995a378-68d2-491d-bb97-5c4c97529c6f	\N	\N	FMTL	activity	\N	\N	\N	\N	\N	\N	t	12	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	sub_activity	NUMERIC	100.00	1	\N	1DAY	tags	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
7394cca9-e79d-4cce-9b28-826a487702e0	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT	sub_activity	NUMERIC	120.00	1	\N	1DAY	tags	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
efe74235-1b94-4dd8-b262-cc14c93ac76b	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO	sub_activity	NUMERIC	400.00	1	\N	1DAY	tags	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
e90dbc8f-3be5-498b-9a14-b60906b4b483	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL DATA POPULATION- TNR TAG NUMBER	sub_activity	NUMERIC	400.00	1	\N	1DAY	tags	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
6487c55f-7263-46e9-ad35-86beccb1c206	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f101cf7f-a64d-47d7-ab20-561b84aa4918	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-REWORK	sub_activity	NUMERIC	250.00	1	\N	1DAY	tags	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
09879764-9418-466d-a074-e221cd858680	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-QC	sub_activity	NUMERIC	500.00	1	\N	1DAY	tags	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
409e399c-0a5c-43bf-8c81-f2672aa31ae7	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d5420990-0f5f-4db3-8e29-00446b644b04	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
9da188f2-513f-4764-9704-6a5e55aa9889	c995a378-68d2-491d-bb97-5c4c97529c6f	\N	FMTL-PUNCH LIST PREPRATION & SUBMISSION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	\N	MTL	activity	\N	\N	\N	\N	\N	\N	t	13	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d0f4b938-7602-42b6-8056-c0838197f643	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-ASSET PHOTO MERGING	sub_activity	NUMERIC	160.00	1	\N	1DAY	tags	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8d8ee379-b82e-42a3-8033-87b5b6d9dd45	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-ASSET PHOTO DATA POPULATION	sub_activity	NUMERIC	100.00	1	\N	1DAY	tags	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
5f7a6ed8-5c77-4fa9-b792-4d3abb28808c	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-ASSET PHOTO MERGING&DATA POPULATION	sub_activity	NUMERIC	65.00	1	\N	1DAY	tags	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
de7c91f2-e76a-4699-a146-677fedb95ea8	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.SPIR DATA MIGRATION AFTER BOM	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
78d5378e-797d-4cc3-acf9-b704f1622ddb	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.DATASHEET DATA POPULATION	sub_activity	NUMERIC	120.00	1	\N	1DAY	docs	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f705bf71-7353-42f3-bf39-9e41b7e7c079	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.TEST CERTIFCATE DATA POPULATION	sub_activity	NUMERIC	250.00	1	\N	1DAY	docs	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
84994799-bff2-4c0f-a37a-43896185b194	e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	DEMOLITION-REWORK	sub_activity	NUMERIC	250.00	1	\N	1DAY	tags	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
9946150a-426f-4419-9d2e-428e090bcc90	\N	\N	COMPANY HOLIDAY	activity	\N	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-20 04:48:19.426711+00
0085ae9c-a74d-446d-b18a-7e18572eb8b2	\N	\N	LEAVE	activity	\N	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-20 07:29:49.691058+00
4ef25cac-8664-4b4f-8206-0f30e6357ab7	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.O&M MANNUALS DATA POPULATION	sub_activity	TASK_BASED	\N	1	PAGES	500 REQUIRED PAGES/DAY	docs	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
06db67fa-12d0-4a90-a075-8fcef0ad613e	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.CROSS SECTION DATA POPULATION(VALVE SCHEDULE DATA MIGRATION OF  SIZE & MESC CODE)	sub_activity	NUMERIC	250.00	1	\N	1DAY	docs	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
40c321f9-96f7-4bde-8d59-979dc5593d34	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.MATERIAL SUBMITTAL DATA POPULATION	sub_activity	TASK_BASED	\N	1	PAGES	500 REQUIRED PAGES/DAY	docs	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
b7caf102-9e2c-49ca-bccb-8beb5e7d22cd	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-DOC.MRIR/RFI/EPIC DATA POPULATION	sub_activity	TASK_BASED	\N	1	PAGES	40 REQUIRED PAGES/DAY	docs	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
60eb7a27-3dfe-4248-98d3-2e4b8e60a8d4	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-LOGICAL APPROCH-EQPT TYPE &SIZE  FROM UNIQUE SPIR AND UPADTE MAKE	sub_activity	NUMERIC	2000.00	1	\N	1DAY	tags	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
b3d2e8bf-1ad0-4b78-9cdf-9e9e84917ff3	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-E-NAME PLATE CREATION & MERGING WITH ASSET PHOTOGRAPHY	sub_activity	NUMERIC	250.00	1	\N	1DAY	tags	t	11	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
78aa0fd3-9208-4006-8932-593374b19b97	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	12	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d7b15e66-89e0-4126-a327-6372b07e3a38	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-REWORK	sub_activity	NUMERIC	200.00	1	\N	1DAY	tags	t	13	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
76c08c5d-f889-423a-885a-6b7e9a65e010	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-QC	sub_activity	NUMERIC	500.00	1	\N	1DAY	tags	t	14	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a8488db4-0b45-45d7-a45f-929858039d3e	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-PUNCH LIST PREPRATION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	15	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ab1f1436-bbce-467d-a4c1-6781c0b1f4be	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	16	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0d1bc115-95a1-42bc-a2f7-d4f1a1c82307	7b174c00-0d3b-4932-863b-c36b56fa2f95	\N	MTL-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	17	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	\N	HIERARCHY	activity	\N	\N	\N	\N	\N	\N	t	14	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
cb5f67e5-4cec-42fc-a5dd-3b00fa798021	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION MIGRATION OF FMTL DATA	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
6edc8669-d260-4521-9316-f7cb8ba5ad45	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION MIGRATION OF MTL DATA	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a6768fd7-080a-4630-9bd9-e3ebf44601bc	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION DEFAULT VALUE FROM ALL RECORDS	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
3c3941cb-706d-4922-a66d-a15dc3cda5da	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
fa6cbf32-66ca-47b3-8d94-67a8a9471b9f	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
80d4c31c-81e2-4ca7-adda-ed6e806e3135	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	\N	FLOC/EQPT-IDB(PMEQM)	activity	\N	\N	\N	\N	\N	\N	t	15	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d901c1af-665d-423a-b904-5bc1810b7172	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	HIERARCHY DATA POPULATION MIGRATION OF FMTL/MTL DATA	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
6ab7921b-3446-44ba-8c0e-058ab1d97f50	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	FLOC/EQPT-IDB(PMEQM)-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
5e991763-e4e8-47cf-8b07-fd84003024b0	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	FLOC/EQPT-IDB(PMEQM)-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
28b1fdd9-3965-48df-b75e-f2c31d53f7dc	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	FLOC/EQPT-IDB(PMEQM)-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	\N	DOC IDB	activity	\N	\N	\N	\N	\N	\N	t	16	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
574b5630-ba34-452b-8da6-214395b87ab4	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f85a2563-1ee5-4c8b-b33a-81105dc68b37	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)	sub_activity	NUMERIC	1000.00	1	RECORDS	RECORDS 1DAY	docs	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
5b8b575b-ee96-4c8c-a77e-0dd75544dcd2	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-DOC FILE PATH/POPULATION OF DOC.NO/DWG NO/TITLE/DOC.TYPE AND ORGANISING DOC.TYPE FOLDER IF MDR/VDR NOT AVAILABLE	sub_activity	NUMERIC	250.00	1	RECORDS	RECORDS 1DAY	docs	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
34933053-aaad-4e98-a24e-9cd858f9a8ab	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-DOC FILE PATH MIGRATION WITH MDR/VDR AND MANUAL MATCHING	sub_activity	NUMERIC	400.00	1	RECORDS	RECORDS 1DAY	docs	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0258b58a-c7e3-4c5b-92c8-ca361557c010	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-DOC MATRIX WITH FMTL DATA MIGRATION&POPULATION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
946b0523-7fe0-4f74-a6b0-911399d82757	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-TYPE WISE DOC.COLLECTION/SPLITUP AND NAMING/ORGANISING FILES DATA AND POULATION AS PER XL WORKING TEMPLATE	sub_activity	NUMERIC	250.00	1	\N	1DAY	docs	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
7e22abba-5cb4-4196-b442-4bfad492bf98	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-RENAMING THE SPLITUP DOCUMENT AS PER DOC.BANDING NUMBER AND ORGANISING FILES	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
3307f18e-23a3-47a8-95d4-d5d223df9a17	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
1cad4e7a-edbb-4b13-8f21-8cd130092001	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-REWORK	sub_activity	NUMERIC	500.00	1	\N	1DAY	docs	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
e676e118-17e6-4fd5-9551-78df7e60c7c3	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-QC	sub_activity	NUMERIC	500.00	1	\N	1DAY	docs	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
2c2e9ae7-28b2-418a-adb5-43d6c576afc6	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
2dca672f-3934-4d0a-b142-0ae9e8c37cef	b45294d9-814e-4d1c-9db5-0b3dbc40b5fa	\N	DOC IDB-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	11	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
79a4621a-bb10-4329-af54-fef9354e31ce	\N	\N	BOM IDB	activity	\N	\N	\N	\N	\N	\N	t	17	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
261773e7-705b-4064-9825-f7fbd29df9ab	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-ADDRRESSING SPIR DOC AS PER MDR/PUNCH LIST FOR NOT AVAILABLE SPIR	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8c99eca0-58ec-4b6f-9631-0a5992209535	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-EXICUTING SPIR TOOL FOR OUT PUT FILE	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
07dc4fd7-1aee-4f9d-aa70-c4fefe1b3087	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-ADDRESSING TAG AGAINST SPIR REQUIRED DOC(LIKE:LCS/INITIAL/NORMAL)	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
18679613-a8fb-46b4-ab1f-5504bd25c320	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-DATA POULATION(MAT.DESC/ASSIGNING DUMMY MAT.NN/MAT.GROUP/MAT.TYPE/TAG AGAINST SUBMT NUMBER)	sub_activity	NUMERIC	100.00	1	SPARES	100SPARES/DAY	spares	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a6c7915b-9472-4949-a995-4b07a6b59310	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	2	\N	2DAYS	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
64c15e5e-368d-4785-99e4-1b20c5e85147	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-REWORK	sub_activity	NUMERIC	300.00	1	SPARES	300SPARES/DAY	spares	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ef846684-8a05-4213-a721-5036b5537911	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-QC	sub_activity	NUMERIC	500.00	1	SPARES	500SPARES/DAY	spares	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
79845b09-05f9-4b1b-bf6c-64d99b926a87	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-CRS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
88da3940-606c-4767-a429-cbb0af389d77	79a4621a-bb10-4329-af54-fef9354e31ce	\N	BOM IDB-OVS CORRECTION	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8a442361-240f-4a74-a141-3ea688a027cf	\N	\N	PM IDB	activity	\N	\N	\N	\N	\N	\N	t	18	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
52ea6b90-7214-4584-8632-25d0a29cc265	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-ADDRESSING PM REQUIRED TAG	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
073fc79e-4042-4084-9075-fb9294e4ff08	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-ADDRESSING MAITENANCE TYPE PM/IM/SD/CM AND ISOLATION REQUIRED TAG	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a8f11f0a-3c2a-4c46-8bf2-3c234eb386aa	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-ADDRESSING EQUIPMENT TYPE WISE MAKE & MODEL AGAINEST EXITING SAP PM DATA	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
2285ce13-484e-4ef7-84f0-d3cc6a0055f7	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-ADDRESSING FIRE & GAS PM PLAN EITHER ZONE BASED OR OBJECT TYPE BASED	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
cdb734d4-90fd-4a6d-b9f6-cc59cff4657e	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
8490ba2e-fdf5-402e-a658-675441830156	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-QC	sub_activity	TASK_BASED	\N	1	\N	1DAY	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
365237e2-ceb4-4272-af91-111cb54c17ba	\N	\N	INITIAL IDB	activity	\N	\N	\N	\N	\N	\N	t	19	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f45e92df-33e9-40d3-afe0-03e8a6463dba	365237e2-ceb4-4272-af91-111cb54c17ba	\N	INITIAL IDB-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	2	\N	2DAYS	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
878455f6-fe62-4f44-8a63-10da24dd7b52	365237e2-ceb4-4272-af91-111cb54c17ba	\N	INITIAL IDB-REWORK	sub_activity	TASK_BASED	\N	2	\N	2DAYS	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0a4a6326-e882-488e-9cfa-5d99eba14aa0	\N	\N	FINAL IDB	activity	\N	\N	\N	\N	\N	\N	t	20	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
7b2b2534-ec8d-4198-916b-53571125ba6b	0a4a6326-e882-488e-9cfa-5d99eba14aa0	\N	FINAL IDB-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	2	\N	2DAYS	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
e533069f-8eb2-4bb3-9d26-f72e3480f5c1	0a4a6326-e882-488e-9cfa-5d99eba14aa0	\N	FINAL IDB-REWORK	sub_activity	TASK_BASED	\N	2	\N	2DAYS	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	\N	TRAINING	activity	\N	\N	\N	\N	\N	\N	t	21	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
abcb3d43-96d2-498d-b1e9-4dc45e2d89b2	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	MASTERS & REFERENCE FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
fcf02751-256e-49f9-a241-c3a31f912b67	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	DOCUMENT FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
94e3360a-6b08-47bd-9677-c61f042404d6	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	TAG ESTIMATION-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
6b2b785b-aaa1-41c6-8fa8-a57f70335730	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	FMTL-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a009374f-f904-4627-a10b-cb299676062d	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	MTL-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
130d2c9a-125e-4346-87fd-8e533cb569cd	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	BOM-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ee164248-c482-479e-a9a0-4185a19ada39	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	DOC IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
c6aa5fa2-3682-4a92-b2f2-992d0629efde	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	HIERARCHY-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
cb91beff-5cc8-4dba-9e88-7e08cbf914a9	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	PM-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
1741d482-322d-44d4-b5c8-500532ed1702	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	INITIAL IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
f132508a-bf4a-42bb-839d-ae97f93ed79d	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	FINAL IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
63664565-6150-44fe-844d-4e8a0af58533	d74b6c18-5472-4dc8-bbc9-e3e8968149e5	\N	CRITICALITY-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	11	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
25eff746-d71e-418d-951d-8a917e9479d7	\N	\N	TRAINER	activity	\N	\N	\N	\N	\N	\N	t	22	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
22303832-b18a-467f-a6be-db4b77eeb261	25eff746-d71e-418d-951d-8a917e9479d7	\N	MASTERS & REFERENCE FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ef1c4ea7-c7f6-4f27-bc3e-c76103bb0c8d	25eff746-d71e-418d-951d-8a917e9479d7	\N	DOCUMENT FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
53f4d463-27b9-4f4b-bc20-89b7e91ff277	25eff746-d71e-418d-951d-8a917e9479d7	\N	TAG ESTIMATION-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
eb0add81-df74-41b7-b28f-80e974efe6d7	25eff746-d71e-418d-951d-8a917e9479d7	\N	FMTL-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
a2ba166c-93cb-4fe1-b789-6ce1ad404f1c	25eff746-d71e-418d-951d-8a917e9479d7	\N	MTL-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0b179f3c-1b90-4316-b971-148b162564f1	25eff746-d71e-418d-951d-8a917e9479d7	\N	BOM-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
d1372351-16a2-4cde-911e-c2ad7cc4d697	25eff746-d71e-418d-951d-8a917e9479d7	\N	DOC IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
c0d48ba8-3b4f-464b-b017-024afb0ff5b2	25eff746-d71e-418d-951d-8a917e9479d7	\N	HIERARCHY-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
4cbce565-de28-487c-a316-534d67e12c0b	25eff746-d71e-418d-951d-8a917e9479d7	\N	PM-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
89c41778-2636-4378-af3c-6065b9a3cb4e	25eff746-d71e-418d-951d-8a917e9479d7	\N	INITIAL IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	9	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
71a864da-fb75-47bb-801d-62983cfc453f	25eff746-d71e-418d-951d-8a917e9479d7	\N	FINAL IDB-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	10	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
e5d54536-3968-428b-b5eb-9644607c2a88	25eff746-d71e-418d-951d-8a917e9479d7	\N	CRITICALITY-FAMILIARIZATION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	11	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
9020dd7f-46e1-4c5c-a13c-0f08eda553bc	\N	\N	CRITICALITY ANALYSIS	activity	\N	\N	\N	\N	\N	\N	t	23	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
054ec7a6-5a28-4265-9b48-2c045ef2c124	9020dd7f-46e1-4c5c-a13c-0f08eda553bc	\N	CRITICALITY ANALYSIS	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
0bfa6e6a-66b3-41d6-8a91-bc3193b3469f	9020dd7f-46e1-4c5c-a13c-0f08eda553bc	\N	CRITICALITY ANALYSIS-AUDIT QUERY WITH REPORT	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
ee37068d-7a1a-4b88-a113-4c356d2afba9	9020dd7f-46e1-4c5c-a13c-0f08eda553bc	\N	CRITICALITY ANALYSIS-QC	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
29c60578-b2b9-458a-ae55-9b67fc96e684	\N	\N	TOOL DEVELOPER	activity	\N	\N	\N	\N	\N	\N	t	24	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
9595fee3-dbd2-49c6-aa44-8770d49ecbfa	29c60578-b2b9-458a-ae55-9b67fc96e684	\N	SPIR EXTRACTION	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
95a3d906-501e-44ac-b35e-496b7be9de10	29c60578-b2b9-458a-ae55-9b67fc96e684	\N	PRODUCTION REPORT TOOL	sub_activity	TASK_BASED	\N	\N	\N	\N	\N	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 06:34:00.985492+00
15887f99-77f8-4ec6-b42f-9528235c49ac	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-REWORK	sub_activity	NUMERIC	100.00	1	\N	1DAY	tags	t	6	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
d0c4fc8f-7277-4c39-bd64-c1f69c9e7846	8a442361-240f-4a74-a141-3ea688a027cf	\N	PM IDB-DATA POPULATION	sub_activity	NUMERIC	40.00	1	\N	1DAY	tags	t	4	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
29eefd8c-fc11-44f7-88b6-4d88ffa9fcd4	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION TPLNR/TPLMA/POSNR/MSGRP	sub_activity	NUMERIC	150.00	1	\N	1DAY	tags	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
2f423f37-d074-44f2-840c-2fdd4b02a984	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION FIT TO 9LEVEL	sub_activity	NUMERIC	2000.00	1	\N	1DAY	tags	t	5	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
7d50b9e8-0f49-4240-a70a-2e4951db3447	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	FLOC/EQPT-IDB(PMEQM)-QC	sub_activity	NUMERIC	500.00	1	\N	1DAY	tags	t	3	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
9c5e0d5d-c9b8-4e09-965c-a793e79e6669	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY-REWORK	sub_activity	NUMERIC	150.00	\N	\N	\N	tags	t	7	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
a32cc26e-a6f5-47cc-b351-17fc66eacd96	ad1f6242-9ea8-4337-a9a4-3355bf2dffce	\N	FLOC/EQPT-IDB(PMEQM)-REWORK	sub_activity	NUMERIC	300.00	1	\N	1DAY	tags	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
a606e789-4d22-45b4-91b5-95366f46abb3	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY-QC	sub_activity	NUMERIC	250.00	\N	\N	\N	tags	t	8	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
c10269e1-d329-4653-85aa-7c0a2ab463ce	e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	DEMOLITION-QC	sub_activity	NUMERIC	500.00	1	\N	1DAY	tags	t	2	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
ef23e761-636a-4b91-9654-fdbb8c9398e7	ee8393e6-a85d-49fc-8b35-8286255a7fb7	\N	HIERARCHY DATA POPULATION ARBPL/BEBER/STORT	sub_activity	NUMERIC	250.00	1	\N	1DAY	tags	t	1	\N	2026-06-16 06:34:00.985492+00	2026-06-16 09:03:56.1206+00
93ad5a19-931f-4857-bc44-5f2f7da3aae0	e03ee0b2-33bc-403e-a953-dc939f3cc54a	\N	DEMOLITION-DATA POPULATION	sub_activity	NUMERIC	150.00	1	\N	1DAY	tags	t	0	\N	2026-06-16 06:34:00.985492+00	2026-06-20 04:48:34.329034+00
\.


--
-- Data for Name: activity_types; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.activity_types (id, code, name, category, requires_project, is_active, created_by, created_at, updated_at, group_name) FROM stdin;
070df695-4289-436c-8ee0-e5eaf547f32f	400	CRS FMTL	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
09762da0-4034-4547-8a01-84ca2a9bd186	360	PM QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
0b7340de-8e91-487d-878c-c311bb097b76	410	CRS DEMOLITION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
0dfb00ee-0acd-4aea-a742-3711e4e5b2f5	40	LEAVE	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
0f1b9399-826b-41e4-a4ba-f786acd1f406	170	DOC MASTER PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
1d0c856b-a837-4064-8516-a250350ce925	70	COMP-OFF	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
247321ac-cf04-4061-bb20-bc8ceb7ddfec	220	DEMOLITION QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
2927fcd8-c263-48fc-bf16-f7bc83e99088	540	CATALOGUING & ENRICHMENT	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
29835cdb-76d4-4f13-83d1-39c6dedbb09e	20	PROJECT MANAGEMENT	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
2f5f66b8-0190-477f-a47c-7b5d005625ad	520	IDB (FINAL) PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
30b77623-a98f-4603-a2c0-7767411397c2	320	SPIR QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
346ef018-cfa6-4f02-8984-20dafdb1dc3c	60	WORK FROM HOME	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
35be5ba9-9909-4114-82d2-c2721f816fe4	460	CRS PM	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
3bd7596a-d865-4135-ba71-e92689d93a92	80	HOLIDAY	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
3d00f407-42f4-4ac0-af7d-b7fced4ac017	500	IDB (INITIAL) PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
3d92f3c4-45e0-44e4-91bc-0b83b591d8f0	310	SPIR REVIEW	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
471cdda5-601e-463f-b4eb-00b143d957fc	250	ASSET PHOTO QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
473df871-e77b-4986-8b00-527b0a7a01bc	30	PROJECT COORDINATION	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
49ad6984-256c-40d2-a78b-75c6ec0b25b2	440	CRS SPIR	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
4f801622-bad1-4e4d-aa53-3f58b1c8db85	480	CRS IDB (INITIAL)	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
5215af2b-ad95-4220-ab67-e808552c6a91	490	CRS IDB (FINAL)	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
5219aace-ddac-472a-9989-567c9b0dc80f	210	DEMOLITION PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
544ffe16-2b64-41d1-a700-9e1ddbd57f68	280	MTL QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
628aeb6f-d223-4db0-9b4a-580ba48387c6	160	DOC COLLECTION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
62bce1d7-4b8f-4e17-a18e-1108e0aecf65	270	MTL PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
694b47aa-7c47-4f17-8e74-32619341fb6a	290	HIERARCHY PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
75a79edb-0b3a-4f08-83bb-5df982e4151b	390	CRS DOC MASTER	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
7c66bc90-133e-4f18-b932-9c0b00142582	230	PHYSICAL ASSET VERIFICATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
7d3d8800-1a85-461e-9d34-38cd8ba5993e	90	TRAINING/ ORIENTATION	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
367a9521-e9be-426a-be0d-d5f066225539	110	TAG ESTIMATION	TAG_ESTIMATION	f	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:31:47.331464+00	\N
1891a085-11be-44b5-8656-7dbf26b8b288	130	MEETING PROJECT	PROJECT	t	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:33:57.269889+00	\N
05ef3a9d-101e-4485-bccc-dbc065e2f83f	140	MEETING GENERAL	GENERAL	f	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:34:02.926116+00	\N
83c427e3-1653-4b71-b2db-4661057134e7	430	CRS HIERARCHY	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
89812a69-7543-4acd-aaab-581fad74ea10	470	CRS SD	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
89de7024-2843-434b-ba91-4349bd06566a	190	FMTL PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
9477eac8-f033-4694-a28e-597a8ab9a237	510	IDB (INITIAL) QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
9751cc91-bb08-45b4-953d-51dc1bd72553	450	CRS BOM	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
9e704e5e-7d9a-487e-b1ee-817816fe287e	300	HIERARCHY QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
a8b352d6-b41a-46c9-b3e1-3ef136ca3a5a	180	DOC MASTER QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
aec7bc79-be60-472f-8f87-8c53c34ff8b3	50	VACATION	GENERAL	f	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
afa557c3-c7be-4b86-8b20-6d25d9f08f2d	530	IDB (FINAL) QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
b0f82e68-f278-4bb5-8a7d-b895ac6e31bd	200	FMTL QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
b2c945d8-741f-4791-a063-0e3f1755a8dc	240	ASSET PHOTOS UPDATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
c8d54fcb-9113-4399-be67-8b64c0f6526a	350	PM PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
d182539d-c473-4e3e-854e-90be7440a548	340	BOM QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
d538267b-e4ba-4ab8-9c19-50365c0042f8	370	SD LIBRARY PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
d73ea38b-9327-4632-90eb-a91e172da936	330	BOM PREPARATION	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
ed4b817e-3abe-4326-abea-cf27ba894f1d	380	SD LIBRARY QA/QC	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
ef8504a3-fada-48c6-99dc-8e0fa6f5c71a	420	CRS MTL	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
f5bd81bc-1e3e-4406-9da9-0cb5699a8058	260	SITE VALIDATION REPORT	PROJECT	t	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 04:59:56.495715+00	\N
f65123d7-699a-40d0-8451-b4853c110212	999	TEST COMBOBOX ACTIVITY	GENERAL	f	f	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 05:22:30.773036+00	2026-06-04 05:22:30.78872+00	\N
a445e0f3-0ace-4b93-8f54-f926142a6fe7	550	ty	GENERAL	f	f	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 06:08:18.727473+00	2026-06-04 06:24:54.262176+00	\N
f2d640ff-6d91-4750-9f16-c3785b29a9be	150	PLANNING & SCHEDULING	GENERAL	f	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:31:33.098248+00	\N
bcaf6e4a-2649-4e3f-891d-8f258c4d9b14	100	IT SUPPORT	GENERAL	f	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:31:45.650725+00	\N
f8597e82-737b-492a-982b-ca3f4b3fab67	120	PROPOSAL SUPPORT	GENERAL	f	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:31:48.239928+00	\N
c323a1ee-3cda-4cf2-ae6b-2db27bc02aee	10	MEETING PROJECT	PROJECT	t	f	\N	2026-06-04 03:59:32.59002+00	2026-06-16 10:32:23.305757+00	\N
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.alembic_version (version_num) FROM stdin;
0043_task_due_date_assigned_day
\.


--
-- Data for Name: attendance_records; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.attendance_records (id, employee_id, attendance_date, check_in_at, check_out_at, total_minutes, overtime_minutes, status, created_by, updated_by, created_at, updated_at) FROM stdin;
111ddee0-0a70-4de7-9329-886ff07cc34c	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-04	2026-06-04 09:02:00+00	2026-06-04 17:05:00+00	483	3	present	2173ab41-9c1b-4d0c-b100-e69e754116cc	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 05:33:02.462816+00	2026-06-04 05:33:02.462816+00
651b3ab3-3124-4d5b-8d11-4e0efba95750	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-10	2026-06-10 09:06:00+00	2026-06-10 17:39:00+00	513	33	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 09:00:36.646999+00	2026-06-10 09:00:36.646999+00
5a0fe8db-bbf0-4d02-8c20-253f961df2bc	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-10	2026-06-10 08:59:00+00	2026-06-10 17:43:00+00	524	44	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:30:12.167998+00	2026-06-10 10:30:12.167998+00
8431548e-b463-4810-b7f9-4914e24a5307	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-10	2026-06-10 09:05:00+00	2026-06-10 17:40:00+00	515	35	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:30:42.207348+00	2026-06-10 10:30:42.207348+00
63b85e9f-d237-452a-a57e-416741b13bb2	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-09	2026-06-10 09:01:00+00	2026-06-10 18:06:00+00	545	65	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:31:16.231522+00	2026-06-10 10:31:16.231522+00
282cb21f-772f-4cf5-a641-99df87e7308f	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-09	2026-06-10 09:01:00+00	2026-06-10 17:38:00+00	517	37	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:31:49.459045+00	2026-06-10 10:31:49.459045+00
e2253217-f146-4089-8a92-6139fe824bfc	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	2026-06-10	2026-06-10 09:03:00+00	2026-06-10 17:39:00+00	516	36	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:32:37.142551+00	2026-06-10 10:32:37.142551+00
390e912f-bf2b-4f9d-b4cc-dc706c5d374e	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	2026-06-15	2026-06-15 08:54:00+00	2026-06-15 18:01:00+00	547	67	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 10:18:37.888105+00	2026-06-15 10:18:37.888105+00
501956bb-91c9-49e6-b841-8eff0d424903	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-15	\N	\N	480	0	present	\N	\N	2026-06-19 11:58:59.119337+00	2026-06-19 11:58:59.119337+00
0bfdd14c-19c5-4a38-85af-12cf4a1fd407	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-16	\N	\N	480	0	present	\N	\N	2026-06-19 11:58:59.119337+00	2026-06-19 11:58:59.119337+00
4feb47b1-2768-4ca3-8176-482f66aa2b6d	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-17	\N	\N	480	0	present	\N	\N	2026-06-19 11:58:59.119337+00	2026-06-19 11:58:59.119337+00
9ddfb13d-704e-48c8-9d1b-7e8316ef5e62	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-18	\N	\N	480	0	present	\N	\N	2026-06-19 11:58:59.119337+00	2026-06-19 11:58:59.119337+00
ff6a25c5-8384-48ac-b130-29cbe89b064e	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-19	\N	\N	480	0	present	\N	\N	2026-06-19 11:58:59.119337+00	2026-06-19 11:58:59.119337+00
37487366-08c3-4e89-845c-ddcc18707efc	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-19	2026-06-19 09:37:00+00	2026-06-19 17:38:00+00	481	1	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-19 12:03:22.929753+00	2026-06-19 12:03:22.929753+00
cfd94162-ea2b-4962-8deb-4d74ae82d9f7	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	2026-06-20	2026-06-20 09:20:00+00	2026-06-20 18:04:00+00	524	44	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-20 03:54:30.370466+00	2026-06-20 03:54:30.370466+00
0216a5a7-21a9-43a6-8a88-798ac9c9882a	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-20	2026-06-20 09:25:00+00	2026-06-20 18:04:00+00	519	39	present	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-20 03:55:10.492141+00	2026-06-20 03:55:10.492141+00
\.


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.audit_logs (id, created_at, actor_user_id, actor_email, actor_role, action, entity_type, entity_id, status, ip_address, user_agent, details) FROM stdin;
70038435-03c9-4e61-821e-1e744bd774e8	2026-06-06 08:53:08.888088+00	\N	manager@wms.local	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8457	{"reason": "invalid_credentials", "attempted_email": "manager@wms.local"}
74d8d232-cec5-4470-8d60-cca963f8659e	2026-06-06 08:59:58.798195+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0cb46670-6a63-4893-9f95-68ae2c632cd6	2026-06-06 09:00:01.075901+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e451f7a2-277b-42c7-a7c9-3a9d0c8e51bb	2026-06-06 09:08:20.500868+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
4a8c9ab7-3bdf-48d1-9812-e5adb363ec44	2026-06-06 09:08:27.941809+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
aaa79a24-5685-4355-bf0c-9dad3a6fbd20	2026-06-06 09:11:03.3273+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ba0ce682-35fe-49a6-bfa1-153c1d095cf2	2026-06-06 09:11:12.665906+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4643df08-d3b3-4cac-8c60-85ca26ec10a5	2026-06-06 09:12:40.399467+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f9df1756-d4d6-4d15-9ab8-bce5241bb344	2026-06-06 09:12:51.214925+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
29b1b06f-199c-48eb-a1dc-b19fbc8efbf2	2026-06-06 09:20:20.718342+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9e80760e-4901-4909-a6b6-d0f005dcaae2	2026-06-06 09:20:31.287274+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
002fc170-a369-41bb-844b-fa80b22eecce	2026-06-06 09:20:59.986998+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.password.change_self	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c8318c57-6a78-42b4-a9cf-947a81f7a254	2026-06-06 09:21:34.015525+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f928f45c-62e7-4c3c-88c1-568b5eab66fd	2026-06-06 09:21:45.221637+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a186e818-6d0c-4279-b8ac-dab45f6dd4ea	2026-06-06 09:24:32.496375+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
883bdf25-60d9-46e0-8ec3-0b7f1a087b8b	2026-06-06 09:24:55.286428+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.failure	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "emp1@gmail.com"}
c741c1c9-f5c6-4868-bc76-2c8e9464e214	2026-06-06 09:25:02.261933+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
404a6943-523b-4414-b47f-e2a920ea5fcc	2026-06-06 09:26:06.460775+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bc0ba320-8f69-4263-be3a-feb003d1d192	2026-06-06 09:26:15.929223+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5bb999b7-7d95-40fb-9fa1-878617c7f0a1	2026-06-06 09:27:28.560173+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": false, "from": true}
2c017b45-b455-4d9e-9c08-01527603c281	2026-06-06 09:27:30.074373+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": true, "from": false}
77547288-bafa-4874-9b8e-49a5d0615851	2026-06-06 09:27:40.885062+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
8de59c7e-d5c9-4e58-97f6-c4e08b2eed46	2026-06-06 09:29:12.811617+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": false, "from": true}
a9c7dc7b-bd01-40c7-beed-0860757753f8	2026-06-06 09:29:14.10546+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": true, "from": false}
daf7f7bf-9e9a-4144-8c3f-01ed5b4476ce	2026-06-06 09:29:18.217601+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.unlink	employee	3107987e-7e92-4e89-97f3-1d5275e65485	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"user_id": "b9a8554b-4498-4a20-b204-0b5fa4efe7aa"}
b5c0d031-a744-48b0-841e-5ad713d9405e	2026-06-06 09:29:23.827231+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.relink	employee	3107987e-7e92-4e89-97f3-1d5275e65485	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"user_id": "b9a8554b-4498-4a20-b204-0b5fa4efe7aa"}
92b9dd0c-fe9d-4d49-9b1e-039fcfe95202	2026-06-09 03:39:38.220329+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f22b7d69-47ec-4331-9ead-f107f1cabcc6	2026-06-09 03:41:56.65888+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.role_change	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": "team_lead", "from": "qc", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
27efb0b6-2dc8-4727-986c-fef3291c254f	2026-06-09 03:51:26.794291+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f08f18a5-5ce6-40e7-9eaf-a1aab347a648	2026-06-09 03:51:36.939328+00	\N	employee@coreops.local	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "employee@coreops.local"}
8e8ccc01-6605-4fb9-8bbb-0b416c2c3e26	2026-06-09 03:51:44.712868+00	\N	employee@coreops.local	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "employee@coreops.local"}
68e3f911-08e9-485b-8c6b-e99ebb51baca	2026-06-09 03:51:55.688154+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
31deaa2b-ebdb-41c2-b3d7-f2d1367ab349	2026-06-09 03:52:04.887646+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
f906995e-c5ce-4912-b6b0-c8595903b3bb	2026-06-09 03:52:27.635839+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1a8bb1ca-21b1-43ee-be1d-09cd85e0d881	2026-06-09 04:01:14.607255+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f394a44a-7668-4948-b821-44afd0c5f541	2026-06-09 04:01:28.42819+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b4b19449-4656-4691-a40c-dd8dd8823578	2026-06-09 04:06:01.595168+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
013ad509-9257-4aea-83f9-6368d32f9022	2026-06-09 04:06:17.405779+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
5967e172-9103-429a-baf3-e4b982f79232	2026-06-09 04:25:53.879637+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
c0c5a200-c733-4167-9aec-c9fd8fd23bf9	2026-06-09 04:25:57.809595+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
c4dd4723-d96a-42f2-8ef7-0a4772013615	2026-06-09 04:25:59.993878+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
42485794-a0cc-4509-bd42-52eebef69ab6	2026-06-09 04:26:03.313375+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
5eb21def-61ff-4781-a438-fae891a8a640	2026-06-09 04:47:50.72212+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
975682ab-7986-4965-a5a4-271ece741ef8	2026-06-09 04:47:59.815644+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
35d3e15a-e498-40d3-b29c-1e1bbb0a8ad1	2026-06-09 04:53:22.196497+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
38719d8c-0230-4a5c-b199-3c4fe7bf4758	2026-06-09 04:53:31.956332+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9e351f60-43bb-4e9b-b942-897ee2532278	2026-06-09 06:33:08.880906+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ee200cbd-56fc-43d9-9c2e-63710a7f2040	2026-06-09 06:35:31.439712+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": false, "from": true}
6c991773-0df0-4bb6-b4b5-931eacaa86db	2026-06-09 06:35:32.465188+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": true, "from": false}
ff3b065a-529b-4394-a732-899c42991660	2026-06-09 06:35:33.508647+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.unlink	employee	d595afe7-1dd9-4c83-ba17-d8fc11a14724	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"user_id": "67188c2e-7217-40da-8222-7ff7b0cdc8b0"}
d95cb468-f8c7-4b4b-9cbc-54bc2328c69a	2026-06-09 06:35:37.240296+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.relink	employee	d595afe7-1dd9-4c83-ba17-d8fc11a14724	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"user_id": "67188c2e-7217-40da-8222-7ff7b0cdc8b0"}
ae0a940c-56f1-46d7-87be-fff4ad7ac7c2	2026-06-09 08:16:29.450984+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ef5fdfaf-d878-4b86-8ed3-c522bcf91cd9	2026-06-09 08:17:54.704166+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
e14806b7-e26c-4a2b-9538-904960bbceed	2026-06-09 09:21:15.68259+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
78678a78-f9e8-4fcf-b229-d300bbe30c18	2026-06-09 09:21:23.689845+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
aa8fdbb3-e51f-46d5-8775-ef30ce1514f9	2026-06-09 09:22:31.179207+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	c500c890-f911-4483-a62d-3ce63e6f0116	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
51a1d40b-9356-445c-82d4-5c9859adc204	2026-06-09 10:25:34.207328+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e61a6884-9001-4a75-9ee9-f4150fe8dde0	2026-06-09 10:27:35.708168+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
88ff3e8d-c45e-470a-86b0-f810cb46aea6	2026-06-09 10:27:47.065147+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
465bdcbf-f67d-4804-9ee3-50fd62e3d916	2026-06-09 10:27:48.929729+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
855fe413-83e1-4038-8ab6-b89b56888b27	2026-06-09 10:27:59.6215+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
3721b1e8-dd54-44d8-b299-7117755c0a41	2026-06-09 10:28:10.68982+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
3af5a4b1-b186-499d-a0fd-0a77d1991bfb	2026-06-09 10:28:23.682425+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
27ec7097-4084-43b2-8a06-072201108ee5	2026-06-09 10:29:00.980556+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.password.reset_admin	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
373d8cf9-286f-4888-99cb-3032b2ea99e4	2026-06-09 10:29:03.656886+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6732e39e-31ca-4004-8d1f-64eba045c1ae	2026-06-09 10:29:13.366201+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5ddc7e85-0d02-4957-928e-5fe01f1643a8	2026-06-09 10:47:59.322713+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ae7bee3a-109a-4e7b-8826-9276cee0f3f8	2026-06-09 10:48:08.796292+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4148b1b4-472f-4353-b1b5-14bda9f947e5	2026-06-09 10:51:40.141373+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
472a4c64-4ddb-4c66-8412-9cb7dbc354a6	2026-06-09 10:51:50.872497+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e3ebc232-667b-400a-8d96-6e0fe4637d5d	2026-06-09 11:45:16.509199+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
500bf2ee-02dc-4dd7-9a28-1d9fcef2aab4	2026-06-09 11:45:31.06613+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c861c184-d338-4dec-b75e-ffdbc706b340	2026-06-09 12:09:40.256874+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6d4db316-c525-4f7e-befb-c166148c5f6c	2026-06-09 12:09:51.060251+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
541ec53e-55ae-47c8-8624-24473a1bc43f	2026-06-09 12:10:40.985225+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e16a63b4-f098-471b-8772-199bf189c382	2026-06-09 12:10:54.86841+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
7e8beaa2-434a-4a55-903a-223bf87c02a2	2026-06-09 12:11:19.07074+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bb9b5000-454b-4002-8283-bcee6ee3b183	2026-06-10 03:46:44.966036+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d1110cae-f3da-4560-9159-1ea6712fbb4f	2026-06-10 03:55:39.685671+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5adbcff3-ee81-4628-94e9-720c4512471d	2026-06-10 03:55:57.595307+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ea96f066-986a-4184-a90a-8b5990207878	2026-06-10 04:03:01.617541+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6fcce1e1-07c8-4f8e-bb8e-e238d94b439f	2026-06-10 04:03:16.833868+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bc6b42e9-e7b2-4f95-94c7-ac0750c69715	2026-06-10 04:07:55.138112+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
6e206c1a-14ec-4ae6-a210-0a4356c54941	2026-06-10 04:08:04.056115+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
972b225a-4bf6-42e7-9a26-6ebe704b53c8	2026-06-10 04:18:15.128359+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
23218f98-01cc-44db-9da7-27c9db2bc24a	2026-06-10 04:07:40.924251+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
786cf791-0e09-401c-aa8e-d70bac081976	2026-06-10 04:15:43.19455+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9136f494-c366-4e60-af9a-1eafb9695407	2026-06-10 04:07:50.803237+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
f9011f88-fe65-40a2-a505-b1ff1778c897	2026-06-10 04:13:24.737732+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
3ce3f449-813a-4e1f-a5b5-299d49794213	2026-06-10 04:15:53.045486+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3dd28d71-37fb-4ef8-b138-96bc1293a297	2026-06-10 04:18:25.47318+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0d95d244-de5a-4e5e-bcdd-2a66293ca82c	2026-06-10 05:20:10.01494+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
696b0029-1650-4b2e-9125-90373c05f58c	2026-06-10 05:20:32.016506+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3be63c9a-26b9-4efb-b831-902252a3ea6a	2026-06-10 05:20:39.838417+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
794806bf-f76f-4676-bc7a-097d2a7088f5	2026-06-10 05:20:45.837628+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2bee6d54-01fe-4f3b-b2f2-c100391ab753	2026-06-10 05:21:41.580125+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9ae425f0-667a-49bc-b5ba-2d2cc5f2ed47	2026-06-10 05:21:51.966443+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e107eba6-e126-4a6e-9cd1-60128dd5945b	2026-06-10 05:22:32.997544+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	task.assign	task	feeec907-4e2e-48ac-ad3b-eff5ade1f5b3	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "prepare demo", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
4cb1ac72-e729-4dfd-8e63-fa29dbb97bf1	2026-06-10 05:22:48.055818+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f0f9cd11-acd2-41cb-ae4a-6f7d346cb485	2026-06-10 05:22:56.210579+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
50b27741-9a30-4e06-a28f-2a34c6aa8b70	2026-06-10 05:25:52.398946+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
22cd5622-4fec-44ae-b66e-840357b2aff7	2026-06-10 05:26:02.870918+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bc0d9d74-135f-434a-a6f2-ba05cef7d0a5	2026-06-10 05:45:51.41414+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
72664ae8-abf9-4e98-95ad-3f181fb745e1	2026-06-10 05:46:07.899903+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a8ebbdd2-7317-4d90-8483-08baba75e9ae	2026-06-10 05:53:50.012683+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
552412d9-72a1-4e70-8591-fffc2410e981	2026-06-10 05:54:03.472208+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
70a02eb8-c1bf-4d95-a433-4d8fd61083c1	2026-06-10 05:58:51.739558+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
275c2f47-7405-4415-b0df-260eecae3eff	2026-06-10 05:59:05.29148+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
29eb16a1-a5ed-4084-b35e-572e1028d5e5	2026-06-10 06:34:00.023693+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3ac67f88-069b-4170-8c28-e088e9f1d4e4	2026-06-10 06:43:35.26087+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
906f25e0-32b4-45fa-b0d1-a094376aa322	2026-06-10 07:16:39.405478+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
823f35c4-a2a2-4988-9429-e3424b37594d	2026-06-10 07:16:49.712675+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
11beeb5e-dcde-4c8f-a8bc-67924b157c52	2026-06-10 07:25:32.479872+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.role_change	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": "team_lead", "from": "contributor", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
ecbba16e-3058-4ff9-8372-5750006d29d3	2026-06-11 04:01:03.251515+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
04f3596e-8b15-461b-bbd8-36f7c9ed7887	2026-06-10 08:11:46.132778+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
1b9d0820-1bdf-4a40-ad4f-492e2d4d7f60	2026-06-10 08:17:07.986715+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9285d1dc-204e-4e7b-9acd-81c4853ba0ee	2026-06-10 09:27:02.226578+00	\N	&ko)KSmB6c"[],Fy%,|D,cE67u-*/FUO9n])"6h",0D9=VTgUd"L:;/z@NhQ4F&$?^'zBChJ7fJDTw<(R_w`c.joWXxFPa?-DN(VVqLkUH9h}"D[KVg!UUMIn*!A)gDmq*~;|=n'#6H-"D||xc;U{0a2)}gwNwjM?QIP(K4Vf.	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "&ko)KSmB6c\\"[],Fy%,|D,cE67u-*/FUO9n])\\"6h\\",0D9=VTgUd\\"L:;/z@NhQ4F&$?^'zBChJ7fJDTw<(R_w`c.joWXxFPa?-DN(VVqLkUH9h}\\"D[KVg!UUMIn*!A)gDmq*~;|=n'#6H-\\"D||xc;U{0a2)}gwNwjM?QIP(K4Vf."}
84eaae79-07d3-47ba-a364-6476fe05f1cb	2026-06-10 09:27:42.856929+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8b505432-e846-4856-812f-76fdfbee224e	2026-06-10 10:00:46.783621+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8457	{}
8ee7b305-761c-47dc-a25e-775502530cc9	2026-06-10 10:00:47.025249+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.failure	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8457	{"reason": "invalid_credentials", "attempted_email": "emp1@gmail.com"}
835330fa-9b4b-41ef-950b-d18d0f316501	2026-06-10 10:00:47.257421+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.failure	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8457	{"reason": "invalid_credentials", "attempted_email": "emp1@gmail.com"}
4b247ed3-1b66-43a8-a2c6-1f6c21915778	2026-06-10 10:01:35.084994+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.7778.96 Safari/537.36	{}
99a7c2cf-1934-4ed6-b185-aa0cc24ad137	2026-06-10 10:03:14.228699+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.7778.96 Safari/537.36	{}
934ca6ac-4c4a-4b55-9c45-c4b6fadec6bb	2026-06-10 10:07:02.456447+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.7778.96 Safari/537.36	{}
3fe78b0b-a131-4c2e-bffa-11c5b6994d25	2026-06-10 10:10:09.235097+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
61082856-e790-4927-ada8-60fd7173b206	2026-06-10 10:16:47.551725+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
7be8f18e-aeca-4656-9901-c247bd684c19	2026-06-10 10:16:56.630328+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4a1245d7-5f56-42d2-9b8e-305d298c2d34	2026-06-10 10:58:43.817321+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.role_change	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": "qc", "from": "team_lead", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
c7e0954f-1530-4a57-be80-6bb7b9052f14	2026-06-10 10:58:49.21514+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.role_change	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": "team_lead", "from": "contributor", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
7eda47a1-985b-4daf-a624-1f7653eb6831	2026-06-10 10:58:52.202521+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
1daf5b95-45ea-486b-b5c7-58cbf45fc8e5	2026-06-10 10:58:55.780403+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d375420d-811b-4ef5-8b87-2898a2c22eab	2026-06-10 10:59:07.007984+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
251d0453-fc4e-4902-87e9-01e8fca2e0aa	2026-06-10 10:59:39.342326+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
73b94539-f09c-4be3-b2a9-b7605c013841	2026-06-10 10:59:47.284222+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
94976168-de0f-40e8-b34d-877385ad5cf9	2026-06-10 11:20:56.495381+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.7778.96 Safari/537.36	{}
3ec1bcaf-3088-44ad-af5a-77596ce3777d	2026-06-10 11:25:56.253285+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
654f3184-828f-4f19-afb3-9b858b9916e5	2026-06-10 11:26:08.186972+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
53ed13c1-2191-4f9b-af25-d2b2bc650fe4	2026-06-10 11:42:45.318055+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a36b9c4d-2738-442f-91aa-e12d122c53f5	2026-06-10 11:42:55.946035+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
24c0027d-7c2d-43d5-adf5-259f0346f796	2026-06-11 04:00:27.675389+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
13fc928e-9045-4e30-817c-16b936621817	2026-06-11 04:01:12.487063+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3ea9acb5-4f6f-40a2-b4ef-e2cef570382b	2026-06-11 04:40:44.050168+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.status.change	task	feeec907-4e2e-48ac-ad3b-eff5ade1f5b3	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "prepare demo", "status": "in_progress", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
1cdf87b3-e66a-44f4-b859-845dde543021	2026-06-11 04:40:53.632676+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.complete	task	feeec907-4e2e-48ac-ad3b-eff5ade1f5b3	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "prepare demo", "status": "completed", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
696dae45-0966-4379-ab3e-1cf397a49ff4	2026-06-11 05:08:18.390771+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2184fb62-b5b5-44b9-b710-90fe45240eb8	2026-06-11 05:08:21.622489+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a922b1fb-2d18-4438-b02f-3d94c1d6ec16	2026-06-11 05:09:07.599452+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
359a2edc-7535-4eba-8ec7-2e472882f046	2026-06-11 05:09:20.429376+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
97dbd790-98c8-4962-93fa-32e207422d49	2026-06-11 05:12:41.380643+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ead808e5-3216-4a99-b077-76d506b19dd3	2026-06-11 05:12:55.655981+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
24a6ce90-d7a1-4d2a-810b-c3fe6f1ab3ed	2026-06-11 05:14:11.20505+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8fb069ef-f820-4362-9e95-57b4ee6ceca5	2026-06-11 05:14:19.069838+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
40360b6e-36ee-4853-a7a3-d554a75f0196	2026-06-11 05:49:28.033081+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
04712847-3992-4e4c-b2db-8b7b05abf403	2026-06-11 05:49:38.860356+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5c2fd967-aca5-4781-a1f2-37195d74ee25	2026-06-11 05:50:57.945567+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5f75bd7a-0640-4b85-abc8-59f3bc739aa4	2026-06-11 05:51:08.411556+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ff310bad-89bb-4919-81f0-12602978858a	2026-06-11 05:53:10.254829+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2a70d633-cbfa-4641-82ba-91fa5ffa0565	2026-06-11 05:53:20.236616+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
4df5db61-83d4-4a11-95b4-43df632c0cb0	2026-06-11 05:53:30.267209+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
61f36a90-67c4-4e17-8a99-fa4de10f547e	2026-06-11 05:55:19.281522+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ac08c929-4f4e-4ae4-a149-722ed73fa5a0	2026-06-11 05:55:29.357178+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e1d16a67-51e9-4592-9fc4-84cc40b07a74	2026-06-11 05:56:06.196802+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e8bf8d6b-106b-4ac3-88fd-238adb514f40	2026-06-11 05:56:18.832844+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9b7391a2-dba3-4e94-b07d-48382c93b5f9	2026-06-11 05:56:48.572183+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
514096f9-be08-4312-aa81-736a489531cd	2026-06-11 05:56:57.539457+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9ff77922-73ea-4235-b2bc-1724cc51952d	2026-06-11 05:57:41.829327+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
18d88396-a966-4d9d-acbe-65f9613fa94c	2026-06-11 05:58:09.615598+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ca07f873-b510-497d-ad12-c017ea27b11d	2026-06-11 06:05:59.636534+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
951c7bcd-b2a9-4ee8-b74f-c4834529573b	2026-06-11 06:10:57.876959+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
81af882e-8fd3-4c19-8984-a5eccb24a3c9	2026-06-11 06:11:07.06553+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6d13bb18-26d6-4bb5-8c4b-f87929ad1505	2026-06-11 06:12:34.952817+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6205c6fc-9acb-4fac-ba33-f3772b4ff07a	2026-06-11 06:12:45.459835+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
674a3e8d-d5a5-44bf-8b3d-e8dfc0fb2c64	2026-06-11 06:18:18.018183+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f59ca175-568d-40b8-9f54-c9c1db22d9db	2026-06-11 06:18:29.670374+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
40181ca8-1500-4605-b28b-30b4abdce99a	2026-06-11 06:19:13.171625+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0048a400-d086-466f-a1c0-b9eb8df2c063	2026-06-11 06:19:20.944718+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5b72ff0b-6227-4b45-9567-e484ab395190	2026-06-11 06:21:24.234889+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0539d044-bb9c-49c5-aadc-5ef6dc9bf246	2026-06-11 06:21:33.815347+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
572e7fb1-b42d-4d73-bfc1-6c69d4718ca2	2026-06-11 06:30:57.640887+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
029b0fe1-bfde-4c30-b43b-6b82c3eaa83f	2026-06-11 06:31:07.222076+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6e7e410c-b784-42e0-b514-ff4802f7a4d5	2026-06-11 07:00:32.961929+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c7407ae6-d01f-40b3-bccf-ebcb4d16d4d5	2026-06-11 07:00:44.413756+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
cac84135-7f05-4406-a240-a11c9b6e1480	2026-06-11 07:01:51.559038+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fe1af8ed-88cf-4b78-b77e-62d4a3915729	2026-06-11 07:01:59.323768+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c083a96b-0f7b-4d5a-bc19-5baee538acb5	2026-06-11 07:02:12.738948+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
477d2428-7323-458b-821a-487c3f07ecab	2026-06-11 07:02:26.268305+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
50234d9c-d999-494e-9365-cc81544b25cc	2026-06-11 07:02:31.179776+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
49951ed3-bbc4-4db4-a2d0-8eedbee75b09	2026-06-11 07:06:59.497652+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "lead", "employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d"}
642e3a3b-cf1d-41f8-ae0a-93484241c506	2026-06-11 07:07:00.342663+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "member", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
00d297b7-f142-4a00-b2f6-2b21f7ab6f91	2026-06-11 07:08:49.87497+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
22a80ffb-5098-419a-84f8-d8a48398e6c2	2026-06-11 07:09:05.502168+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
94a9937a-8ffc-4d4a-8069-56a64fde2e15	2026-06-11 07:29:08.984168+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4c02a2d0-9345-4841-84fe-2b4d273b0684	2026-06-11 07:29:25.738578+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
39f7dac2-b4d1-4027-8811-943949e17b7b	2026-06-11 07:29:31.941991+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fc3cfa41-b48d-401c-8ee1-9b3050746350	2026-06-11 07:29:49.719656+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	task.assign	task	096b7ae9-b916-49c0-8b6c-d916e8416fd0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
cbfbf32b-2dc7-4691-b71d-da66cb5e1d6d	2026-06-11 07:29:56.137355+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a2e9f0ea-1b48-419d-a6cb-96870578a31d	2026-06-11 07:30:03.672681+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
cb3298a9-3226-4a54-a66e-6f4f7eb1fcdf	2026-06-11 07:30:09.768133+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.status.change	task	096b7ae9-b916-49c0-8b6c-d916e8416fd0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task", "status": "in_progress", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
0396c7fa-9bd1-49db-af44-48c326677ee8	2026-06-11 07:30:14.696189+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.complete	task	096b7ae9-b916-49c0-8b6c-d916e8416fd0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task", "status": "completed", "assigned_by_employee_id": "44659769-37c8-4b98-b5b0-4e1e6a7f7d2d", "assigned_to_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
d6aa4dad-b328-4eef-a158-b1c8bbfb2c76	2026-06-11 08:29:59.441863+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.assign	task	8b878fe9-d4b1-47fc-af85-bfa898d98458	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "monthly attendance report", "project_id": "5a119e5f-cdf8-42b3-bc96-95fd7a03025e", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
458979e7-1e3d-493a-a0ce-402d1f613c8e	2026-06-11 08:30:37.237817+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
7d62b27d-60c7-42d5-a501-be7d7ef8ed21	2026-06-11 08:30:47.181668+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	task.status.change	task	8b878fe9-d4b1-47fc-af85-bfa898d98458	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "monthly attendance report", "status": "in_progress", "project_id": "5a119e5f-cdf8-42b3-bc96-95fd7a03025e", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
0f41c074-c83b-4339-90de-1288cd62e745	2026-06-11 08:30:52.479279+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	task.complete	task	8b878fe9-d4b1-47fc-af85-bfa898d98458	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "monthly attendance report", "status": "completed", "project_id": "5a119e5f-cdf8-42b3-bc96-95fd7a03025e", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
0b55f8f0-90d8-42eb-ae72-72dcb84ea5d4	2026-06-11 09:33:00.841163+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5eeb57a7-d06e-42f8-8d55-121b3349639e	2026-06-11 09:41:23.016891+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
175ae477-f6e4-44bd-a97f-cb3b46b8bfc4	2026-06-11 09:41:44.430165+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
5f29f728-0553-48ec-9229-397f1cc49fdc	2026-06-11 09:41:46.117623+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
541e0243-b9b0-454c-982f-bf8e88e3eb33	2026-06-11 11:35:08.533721+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9dd89b96-305a-423a-b70c-6e6778273a91	2026-06-11 11:35:49.788152+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4bc7b46c-4395-4409-b4d5-45acdb454691	2026-06-12 06:19:05.930935+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
703fa43e-6b40-466f-9b04-e2cce48665a7	2026-06-12 06:19:11.97619+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2e312aca-8193-4bcb-a714-66b719a5358a	2026-06-12 06:19:56.021582+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8ef6dcac-7149-4a6c-980f-8f988f7cf5a2	2026-06-15 03:37:45.509995+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
02f356e1-fe40-4306-a609-297f511a7914	2026-06-15 04:10:47.433509+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9822ca08-f5cb-4be9-9915-c38592434739	2026-06-15 04:11:09.032169+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9d7b9637-eec0-4d83-b56a-8f82aec90ae7	2026-06-15 04:16:29.962758+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4a573d67-ae04-411d-96fc-7aa9976d202c	2026-06-15 04:16:39.876465+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fa5ade22-e29f-4a29-830c-602fc0c6f3af	2026-06-15 06:22:25.561546+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
503980e4-de3a-4243-85dc-0ff4a3e2ff7a	2026-06-15 06:22:27.606549+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a3a86bd7-85fb-44ff-9768-f9a7cbd23f72	2026-06-15 06:33:10.119062+00	\N	admin@coreops.local	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"reason": "invalid_credentials", "attempted_email": "admin@coreops.local"}
00cff397-a1fa-49e4-a4a0-b87cbdc86847	2026-06-15 06:33:36.898754+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
9fa48b65-3131-4817-b6de-23fd095aa450	2026-06-15 07:23:19.097825+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2652abd8-68e1-47b6-8f20-d7368587cb86	2026-06-15 08:23:57.706063+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
32f288bc-6f84-4329-a984-7cd311b1d529	2026-06-15 08:24:06.475122+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ab1c25e3-6b43-414c-b8f1-eddb23e5f490	2026-06-15 09:02:27.192578+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	305f8d94-a201-4efe-b088-6afc4313c23b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
62904cd2-d2ce-4ce0-8abc-002f13e92f42	2026-06-15 09:27:37.854735+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
efee2dfe-8b86-4dc5-ae3c-0e57d99a35b4	2026-06-15 09:34:38.74737+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.planned_date.change	project	4b350de2-1c20-4576-980c-f03eacbceb57	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "vss", "new_date": "2026-06-24", "old_date": null}
c879ae3a-87b1-427c-a3a0-89f4ddfeba49	2026-06-15 09:34:45.964436+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	4b350de2-1c20-4576-980c-f03eacbceb57	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
70af1b07-9d1c-450c-8873-fa7b438bb89d	2026-06-15 09:39:12.744502+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	4b350de2-1c20-4576-980c-f03eacbceb57	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
7633ca6e-5081-4c57-b318-b4147139d651	2026-06-15 09:50:48.574802+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
692f1c39-664f-4d2a-ba6e-07ad676d89a4	2026-06-15 10:15:20.01127+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.planned_date.change	project	95515988-270a-4bd2-81c6-59e50d49c91f	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "requires verification", "new_date": "2026-06-19", "old_date": "2026-06-16"}
1c023204-0628-4222-9bd4-fe78a8dec0f3	2026-06-15 10:15:48.237236+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.planned_date.change	project	95515988-270a-4bd2-81c6-59e50d49c91f	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "demo", "new_date": "2026-06-16", "old_date": "2026-06-19"}
43e7ad25-598c-4c17-b6e0-a4754e2c6936	2026-06-15 10:17:06.489919+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	95515988-270a-4bd2-81c6-59e50d49c91f	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "3107987e-7e92-4e89-97f3-1d5275e65485"}
2ce63307-42f8-4bde-9a4a-124c953bd232	2026-06-15 10:17:17.371165+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	95515988-270a-4bd2-81c6-59e50d49c91f	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
f48485d4-bca4-456c-ad7d-0fc3f77c5294	2026-06-15 10:22:29.332047+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0bdfa3e8-2617-4942-8055-ccea8cd3b407	2026-06-15 10:22:39.591213+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
37786bac-3757-4188-9aa9-b6db654f98b8	2026-06-15 10:27:18.221853+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
efa7c8a0-32b5-4f6e-97ce-a763b2fdf952	2026-06-15 10:27:32.090518+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e401ec8f-3e16-4906-8eab-45213a433e3e	2026-06-15 10:30:24.704471+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	5be2de87-8430-4395-9102-3a7fdc76eb48	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "qc", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
891f65fa-7b11-49fd-a040-0ea95959f8c8	2026-06-15 10:32:38.926067+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e32b896e-84b8-4f57-91e6-59872899beb9	2026-06-15 10:32:51.058069+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
0e279028-5bb5-4bb7-a739-7be8a434ec6d	2026-06-15 10:32:58.466293+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
7cca04a0-03c9-4cd0-8b20-213e9205d02c	2026-06-15 10:33:01.854338+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
4ffdf021-9ed5-42d7-be94-d5ee8cd8c23c	2026-06-15 10:33:09.178015+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1b6a5550-9ff8-4be6-b882-19fa1f2e2f25	2026-06-15 11:56:33.537458+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
016625ef-c9c9-4612-9d1d-76a6b512c211	2026-06-15 11:57:42.568977+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
aaf5084b-e318-4a14-8ba8-47a6321c19cf	2026-06-15 11:57:52.673201+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0a6a56d3-34e9-467f-a028-351c8b835867	2026-06-15 11:58:42.222695+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c7013e2e-f59e-4a1c-adcd-af56ad81a710	2026-06-15 11:58:49.200677+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
df6c992c-073f-47dd-86a3-1522a163b14b	2026-06-15 11:59:19.853415+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fb8f92e0-bd3d-40de-b92e-f131c8727f0a	2026-06-15 11:59:29.874465+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
cf562208-2374-42f4-b241-8834332aff92	2026-06-15 12:00:11.095949+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b5e5cb6e-e9e2-4e38-a54d-500523dedf4b	2026-06-15 12:00:03.634849+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
04bd96d2-a5c8-4cb3-bdf6-a925f717aa95	2026-06-16 04:03:28.96742+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8a2226c0-8c6c-47ab-bf5a-6b3b5a570ae9	2026-06-16 04:22:54.239574+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
11f460a6-70ff-4c6d-8ee2-5481e3c987c8	2026-06-16 04:23:05.94216+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
4d515f1e-ba65-434b-a8b6-5beb2dff394f	2026-06-16 04:23:13.075084+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b79ca9df-803d-448f-b7c8-3d9660e5fb3b	2026-06-16 05:23:23.650233+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f5c448a6-6c6b-4bc4-95d4-e02e88b9ae24	2026-06-16 06:50:29.584523+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
d714ab07-09b0-4484-ba7a-5481439f4a0a	2026-06-16 06:50:31.535847+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9def67a6-a423-4896-b141-c532d8aaef1c	2026-06-16 07:11:38.567888+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
33ffa202-b6b9-4eb7-acae-ee7079e9147d	2026-06-16 07:11:47.311606+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5b30344d-ce0d-402e-a3c5-d0dd6241c37e	2026-06-16 08:23:25.637235+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
05850389-7e96-404a-a5ff-87bb6494b729	2026-06-16 08:23:27.643527+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
639313c6-6284-4181-90f2-a389a4318c2c	2026-06-16 08:23:35.092312+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ca3ce3f9-20b1-4cad-93aa-b0b2d68e35e8	2026-06-16 08:23:43.383022+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e809f98e-2f3f-4d4c-b936-c631693b7eee	2026-06-16 09:21:15.017692+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
23f69d08-5605-41bd-8e0e-3b6efb0a8ccc	2026-06-16 10:27:40.290193+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
896c2f50-ce29-4261-837e-082bc551be0e	2026-06-16 10:40:50.549813+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
51061b06-7e6c-4116-8e8c-b5316822166c	2026-06-16 10:41:50.663036+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
29d5bbaa-38f0-4c83-9047-bc135a1f6f50	2026-06-16 10:42:04.260185+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4379a57d-e660-48eb-8bb0-d2a9ab374163	2026-06-16 10:44:51.709092+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4a4658b4-2271-44ac-a3e6-724a06a99e59	2026-06-16 10:45:01.090285+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.failure	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "manager@coreops.local"}
439e8b13-ebca-4b4f-be2a-301043857fa1	2026-06-16 10:45:03.166195+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2f3838e7-583c-4782-8094-e13f587fb6df	2026-06-17 03:58:18.65184+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3eb06472-4b79-443d-986f-3aa614301c6d	2026-06-17 04:18:22.115014+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
232a05cf-e223-49dd-b7e8-3a8f9fbfd20b	2026-06-17 04:21:07.840323+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
d3107e91-90ee-4e30-a361-e06fa0d7f2aa	2026-06-17 04:21:11.976509+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
e492faa8-9a1a-4724-9186-38cb4060cc29	2026-06-17 04:22:14.193601+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b1ac57c3-fc68-4b8b-9337-abfc5b3c9f6a	2026-06-17 04:22:27.2345+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
07a02c85-6559-436e-a486-d7f59c16cf45	2026-06-17 04:53:08.885533+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4a171e07-226f-4e72-88c8-cc09f8fe6602	2026-06-17 05:02:12.304448+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6be9ec17-8b95-4396-b701-bec15361b864	2026-06-17 05:02:22.207948+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fb999de9-f2c7-491b-835b-2765bb94700a	2026-06-17 05:36:11.384623+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
de353647-7797-49cb-bef9-cac13389533b	2026-06-17 09:21:48.208215+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4ad9d490-9516-4a1d-aa1a-048d74fcccce	2026-06-17 10:12:02.814096+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1e16befe-7cc2-498a-b9fd-f5fa85e473b4	2026-06-17 10:12:11.731258+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4b8f9783-8714-430a-9b08-1981a682d819	2026-06-17 10:40:36.12915+00	\N	verify-pm@x.com	\N	auth.login.failure	user	\N	failure	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"reason": "invalid_credentials", "attempted_email": "verify-pm@x.com"}
0ee86b15-5057-4c8e-b4b0-e8a21cf97f65	2026-06-17 10:41:02.506496+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
1a078b48-708d-4805-80a8-08f2367a7b4a	2026-06-17 10:41:50.402877+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
0e6603c0-283d-4fe5-8c5d-8d88d2c2c435	2026-06-17 10:41:50.620478+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.create	employee	322d1a8d-7e43-4cb6-8ec4-7edcba536c94	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"employee_code": "VERIFY-161150"}
852c7b8d-cded-478f-ae9c-1f34960743a6	2026-06-17 10:41:50.635713+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.create	user	8a3aac26-e80a-4368-a362-2fc6cd602575	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify-phase3-161150@x.com"}
d44fb467-650a-4e1f-a988-c95b337ffb8d	2026-06-17 10:41:50.861309+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.link	employee	322d1a8d-7e43-4cb6-8ec4-7edcba536c94	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify-phase3-161150@x.com", "user_id": "8a3aac26-e80a-4368-a362-2fc6cd602575"}
565eb031-9bb2-464e-8f12-e45374795b27	2026-06-17 10:41:50.891166+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	0fccd6d1-6693-44e3-afad-7162325e52e8	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "member", "employee_id": "322d1a8d-7e43-4cb6-8ec4-7edcba536c94"}
341bed08-ed0d-41b0-a374-ce7df16bd53b	2026-06-17 10:42:37.516075+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
57453db6-0fec-4f7e-9169-34ddde7d06e9	2026-06-17 10:42:54.909823+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
fa6eed7e-a550-4647-8961-91e849ff76a7	2026-06-17 10:43:28.130574+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
106fe489-8981-467a-a2a5-35ea3462fb32	2026-06-17 10:43:28.381201+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.deactivate	employee	322d1a8d-7e43-4cb6-8ec4-7edcba536c94	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
ba2b7aa6-c57d-4249-af30-dfe2f7014b17	2026-06-17 10:42:20.817638+00	\N	verify-phase3-161150@x.com	employee	auth.login.success	user	8a3aac26-e80a-4368-a362-2fc6cd602575	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
1ffd7c2f-c893-4c6f-9c32-65bf16dee0f2	2026-06-17 10:42:37.757495+00	\N	verify-phase3-161150@x.com	employee	auth.login.success	user	8a3aac26-e80a-4368-a362-2fc6cd602575	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
4a8283e0-e396-40db-b584-b92f1c94af14	2026-06-17 10:42:54.683045+00	\N	verify-phase3-161150@x.com	employee	auth.login.success	user	8a3aac26-e80a-4368-a362-2fc6cd602575	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
35dbe59c-8091-49d2-b989-3b1d44a213a9	2026-06-17 11:16:26.485802+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
745133b9-7761-4a3b-8c97-681b40612a56	2026-06-17 11:26:15.602464+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
781a73ca-4e2e-4824-a309-6c7bb6b78d52	2026-06-17 11:26:15.858399+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.create	employee	b42767bd-7b48-4474-902d-9f6d074bb33c	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"employee_code": "VERIFY2-165615"}
951d1b4e-5427-41ed-902a-b2ea7d412a55	2026-06-17 11:26:15.880626+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.create	user	c8a2deda-ed10-4226-950e-7fcaf2e9395b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify2-165615@x.com"}
20be29bc-f51a-41a9-9dd4-c999f068edac	2026-06-17 11:26:16.097625+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.link	employee	b42767bd-7b48-4474-902d-9f6d074bb33c	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify2-165615@x.com", "user_id": "c8a2deda-ed10-4226-950e-7fcaf2e9395b"}
35fd39e6-9b36-4755-801e-0d665525eb97	2026-06-17 11:26:16.124951+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	a6734845-f8ad-4c16-acba-bb46df89f109	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "member", "employee_id": "b42767bd-7b48-4474-902d-9f6d074bb33c"}
0b24c9ed-bfeb-4a6d-bc98-6fe2577a9158	2026-06-17 11:26:38.538859+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
ce9d7931-9563-46b4-b542-4ac8c7b66120	2026-06-17 11:26:38.778718+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.deactivate	employee	b42767bd-7b48-4474-902d-9f6d074bb33c	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
e5060fe8-ef19-48aa-9c26-f6656086fb47	2026-06-17 11:26:16.165886+00	\N	verify2-165615@x.com	employee	auth.login.success	user	c8a2deda-ed10-4226-950e-7fcaf2e9395b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
6a2a82e3-c088-4987-901a-a1e4cd4bda3e	2026-06-17 11:28:22.195875+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c378dcc3-97da-4003-83dd-38e5b7e7c2e2	2026-06-17 11:28:36.539003+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8dfa5f6c-6c6b-41ad-afc2-41c3d57c91f5	2026-06-17 11:29:59.825809+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8abfb719-f031-47c2-9204-71d2b48e0b7e	2026-06-17 11:30:01.85786+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8a5fc684-b46e-470d-bf2d-aef0b0958df9	2026-06-17 11:56:05.907381+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
da802df9-c303-4338-b5cd-8746eca452e8	2026-06-17 11:56:06.157039+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.create	employee	2634d088-1297-4db2-b947-89a7edf76e07	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"employee_code": "VERIFY3-172606"}
361a8e80-0a51-44cd-9ebd-45383b19d487	2026-06-17 11:56:06.171944+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.create	user	64bfbc0f-a5f9-4dc3-bb42-9bcb7ac79779	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify3-172606@x.com"}
9c4ece54-46a6-44ba-bbc5-67d2026a1948	2026-06-17 11:56:06.386728+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.account.link	employee	2634d088-1297-4db2-b947-89a7edf76e07	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "employee", "email": "verify3-172606@x.com", "user_id": "64bfbc0f-a5f9-4dc3-bb42-9bcb7ac79779"}
80fafb22-06ba-4eb9-a553-236e1a786711	2026-06-17 11:56:06.415802+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	89759f23-3c40-4585-be92-7fdff278aadb	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{"role": "member", "employee_id": "2634d088-1297-4db2-b947-89a7edf76e07"}
cb024b5c-e7a3-4f54-83d6-dca3bcf704b1	2026-06-17 11:56:38.4107+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
14a91917-40f5-434a-984c-225c81f9da26	2026-06-17 11:57:03.834053+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
65a3db9a-31de-40de-a851-ca8d442f6236	2026-06-17 11:57:04.072744+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	employee.deactivate	employee	2634d088-1297-4db2-b947-89a7edf76e07	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
435189d6-fcb6-4a46-843a-40d06cd7545a	2026-06-17 11:56:06.464732+00	\N	verify3-172606@x.com	employee	auth.login.success	user	64bfbc0f-a5f9-4dc3-bb42-9bcb7ac79779	success	172.19.0.1	Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100.8655	{}
3ce13835-4b61-46bd-9c73-c0466b89235f	2026-06-17 11:58:27.136327+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
83a59d8c-7fd7-474d-80a6-cdc49398107f	2026-06-17 12:01:02.013842+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
412c110e-3206-4f21-b724-ecf7b96b8c3d	2026-06-17 12:01:11.634102+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
cf755c37-6321-4e8d-976d-7450e816e9be	2026-06-17 12:02:49.96103+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
baed3832-6329-4de5-a760-cc41b3631592	2026-06-17 12:03:01.909729+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
5ac46fc9-093d-4dd2-8d6b-31ca1345ba66	2026-06-17 12:03:05.363337+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
6e5add25-80ca-4b1a-ac64-fd50ac0d2f88	2026-06-17 12:03:11.879904+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9533ee44-a542-4f36-b180-8c282cfe38e4	2026-06-18 03:51:31.609405+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b37f357d-ce0d-49b1-ab0f-953f3c3a0fd4	2026-06-18 04:01:43.333744+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d0df57ff-cfaf-4263-811f-128c41cab3d2	2026-06-18 04:01:52.400804+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
c7b538bb-8cfc-42ab-a5c7-353c482a2ad6	2026-06-18 04:01:57.149543+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
466619e0-3f50-4b7c-af8c-975f47277595	2026-06-18 04:02:01.181248+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
dfca3390-157f-4de3-a58d-c65f1a68da8b	2026-06-18 04:02:08.095217+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
26ada017-8724-4be9-bb61-37c90f946321	2026-06-18 05:09:23.516514+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0589d077-4976-408a-83f0-4efb37c47d80	2026-06-18 05:46:58.079096+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1b2807a1-6b5a-4b29-b616-26f72076eff9	2026-06-18 05:47:15.218317+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
38c78028-b657-41c4-b2da-3dd66ee70f2c	2026-06-18 06:12:47.205306+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6db5c890-7c47-420b-9a54-da5a9fa96ea1	2026-06-18 06:12:49.054213+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9202aa39-8ee3-4874-9506-97b2e2d50d16	2026-06-18 06:12:50.235257+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4b041ffb-b1cd-4251-8d35-463b11521a16	2026-06-18 06:13:45.257269+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3cf9b26b-3ab3-47ac-b394-9dfaf8283fc5	2026-06-18 06:13:53.953219+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9c09c586-e719-4bce-be14-94feecd47002	2026-06-18 06:40:05.113663+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
82890525-3363-4dcb-b7f7-9885fbe76cc7	2026-06-18 06:40:16.736174+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.failure	user	9f946201-e71e-4356-b830-2dddae74e9f9	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "santhoshkumar29948@gmail.com"}
4525dee9-0374-4542-ac08-d78da04d6c3b	2026-06-18 06:40:24.413746+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ac2c555a-607f-4437-a36f-1e682e863fae	2026-06-18 06:43:53.721296+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e3525089-5ccf-4f85-b5d7-15111fe15efc	2026-06-18 06:44:02.641739+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e2f7ee77-6ff5-4f75-b278-f3bb6d009ecf	2026-06-18 06:46:46.129699+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c3b0cb95-096d-4d69-a585-2833df5deb7e	2026-06-18 06:46:52.883588+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
26e609f2-e26f-4dd5-8862-645a4926e762	2026-06-18 06:47:08.82661+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	task.assign	task	7764733e-1d76-436c-ae83-a3c217daf9fe	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task 2", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
c35acefe-318d-4f2f-ba2f-3911270423a9	2026-06-18 06:47:13.603549+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a3b75edf-02d8-4716-ae15-898ecb3bea39	2026-06-18 06:47:22.705109+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
21cf0066-0be8-48d5-9786-5d3ff9090542	2026-06-18 06:47:28.148432+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	task.status.change	task	7764733e-1d76-436c-ae83-a3c217daf9fe	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task 2", "status": "in_progress", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
0a815e2c-5123-4b7e-9b4f-078f1f838ab1	2026-06-18 06:47:37.690452+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	task.complete	task	7764733e-1d76-436c-ae83-a3c217daf9fe	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"title": "demo task 2", "status": "completed", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6", "assigned_by_employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0", "assigned_to_employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}
80bca026-c2b0-46c3-896c-4ce66648b7f7	2026-06-18 06:58:28.984214+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c7613f8b-7fdf-41ec-bdec-ef13b3b0c831	2026-06-18 06:58:35.75196+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4df0bb2e-0e5e-4aa9-94b4-10c87f2a5718	2026-06-18 06:58:44.85047+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b3cf821c-f726-460a-b3f0-44b3b0fd4397	2026-06-18 06:59:00.121665+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
349911b2-e990-4064-aa99-ea3166b458de	2026-06-18 06:59:10.754766+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
174e2c56-8487-48f4-a120-5b8e2e4445dc	2026-06-18 06:59:18.52505+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
4894a478-fc95-4b23-9f5c-f7a3e3c07fa2	2026-06-18 06:59:25.991573+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "contributor", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
de0b4bd8-79a8-4d8c-bd32-ca6f6f7ebef6	2026-06-18 06:59:49.406318+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
e24ee2b9-911b-4758-b1f8-8c1cf6dfcab0	2026-06-18 07:00:55.463693+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4cf5a86d-a204-48eb-8060-4c1ff18ad17a	2026-06-18 07:05:42.167911+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
57c23d1a-9adc-4f4f-a520-21ead33436a7	2026-06-18 07:00:20.611057+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0ccfe2d7-af31-4d00-a74c-71e774e3b162	2026-06-18 07:00:28.408429+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f54ac38f-7407-4e5a-860d-de54f26f8674	2026-06-18 07:00:44.898712+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3fb5bb17-103b-4ef1-a27d-c7b64cc24418	2026-06-18 07:02:13.575753+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
681e3666-cc4a-4694-af9c-1d2bc7b174b2	2026-06-18 07:08:56.488078+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f096df22-ba90-4809-96d2-de385c76f265	2026-06-18 07:09:04.986479+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
cbb0e7a9-71c6-4ad2-af90-b2d714cf8c0a	2026-06-18 07:09:16.059288+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1d00feb4-97a9-4931-91cc-555106c38b40	2026-06-18 07:09:23.686854+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
076d2e1f-e50a-47bc-a4e8-ad6a28d4e79c	2026-06-18 07:16:03.584229+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
915f0108-7c07-49b1-a2af-c0a9fd8060b2	2026-06-18 07:16:13.745673+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
70e09d05-8819-4d82-800f-3c6bd049d9c8	2026-06-18 07:17:21.610762+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e9eba293-c894-425b-9a8c-1efafbfbe088	2026-06-18 07:17:29.030272+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c49e9507-2e07-4d7d-8a33-2f4d54597646	2026-06-18 07:18:56.508452+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3c4eaf63-c1b2-49af-b044-4c7effc7a633	2026-06-18 07:19:07.276665+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.failure	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "nainar@gmail.com"}
6e464618-17e3-4060-93b4-cf428b4685b3	2026-06-18 07:19:15.43368+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a94b3bc2-acc2-4690-ad95-f0aa89f0f474	2026-06-18 08:00:48.919244+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e3c8a198-cb4d-41a0-9df8-34cfcf2e4c00	2026-06-18 08:00:58.640593+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
597124da-328d-47e9-acb3-7acdb5441dac	2026-06-18 08:02:19.765192+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.add	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
64190e70-ac13-44e7-b3c7-108e63f465d8	2026-06-18 08:02:21.501412+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
414d292e-59ab-4389-b682-b0de14715803	2026-06-18 08:02:30.095633+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e079f86c-c28c-4a7a-a524-d0b0a1b4b6a7	2026-06-18 08:16:07.533058+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d985a286-4fb9-49f8-93d2-460bb6d113b7	2026-06-18 08:16:16.216439+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d6b59513-bda6-436a-9221-40119d5c0200	2026-06-18 08:16:37.534586+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	project.member.remove	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"role": "team_lead", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}
4efe3839-4a1a-445e-85e0-6b6f75dbf393	2026-06-18 08:16:40.61456+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f0840f0a-7899-4ba3-9ae2-adfbd86ab6a9	2026-06-18 08:16:54.084402+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ed8759f0-db9a-4660-8daf-0531f7218716	2026-06-18 08:17:16.835747+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ba315827-3a03-4e5f-82bd-635f2fa7fb01	2026-06-18 08:20:08.555287+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
244f20e9-e316-4c27-8010-51d6f4ead51a	2026-06-18 08:20:10.587978+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0cf5c645-2c95-4a8c-b6c6-e1b0c67da483	2026-06-18 09:20:25.91745+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3f45256b-115b-47ed-8b2a-53a2d228f383	2026-06-18 10:39:22.617064+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2587c093-ac01-43b0-be26-99160a145ce4	2026-06-18 10:39:24.381671+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0f2f2845-4715-4fde-9141-0a5597be9042	2026-06-18 10:39:25.987003+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
59b81527-e860-4c8c-9f55-32859aca1305	2026-06-18 10:44:57.146983+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
633536ec-7c4f-49c0-890b-c694d2c61951	2026-06-18 10:45:10.675106+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ad7639bb-4c0a-4e25-ad4c-6919ef5dcb90	2026-06-18 10:45:33.036912+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
47c75937-f968-4365-b938-97eaefd32110	2026-06-18 10:45:43.889132+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1bc66585-b4a9-4c12-9bcd-17a5020d968c	2026-06-18 11:48:17.103895+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c8cf2934-21bc-4727-acfd-7d52af4f9018	2026-06-18 11:54:54.819143+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b69e4717-7a44-4fa0-9321-936ef1087169	2026-06-18 12:01:12.467862+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ec661e69-8241-459d-94c1-a6aa059aa883	2026-06-18 12:01:22.152052+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ef2a9356-feb0-4fd5-a451-8be2a38a8071	2026-06-19 04:40:05.278263+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
24224a73-0e9c-4595-8669-a3d1b5051d0b	2026-06-19 04:51:48.930963+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b80f9e37-21f2-4f58-885e-43ae315a3ebe	2026-06-19 04:51:58.230839+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2f03ac47-30b1-4c6f-a11c-c921f256ed18	2026-06-19 04:58:16.920969+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1f451bf7-a837-4f8b-84f7-a54c90a69380	2026-06-19 04:58:28.372594+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
724ba6ad-728f-4fbb-9757-d1660d032c60	2026-06-19 04:58:42.056999+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1ff676fa-a4e0-4c8c-a050-1836a0f286d4	2026-06-19 04:58:50.537905+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fa1eae9d-e37f-43a9-bda4-29fb29d38587	2026-06-19 05:12:10.070286+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
dfb753e8-bc8a-4053-beee-cd9d95234d63	2026-06-19 05:12:18.71627+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a69f6d5c-2601-413a-8d1c-f3936ebb1afa	2026-06-19 05:16:55.629058+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1aa17aee-b1d9-482e-81b6-331d7ef454f9	2026-06-19 05:17:03.697586+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a26885b3-8dd5-4a95-9413-42608001b589	2026-06-19 05:58:18.002015+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
09dac3c8-3edb-430f-b6ca-5682c091010b	2026-06-19 05:58:29.234862+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1e1f8e1b-8a62-40d1-823a-783ca382d227	2026-06-19 05:58:33.657478+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bcf70c25-d4ef-4a02-9427-c321ed84055b	2026-06-19 05:58:41.905339+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
524ccfd9-185d-4ca6-8c1a-8f4841d7c2a1	2026-06-19 06:58:36.736973+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bc3d77d9-5aa7-4b29-b2e8-76896dec2603	2026-06-19 06:58:46.200866+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
81d82fb8-5d33-4e57-95f1-19f868379e91	2026-06-19 06:58:48.008822+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
50c158f1-394b-466d-b1e3-6887963eff7f	2026-06-19 07:06:56.45553+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1310e8ae-af5d-4f2f-8418-0b998c0dd1c1	2026-06-19 07:07:09.085189+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
9d40139a-de5f-4488-bcee-ddd5f4711624	2026-06-19 07:08:01.469763+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
5c106a81-fc2f-4028-a5c6-fea0438ff5a4	2026-06-19 07:32:27.123903+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
81114ffc-7e1e-4bd0-b775-7b0966324b0d	2026-06-19 07:32:36.291949+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b19a9f83-d6c5-4628-9fe6-486eda4ae501	2026-06-19 08:10:58.922509+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ff0b371d-f2a6-4913-b7ab-e0eeb3edea77	2026-06-19 08:26:31.800622+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": false, "from": true}
b938f4d0-fe0a-4070-9620-892b7572f734	2026-06-19 08:26:32.468541+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	user.status.change	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"to": true, "from": false}
e49c468c-2ddc-4fa8-8683-dcafb5de9172	2026-06-19 08:35:29.450915+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2a8c2d16-cf61-41d4-a894-270a822adbde	2026-06-19 09:15:54.44441+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b7a1b240-ff2d-4bb9-a9b1-db74180842e1	2026-06-19 09:19:20.079817+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
be52b924-ddc6-45c0-a4fd-0c2ef8cd758b	2026-06-19 10:25:37.094009+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
92832235-16c0-45d0-877b-c2441b253e5b	2026-06-19 11:12:33.756803+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1e8eda6f-6455-405e-b3be-77602a85ba0b	2026-06-19 11:29:23.16754+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
87f94bea-5ce6-4147-a2ef-fb433d66f9cb	2026-06-19 11:59:24.59771+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a942519f-ca0f-4d01-9846-91da745dac3a	2026-06-19 11:59:41.448569+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
05c085aa-0c11-4a89-8589-8ca486b9b962	2026-06-19 12:00:43.56256+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
bafa577d-1b95-43c1-9599-4faf8b95778a	2026-06-19 12:00:53.512065+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a4bffa62-eabf-4e9a-b425-9885c606b146	2026-06-19 12:01:21.109738+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
0176132c-3d7f-4def-94ae-89ad6f2869f1	2026-06-19 12:01:31.204275+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
963e35fe-2ca5-41f2-9f5c-78ec872b2d89	2026-06-19 12:02:10.373394+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
b48f1766-590d-464c-abc4-a3ead40ddd22	2026-06-19 12:02:17.65462+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
97318ba0-af48-4e9a-839a-bccb0453480b	2026-06-19 12:02:31.105449+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
66bc4b6a-87ee-4c1a-b107-7b78728420f3	2026-06-19 12:02:40.984177+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
7d49baca-b288-4e65-831b-bad670c5a4b6	2026-06-19 12:02:46.858574+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
108654b6-cbee-43ff-b01e-90bac4ead165	2026-06-19 12:03:35.035034+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.login.success	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
43729e94-8b48-4776-94cd-21e6c1d2dc90	2026-06-19 12:03:57.637319+00	67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	employee	auth.logout	user	67188c2e-7217-40da-8222-7ff7b0cdc8b0	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2780aea1-cb85-4206-87a4-1b2b9d189aeb	2026-06-20 03:53:47.838317+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1ea99cf7-2dbf-4dae-8170-d0f5bb054470	2026-06-20 03:54:35.368122+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4289ff45-3848-441d-a7a7-72ab1c1e8e84	2026-06-20 03:54:46.758664+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e750df95-cd2f-4d57-9f28-05b3c75f38be	2026-06-20 03:55:24.820088+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
a0aa4498-2a97-4004-ab2f-eaaff0dc10e9	2026-06-20 03:55:32.887491+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
daa4c046-1cb5-4390-bf52-e62c9841cace	2026-06-20 03:57:03.16668+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
4afcfbe3-48c2-4c92-94c5-c0d5526ac75e	2026-06-20 03:57:12.658427+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
062fbef3-3d96-4c3a-8cd4-4236cfe57bb1	2026-06-20 04:25:28.869124+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.logout	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f9801dd6-aa5f-479d-b8b7-b8f36f561a87	2026-06-20 04:25:39.264616+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f34a3406-f61d-4a7c-a503-0a179f690969	2026-06-20 04:25:46.871531+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
6b151278-91b9-4b30-ab65-6d0d1adfd7bc	2026-06-20 04:25:55.23022+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
52764cc5-3f1e-4b87-b160-aa3fd2e183a9	2026-06-20 04:26:11.032801+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
352f2e53-9ccc-4a3b-8822-ecf1ec2afab9	2026-06-20 04:27:32.808287+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e194cc6e-e703-431a-a57a-f7f87eb1d22d	2026-06-20 04:27:34.673259+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
22d321a6-a155-4238-adce-4de2704ff299	2026-06-20 04:39:12.114685+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
82890a9f-525a-4bac-9861-645e069e5acd	2026-06-20 04:39:20.147674+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
c6276db1-15ad-48f6-a908-cf4fe013010b	2026-06-20 06:02:15.076173+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
343ef85e-d7e1-466d-b0fd-6d0147106068	2026-06-20 06:12:39.572339+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
454b0fd7-11cf-4c30-862a-e6045c659325	2026-06-20 06:12:48.106262+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d6d9306b-2d07-4a9d-8b47-3796c03092d4	2026-06-20 07:01:33.655855+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
82d68f55-62d8-4763-b96f-32f2611e48d1	2026-06-20 07:18:54.32782+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
41cde37d-1433-439d-88c7-2d5fdc0e3e6b	2026-06-20 08:16:23.408254+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
06cf1602-e003-49be-b3f7-586ec72b8cb2	2026-06-20 08:22:09.375992+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1c6c049a-1a37-4c90-99b1-1f540e4d0172	2026-06-20 09:17:19.986336+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
05d1cda9-9c32-4c19-a36e-c9e72fc304d6	2026-06-20 09:33:16.970464+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
e33cdce2-a5a8-454d-9be2-dd374cf2e730	2026-06-20 09:35:49.181303+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ed55aa5f-53bc-4a3e-85d4-712c106dfdb6	2026-06-20 09:35:57.52912+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
656b2d16-d2d1-4da0-9e91-2e18acd02b27	2026-06-20 09:42:29.379633+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
58d15e9a-7be3-431d-96d1-73b2f81439c1	2026-06-20 09:42:37.457522+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d0264358-1baa-4337-bcf3-0671516bb7df	2026-06-20 10:44:09.319827+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
1b523ae2-083b-4413-aff9-1f4ac42ef593	2026-06-20 10:44:30.385524+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
f3c335d9-e7ee-4f65-9556-ece3b7ebac86	2026-06-20 12:02:23.440008+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8ad59559-20d9-44dc-bd45-015a2e2558c7	2026-06-20 11:40:53.281053+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
12d1d6be-1fcc-4dc1-9ce8-2405f32db034	2026-06-20 11:41:18.48198+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
fa737088-35f7-4e6a-a990-be4a46c8c6e4	2026-06-20 11:44:40.743107+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
3c3d43d3-697c-4143-a861-c34135f3af96	2026-06-20 12:02:14.995278+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d5f48d17-182d-4c2d-9467-2337c3f1c7bc	2026-06-20 12:16:18.533731+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
70461043-98e2-492b-a12c-353e64bf86b7	2026-06-20 12:16:34.030745+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
251dbf04-f066-46e4-ab32-ffd8355d5044	2026-06-20 12:26:42.704757+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2a79387d-0931-409f-8044-0f4e2c9ffeba	2026-06-20 12:27:02.691163+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
8f1a3baf-7c9b-49fb-a5e9-bd718c25902f	2026-06-20 13:00:21.254346+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.logout	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2ab0ce90-60e6-48c3-873e-f0a88a86c9a6	2026-06-20 13:00:29.862938+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
33608597-8ef4-4820-9ac4-04e917a479b1	2026-06-20 13:09:36.055635+00	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	project_manager	auth.login.success	user	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
ff65b010-cd6b-491a-b084-5fe37addd8d3	2026-06-20 14:02:35.934381+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.login.success	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
d297198d-da3c-4ccd-84fd-93e2d4d3a8c6	2026-06-20 14:12:16.047645+00	9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	employee	auth.logout	user	9f946201-e71e-4356-b830-2dddae74e9f9	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
2075318a-cbdf-4780-a039-72ff1ccb3bda	2026-06-20 14:12:26.643535+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.failure	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	failure	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{"reason": "invalid_credentials", "attempted_email": "nainar@gmail.com"}
eebc8cb2-6ab4-49f9-96aa-a7693d9966ad	2026-06-20 14:12:32.394021+00	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	employee	auth.login.success	user	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	success	172.19.0.1	Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36	{}
\.


--
-- Data for Name: company_calendar_events; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.company_calendar_events (id, event_date, title, event_type, description, created_by, updated_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: daily_work_reports; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.daily_work_reports (id, employee_id, report_date, status, summary, total_minutes, submitted_at, reviewed_by, reviewed_at, review_note, created_by, updated_by, created_at, updated_at, day_status, location, remarks, query_text, well_head_no, pm_plant, task_list_count, task_list_op_count, maintenance_item_count, maintenance_plan_count, edit_requested_at, edit_request_note) FROM stdin;
aac55b99-c681-4d9e-ad73-5b4f150fda1d	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-19	submitted	\N	480	2026-06-19 04:41:19.541808+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-19 04:41:14.477151+00	2026-06-19 04:41:19.535876+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
70e0d64d-88e0-4000-859d-041a4b4c150b	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-20	submitted	\N	360	2026-06-20 12:26:22.415328+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:26:12.53462+00	2026-06-20 12:26:22.408734+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
2e8faded-23b5-42a3-a9c7-eceb63df3698	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-20	submitted	\N	480	2026-06-20 08:45:27.504369+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-20 08:45:10.607596+00	2026-06-20 08:45:27.499088+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
6f01a62f-c5d8-4e07-82db-9daafb3f11ae	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-08	submitted	\N	578	2026-06-11 09:22:37.832223+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-11 09:22:12.254611+00	2026-06-11 09:22:37.827755+00	office	chennai	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
7981001e-8a6b-468e-959a-4490412a7f33	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-16	submitted	\N	480	2026-06-20 12:17:12.371218+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:17:06.895038+00	2026-06-20 12:17:12.365393+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
dfb9c1ae-3383-4a43-8acb-9bd0226569a0	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-19	submitted	\N	480	2026-06-20 12:17:52.127734+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:17:50.796219+00	2026-06-20 12:17:52.123865+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
79e757e0-5b64-4f65-aa10-4df6846dc1d9	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-17	submitted	\N	540	2026-06-20 12:18:51.625219+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:18:49.653826+00	2026-06-20 12:18:51.621774+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
431de1dd-90c4-44f8-bbe5-49ec2193602f	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-01	submitted	\N	480	2026-06-18 10:42:12.453035+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-18 10:41:59.661587+00	2026-06-18 10:42:12.449527+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
f2aeef12-1011-4f4b-8cd6-3cea27d607ec	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-18	submitted	\N	480	2026-06-20 12:19:38.075488+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:19:24.564036+00	2026-06-20 12:19:38.071916+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
4b4c4614-7680-487e-b2d5-2be890c5e55f	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-16	submitted	\N	480	2026-06-16 10:43:00.616987+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-16 10:42:42.011906+00	2026-06-16 10:43:00.611606+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
5bf88bb7-a198-4cf8-8dfc-1250ee54ae09	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-15	submitted	\N	420	2026-06-20 12:22:58.690606+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:21:04.547713+00	2026-06-20 12:22:58.68679+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
079ace61-a9cf-436e-a717-fa621baea3b0	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-15	submitted	\N	480	2026-06-16 10:43:50.381676+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-16 10:43:29.309447+00	2026-06-16 10:43:50.373799+00	office	chennai	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
38e574b4-5a1c-4fc3-b3f6-9b7bac7f7e81	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-02	draft	\N	0	\N	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 12:59:32.957144+00	2026-06-20 12:59:32.957144+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
f148fe94-2dcd-4e8b-b9e3-00f82877a3e6	3107987e-7e92-4e89-97f3-1d5275e65485	2026-06-03	submitted	\N	0	2026-06-20 13:00:15.512209+00	\N	\N	\N	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	2026-06-20 13:00:01.633956+00	2026-06-20 13:00:15.505127+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
c65a2c33-ff92-4a55-9703-e0aadb0e9b0a	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-13	draft	\N	0	\N	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-20 13:00:50.635623+00	2026-06-20 13:00:50.635623+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
14f751dc-8c69-4142-838d-f9e7397b72c7	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-08	draft	\N	0	\N	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-20 13:12:17.60513+00	2026-06-20 13:12:17.60513+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
09849a5f-e738-4ab4-bdeb-14f4fba589af	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-06	submitted	\N	0	2026-06-20 13:13:21.062899+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-20 13:12:53.419248+00	2026-06-20 13:13:21.055987+00	office	chennai	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
d6e40df2-543a-4731-b87c-60ed0e446670	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-17	submitted	\N	480	2026-06-18 05:15:29.448007+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-18 05:15:26.347966+00	2026-06-18 05:15:29.443204+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
219d4a01-c2cd-47aa-8d1b-c4ac3659cdc3	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-18	submitted	\N	960	2026-06-18 05:17:46.25743+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-18 05:17:42.540199+00	2026-06-18 05:17:46.252002+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
845859b5-f91a-4956-88db-5d262cf1f97e	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-14	submitted	\N	480	2026-06-18 05:19:51.712111+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-18 05:19:24.599916+00	2026-06-18 05:19:51.708056+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
9155dd7a-3d33-4b74-9978-7c8a058fcc15	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-16	submitted	\N	480	2026-06-18 09:47:38.573821+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-18 09:47:36.185032+00	2026-06-18 09:47:38.568873+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
48ca50a7-8b2b-4332-987f-a5c385e04a22	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-15	submitted	\N	480	2026-06-18 09:48:19.35287+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-18 09:46:43.425995+00	2026-06-18 09:48:19.348647+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
a857ac14-1c15-43d8-b6a2-b74e189a4ea0	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-18	submitted	\N	480	2026-06-18 09:49:04.607191+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-18 09:49:02.938248+00	2026-06-18 09:49:04.603219+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
46de0335-6e37-4c6b-841e-cb6c0b4b5400	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-12	submitted	\N	480	2026-06-18 09:55:54.475432+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-18 09:55:32.158932+00	2026-06-18 09:55:54.470904+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
bf096e33-db9d-4f2c-a6aa-900334d4d621	e5ce164a-f805-4970-80be-cbd21533d1d0	2026-06-17	submitted	\N	480	2026-06-18 09:57:08.601558+00	\N	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-18 09:57:06.425051+00	2026-06-18 09:57:08.596751+00	office	chennai	\N	\N	\N	\N	0	0	0	0	\N	\N
7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	d595afe7-1dd9-4c83-ba17-d8fc11a14724	2026-06-05	submitted	\N	540	2026-06-11 06:18:46.513401+00	\N	\N	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	2026-06-11 05:50:24.320239+00	2026-06-11 06:18:46.510163+00	office	chennai	\N	tags are not valid\n	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: employees; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.employees (id, user_id, employee_code, first_name, last_name, work_email, phone, department, designation, manager_id, date_of_joining, status, created_by, updated_by, created_at, updated_at, deleted_at, office_id, reporting_pm_id, personal_email) FROM stdin;
44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	MGR-001	Alex	Manager	\N	\N	Engineering	Engineering Manager	\N	\N	active	\N	\N	2026-06-03 08:29:38.753384+00	2026-06-03 08:29:38.753384+00	\N	\N	\N	\N
e5ce164a-f805-4970-80be-cbd21533d1d0	9f946201-e71e-4356-b830-2dddae74e9f9	EMP225	Santhosh	Kumar	cdccmms@gmail.com	9042946902	IT	Developer	\N	2026-03-16	active	2173ab41-9c1b-4d0c-b100-e69e754116cc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 05:30:38.857212+00	2026-06-06 06:33:31.02404+00	\N	42019185-c95d-4a26-b1c9-2acb1a467d3c	\N	\N
3107987e-7e92-4e89-97f3-1d5275e65485	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	EM2160	NAINAR	B	nainar-cdc@gmail.com	1234556660	Engineering	Engineer	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	2026-06-06	active	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 05:01:27.537142+00	2026-06-06 09:29:23.827231+00	\N	3d90ad52-0d01-44eb-a25b-713ddca502ad	\N	\N
d595afe7-1dd9-4c83-ba17-d8fc11a14724	67188c2e-7217-40da-8222-7ff7b0cdc8b0	EM001	EMP	1	emp1-cdc@gmail.com	9090909090	IT	Tool Dev	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	2026-06-06	active	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 07:13:56.239118+00	2026-06-09 06:35:37.240296+00	\N	42019185-c95d-4a26-b1c9-2acb1a467d3c	\N	\N
\.


--
-- Data for Name: export_jobs; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.export_jobs (id, requested_by, export_type, status, params, filename, file_data, row_count, error, created_at, updated_at, completed_at) FROM stdin;
47bab195-db01-4d03-9910-0a5be3e8890c	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	employee	success	{"preset": "monthly", "date_to": "2026-06-30", "date_from": "2026-06-01", "employee_id": "d595afe7-1dd9-4c83-ba17-d8fc11a14724"}	employee_2026-06-01_2026-06-30.xlsx	\\x504b03041400000008009653ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008009653ca5cc0a2078505010000fa01000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9bb4d321a1cb8d1f2028880e14ef42f26e0be68be49d6dffbd6db7758ade79999ce73c9c904606267d84a7e80344d490b2ce1a97980cab7c8718182149eec08a540e841bc28d8f56e0708c5b1284fc105b2035a54b6201851228c8282cc26ccc8f4a256765d8473309942460c082c344aab222671621daf467614a66b24b7aa6dab62ddbc5c40d8b2af2f6f8f0328d2fb44b289c849c374a321941a08f7c7c51e83bd3906f9723801a0df07ba7f4a7567b61b25b1b8cef01b267083ee2543840cd71eaa10f2a1b0631ec03acf253f2bab8be59dfe5bca6f5b2a0cba2a2eb8ab2fa8a5d5cbe8fa61ffdb3d07aa537fa1fc6938037e4d737f32f504b03041400000008009653ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008009653ca5cd761f52c9d0200004d09000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d96cb72db2014865f85d1bed1c5d7646ccf246e3bcd22534fd2cb1a4b47160de2a880e37ad787e813f6490ac896b510d433b60582ff3f1f600e2c0e285f5505a0c9af9a0bb58c2aad9bbb38567905355537d880302d25ca9a6a5395bb58351268e144358fb32499c63565225a2ddcbb8d5c2d70af3913b09144edeb9acae303703c2ca3343abf7866bb4abb17f16ad1d01dbc80feda1881a9c69d4fc16a108aa12012ca65749fde3da41327715dbe3138a85e99d8d16c115f6de5b158468985020eb9b61ed43cde600d9c5b2b83f2f3e41a5da25a65bf7cb6ffe826c0f06da98235f2efacd0d5329a47a48092eeb97ec6c327380daa45cc912bf74b0e6de76c1a917caf34d627b5095c33d13ee9aff36cf414e3c4a3c84e8aac456f4339d0f754d3d542e28148dbddd8d9821bae931b3e26ece2bc68695a99d1e9d5a328d81b2bf694930f75c3f108409ea141a917b136feb6579c9baff1edcc479df9c899671ef32123a77b185d8f13e018771ce320c7b0554b32f6699e36240dc49e74b12757c5266b2c0601265e802409014c3b806910e07359b27c30f2d4a3585720046581d8b32ef62c187b03926131147be6516449367d97984f4a3492736d940460e61dcc3c0c2341c1e0bf71ee51d42874c58f81d8b75decdb60ec7bad411454e4400a7a544310b71e6968e86972d9e64910e00b6ab3a76c96848254b897830cd66418e22688d1cb36e97fd6007f989cac4e24830cbe5415da0c697621c8aec8498afcfdfdc79c48db9a999519e6f0390467e2921ad36b7263cb419b46e29b07c3972a83d371c98c693835f63124d8b5f160f8f26470362e49320d67c93e46216939b84d535faa1c64887b87a2bd663c51b96342110ea531496e66c64db6c7765bd1d8b873728bda1cbbae5899eb0e48dbc1b49788baabd8b3b7bb41adfe01504b03041400000008009653ca5c187b3f80e8010000da04000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d94db6edb300c407f45d007d4499a6443611b58d3052db0a14583aecf8a4dc74264c993e8baddd78f929cac582ec88b2d523c142fa2d2ded8adab0190bd374abb8cd788ed4d92b8a28646b82bd382a69dcad84620897693b8d6822803d4a864321acd934648cdf334e89e6c9e9a0e95d4f06499eb9a46d88f5b50a6cff898ef14cf725363502479da8a0dac005f5a02484cf67e4ad98076d26866a1caf8b7f1cd3212c1e29784de7d5a339fccda98ad171eca8c8fb8f7ad817dac5a25e37168da1f50e10294228713ce4481f20d9ec82ce36b83681abf4f81a2405255d6fc011d0f0505644cd1b407d6d1cbe0d5a7f97b8898ffcbc887f579bd8b7d198a4bb9af85838551afb2c43ae35f392ba1129dc267d3dfc350b059705818e5c297f5d1783ce2ace81cc533d074702375fc8bf75da52f212603313920c62788eb81b83e20a62788e9404c0f88f909623610b38bf3980fc43cb620962c14fc4ea0c8536b7a66bd39b9f38bd0b69004d5596a7f8157686957128739419026489ebc9c1403757b9e5ad4506cd9833e422e2e211f3b3c82de9d475f690ea064f7a6b3ee08fdfd3cfdf8061669f04ef2cbf3fc8a06a7fb8f4ba8d8bbab1fabef67fea7b01ba91d53344234ad575fa8b936def328d0b0867ec6490bcb9ade1eb0de80f62b63702ff826ef9fb3fc2f504b03041400000008009653ca5ca5f2328693020000ee06000018000000786c2f776f726b7368656574732f7368656574332e786d6c8d95db72da3010865f45e38bde35c60e8724359e213621991260eca4b956ec05d4d8962b0948faf45dc986d26033bd011df6fb57abf5aebc1d176f720da0c87b9e157268ad952a6f6c5b266bc8a9bce02514b8b3e422a70aa76265cb52004d0d9467b6dbe9f4ed9cb2c2f23db3b610bec7372a63052c04919b3ca7e2e31632be1b5a8eb55f88d86aadcc82ed7b255d410ceab94400a7f6412765391492f18208580ead917333710d612c7e30d8c9a331d1c1bc72fea6270fe9d0ea585abb00f2119719abdc295e4e61a902c8321444359a28b685059a0dad57ae14cff53e1e5451854b4bc17f435139850cd0184f539e58572ab5aa0ef3577d62eb6f44fa58c7e3fdd9efcce562ecaf5442c0b31796aaf5d0bab2480a4bbac954c477f7505f58cf08263c93e697ec2a630723493612cf53d3e8386745f54fdff7377d4c745b08b726dccf44bfd3425cd6c4e5898f7e0bd1ad89ee09d1e6a35713bd13e2aa85e8d744ff84e8b510839a185449ab2ed9a428a48afa9ee03b22b439cae98149b4091b33c30afdc9c74ae02e434ef90881672b54d2733ba9a9dbf3d442f09ff8999180a74d74f07ff48ce64d74789e1ee9af98a98f06727c9ebce71b211bb0bbf3d80b562c0941268295bab21a1426e7152228b95024c66add7c3a808df93a24cd3d24cd357a5da3a7bbd6d6eff69dc1b5676f8f93e4b6f89b04ceb5d31960db6b4a4e1bb5b81fc5e3af0e0983987ca179f98dccc64f2ff3e83b795e4ca2513826a359482a2b9704f3d953349f4ec751bcdf6fca659bb3701ea004e2c1d3c37cd6944bf738f87f03bf6b53c5c664da5fb122294f9a723d694369590abe85b4293df6517de977e0918a152b24c9b0ad6207bf1860b18aaaf755136ce0a662abee6b866b7c8f406803dc5f72ae0e135dc68727ceff03504b03041400000008009653ca5c869fa4ddef010000c203000018000000786c2f776f726b7368656574732f7368656574342e786d6c7d53db72d33010fd158d1e78a34a4c294cb13d931b84212419bba5cf4abcb64565cb484adcf2f5ac24278481f2626b2fe7ecd9d52aee957e343580254f8d6c4d426b6bbb5bc6ccbe86869b2bd5418b9152e9865b3475c54ca781171ed448168d4637ace1a2a569ec7d5b9dc6ea60a56861ab8939340dd7cf5390aa4fe8989e1c99a86aeb1d2c8d3b5e410ef6be43009aeccc5388065a23544b3494099d8c6fa79147f88c6f027a737126ae999d528fcef85c2474441d770be439efa408e5acea5650da19488984c8c6f7561c618b6909dd296b55e3e228d4728bae52ab9fd086a2200193514df757766019585d9b3f06c5f477474ed6e5f9a4fda31f2ef6bee306664a3e88c2d6097d4f4901253f489ba97e09c3c0de7ac2bd92c67f491f926f4694ec0f06f50c682cdc8836fcf9d369d21788f1f50b8868408449b350ca0b9d73cbd358ab9e68978e74eee0db4de81b9c6d4245eb2e3eb71aa3027136dd6af51dc716338b64cec5f60370fa7fe0521db4212b555550fc896628e1ac233aeb885e52b09ce48bd763329fe5e4156fba0f64bdb87bd8645fc8fdf65336992fc8643d27212b22b3cdfa2edbac568b2c3fc5ffa53d14735b7f4caf6376bc54c62ea6e576fb2bd795680d91b82ab89557eff01275b8cf60e052faf9878df2c71adf18689780f152297b36dca59c9f6dfa0b504b03041400000008009653ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b03041400000008009653ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008009653ca5c989c0e5265010000f30200000f000000786c2f776f726b626f6f6b2e786d6c8d926f4bc3400cc6bf4ab90f60e79c82c30ae2f00f888a137d7d6b531b777729b9d4a99fde5ccbb43018bebae649fabbe4c99d6d88d72ba275f6e95d88732e4c23d2cef33c960d781b0fa885a0b99ad85bd190df72aa6b2c614165e721483e9d4c4e7206670529c406db6806da7f58b165b0556c00c4bb01e52d06737eb6edec91b37c1c9140996e4a6a525e1036f1af2085d907465ca143f92a4cffedc0641e037afc86aa301393c5863637c4f84d41ac5b964cce15e67048bc000b963bf232b5f96c57b157c4ae9ed2cc85399928b0468ed257f47cab4d7e80160f512774854e801756e09aa96b31bcf5181d231fcdd15bb13db3603d1466d9796ff92b35a1e26d3534244a1a8dc773d404df560373fcff850884ca86124688e91ec47407f1aaf6664fd0124b1c418ef6408e7620babc775dde1830db03980de66c1da9a0c600d5bda2624ae87e4a7d1ce9e82d99ce8e0f4f750f9d7397aa3d843bb2d5afc5dbf771fe03504b03041400000008009653ca5c49ca0b6ec2000000b10300001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73cd93390e83301045af62f9004c58421101551ada2817b06058c462cb3351c2ed8348019652a441a1b2fe587eff15e3e486bde2568fd4b486c46be8474a65c36c2e0054343828f2b4c171bea9b41d14cfd1d66054d1a91a21389d62b05b86cc922d53dc2783bf107555b5055e75f11870e42f60786adb5183c852dc95ad915309af7e1d132c87efcd6429f23295362f7d29e0df468163141cc028748cc20318458e51b4a711f1d423ad3a9fecf49ff7ece7f92daef54bfc0cddd58d1709707e68f606504b03041400000008009653ca5cd393bfe42801000072050000130000005b436f6e74656e745f54797065735d2e786d6ccd54cb4ec33010fc9528d72a712988036a7a01aed0033f60924d63d52f79b725fd7b360e8d042a2d552ad18b2d7b6767c63b92e76f3b0f98b4465b2cd286c83f088165034662ee3c58aed42e18497c0c2be165b9962b10b3e9f45e94ce1258caa8e34817f327a8e54653f2dcf2352a678b3480c63479ec819d56914aefb52a25715d6c6df54325fb52c8b93362b0511e270c4813715022967e55d837be6e21045541b294815ea4619868b540da69c0fc38c70197aeae5509952b37865b72f40164850d00199df7a49313d2c443867ebd196d20d21c5564e832388f9c5a80f3f5f6b174dd99672208a44e3c729064eed12f842ef10aaabf8af3843f5c58c74c50c46dfc98bfe73cf09f6b64762d466eafc5c8dd7f1a79776e7de92fa0db7323951d0c88f8d52e3e01504b010214031400000008009653ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008009653ca5cc0a2078505010000fa0100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008009653ca5c995c9c23100600009c2700001300000000000000000000008001f7010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008009653ca5cd761f52c9d0200004d090000180000000000000000000000808138080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008009653ca5c187b3f80e8010000da04000018000000000000000000000080810b0b0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008009653ca5ca5f2328693020000ee0600001800000000000000000000008081290d0000786c2f776f726b7368656574732f7368656574332e786d6c504b010214031400000008009653ca5c869fa4ddef010000c20300001800000000000000000000008081f20f0000786c2f776f726b7368656574732f7368656574342e786d6c504b010214031400000008009653ca5c81a25029e20200002a0d00000d0000000000000000000000800117120000786c2f7374796c65732e786d6c504b010214031400000008009653ca5cb747eb8ac0000000160200000b00000000000000000000008001241500005f72656c732f2e72656c73504b010214031400000008009653ca5c989c0e5265010000f30200000f000000000000000000000080010d160000786c2f776f726b626f6f6b2e786d6c504b010214031400000008009653ca5c49ca0b6ec2000000b10300001a000000000000000000000080019f170000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008009653ca5cd393bfe428010000720500001300000000000000000000008001991800005b436f6e74656e745f54797065735d2e786d6c504b0506000000000c000c0010030000f21900000000	1	\N	2026-06-10 10:28:45.282166+00	2026-06-10 10:28:45.304948+00	2026-06-10 10:28:45.315595+00
17d48cc0-21bb-4930-8127-98bae04f9f3c	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	attendance	success	{"date_to": "2026-06-30", "filters": {"year": 2026, "month": 6}, "date_from": "2026-06-01", "employee_ids": null}	attendance_2026-06-01_2026-06-30.xlsx	\\x504b0304140000000800ca50ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800ca50ca5cc99231cc01010000f901000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9bb4835e842e2013af1c880e14ef42f26e0de68be495b6ffdeb6db3a45efbc4cce731e4e482b03933ec253f401226a48d9608d4b4c866dde21064648921d5891ca89705378f4d10a9c8ef14482901fe204a4a6b4211650288182ccc222acc6fca254725586cf68168192040c587098485556e4c622449bfe2c2cc94a0e49af54dff765bf59b8695145def68f2fcbf842bb84c249c879ab24931104fac8e7178571302df9763903a8d100df7b879d19b33b44706aae67cf107cc4853f33ed65e9b90e2a9bf6301c036cf36bf2bad9dd1f1e725ed3ba29685354f45051461b5657efb3e947ff26b45ee9a3fe87f12ae02df9f5cbfc0b504b0304140000000800ca50ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800ca50ca5cc0618cafee0100002a05000018000000786c2f776f726b7368656574732f7368656574312e786d6c9554cd8eda30107e152bf76e428050a11009b6addac34a08baedd92403b1d6f1a4f65096b7efd881940344ad94c41e7bbe1f3b1ee727b46fae0620f1de68e316514dd4cee3d8953534d23d610b8667f6681b491cda43ec5a0bb20aa046c7699264712395898a3c8cad6d91e391b432b0b6c21d9b46daf30a349e16d128ba0e6cd4a1a6301017792b0fb0057a6d19c061dcf354aa01e3141a6161bf8896a3f96a161021e3878293bbe90bbf981de29b0fbe558b28f19e4043499e4272f31b9e416bcfc44e7e5d48a3bfa21e79dbbfd27f09eb677b3be9e019f54f5551bd883e46a282bd3c6adae0e92b5cd6340d84256a17bee2d425a75924caa3236c2e68166e94e95af97edd8c1bc4247980482f88b4b3de4905a39f24c922b77812d6a7339def84e50638fb53c6ff9b2d599e558ca3e2050dd5fa2c9644602a694a101b68d1521e13d3fba4b8e497697bee71cf3d0edce903ee7b4401b71affb39b011b93dec664d0c61aacc2ea9e8dc903449aa4d987849f912014d7689c0c9899f666a683663e37adc63380bbe767fa00b4d47a403aeba5b341e9ef485273359568abbbf2d9a3ed18109ff5e2b341f12d493abab9e00bc481b97b2866ff231fdf1c797f87bc487b50c6090d7b26499e66bc97b62bca2e206c4315ec90b8a842b7e6bb0cac4fe0f93d22f581afacfe7a2cfe00504b0304140000000800ca50ca5cb9789263c50200009209000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d96db729b3010865f85e1010c069fc7f64ce31cec69d378e26973adc0623401894ac24efaf45d09e2921811e7c2d161bfd5aefe45d2fcc8c58b4c0194f39a674c2edc54a962e679324a2127b2c70b603893709113855db1f7642180c406ca332ff0fd919713cadce5dc8c6dc572ce4b9551065be1c832cf8978bb828c1f176edf7d1f78a4fb5499016f392fc81e76a07e150860d73bf989690e4c52ce1c01c9c2fdd69f6d4243188bdf148eb2d1767432cf9cbfe8ce265eb8beab7d3370de764546abe5142f7e40a2569065e830701d12297a802d9a2ddc67ae14cff53c06aa88c2a144f0bfc0aa45210334c6688a33ebca4bed55a7f9a78ed8fd9f910eabd97e8ffdd66c2ee6fe4c24ac78f64463952edc89ebc4909032538ffcb8867ac386c661c433697e9d6365acc7a352623c358d0be79455ffc9ebfb4e37899185086a2238237c0b11d64478460416625013838bd718d6c4f08ce85b88514d8cce88818518d7c4f8e2bd9ad4c4e4e23ca63531ad0aa312d294c13551643917fce8086d8eee74c31493d95a549f32fd59ed94c0598a9c5adee445c6df009c158f61ee2974a927bca8c6af2ec47f92bc0d5f75e30f4942a336eeba9bc354dba89b6e6a9542f4e26c580b797b09f950aa16f4ae1b7dc233056267cd4b215be8f5171b7400a1f010b3f29b6e7e878750f989f3b0444e75129cea24b0497cbf0d82615b69d8881d612ae53275be977854b755858dc47d668cd0b682084c9e0303eabbe2b01c8cfae3f1dc3b340bc0e6d89fcefca04d771bd01fcffcb6a4ef824604939e3ff41b7ffd8fd1ac9bb67e4ffb6b4e6f6c6be3fd2881a90ed5c2936ad60fd3aa9ab554be54ade3ebb0a916b6a936093fa96673ac551bb5a9660350b570daa65af841b561a76ae107d5869f55b3addda19ad7389ff55be59e883d65d2c9f0eac757466f8c9792a8eee7aa838f0c73e2572f04d34cf1cd04421be07cc2b93a75f435707a862dff01504b0304140000000800ca50ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b0304140000000800ca50ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800ca50ca5c397ef814460100006d0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ac34010855f25ec03983468c1d214c4a21644c54aef37d94933747fc2eca4b57d7a7713a20141bcdacc99c9b7e7cc2e4f8e0ea57387e4d368eb17548886b95da4a9af1a30d25fb9166ce8d58e8ce450d23e75758d15ac5dd519b09ce659364f09b46474d637d87a31d0fec3f22d8154be0160a307949168c56a393a7ba3249d568ea18a3745352a3b8493ff19886572448f256ae47321fa6f0d223168d1e00554213291f8c69d9e1ce1c559967a5b91d3ba10b3a1b10362ac7ec9db68f34396be575896ef317321e65900d6489efb899e2f83c92384e1a1ead83da066a0b5647824d7b568f73d26c4482739fa558c6762a581426c3b63249da389206ed460880369128f16181ab4510373faff1d3358256d051344fe07221f6c8d5e14d46841bd04988f8db0992a3c4b3c7a33f9f5cdec366ca0d3fa3e68aff6d949f51d6e7c99d517504b0304140000000800ca50ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800ca50ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800ca50ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800ca50ca5cc99231cc01010000f90100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800ca50ca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800ca50ca5cc0618cafee0100002a050000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800ca50ca5cb9789263c5020000920900001800000000000000000000008081580a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800ca50ca5c81a25029e20200002a0d00000d00000000000000000000008001530d0000786c2f7374796c65732e786d6c504b01021403140000000800ca50ca5cb747eb8ac0000000160200000b00000000000000000000008001601000005f72656c732f2e72656c73504b01021403140000000800ca50ca5c397ef814460100006d0200000f0000000000000000000000800149110000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800ca50ca5cab5e722eb40000008d0200001a00000000000000000000008001bc120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800ca50ca5ca5e11b581f010000600400001300000000000000000000008001a81300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000f81400000000	2	\N	2026-06-10 10:03:29.915738+00	2026-06-10 10:06:21.290039+00	2026-06-10 10:06:21.306124+00
af8e75f2-bde9-4d67-b8e8-7f1443942ea8	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	attendance	success	{"date_to": "2026-06-30", "filters": {"year": 2026, "month": 6}, "date_from": "2026-06-01", "employee_ids": null}	attendance_2026-06-01_2026-06-30.xlsx	\\x504b0304140000000800e850ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800e850ca5cb17b870a02010000f901000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9bb4830e4217188a570e44078a772179b706f345f24ad77f6fdb6d9da2775e26e7390f27a49581491fe129fa001135a4ec648d4b4c864dde21064648921d5891ca91706378f0d10a1c8ff14882901fe208a4a6b42116502881824cc2222cc6fca254725186cf68668192040c587098485556e4c622449bfe2cccc9429e925ea8beefcb7e3573e3a28abced1e5fe6f1857609859390f35649262308f4914f2f0ac3c9b4e4dbe504a046037ce71d7666c8b688e0d454cf9e21f888337f66dacbd2731d5436ee613804d8e4d7e4757577bf7fc8794deba6a04d51d17d45195db36afd3e997ef46f42eb953ee87f18af02de925fbfccbf00504b0304140000000800e850ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800e850ca5cc0618cafee0100002a05000018000000786c2f776f726b7368656574732f7368656574312e786d6c9554cd8eda30107e152bf76e428050a11009b6addac34a08baedd92403b1d6f1a4f65096b7efd881940344ad94c41e7bbe1f3b1ee727b46fae0620f1de68e316514dd4cee3d8953534d23d610b8667f6681b491cda43ec5a0bb20aa046c7699264712395898a3c8cad6d91e391b432b0b6c21d9b46daf30a349e16d128ba0e6cd4a1a6301017792b0fb0057a6d19c061dcf354aa01e3141a6161bf8896a3f96a161021e3878293bbe90bbf981de29b0fbe558b28f19e4043499e4272f31b9e416bcfc44e7e5d48a3bfa21e79dbbfd27f09eb677b3be9e019f54f5551bd883e46a282bd3c6adae0e92b5cd6340d84256a17bee2d425a75924caa3236c2e68166e94e95af97edd8c1bc4247980482f88b4b3de4905a39f24c922b77812d6a7339def84e50638fb53c6ff9b2d599e558ca3e2050dd5fa2c9644602a694a101b68d1521e13d3fba4b8e497697bee71cf3d0edce903ee7b4401b71affb39b011b93dec664d0c61aacc2ea9e8dc903449aa4d987849f912014d7689c0c9899f666a683663e37adc63380bbe767fa00b4d47a403aeba5b341e9ef485273359568abbbf2d9a3ed18109ff5e2b341f12d493abab9e00bc481b97b2866ff231fdf1c797f87bc487b50c6090d7b26499e66bc97b62bca2e206c4315ec90b8a842b7e6bb0cac4fe0f93d22f581afacfe7a2cfe00504b0304140000000800e850ca5cb9789263c50200009209000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d96db729b3010865f85e1010c069fc7f64ce31cec69d378e26973adc0623401894ac24efaf45d09e2921811e7c2d161bfd5aefe45d2fcc8c58b4c0194f39a674c2edc54a962e679324a2127b2c70b603893709113855db1f7642180c406ca332ff0fd919713cadce5dc8c6dc572ce4b9551065be1c832cf8978bb828c1f176edf7d1f78a4fb5499016f392fc81e76a07e150860d73bf989690e4c52ce1c01c9c2fdd69f6d4243188bdf148eb2d1767432cf9cbfe8ce265eb8beab7d3370de764546abe5142f7e40a2569065e830701d12297a802d9a2ddc67ae14cff53c06aa88c2a144f0bfc0aa45210334c6688a33ebca4bed55a7f9a78ed8fd9f910eabd97e8ffdd66c2ee6fe4c24ac78f64463952edc89ebc4909032538ffcb8867ac386c661c433697e9d6365acc7a352623c358d0be79455ffc9ebfb4e37899185086a2238237c0b11d64478460416625013838bd718d6c4f08ce85b88514d8cce88818518d7c4f8e2bd9ad4c4e4e23ca63531ad0aa312d294c13551643917fce8086d8eee74c31493d95a549f32fd59ed94c0598a9c5adee445c6df009c158f61ee2974a927bca8c6af2ec47f92bc0d5f75e30f4942a336eeba9bc354dba89b6e6a9542f4e26c580b797b09f950aa16f4ae1b7dc233056267cd4b215be8f5171b7400a1f010b3f29b6e7e878750f989f3b0444e75129cea24b0497cbf0d82615b69d8881d612ae53275be977854b755858dc47d668cd0b682084c9e0303eabbe2b01c8cfae3f1dc3b340bc0e6d89fcefca04d771bd01fcffcb6a4ef824604939e3ff41b7ffd8fd1ac9bb67e4ffb6b4e6f6c6be3fd2881a90ed5c2936ad60fd3aa9ab554be54ade3ebb0a916b6a936093fa96673ac551bb5a9660350b570daa65af841b561a76ae107d5869f55b3addda19ad7389ff55be59e883d65d2c9f0eac757466f8c9792a8eee7aa838f0c73e2572f04d34cf1cd04421be07cc2b93a75f435707a862dff01504b0304140000000800e850ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b0304140000000800e850ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800e850ca5c397ef814460100006d0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ac34010855f25ec03983468c1d214c4a21644c54aef37d94933747fc2eca4b57d7a7713a20141bcdacc99c9b7e7cc2e4f8e0ea57387e4d368eb17548886b95da4a9af1a30d25fb9166ce8d58e8ce450d23e75758d15ac5dd519b09ce659364f09b46474d637d87a31d0fec3f22d8154be0160a307949168c56a393a7ba3249d568ea18a3745352a3b8493ff19886572448f256ae47321fa6f0d223168d1e00554213291f8c69d9e1ce1c559967a5b91d3ba10b3a1b10362ac7ec9db68f34396be575896ef317321e65900d6489efb899e2f83c92384e1a1ead83da066a0b5647824d7b568f73d26c4482739fa558c6762a581426c3b63249da389206ed460880369128f16181ab4510373faff1d3358256d051344fe07221f6c8d5e14d46841bd04988f8db0992a3c4b3c7a33f9f5cdec366ca0d3fa3e68aff6d949f51d6e7c99d517504b0304140000000800e850ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800e850ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800e850ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800e850ca5cb17b870a02010000f90100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800e850ca5c995c9c23100600009c2700001300000000000000000000008001f4010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800e850ca5cc0618cafee0100002a050000180000000000000000000000808135080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800e850ca5cb9789263c5020000920900001800000000000000000000008081590a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800e850ca5c81a25029e20200002a0d00000d00000000000000000000008001540d0000786c2f7374796c65732e786d6c504b01021403140000000800e850ca5cb747eb8ac0000000160200000b00000000000000000000008001611000005f72656c732f2e72656c73504b01021403140000000800e850ca5c397ef814460100006d0200000f000000000000000000000080014a110000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800e850ca5cab5e722eb40000008d0200001a00000000000000000000008001bd120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800e850ca5ca5e11b581f010000600400001300000000000000000000008001a91300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000f91400000000	2	\N	2026-06-10 10:07:17.132756+00	2026-06-10 10:07:17.150511+00	2026-06-10 10:07:17.161639+00
23b98fd2-546c-4505-aee8-7ca44eb7b1f2	9f946201-e71e-4356-b830-2dddae74e9f9	attendance	success	{"date_to": "2026-06-10", "filters": {"year": 2026, "month": 6}, "date_from": "2026-06-10", "employee_ids": ["e5ce164a-f805-4970-80be-cbd21533d1d0"]}	attendance_2026-06-10_2026-06-10.xlsx	\\x504b03041400000008006451ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008006451ca5c4023239201010000f901000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9ba48322a12b88e29503d181e25d48deadc17c91bcd2f6dfdb765ba7e89d97c979cec3096964e0d247788a3e40440d291bac7189cbb0cd3bc4c00949b2032b5239116e0a0f3e5a81d3311e4910f2431c815494d6c4020a255090595884d5989f954aaecaf019cd22509280010b0e13612523571621daf46761495672487aa5fabe2ffbcdc24d8b1879db3dbe2ce30bed120a27216f1b25b98c20d0c7767e511807d3906f9733801a0db43befb03363768b084ecdf5ec19828fb8f027a6392f3dd54165d31e8e63806d7e495e3777f7fb87bcad685517b42e18dd33ca19e3f4e67d36fde85f85d62b7dd0ff305e046d437efd72fb05504b03041400000008006451ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008006451ca5c28abe525eb0100002805000018000000786c2f776f726b7368656574732f7368656574312e786d6c9d544b8f9b3010fe2b16f75d0849481501d266dbaa3dac14257d9c1d98046b6d0fb52765f3ef6b9b84cd21416d0fc08c3ddfc3c6e3bc43f36a1b00626f4a6a5b440d51bb8c635b35a0b87dc416b49bd9a3519c5c6a0eb16d0df03a80948cd324c962c5858eca3c8cad4d99e391a4d0b036cc1e95e2e6b402895d114da2cbc0461c1a0a037199b7fc005ba0efad03b8341e786aa1405b819a19d817d1d364b95a0444a8f821a0b35731f38bd921befae46b5d4489f704122af214dc7d7ec33348e9999c935f67d2e85dd423afe30bfde7b07e676fc72d3ca3fc296a6a8ae843c46ad8f3a3a40d765fe0bca67920ac50daf0665d5f9c6611ab8e96509dd14e5809dd7ff9db6533ae10b3e40e223d23d2de7a2f158c7ee4c4cbdc60c78c2f77743e08cb0d70e74f68ff6fb664dcac70382a5f5053234fec890874cd75056c032d1aca6372f4be28aedce36807eee9c03d0ddce91dee5b4401b79afeb59b111bb3c1c66cd4c61a8cc0fa968dd91d449aa4d943923d4c1246c8deb31133f3c1cc7cd4cc27d54a3c01d85b7ee677409311e16c10ce4685bf2171e97aa94253df14cffe437c31882f46c5b7c4e96897cc5d1f16f4cd23b1f817f9f8eac0fb1be4859b83d09649d83b92e471e176d2f42dd927846de8811d926ba91036ee2603e30bdcfc1e9186c4f7d57039967f00504b03041400000008006451ca5c62a4d2e586020000dc07000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d95db72da3010407fc5e30fc0c6dc19e39986248569d33061da3c2bf61a6bb025579221e9d767252bd429368507d065cf6a6fec86472ef6320350ce6b9133b97033a5cab9e7c9388382c81e2f81e14dca4541146ec5ce93a5009218a8c8bdc0f7c75e412873a3d09c6d4414f24ae594c14638b22a0a22de6e20e7c785db773f0e9ee82e53e6c08bc292ec600bea6789006ebd939e8416c024e5cc11902edc2ffdf93a308491f845e1281b6b473bf3c2f95e6fd6c9c2f55dad9b81f3b62d735a3fa778f91d52b5843c4785a88dc48a1e6083620bf7852bc50b7d8f862aa2f02815fc0fb0fa51c80185d19af24cbad662b56a377f5b8bddbf1e69b39aeb0fdbef4d70d1f7172261c9f3679aa86ce14e5d27819454b97ae2c715d8808d8cc298e7d27c3bc75a589fc795447b2c8d0f1794d5bfe4f523d24d62dc41049608ce08bf831858627046041dc4d012c3abdf1859627446f43b88b125c667c4b0839858627275aca696985eedc7cc12b3ba30ea449a32b8258a44a1e04747687154a717a6984c6831fb94e9bfd55609bca5c8a9e8ae2873fe06e02c7902a1a750a5bef0628bdf5c89ff20451bbebc8c3fa6298ddbb8dbcb1cbada46dd5da69619c47b67cd5ac8fb6bc8c74ab5a05f2fa3cfd853207156bc12b2855efd274007100a9b5827bfbecc6fb10955ff701e96c8a94e82539d045d297ed804c1a8ad34ba882d612ae33273be55d8aadbaaa28bc4383346685b4104c6cfa101f5ac3844c3717f3a08bd43b300ba14fbb3b93f6ecb7b17d09fcc07b3b66c070d0ba6bdd1c86f7cfa9fad5935657d94fd7cbdee7a1be7a304a6dab2e635fee97aea3d10b1a34c3a390e119c57bd09b6375177fa7a83e3caf48e7ad6986586d3178416c0fb947375dae886721ae8d13b504b03041400000008006451ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b03041400000008006451ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008006451ca5c397ef814460100006d0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ac34010855f25ec03983468c1d214c4a21644c54aef37d94933747fc2eca4b57d7a7713a20141bcdacc99c9b7e7cc2e4f8e0ea57387e4d368eb17548886b95da4a9af1a30d25fb9166ce8d58e8ce450d23e75758d15ac5dd519b09ce659364f09b46474d637d87a31d0fec3f22d8154be0160a307949168c56a393a7ba3249d568ea18a3745352a3b8493ff19886572448f256ae47321fa6f0d223168d1e00554213291f8c69d9e1ce1c559967a5b91d3ba10b3a1b10362ac7ec9db68f34396be575896ef317321e65900d6489efb899e2f83c92384e1a1ead83da066a0b5647824d7b568f73d26c4482739fa558c6762a581426c3b63249da389206ed460880369128f16181ab4510373faff1d3358256d051344fe07221f6c8d5e14d46841bd04988f8db0992a3c4b3c7a33f9f5cdec366ca0d3fa3e68aff6d949f51d6e7c99d517504b03041400000008006451ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008006451ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008006451ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008006451ca5c4023239201010000f90100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008006451ca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008006451ca5c28abe525eb01000028050000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008006451ca5c62a4d2e586020000dc0700001800000000000000000000008081550a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008006451ca5c81a25029e20200002a0d00000d00000000000000000000008001110d0000786c2f7374796c65732e786d6c504b010214031400000008006451ca5cb747eb8ac0000000160200000b000000000000000000000080011e1000005f72656c732f2e72656c73504b010214031400000008006451ca5c397ef814460100006d0200000f0000000000000000000000800107110000786c2f776f726b626f6f6b2e786d6c504b010214031400000008006451ca5cab5e722eb40000008d0200001a000000000000000000000080017a120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008006451ca5ca5e11b581f010000600400001300000000000000000000008001661300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000b61400000000	1	\N	2026-06-10 10:11:08.38032+00	2026-06-10 10:11:08.396998+00	2026-06-10 10:11:08.408225+00
3e74a1cb-bde6-4dae-9542-95077a61d782	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	attendance	success	{"date_to": "2026-06-14", "filters": {"year": 2026, "month": 6}, "date_from": "2026-06-08", "employee_ids": null}	attendance_2026-06-08_2026-06-14.xlsx	\\x504b03041400000008001d54ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008001d54ca5c7eb05bc902010000f901000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9b7e60c1d00544f1ca81e840f12e24efd660be485e69fbef6dbbad53f46e97c979cec3096985a7c205780ece43400531198cb6910abf493b444f0989a203c3633e11760af72e188ed3311c88e7e2931f805445d11003c825474e6661e657637a524ab12afd57d08b400a021a0c588ca4cc4b7261118289ff1696642587a856aaeffbbcaf176e5a5492f7edd3eb323e533622b70252d64a4145008e2eb0f9457e1c744b7e5cce002ad4c0b6ce62a7c7e40e11ac9cebc90b781770e18f4c7b5a7aac834ca63d14470f9bf49cbcd5f70fbbc7945545d564459395c5ae2c685dd19bdb8fd9f4ab7f111a27d55e5d613c0b584bfefc32fb06504b03041400000008001d54ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008001d54ca5c9cb9467dee0100002a05000018000000786c2f776f726b7368656574732f7368656574312e786d6c95544b8fda3010fe2b56eedd840061854224d8b66a0f2b21e8e36c928158eb78527b28cbbfefd881940344ad94c41e7bbe871d8ff313da37570390786fb4718ba8266ae771ecca1a1ae99eb005c3337bb48d240eed2176ad05590550a3e33449b2b891ca44451ec6d6b6c8f1485a19585be18e4d23ed79051a4f8b68145d0736ea505318888bbc9507d8027d6f19c061dcf354aa01e3141a6161bf8896a3f96a161021e3878293bbe90bbf981de29b0fbe568b28f19e4043499e4272f31b5e406bcfc44e7e5d48a3bfa21e79dbbfd27f0eeb677b3be9e005f54f5551bd889e2351c15e1e356df0f4052e6b9a06c212b50b5f71ea92d32c12e5d1113617340b37ca74ad7cbf6ec60d62923c40a41744da59efa482d18f9264915b3c09ebd399ce77c272039cfd29e3ffcd962ccf2ac651f18a866a7d164b2230953425880db468298f89e97d525cf2cbb43df7b8e71e07eef401f73da2805b8dffd9cd808d496f633268630d566175cfc6e401224dd2ec43c2cfb32014d76834193033edcd4c07cd7c6a5a8d670077cfcff40168a9f58074d64b6783d2df90a4e66a2ad15677e5b307c06c407cd68bcf06c5b724e9e8e6822f1007e6eea198fd8f7c7c73e4fd1df22aed41192734ec9924799af15edaae28bb80b00d55b043e2a20add9aef32b03e81e7f788d407beb2faebb1f803504b03041400000008001d54ca5c8d021645ad0300000010000018000000786c2f776f726b7368656574732f7368656574322e786d6c95975d73ab361086ff0ac37dcd87f9b2c7f64ce2731c33ad73dc64da73add87260021215729cf4d757128402d6624e2e12407a76577a77a5ece242d95b9960cc8d8f3c23e5d24c382fe696551e129ca372420b4cc4c889b21c71f1ca5eadb260181d159467966bdb8195a39498ab85fab667ab053df32c2578cf8cf29ce7887ddee38c5e96a6637e7d784a5f13ae3e58ab45815ef133e67f150210af5663e798e69894292506c3a7a579e7cce350116ac6df29be94ad67432ee685d237f9121f97a66d4adb041b9fcf459656ee382dfec027bec659260cbaa6810e3c7dc77b316d69be50ce692ec745a01c71f1e9c4e8bf98544e7186c564114d7135bbb2525b95cbfca78ed8fc7f4532acf6f357ec1bb5b962ed2fa8c46b9afd4c8f3c599a91691cf1099d33fe442f5b5c6f98af0c1e6856aadfc6a59a2cbf1fcea588a7a685e33c25d55ff4f1b5d36d220008b726dc2bc20688694d4caf081720bc9af046fbf06bc2bf221c80086a22b8223c80086b221cbd57514d44a3d731ab8959951895902a0dbe218e560b462f0693d38539f9a092496dad503f25b2ac9e3913a3a9e0f8ea7b5e64f41363634d8f78617161520e58871abf1f893fa25c87af87f11fa7537ad071df8639b1541df57d985a27f8f066c444436ec6903fce5c833e0ca33fc599828fc6969e59a9a1b73736e81d332e0e31908f87f96771089d7b9c2552a4c913b7c913179278e73a81ad4b0d8878bc8b1fef9e8c7b5d3e40cc9f2279992e115cb53e4f61f28e785f798113b90bebbd2d3c64d69ecd6d47a7370438d1dc0e742abbad0866133bea06b06d0f3b57c331e44e5c8525267c40a06923105883bbbdebfa3a81c0ac408427b44c8cdfcfb976d7d7038540084a75424d4709051906858200279c4f239d50d35604d1247066ed9f9e6aedb9f624e8051b43be6fabe635aa79bf5c561031545610039695a7556bda530b322bd5d265dc0602845a9e6eb10f5e472dbf5f565e47a0fe700cb9bb2d90df08e40336760f4fbfd9da9cbc8790bb0c7f183b44c4bfa3daaaea73eace5772f8a3e480fc4a39a63a39204016cf4c2787df2d9e9e1a7eb75c7a6240ce6e8b1134620460b50052c0c0ded0016b081838d98251e24086ed68eeebf67a0301b256746a3e041d71c25e00dba0a34e7f3886dcdd96276ce4097ff90a8288db5710440e08158e120a322cab4877f56f2000aca2b07ba8f976ebc7e9a916764f38bfa71ae47b4035abd50dc8ce7887d86b4a4a23138da6e86927a12854567583d58b6869557f51f5a3ea31111d3a667282183f51ca9b17d974344dffea3f504b03041400000008001d54ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b03041400000008001d54ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008001d54ca5c397ef814460100006d0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ac34010855f25ec03983468c1d214c4a21644c54aef37d94933747fc2eca4b57d7a7713a20141bcdacc99c9b7e7cc2e4f8e0ea57387e4d368eb17548886b95da4a9af1a30d25fb9166ce8d58e8ce450d23e75758d15ac5dd519b09ce659364f09b46474d637d87a31d0fec3f22d8154be0160a307949168c56a393a7ba3249d568ea18a3745352a3b8493ff19886572448f256ae47321fa6f0d223168d1e00554213291f8c69d9e1ce1c559967a5b91d3ba10b3a1b10362ac7ec9db68f34396be575896ef317321e65900d6489efb899e2f83c92384e1a1ead83da066a0b5647824d7b568f73d26c4482739fa558c6762a581426c3b63249da389206ed460880369128f16181ab4510373faff1d3358256d051344fe07221f6c8d5e14d46841bd04988f8db0992a3c4b3c7a33f9f5cdec366ca0d3fa3e68aff6d949f51d6e7c99d517504b03041400000008001d54ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008001d54ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008001d54ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008001d54ca5c7eb05bc902010000f90100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008001d54ca5c995c9c23100600009c2700001300000000000000000000008001f4010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008001d54ca5c9cb9467dee0100002a050000180000000000000000000000808135080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008001d54ca5c8d021645ad030000001000001800000000000000000000008081590a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008001d54ca5c81a25029e20200002a0d00000d000000000000000000000080013c0e0000786c2f7374796c65732e786d6c504b010214031400000008001d54ca5cb747eb8ac0000000160200000b00000000000000000000008001491100005f72656c732f2e72656c73504b010214031400000008001d54ca5c397ef814460100006d0200000f0000000000000000000000800132120000786c2f776f726b626f6f6b2e786d6c504b010214031400000008001d54ca5cab5e722eb40000008d0200001a00000000000000000000008001a5130000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008001d54ca5ca5e11b581f010000600400001300000000000000000000008001911400005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000e11500000000	6	\N	2026-06-10 10:32:59.001962+00	2026-06-10 10:32:59.018513+00	2026-06-10 10:32:59.027134+00
c229436c-99a5-42de-b68c-21daecbf0ee9	9f946201-e71e-4356-b830-2dddae74e9f9	employee	success	{"preset": "weekly", "date_to": "2026-06-14", "date_from": "2026-06-08", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}	employee_2026-06-08_2026-06-14.xlsx	\\x504b03041400000008008051ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008008051ca5c1ea794e504010000fa01000011000000646f6350726f70732f636f72652e786d6ca5915d6bc3201885ff4ac87da2a6900b49bdd9070c36185b616377a26f5b9946d1b74bf2ef97a46dbab1ddf552cf731e8ed8a8c0958ff01c7d80880652d63bdb26aec23adf23064e48527b70329523d18ee1d64727713cc61d09527dca1d908ad29a3840a9254a32098bb018f39352ab45190ed1ce02ad085870d06222ac64e4c2224497fe2dccc942f6c92c54d77565b79ab9711123ef4f8faff3f8c2b40965ab20178d565c4590e8a3985e1486de36e4c7e504a0410be2a1d5e6cbe883b4d99d0bd60f00d90b041f712e1ca1e634f5d8079d8d83380e01d6f939795bdddc6eee7351d1aa2e685d30ba6194b38a53fa31997ef52f42e7b5d99a2b8c678168c89f6f16df504b03041400000008008051ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008008051ca5cabc5fb11aa0200005709000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d96cb8e9b3018855fc562dfe192eb8c924893b45547d5a851a697b5033fc18db1a96d86c9ae0fd127ec93d436096181dd4821d8e073fe0f0cc72c1a2e8eb20050e8ada44c2e8342a9ea210c655a4089e51daf80e93339172556ba2b0ea1ac04e0cc8a4a1a2651340d4b4c58b05ad8635bb15af05a51c2602b90accb128bd31a286f96411c5c0eecc8a150f640b85a54f8002fa0be555aa0bb61e793911298249c2101f932788c1fd6f1c44aec90ef041ad96b2373357bce8fa6f3942d83c840018554190fac77afb0014a8d9546f975760dae558db2dfbed87fb43740f3edb1840da73f48a68a65300f500639aea9daf1e6139c2faa454c3995f61f35ede0641aa0b4968a9767b52e5c12d6eef1dbe56ef414e3c8a148ce8aa4456f4b59d0f758e1d542f00609335cdb9986bd5c2bd77c8499c97951429f255aa7564f2c23af24ab31451fca8af21300da41c5855a844afb9b5161aa37eddb998f3af391354f1ce6434656b71edd8ee3e118771c632fc7b0554b3276685e3053059705fa5ceba7d60331e920263741a00dcf0649262ee1f33649261e82694730f5127cc973920e969e3a149b0218c3c4537bd6d59e796b6f41109e0dd59e391449944cdf45fa37478aa34b2f1e7b60e61dccdc0f2340c2e0733977281a80233d794adf77a5efbda51f950296619602caf0490e31dc3ba4b1a77c1c5ddff7c80bf0952bfd7299b8840c15bc16830cc664503ebf9bf81ec5b8973bf17fe680ffd4e92ccf288310aed04a7c04c99520b9219d24fafbfb8f5e9bf625d15333cce172887c1cd7908c6f49c996035795e0af0e0c57688e7c18d78c8cfd21d9c71060e6c681e14a4cefddb8a664ec8fc93e4626703ef89ac6aeac1c64087bcba3f9e078c6e240984414726d12ddcdb49b6817f0b6a3786557cc3d577a01b6cd427ff8803003f4f99c73d575cc2adc7d4badfe01504b03041400000008008051ca5c57aec44234020000f105000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d946d6f9b3010c7bf0ae203948724348d00694d1bb5d2a6468db6be76c211ac189bd926b4fbf43b1b92d105a2f2027cf6fdce777fec8b1b210faa00d0ce7bc9b84adc42eb6ae1796a574049d48da880e34a2e6449349a72efa94a02c92c54322ff4fdc82b09e56e1adbb9b54c63516b4639aca5a3eab224f2e31e98681237704f13af745f683be1a57145f6b001fdb342004def1c27a3257045057724e489fb2d58ac424b588f5f141ad51b3ba698ad1007633c6789ebbb263607e7635331da6ea745f51d72bd04c6302046233b4d8fb046b7c4dd0aad4569d631514d344ee552fc01de6e0a0cd019b3a92ebcdb285d5453e6ef2e63f75f4526adfef894fbca8a8bb56f8982a5606f34d345e2ce5d27839cd44cbf8ae6093ac16636e04e3065df4ed33a0758c9ae56984f47e3c625e5ed97bc9f94ee13fe0811764478410423c4a4232617c474849876c4f4828846885947ccbe5c47d41151fb0b5ac9ace00f44933496a271a471c77066607f9b2d0275a6dc1ce08d96b84a91d32942107b1a2319dbdb75d4fd756a59c0eee03cf30172f915f2a5d603e8c375f40def0164ce93a8a51aa01fafd32f47901a2fde28bfbace6ff0e2d4ff711e8a7d563c3c2b1eda40531bc83490633a8d82f924f68e7d85c3918dfcbb851f0d093b0604b78bc9dd909c612f83f9cd6ce6f79ee073368f7d5f1f7d3f2fafc6f6c6a6a980eb2159bcdea134adf007917bca95c3b0b36013bbb9c5332fdbebdf1ad8c3ec316f1b901d16d892411a075ccf85d067c39cfd73974fff02504b03041400000008008051ca5c4715aff68a030000bd0a000018000000786c2f776f726b7368656574732f7368656574332e786d6ccd96df93a23810c7ff952eaeea6af7e1060574a676d52a8488d6287a803bb58f8c46e516081be2b8b37ffd7580f15c8758fb782f9a1ffde9eef43721199c18ff561e2815f0234bf372a81d84283ee97ab939d02c2eef5841739cd9319ec502bb7caf9705a7f1b682b254373a9dbe9ec549ae8d06d5d88a8f06ec28d224a72b0ee531cb62fe3aa6293b0db5aef6361024fb83a806f4d1a088f734a4625d20805dfdec679b64342f139603a7bba166773f79564554165f127a2a2fda2017f3ccd837d9996d875a4793be730aaf6191267538c18a39dd0987a6293a343488372279a12b341b6acf4c0896c9794c54c40287769cfda4791d94a6148d319be29d75eda5f12a97f9bdc958fb6f4532adcbf65bee93aab8b8f6e7b8a40e4b9f92ad380cb5070db674171f5311b0d3943605eb550e372c2dab5f38d5c65d5cc9e658623e0d8d81b324afffe31f6f95be242c05613484714df43b0ac26c08f39a305431ac86b0de65a58ad16b88de35619a0aa2df10fd77317a0ae2be21ee6bd1ea225712b9b1884703ce4ec0a539ba938d4ae86ad9a84c92cb2d1f0a8eb309726284101de8023dc9bebe69a8f16d6ac5d93fb8cdc061db36daf93dda8fb336dabd4ddb721727e2b58524b7c9293bf2b2059bdcc69ef0c4824bcb0d4f0a79b25a3c78b73d04b4605c4088a7f57895808e7a9d4533cea219953fabf227bf5a2f23abdf7d3006facba5488622dedc318c6ec7ea753a6de2a828b29a393059061090d5dc76c882f8112c27b01c87cb39890884ced42733970440fe5ecf56d5fc07f3ce7cfc02e1d32c72a61eb1838f30f3e1716a47b3aff614fc65104dc1255e40ec70e67b104638b3f4e183bb4623ff639bfeaa04dda5030b3b8c308115e6680795abb67d605c14aef36bd126b7bccfdc719bba2a242e0ace5ee8f686a4e65952b355d2ee95a4aa2d745b5215f5bf9154f92998dbbe2f9dfc1967c567990e71d7731c6853d5bca8ddc395aaaa007855551762be872ddbb49d7e4f85fe86bad6595dab555df34a5d4b11caabd435efdbd55551eb9517d82e81684ac075421d48e8ea132f84f02b1e9205d811cc49f087d1b3c1f6ddf32c0ee3d119ffe582efcd21b2fd4798d8c1a24d3655e405219154cd233e09ec799b58d60db19465a039e5710a19de6652b153220ef01daf350e82c6599b782a57b7c4d32fae4bf9ac5bc47c9fe425a4f84ac207d9dd3ddebdbc7ecad41d7c8f551770fd98aa9a077c5e522e0d707ec7983877e4ad7c7eb18efe05504b03041400000008008051ca5c3f2bba16660200009d04000018000000786c2f776f726b7368656574732f7368656574342e786d6c7d544d739b3010fd2b3bea2539347270936632c08c0cb26162630a38991c892ddb3480a890eda4bfbe0b38d49d26b980f6e33dbd5d76310f523dd75b2134bc1479595b64ab75754b69bddc8a22ad2f64254a8caca52a528da6dad0ba52225db5a022a7c660704d8b342b896db6be50d9a6dce93c2b45a8a0de1545aa5e472297078b5c923747946db6ba7550dbacd28d88855e54084093f63cabac10659dc91294585b845dde8e862da2cdb8cfc4a13e394353cc9394cf8de1af2c32200d7729e035aef2acbb4ecb6a2ad6da11798e84068174a9b3bd0831cd224f526b59347114aa538daeb592bf45d95d2a7281c9a8a6fa2fbb6339b23665fe3a2a267f2b6a649d9edfb48fdbe662ed4f692d1c993f642bbdb5c80d819558a7bb5c47f2e08963c3ae5ac2a5ccebf609872ef97a4060b9ab51cf118d171759d9bdd397b74e9f202ebf7d80308e08a393de5dd50a75539ddaa69207504d3ad23587b65c8be087417d59d97cf8582b8c6688d376a8e44f6c9b493592352eba3c02479f033db953354ce5662356ffa2294ae87518bd0ee303221efa0e8ce711443c9c3287cf7890c07c0cf3513c9ff28443ec7801f75d1e01ffb1f0c3367e36bc18dedd43fce0278e37e12c3a073f803b8f25fe23f320984789072e9f449cc57e308138c1c83c8033778149c1f97bf576029b4dd9db3726ddbf53cdb0afe6a3b62cc249c45c0e89c7c175620a3c76e9781243fc18277c062c81298fbe18570c58e0f65174b3888dbeba104ca690b0e00ec62c9abd2773f8894c7a3208cddace52b5c9ca1a72dc025cb88bef389faa1bd5cec07d6b47ab5b96f6b8c5df87504d02c6d752eade68e6adff23d97f00504b03041400000008008051ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b03041400000008008051ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008008051ca5c989c0e5265010000f30200000f000000786c2f776f726b626f6f6b2e786d6c8d926f4bc3400cc6bf4ab90f60e79c82c30ae2f00f888a137d7d6b531b777729b9d4a99fde5ccbb43018bebae649fabbe4c99d6d88d72ba275f6e95d88732e4c23d2cef33c960d781b0fa885a0b99ad85bd190df72aa6b2c614165e721483e9d4c4e7206670529c406db6806da7f58b165b0556c00c4bb01e52d06737eb6edec91b37c1c9140996e4a6a525e1036f1af2085d907465ca143f92a4cffedc0641e037afc86aa301393c5863637c4f84d41ac5b964cce15e67048bc000b963bf232b5f96c57b157c4ae9ed2cc85399928b0468ed257f47cab4d7e80160f512774854e801756e09aa96b31bcf5181d231fcdd15bb13db3603d1466d9796ff92b35a1e26d3534244a1a8dc773d404df560373fcff850884ca86124688e91ec47407f1aaf6664fd0124b1c418ef6408e7620babc775dde1830db03980de66c1da9a0c600d5bda2624ae87e4a7d1ce9e82d99ce8e0f4f750f9d7397aa3d843bb2d5afc5dbf771fe03504b03041400000008008051ca5c49ca0b6ec2000000b10300001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73cd93390e83301045af62f9004c58421101551ada2817b06058c462cb3351c2ed8348019652a441a1b2fe587eff15e3e486bde2568fd4b486c46be8474a65c36c2e0054343828f2b4c171bea9b41d14cfd1d66054d1a91a21389d62b05b86cc922d53dc2783bf107555b5055e75f11870e42f60786adb5183c852dc95ad915309af7e1d132c87efcd6429f23295362f7d29e0df468163141cc028748cc20318458e51b4a711f1d423ad3a9fecf49ff7ece7f92daef54bfc0cddd58d1709707e68f606504b03041400000008008051ca5cd393bfe42801000072050000130000005b436f6e74656e745f54797065735d2e786d6ccd54cb4ec33010fc9528d72a712988036a7a01aed0033f60924d63d52f79b725fd7b360e8d042a2d552ad18b2d7b6767c63b92e76f3b0f98b4465b2cd286c83f088165034662ee3c58aed42e18497c0c2be165b9962b10b3e9f45e94ce1258caa8e34817f327a8e54653f2dcf2352a678b3480c63479ec819d56914aefb52a25715d6c6df54325fb52c8b93362b0511e270c4813715022967e55d837be6e21045541b294815ea4619868b540da69c0fc38c70197aeae5509952b37865b72f40164850d00199df7a49313d2c443867ebd196d20d21c5564e832388f9c5a80f3f5f6b174dd99672208a44e3c729064eed12f842ef10aaabf8af3843f5c58c74c50c46dfc98bfe73cf09f6b64762d466eafc5c8dd7f1a79776e7de92fa0db7323951d0c88f8d52e3e01504b010214031400000008008051ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008008051ca5c1ea794e504010000fa0100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008008051ca5c995c9c23100600009c2700001300000000000000000000008001f6010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008008051ca5cabc5fb11aa02000057090000180000000000000000000000808137080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008008051ca5c57aec44234020000f10500001800000000000000000000008081170b0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008008051ca5c4715aff68a030000bd0a00001800000000000000000000008081810d0000786c2f776f726b7368656574732f7368656574332e786d6c504b010214031400000008008051ca5c3f2bba16660200009d040000180000000000000000000000808141110000786c2f776f726b7368656574732f7368656574342e786d6c504b010214031400000008008051ca5c81a25029e20200002a0d00000d00000000000000000000008001dd130000786c2f7374796c65732e786d6c504b010214031400000008008051ca5cb747eb8ac0000000160200000b00000000000000000000008001ea1600005f72656c732f2e72656c73504b010214031400000008008051ca5c989c0e5265010000f30200000f00000000000000000000008001d3170000786c2f776f726b626f6f6b2e786d6c504b010214031400000008008051ca5c49ca0b6ec2000000b10300001a0000000000000000000000800165190000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008008051ca5cd393bfe4280100007205000013000000000000000000000080015f1a00005b436f6e74656e745f54797065735d2e786d6c504b0506000000000c000c0010030000b81b00000000	4	\N	2026-06-10 10:12:00.109134+00	2026-06-10 10:12:00.130256+00	2026-06-10 10:12:00.146182+00
600a28aa-2020-4f33-8a51-fdcf4046bfdb	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project	success	{"preset": "weekly", "date_to": "2026-06-14", "date_from": "2026-06-08", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_2026-06-08_2026-06-14.xlsx	\\x504b03041400000008002252ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008002252ca5ccad2573100010000f301000011000000646f6350726f70732f636f72652e786d6ca591414ec3301045af12659f8c9d8a2059a93720562021a854c4ce72a6ad218e2d7b50dadbe3a46d0a825d97f67ff3f4c76eb417da057c0ece63208331dbdbae8f42fb65be23f20220ea1d5a15cb44f429dcb86015a563d88257fa536d112ac66ab048aa55a46014167e36e62765ab67a5ff0add2468356087167b8ac04b0e179630d8f8efc094cce43e9a991a86a11c1613971a71787b7a7c9dca17a68fa47a8db96c5a2d7440452ec871237fd8770dfcb81c0132d4a14c8ff2819ab2b58998bda0778126f29836a78ec7416cb3d444d0c1e3323f27ebc5ddfdea219715abea82d505672bce04bf15ece67d34fd9abf08ad6bcdc65c613c0b64037ffe577e03504b03041400000008002252ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008002252ca5c06a59b8542020000e705000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d54c992da3010fd1595efc10b609829a0ca9865a84906174be62c70831564cb91443c73cb3f245f982f8924c0e1603b53e545add65b5a2af5a060fc24120089de529a89a19548993fdab6d8279062d16239642a73603cc55285fc688b9c038e0d28a5b6e738be9d629259a381998bf868c0ce92920c228ec4394d317f1f0365c5d072addbc48a1c136926ecd120c7475883dce60aa042bbe489490a99202c431c0e432b701fc77d83302bbe1228c4dd18e962768c9d74b0888796a33d0185bdd41458fd7e4008946a26e5e4fb95d4fa27aa91f7e31bfdccd4afecedb08090d15712cb64682933311cf099ca152b9ee05a53d710ee1915e68b8acb62cfb7d0fe2c244baf68259c92ecf2c76fb7cdb843749c1a8477457817eb1729637482251e0d382b10d7cb159d1e98720d5cf923993e9bb5e42a4b144e8e22cebea94d42af44005a41ceb81cd85211ebb4bd57af222c59db256bdbb07a35ac554406376e7fc04783814e69a0d368e04a57e5a053039987ee83ebb80f8e83fefcfc8da6d12244b3e50a4db6cf4fc10b8a56cbc936dc2c962f6816848bcf8bcd62ba46db68be0a2653143d05eba91b28e42f1405e173309f22b7a18e6e5947b7b90ee084c55565746b109ee3f99f1cf5f49164e816b99d06337e69c6ffcfa68280ca3df56b1005c089be3748f74ae95ea3f486494ccd25473a25aa4cf46ab04e837ebfd4ef7f403f61675e29ddaf936e558adb77f75537c02f981f4926108583a2715a3d75b8fcd2512e8164b9b9c23b26554730c3443562e07a81ca1f189365a0db42d9db477f01504b03041400000008002252ca5c54b763da320200009806000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d956d6fdb2010c7bf0ae203d4699e5bd996daa45d5a6d539468eb6b629f63566c3cc04db34fdfc390ac5a9ccc6f120eeef7e780bb73b893ea55e70086bc17a2d411cd8da96e83402739144c5fc90a4a5cc9a42a9841536d035d296069031522e8f77ae3a060bca471d8cc2d551ccada085ec252115d170553fb7b107217d16b7a9858f16d6e9a89200e2bb68535981f15026806479d9417506a2e4ba2208be8ddf5edb3231a8f9f1c76fad398d8c36ca47cb5c6531ad11eb5da2590fdba12dc6d6764f5153233032150b04f094b0c7f8325ba4574238d91855dc7400d33389529f9074ab7290840678ca63af1762a5ed51ef3b78f98fe3d910debf3f810fb6373b978f60dd33093e285a7268fe894921432560bb392bb05f80b1b35828914baf9253be77cdda324a935c6e369dcb8e0a5fb67ef879bee42f43dd1ef4c0c3c31e84c0c3d313c21a6678891274627c4e80c31f6c4b87354134f4c4e88c11962ea89e909313c43dc78e2a63361c3754fd873c9e41ebf499d39332c0e95dc11650114b48326019be7c08ce1a52dc5b551b8ca9133f1435109b9070803836a762e483c797f99c4eddaa8d965eaced60637fb16727e995cc85ae916ece132f6827d80cc41278a57b65e5b141e2f2baca092ca9035f680ba2d802fffc3dfb0be41b5908b2e243973d14f97e1a592bfb04391994cdbe8e76ef47756fc4307986087c6e532ce76ec6f4c6d79a989c00688bdf66a8285a85c977206b6da268b5d9f6c86397e394059075ccfa43447c326f6f163147f00504b03041400000008002252ca5cfdd7243cc5020000900c00000d000000786c2f7374796c65732e786d6cdd576d6f9b3010fe2b881f3042c8589892481b5aa449db54a9fdb0af261862c92fcc982ae9af9fcf2640da1e6d27f5cb889af8eef173cf9d7d36eaa635674e6f8f949ae024b86cb7e1d198e67314b5872315a4fda01a2a2d52292d88b1a6aea3b6d194942d90048f968b451a09c264b8dbc84eec85698383eaa4d9868b3088769b4ac9d1b50abdc3ce258206f7846fc39c705668e62713c1f8d9fb97ce73505ce9c0d86ce8368c9dab7df013e2de8454fb588249a59d37f232febbe809d7f4d50b1371c427a5ebc216b9d8bb67ca703fad6532ce87d293d03b769b861843b5dc5bc3939cf729d68fefce8d2dbdd6e41c2f3f86af67b48ab31244eb7c9a6ebc5f7dfbb476710a14892651073df763cb2a942ea91e0a8bc38b6bb7e1b432c0d7ac3eba81518d5352c62801a392915a49e22bbfd0fa818d7da09cdf4253feaeae044e55e0bbeb7be91a0b56f832b459f5431fa63740601ace079fc45dfd5bdc86dd2bf3b5b3054967ffe994a1379a56ece4ec53352680858fdf37fcf27dc32763f8e5a3f0a469f8f90b67b514d4efddab15771b72e10547a5d983558323073d1506f7541b7600fb6027d0fe909faa7e9387fd75bb7dd53a8337803b671bfe82bb8c4f2a2d3ac60d93bd75646549e5d30eb2f10d29ec6d7925606795b4221d377703b80dc7f14f5ab24e64c3ac1b588c7ed638fe01c7254ec7bbc58a3159d2132df3deb467f4eab0fac7311e43930be92984b23c884000a25a681a28cbf350adffb1ae355e9707d10cd7cf436b9cb5c6599ef72c94bb0faa85b032fb2025675992a429babc79fe7c1a39ba86690a7f48403443e0a05aa0f6d6959f698099b679a137d05d9e6d1bb4e49916454b9e5979809035044e96210d806a0107dd14b4a32009440b5a0d612509ec339a217acc67a02c43216852a47bd3145ba8143ec87ea1872849b20c810044d248121482033b03a1694022289424fe45fae87d165dde73d1f83fc8ee2f504b03041400000008002252ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008002252ca5cc70e0c5a480100006f0200000f000000786c2f776f726b626f6f6b2e786d6c8d91d14ec3300c457fa5ca07d0ad82494c2b2f4cc024046843e3396dddd55a12578ebbb17d3d49ab412524c453ea6bf7e45e677124de1744fbe4d31ae7e79cab46a49da7a92f1bb0da5f510b2ef46a62ab2594bc4ba9aeb18425959d0527693699cc5206a305c9f9065baf06da7f58be65d0956f00c49a0165353a75b7b8387be3241d572450c69ba21a952dc2d1ff0cc43239a0c7020dca2957fdb70195587468f10c55ae262af10d1d9f88f14c4eb4d9944cc6e46a3a34b6c082e52f79136dbeebc2f78ae8621d33e76a3609c01ad94b3fd1f375307980303c549dd0031a015e6a8147a6ae45b7eb3121463acad1afe272264e5bc8d5a6b356f3299a08e2aa1a0c49208de2f11c438357d5c01cffff117693aca125163f82647f40b2c1d8c54d05353aa85e02cec746d84d191e261ebd9decfa667a1b76d019731fb457f74cbafa8e77799bbb2f504b03041400000008002252ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008002252ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008002252ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008002252ca5ccad2573100010000f30100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008002252ca5c995c9c23100600009c2700001300000000000000000000008001f2010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008002252ca5c06a59b8542020000e7050000180000000000000000000000808133080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008002252ca5c54b763da32020000980600001800000000000000000000008081ab0a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008002252ca5cfdd7243cc5020000900c00000d00000000000000000000008001130d0000786c2f7374796c65732e786d6c504b010214031400000008002252ca5cb747eb8ac0000000160200000b00000000000000000000008001031000005f72656c732f2e72656c73504b010214031400000008002252ca5cc70e0c5a480100006f0200000f00000000000000000000008001ec100000786c2f776f726b626f6f6b2e786d6c504b010214031400000008002252ca5cab5e722eb40000008d0200001a0000000000000000000000800161120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008002252ca5ca5e11b581f0100006004000013000000000000000000000080014d1300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a00840200009d1400000000	0	\N	2026-06-10 10:17:05.359761+00	2026-06-10 10:17:05.376923+00	2026-06-10 10:17:05.391736+00
0cc6f272-c3ac-404d-8f04-c8c94620dda4	9f946201-e71e-4356-b830-2dddae74e9f9	project_mandays	success	{"preset": "monthly", "date_to": "2026-06-30", "date_from": "2026-06-01", "project_id": "5a119e5f-cdf8-42b3-bc96-95fd7a03025e"}	project_mandays_2026-06-01_2026-06-30.xlsx	\\x504b0304140000000800e35dca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800e35dca5c636a33fd02010000f601000011000000646f6350726f70732f636f72652e786d6ca591cb4ec33010457f25ca3eb193a254b2526f40aca884a012889d654f5b43fc903d28c9dfe3a46d0a821d4b7bce3dba63b7d233e9023c06e721a086980da6b39149bfc98f889e1112e5118c8865226c1aee5d3002d3311c8817f2431c80d49436c4000a2550904958f8c5989f954a2e4aff19ba59a024810e0c588ca42a2b72651182897f06e6c9420e512f54dff765bf9ab9d4a822afdb87e7b97ca16d446125e4bc5592c900025de0d3467e1cba967cbb9c00d4d8014f8ff20e12b3adb04a8c317b02ef02cef00968cf354f5950592ac370f4b0c92f9397d5edddee3ee735ad9b823645457755c56ed68caedf26d38ffc55689cd27bfd0fe345c05bf2eb8bf917504b0304140000000800e35dca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800e35dca5c1286eca4a0020000ec07000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d556d73a23010fe2b997c6f515eda9b8e3083c879cca97594ebcd7d4c354aa640b8106b7bbffef242292a60bf6892dd67779f67437674a4eca54c30e6e02d4bf3d28509e7c58361949b0467a8bca505ce8565475986b8d8b2bd51160ca3ad0265a9610e06774686480ebd913a5b326f440f3c25395e32501eb20cb1f7314ee9d18543f871b022fb84ab03c31b15688fd798ff2a04406c8d3ace9664382f09cd01c33b17fac387d05108e5f144f0b16cac8124f34ce98bdc445b170ea08c9d63f0b62e52a2d3bd7f2e392d6678c7039ca62e1c9b10a00d27af7829102e7ca69cd34c95298ae6888bb31da3ff70ae0bc02916dea2b242b98b58956f8b51c792b97acc155cd7a06bf2a55e7f2beaf0531ac9afb9fe10e1bbea9210f1199538a0e96fb2e5890bbf41b0c53b7448f98a1e7fe04a792de486a6a5fa0547ed3cbc876073284541155a24ce48aeffd1db47cb9a08ab03615608f302d195c3aa10d639c2ecca615708fbcb55391542f337b4004abe09e2c81b317a044cba8b7072a19aa0ef8b0b492eeff59a33612502c73d3f88a3a728fe3332b88826cf8c4d851cf723c3f96030bc09e74b306c0107d7c0e6f06e70b3f0a385bf02e39600936b0196a6e9dcac51ce135a26e0e7417c962d61c2fe305386f22d882947e929d8103ad6629ab598a68a6676448bfd2908d77134f7e3e871d126e93952755de9a52df2197af584a0af4d293a5161b39e73ec0905aba660f5529887611c2da6601a2ec2953f6be3607572e8b44cac4685d629bbd0bae060b573b06b0e762f87c9630082c7d92c0cbada60778b1dd89d243a2da1fdd536383505a79742e7bdd4f53b3df9348bab1e934b8ff3c65c7a3867ac8cc6c323a7e01cb13dc94b908a5921e6d7edbd08c1f483ad3762cea88f51cf0cb54cc434c64c3a08fb8e525e6fe4fb560f78ef3f504b0304140000000800e35dca5cc4d12ed86e020000b407000018000000786c2f776f726b7368656574732f7368656574322e786d6c9d956d73a2301080ff4a26df4f14d1de74801914f49cf36dd4f6a61fa346cd140817626dfbeb6f1390322a5cc72f9acdeeb36f0959fbc4c56b7aa054a2f7288c53071fa44c1e0d23dd1c6844d2064f680c9a1d171191208abd91268292ad86a2d0309bcdae11111663d7d67b73e1dafc284316d3b940e9318a88f8e8d1909f1cdcc2e78d05db1fa4de305c3b217bbaa4f229010044a3f0b365118d53c66324e8cec15eeb716069425b3c337a4a4b6ba48a5973feaa84d1d6c14dac7cc7147d2c939065e1244fc67427fb340cc1a18911d948f646e760e6e0359792474a0f894a22616b27f8278db3a034a4600cd92457d69997dcab2af36f9e31feaa48a5555e9f731fe8e642ed6b92d23e0fffb0ad3c38f827465bba23c7502ef8e917cd1bd6d10e373c4cf52f3a65c6ad26469b630af9e434048e589cfd93f773a7cbc4430561e684f96da29d13ed2ba22a2b2b27ac2ba253417472a2f3ed18dd9ce8664790b54c37dc2792b8b6e027249439b8530b7d6cd91d71308bd5055e4a015a069c7497e3c674661b125ca90d639363bd7accebaf46cfa3d5cb0db2ff9f804fbd1f35b45f4f4fbca9efbd2c6f80413db89aadbc31aac607f5f82298788bdf17a001bd2e1a6e160d37b50ff572bcb92ddb782b77d5acf0efcffaa83f1b8f03e8cc6c7aabab77937e4d3e418d6e701951dfb772c9eda2e476c98d795172bbea288360359a0ed13098060b6f7cabe6fb51bf9c51fba2e81adde032e455d15651b455eda667555d436f8882e56a34f1aacef96ed2b76aceb94637b88cf855b2517a57d4349b10b167718a42180e30871a0ff06c89ec05cf041843fa1bca66885e1e60aa52a10c40bfe35c16820a530c6af71f504b0304140000000800e35dca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b0304140000000800e35dca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800e35dca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b0304140000000800e35dca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800e35dca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800e35dca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800e35dca5c636a33fd02010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800e35dca5c995c9c23100600009c2700001300000000000000000000008001f4010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800e35dca5c1286eca4a0020000ec070000180000000000000000000000808135080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800e35dca5cc4d12ed86e020000b407000018000000000000000000000080810b0b0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800e35dca5c7bb6dee0b8020000080c00000d00000000000000000000008001af0d0000786c2f7374796c65732e786d6c504b01021403140000000800e35dca5cb747eb8ac0000000160200000b00000000000000000000008001921000005f72656c732f2e72656c73504b01021403140000000800e35dca5c698cf10e450100006a0200000f000000000000000000000080017b110000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800e35dca5cab5e722eb40000008d0200001a00000000000000000000008001ed120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800e35dca5ca5e11b581f010000600400001300000000000000000000008001d91300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000291500000000	5	\N	2026-06-10 11:47:07.750484+00	2026-06-10 11:47:07.766804+00	2026-06-10 11:47:07.776007+00
8ff7bba4-d295-4547-8577-909fecbfe292	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project	success	{"preset": "weekly", "date_to": "2026-06-07", "date_from": "2026-06-01", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_2026-06-01_2026-06-07.xlsx	\\x504b03041400000008002952ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008002952ca5c89bab78800010000f301000011000000646f6350726f70732f636f72652e786d6ca591414ec3301045af12659f8c9d4a0159a93720562021a854c4ce72a6ad218e2d7b50dadbe3a46d0a825d97f67ff3f4c76eb417da057c0ece63208331dbdbae8f42fb65be23f20220ea1d5a15cb44f429dcb86015a563d88257fa536d112ac66ab048aa55a46014167e36e62765ab67a5ff0add2468356087167b8ac04b0e179630d8f8efc094cce43e9a991a86a11c1613971a71787b7a7c9dca17a68fa47a8db96c5a2d7440452ec871237fd8770dfcb81c0132d4a14c8ff2819ab2b58998bda0778126f29836a78ec7416cb3d444d0c1e3323f27ebc5ddfdea219715abea82d505672bce04bf11fcf67d34fd9abf08ad6bcdc65c613c0b64037ffe577e03504b03041400000008002952ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008002952ca5c11ab0e9540020000e705000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d54c992da3010fd1595efc10beb4c0155c62c434d32b8583267811bac205b8e24e2995bfe21f9c27c4924191c0eb633555ed46abda5a5520f73c6cf220690e82da1a91859b194d9a36d8b430c09162d9641aa3247c6132c55c84fb6c838e0c880126a7b8ed3b3134c526b3c3473211f0fd945529242c891b82409e6ef13a02c1f59ae759b5893532ccd843d1e66f8041b90bb4c015468973c1149201584a588c37164f9eee364601066c55702b9b81b235dcc9eb1b30e96d1c872b427a070909a02abdf0f088052cda49c7cbf925aff4435f27e7ca39f9bfa95bd3d161030fa4a22198f2c65268223be50b966f9135c6bea1ac203a3c27c515e2cf67a163a5c8464c915ad841392167ffc76db8c3b44c7a94178578457582fa48cd12996783ce42c475c2f57747a60ca3570e58fa4fa6c3692ab2c5138390e39fba63609bd1201680d19e372684b45acd3f641bd8ab0646d97ac6dc3ead5b0561119dca4fd011f0d063aa5814ea3812b5d95834e0d6411b80faee33e380efaf3f3379a85cb00cd576b34dd3d3ff92f285cafa6bb60bb5cbda0b91f2c3f2fb7cbd906edc2c5da9fce50f8e46f66aeaf90bf50e807cffe6286dc863aba651ddde63a8013165595d1ad41788ed7fbe4a8c74592a132ea3798e995667affd9541050b9a7bd1a440e70a6ef0dd2fd52badf28bd65125373c9914e892a13fd1aacd3a03f28f5071fd08fd985574a0feaa45b95e2f6dd7dd50df00be627920a44e1a8689c565f1d2e2f3a4a114896992bbc67527504338c552306ae17a8fc91315906ba2d94bd7dfc17504b03041400000008002952ca5c54b763da320200009806000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d956d6fdb2010c7bf0ae203d4699e5bd996daa45d5a6d539468eb6b629f63566c3cc04db34fdfc390ac5a9ccc6f120eeef7e780bb73b893ea55e70086bc17a2d411cd8da96e83402739144c5fc90a4a5cc9a42a9841536d035d296069031522e8f77ae3a060bca471d8cc2d551ccada085ec252115d170553fb7b107217d16b7a9858f16d6e9a89200e2bb68535981f15026806479d9417506a2e4ba2208be8ddf5edb3231a8f9f1c76fad398d8c36ca47cb5c6531ad11eb5da2590fdba12dc6d6764f5153233032150b04f094b0c7f8325ba4574238d91855dc7400d33389529f9074ab7290840678ca63af1762a5ed51ef3b78f98fe3d910debf3f810fb6373b978f60dd33093e285a7268fe894921432560bb392bb05f80b1b35828914baf9253be77cdda324a935c6e369dcb8e0a5fb67ef879bee42f43dd1ef4c0c3c31e84c0c3d313c21a6678891274627c4e80c31f6c4b87354134f4c4e88c11962ea89e909313c43dc78e2a63361c3754fd873c9e41ebf499d39332c0e95dc11650114b48326019be7c08ce1a52dc5b551b8ca9133f1435109b9070803836a762e483c797f99c4eddaa8d965eaced60637fb16727e995cc85ae916ece132f6827d80cc41278a57b65e5b141e2f2baca092ca9035f680ba2d802fffc3dfb0be41b5908b2e243973d14f97e1a592bfb04391994cdbe8e76ef47756fc4307986087c6e532ce76ec6f4c6d79a989c00688bdf66a8285a85c977206b6da268b5d9f6c86397e394059075ccfa43447c326f6f163147f00504b03041400000008002952ca5cfdd7243cc5020000900c00000d000000786c2f7374796c65732e786d6cdd576d6f9b3010fe2b881f3042c8589892481b5aa449db54a9fdb0af261862c92fcc982ae9af9fcf2640da1e6d27f5cb889af8eef173cf9d7d36eaa635674e6f8f949ae024b86cb7e1d198e67314b5872315a4fda01a2a2d52292d88b1a6aea3b6d194942d90048f968b451a09c264b8dbc84eec85698383eaa4d9868b3088769b4ac9d1b50abdc3ce258206f7846fc39c705668e62713c1f8d9fb97ce73505ce9c0d86ce8368c9dab7df013e2de8454fb588249a59d37f232febbe809d7f4d50b1371c427a5ebc216b9d8bb67ca703fad6532ce87d293d03b769b861843b5dc5bc3939cf729d68fefce8d2dbdd6e41c2f3f86af67b48ab31244eb7c9a6ebc5f7dfbb476710a14892651073df763cb2a942ea91e0a8bc38b6bb7e1b432c0d7ac3eba81518d5352c62801a392915a49e22bbfd0fa818d7da09cdf4253feaeae044e55e0bbeb7be91a0b56f832b459f5431fa63740601ace079fc45dfd5bdc86dd2bf3b5b3054967ffe994a1379a56ece4ec53352680858fdf37fcf27dc32763f8e5a3f0a469f8f90b67b514d4efddab15771b72e10547a5d983558323073d1506f7541b7600fb6027d0fe909faa7e9387fd75bb7dd53a8337803b671bfe82bb8c4f2a2d3ac60d93bd75646549e5d30eb2f10d29ec6d7925606795b4221d377703b80dc7f14f5ab24e64c3ac1b588c7ed638fe01c7254ec7bbc58a3159d2132df3deb467f4eab0fac7311e43930be92984b23c884000a25a681a28cbf350adffb1ae355e9707d10cd7cf436b9cb5c6599ef72c94bb0faa85b032fb2025675992a429babc79fe7c1a39ba86690a7f48403443e0a05aa0f6d6959f698099b679a137d05d9e6d1bb4e49916454b9e5979809035044e96210d806a0107dd14b4a32009440b5a0d612509ec339a217acc67a02c43216852a47bd3145ba8143ec87ea1872849b20c810044d248121482033b03a1694022289424fe45fae87d165dde73d1f83fc8ee2f504b03041400000008002952ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008002952ca5cc70e0c5a480100006f0200000f000000786c2f776f726b626f6f6b2e786d6c8d91d14ec3300c457fa5ca07d0ad82494c2b2f4cc024046843e3396dddd55a12578ebbb17d3d49ab412524c453ea6bf7e45e677124de1744fbe4d31ae7e79cab46a49da7a92f1bb0da5f510b2ef46a62ab2594bc4ba9aeb18425959d0527693699cc5206a305c9f9065baf06da7f58be65d0956f00c49a0165353a75b7b8387be3241d572450c69ba21a952dc2d1ff0cc43239a0c7020dca2957fdb70195587468f10c55ae262af10d1d9f88f14c4eb4d9944cc6e46a3a34b6c082e52f79136dbeebc2f78ae8621d33e76a3609c01ad94b3fd1f375307980303c549dd0031a015e6a8147a6ae45b7eb3121463acad1afe272264e5bc8d5a6b356f3299a08e2aa1a0c49208de2f11c438357d5c01cffff117693aca125163f82647f40b2c1d8c54d05353aa85e02cec746d84d191e261ebd9decfa667a1b76d019731fb457f74cbafa8e77799bbb2f504b03041400000008002952ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008002952ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008002952ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008002952ca5c89bab78800010000f30100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008002952ca5c995c9c23100600009c2700001300000000000000000000008001f2010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008002952ca5c11ab0e9540020000e7050000180000000000000000000000808133080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008002952ca5c54b763da32020000980600001800000000000000000000008081a90a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008002952ca5cfdd7243cc5020000900c00000d00000000000000000000008001110d0000786c2f7374796c65732e786d6c504b010214031400000008002952ca5cb747eb8ac0000000160200000b00000000000000000000008001011000005f72656c732f2e72656c73504b010214031400000008002952ca5cc70e0c5a480100006f0200000f00000000000000000000008001ea100000786c2f776f726b626f6f6b2e786d6c504b010214031400000008002952ca5cab5e722eb40000008d0200001a000000000000000000000080015f120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008002952ca5ca5e11b581f0100006004000013000000000000000000000080014b1300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a00840200009b1400000000	0	\N	2026-06-10 10:17:18.810212+00	2026-06-10 10:17:18.821665+00	2026-06-10 10:17:18.831169+00
817c40ac-7ffc-4a2a-bfcb-a61638c54404	9f946201-e71e-4356-b830-2dddae74e9f9	attendance	success	{"date_to": "2026-06-10", "filters": {"year": 2026, "month": 6}, "date_from": "2026-06-10", "employee_ids": ["3107987e-7e92-4e89-97f3-1d5275e65485", "d595afe7-1dd9-4c83-ba17-d8fc11a14724", "e5ce164a-f805-4970-80be-cbd21533d1d0"]}	attendance_2026-06-10_2026-06-10.xlsx	\\x504b0304140000000800d858ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800d858ca5c45fbd41d02010000f901000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9bb49382a10b88e29503d181e25d48deadc17c91bcd2eedfdb765ba7e8dd2e93f39c8713d2cac0a48ff01c7d80881a523658e31293619d7788811192640756a47224dc18ee7cb402c763dc9320e4a7d803a9296d8805144aa02093b0088b313f29955c94e12b9a59a0240103161c26529515b9b008d1a67f0b73b29043d20bd5f77dd9af666e5c5491f7cdd3eb3cbed02ea1701272de2ac96404813ef2e945e1309896fcb89c00d468806fbcc3ce1cb23b44706aaa672f107cc4993f32ed69e9b10e2a1bf7303c0458e7e7e46d75ffb07dcc794deba6a04d51d16d5531dab09bdb8fc9f4ab7f115aaff44e5f613c0b784bfefc32ff06504b0304140000000800d858ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800d858ca5cc8332579eb0100002805000018000000786c2f776f726b7368656574732f7368656574312e786d6c9d544b8f9b3010fe2b16f75d0849481501d266dbaa3dac14257d9c1d98046b6d0fb52765f3ef6b9b84cd21416d0fc08c3ddfc3c6e3bc43f36a1b00626f4a6a5b440d51bb8c635b35a0b87dc416b49bd9a3519c5c6a0eb16d0df03a80948cd324c962c5858eca3c8cad4d99e391a4d0b036cc1e95e2e6b402895d114da2cbc0461c1a0a037199b7fc005ba0efad03b8341e786aa1405b819a19d817d1d364b95a0444a8f821a0b35731f38bd921befae46b5d4489f704122af214dc7d7ec33348e9999c935f67d2e85dd423afe30bfde7b07e676fc72d3ca3fc296a6a8ae843c46ad8f3a3a40d765fe0bca67920ac50daf0665d5f9c6611ab8e96509dd14e5809dd7ff9db6533ae10b3e40e223d23d2de7a2f158c7ee4c4cbdc60c78c2f77743e08cb0d70e74f68ff6fb664dcac70382a5f5053234fec890874cd75056c032d1aca6372f4be28aedce36807eee9c03d0ddce91dee5b4401b79afeb59b111bb3c1c66cd4c61a8cc0fa968dd91d449aa4d943923d4c1246c8deb31133f3c1cc7cd4cc27d54a3c01d85b7ee67740d311e16c10ce4685bf2171e97aa94253df14cffe437c31882f46c5b7c4e96897cc5d1f16f4cd23b1f817f9f8eac0fb1be4859b83d09649d83b92e471e176d2f42dd927846de8811d926ba91036ee2603e30bdcfc1e9186c4f7d57039967f00504b0304140000000800d858ca5c0de220f5030300001c0b000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d96db72da3010865f45e30788cf9c069809e400d326a161da5c2b20634d6cc995e4d0f4e9bbb21d6a4072c805d1e95bedea5f593bde73f126534214fa93674c4e9c54a962e4ba7293921ccb2b5e10063309173956d0153b571682e06d05e5991b785ecfcd3165ce745c8dadc474cc4b9551465602c932cfb1f898918cef278eef7c0e3cd35daaaa01773a2ef08eac89fa5900005df760674b73c224e50c09924c9c6b7fb48c2aa25af18b92bd6cb5910ee695f337dd596e278ee768db8ca08f7591d17a3bc58bef245173926560307010de28fa4e56b06ce2bc72a578aee7c15185150c2582ff25acde946404168337c5d9eada4a635587f9bbf1d8f91f9176abddfef4fdae3a5c88fd154b32e7d90bddaa74e20c1cb425092e33f5ccf70bd21c585c19dcf04c56bf685f2fd6e39b52823f0d0d1be794d5fff19fcf936e133d0b11344470467816226c88f08c082c44d410d1c57bc40d119f11be85e83544ef8c882c44bf21fa179fd5a0210617c7316c88619d18b590551adc6085a763c1f748e8e5604e37aa64aa8e16d4a74c5fabb512304b8153d3dbbcc8f8072168ceb764ec2a30a927dc4d83cf2ec41f716ec2e7ddf85392d08d89bbe9e620541375db4dcd53b279434b6620ef2e219f4a6540efbbd117f8a6902d5af0524803bdf8e280de8950f011b3f2cb6e7e0d1fa1f2847321450e79121cf224b049fc10f83dcf941a36e2f17af978fd8c66a67cb0313f2079852911822abea8c2f41bf13e8d7afe201cbbef6de16d66bde1c88b4d7adb00bf3f8a4cc1de072d0f0657f1e0d881457bda3b9b5edab683a75012a63a040a0f0259efe083e7f9267decc00a99807947fa3386a9499ef022796c86bdc1281e9ae4b1015a9ed0244f78244fffc481457824cfe9f4d2b6ddd7f244077922fb69078129076736628d994ab94cd1b732375e8ab98dec102aba48289b617d8f7a26a16c0008159a94bd8f8eef51ecb5fefc13d5a2e34b159fa866dbbb4335b7f552eaaaf1018b1d651265508441bd77d587f240d49552dd8172af7a7beb5aad6aa650bd12a117c07cc2b93a74f4837c2888a7ff00504b0304140000000800d958ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b0304140000000800d958ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800d958ca5c397ef814460100006d0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ac34010855f25ec03983468c1d214c4a21644c54aef37d94933747fc2eca4b57d7a7713a20141bcdacc99c9b7e7cc2e4f8e0ea57387e4d368eb17548886b95da4a9af1a30d25fb9166ce8d58e8ce450d23e75758d15ac5dd519b09ce659364f09b46474d637d87a31d0fec3f22d8154be0160a307949168c56a393a7ba3249d568ea18a3745352a3b8493ff19886572448f256ae47321fa6f0d223168d1e00554213291f8c69d9e1ce1c559967a5b91d3ba10b3a1b10362ac7ec9db68f34396be575896ef317321e65900d6489efb899e2f83c92384e1a1ead83da066a0b5647824d7b568f73d26c4482739fa558c6762a581426c3b63249da389206ed460880369128f16181ab4510373faff1d3358256d051344fe07221f6c8d5e14d46841bd04988f8db0992a3c4b3c7a33f9f5cdec366ca0d3fa3e68aff6d949f51d6e7c99d517504b0304140000000800d958ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800d958ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800d858ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800d858ca5c45fbd41d02010000f90100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800d858ca5c995c9c23100600009c2700001300000000000000000000008001f4010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800d858ca5cc8332579eb01000028050000180000000000000000000000808135080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800d858ca5c0de220f5030300001c0b00001800000000000000000000008081560a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800d958ca5c81a25029e20200002a0d00000d000000000000000000000080018f0d0000786c2f7374796c65732e786d6c504b01021403140000000800d958ca5cb747eb8ac0000000160200000b000000000000000000000080019c1000005f72656c732f2e72656c73504b01021403140000000800d958ca5c397ef814460100006d0200000f0000000000000000000000800185110000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800d958ca5cab5e722eb40000008d0200001a00000000000000000000008001f8120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800d958ca5ca5e11b581f010000600400001300000000000000000000008001e41300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000341500000000	3	\N	2026-06-10 11:06:49.919308+00	2026-06-10 11:06:49.980024+00	2026-06-10 11:06:50.002869+00
6be0af9b-d58c-498d-b805-d31c9c4213be	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project	success	{"preset": "weekly", "date_to": "2026-06-07", "date_from": "2026-06-01", "project_id": "1f6198c9-1a1a-4e52-bf0c-bbaf41be051a"}	project_2026-06-01_2026-06-07.xlsx	\\x504b03041400000008003b52ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008003b52ca5cfdc6485900010000f301000011000000646f6350726f70732f636f72652e786d6ca591414ec3301045af12659f8cdd4290ac341b102b9010542a6267d9d3d610c7963d28e9ed71d23605c18ea5fddf3cfdb16be58572019f82f318c860cc06db765128bfcaf7445e0044b5472b6399882e855b17aca4740c3bf0527dc81dc282b10a2c92d492248cc2c2cfc6fca4d46a56facfd04e02ad005bb4d851045e72b8b084c1c63f07a66426876866aaeffbb25f4e5c6ac4e1f5f1e1652a5f982e92ec14e64dad95500125b9d08c1bf9c3d0d6f0ed7204c8508b4d7a947754946d4cc4ec19bd0b3491c7b43e753c0ea2ce521341078fabfc9c6c96b777ebfbbc59b04555b0aae06ccd99e037e2faea6d34fd98bf08add3666bfe613c0b9a1a7efd6ff305504b03041400000008003b52ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008003b52ca5ca40f5783840200009906000018000000786c2f776f726b7368656574732f7368656574312e786d6c9555cd729b30107e951d4ec9a106e3ff8ced191b939849825d20c9f4a8d86b4303884a72486e7d883e619fa44276a80f40d31963b4dafd7e1631cb38a7ec85878802de9238e5132d1422bbd275be093121bc45334c6566475942840cd95ee71943b255a024d64dc3e8eb0989526d3a567b6b361dd38388a314d70cf82149087b9f634cf389d6d63e36bc681f0ab5a14fc719d9a38fe221930019ea25cf364a30e5114d81e16ea2cdda57f39142a88ac708737eb686a299674a5f8ac0d94e34a3f084316e444141e4ed152d8ce382493af97122d5fe8a16c8f3f507fdb5ea5fda7b261c2d1a3f455b114eb4a1065bdc91432c3c9a2ff1d4534f116e68ccd53fe4c762b3afc1e6c0054d4e68299c44e9f14ede3e1ec619a26bd420cc13c23c5a3f4a29a30b22c874cc680eac289774c542b5abe0d25f941667e30b26b391c489e99ad1eff221c153c4113ccc2813635d48e222ad6fe425094bd64ec9da51ac660d6b1591c2cd3b9ff0d160a05b1ae8361a38d15539e8d640ee2cd36c1bdd9e61c0ef9fbfc05e3b165caf3cf0ecf5ddccb2ef6d3780d535ace6feeace0e6cf0ada56b3b0bdb03fbeb83b356f98b4eab73fb08fe931358cb1b7be65d82e3c2ed721638df664b70575eb084857de3d933df716fc00f6466e5c2c5e24116b9970d9df7cace7bcd9d238be8b6aaf15e0dc234ccfe1743feda202894d1a0c14cbf34d3ffc73120c7ca53e8d72072c497f8bd417a504a0f1aa5032a48acc60214295e656250836d37e80f4bfde127f4437a6095d2c31a98d1321ac447a5f8a851dc17441cf815902c63f4152b5f87d1ff34af9f4d986264df13b68f520e31ee2489d11ac8978b1d67e03110345343e7990a39c3d432949f0e644581ccef281565500cb2f26b34fd03504b03041400000008003b52ca5c85d729a0160300000709000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d965d73a2301486ff4a86abf6620be2673bea0c020aad4516b49dbd4c350a5b206c885af7d7ef0950d7ade03ad3b1f97ade9c246f4ee8ef297bcf024238fa88a3241b4801e7e9832c67cb80c438bba32949a0674d598c3954d946ce5246f02a87e2485615a523c7384ca4613f6f73d9b04fb73c0a13e232946de318b3c38844743f901ad26783176e029e37c8c37e8a37c4277c91020055f9a8b30a639264214d1023eb81a4351e1ed59cc847bc84649f9d949158cc1ba5efa262af06922209ed84a0839f4661311da7e994acb94ea20804410d2f79b8232e0c1b486f94731a8b7e0894630e4d6b467f93a498944404064334e9d9e842a55415cbfc55462cfd5d9108ebb4fc19fb38df5c58fb1bce884ea3d770c58381d493d08aacf136e21edd5ba4dcb0762eb8a45196ffa27d31b8d191d0729b413c250d13c76152fcc71f9f3b7d4aa835845a12ead544b3249a67845243b44aa27546f46a887649b4cf88760dd12989ce19d1aa21ba25d13d239a3544af247a57cf715f12f75f894edd5e894d2c8e5029cc541c7e6e1d03733cec33ba474c0020280ab901f3e300c78489b88a3e67d01b02c787669c46f440485fe6a026dae465498e2e93305d15a55fa6347137427ea8208dcba445b72cabc0cccbd82be40164906cc9c254dcd70a85f165058fa49471e4430ed8560530f91fbe83fb4d5805695d43a29a8db62fc32ea33f2143219daeaae8c7eb6807c75f68190c7674997a74995a23e4e38407340bd0d316527d95cbd43c9056ce8b8763376c751add5e5fde9dbaaa4edf9e237fe1ba336f5ee528f54455f957d1ac5334663ab28d51954fea109ca68ceec8aaca1c758c16910ff48c1378ee2aad51c7a98adaf9a6c05fbbca1375d45457d586d26a2b4a9517ea28d3b575349e79c833dda9a69bcfa63347b3319a8dfcd9d49c9bc8d72dc7b40dd343e6f785ede6fd37cdbbe6d30bf25fedb96e4d4ccdbb45b6839e2c6d6effd02ce4c05159c830279ea9f9b63341fe1c7a660eba311630c8b9adb29b7c92e0c407c233669b30c95004ef2d3ced775dc8fbac78148b0abcec79d22c9ee5bc18c0870a616200f4af29e5c78ac8a3c76f9fe11f504b03041400000008003b52ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b03041400000008003b52ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008003b52ca5cc70e0c5a480100006f0200000f000000786c2f776f726b626f6f6b2e786d6c8d91d14ec3300c457fa5ca07d0ad82494c2b2f4cc024046843e3396dddd55a12578ebbb17d3d49ab412524c453ea6bf7e45e677124de1744fbe4d31ae7e79cab46a49da7a92f1bb0da5f510b2ef46a62ab2594bc4ba9aeb18425959d0527693699cc5206a305c9f9065baf06da7f58be65d0956f00c49a0165353a75b7b8387be3241d572450c69ba21a952dc2d1ff0cc43239a0c7020dca2957fdb70195587468f10c55ae262af10d1d9f88f14c4eb4d9944cc6e46a3a34b6c082e52f79136dbeebc2f78ae8621d33e76a3609c01ad94b3fd1f375307980303c549dd0031a015e6a8147a6ae45b7eb3121463acad1afe272264e5bc8d5a6b356f3299a08e2aa1a0c49208de2f11c438357d5c01cffff117693aca125163f82647f40b2c1d8c54d05353aa85e02cec746d84d191e261ebd9decfa667a1b76d019731fb457f74cbafa8e77799bbb2f504b03041400000008003b52ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008003b52ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008003b52ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008003b52ca5cfdc6485900010000f30100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008003b52ca5c995c9c23100600009c2700001300000000000000000000008001f2010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008003b52ca5ca40f57838402000099060000180000000000000000000000808133080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008003b52ca5c85d729a016030000070900001800000000000000000000008081ed0a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008003b52ca5c81a25029e20200002a0d00000d00000000000000000000008001390e0000786c2f7374796c65732e786d6c504b010214031400000008003b52ca5cb747eb8ac0000000160200000b00000000000000000000008001461100005f72656c732f2e72656c73504b010214031400000008003b52ca5cc70e0c5a480100006f0200000f000000000000000000000080012f120000786c2f776f726b626f6f6b2e786d6c504b010214031400000008003b52ca5cab5e722eb40000008d0200001a00000000000000000000008001a4130000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008003b52ca5ca5e11b581f010000600400001300000000000000000000008001901400005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000e01500000000	1	\N	2026-06-10 10:17:54.936086+00	2026-06-10 10:17:54.950807+00	2026-06-10 10:17:54.962415+00
1a94a4ee-4cb0-439e-8ce8-7d1af62bee44	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	employee	success	{"preset": "monthly", "date_to": "2026-06-30", "date_from": "2026-06-01", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}	employee_2026-06-01_2026-06-30.xlsx	\\x504b0304140000000800b252ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800b252ca5c771e4d3405010000fa01000011000000646f6350726f70732f636f72652e786d6ca591cb6ac33014447fc5786fcbb2c10be168d307145a286da0a53b21dd24a27a21ddd4cedfd77612a7a5dd6529cd99c308753230e9233c471f20a286940dd6b8c46458e53bc4c00849720756a47224dc186e7cb402c763dc9220e4a7d802a9abaa2516502881824cc2222cc6fca4547251867d34b3404902062c384c8496945c588468d3bf853959c821e985eafbbeec9b991b1751f2fef4f83a8f2fb44b289c849c774a321941a08f7c7a51380ca6233f2e2700351ae00f4ee92fadf6c2647736187f00c85e20f88873e10875a7a9c73ea86c1cc4f01060959f93b7e6e6767d9ff3baaadba26a0b5aad69c56aca9af66332fdea5f84d62bbdd15718cf02de913fdfccbf01504b0304140000000800b252ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800b252ca5ce8faa0faab0200005809000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d96dd6eda3018866fc5caf99a1f20d00a905ab669d5540dd1fd1c1bf285784dfc65b653cad92e6257b82b99ed40c841ec21f163277edfef491cbfcefc80e24516008abc5525978ba050aabe0b43b92ba0a2f2066be0fa4c8ea2a24a77c53e94b5009a595155864914a56145190f96737b6c2d96736c54c938ac05914d5551717c80120f8b200ece07366c5f287b205cce6bba876750df6a2dd0ddb0f3c958055c32e44440be08eee3bb8778622576c8770607d96b1373355bc417d379cc164164a0a0849d321e54ffbdc20acad25869945f27d7e052d528fbedb3fd477b0334df964a5861f98365aa5804b3806490d3a6541b3c7c82d345b5883b2ca5fd25877670920664d74885d549ad0b578cb7fff4ed7c377a8a71e450242745d2a2b7a52ce87baae8722ef0408419aeed4cc35eae956b3ec6cde43c2ba1cf32ad53cb479eb1579635b4241faabac42300d9408d42cd43a5fdcda870a7bfdab7331f75e6236b9e38cc878cacee61743d8e8763dc718cbd1cc3562dc9d8a179a65c15280bf2b9d14fad0762d2414cae82202bcc0649262ee1d33a49261e82b42348bd045ff29ced064ba70ec5aa00ce29f3d49e76b5a7deda6b100cb3a1da5387228992f45da43f315148cebd51e481997530333f8c000983cfe5cca1a8503f0de5d153fbb6ab7debad7daf14f08cf21d908c1ee510c4adeb8e78cac7d165c1475e80afa8f4ea3279091929b011830cc664501ea737a98fa3173cf17f26017fea789627944108576a8d7c04c98520b9229e24f9fbfb8fde9cb615d35333cce172887d1c97948caf89c99683d6b5c05707862b35bd137209c9d89f927d0c01666e1c18aec8f42dcdf81293b13f27fb1899a0f9e03a8d5d6139c810f6f647f3c6f144c59e71494ac8b5497433d56ea2ddc1db8ec2da6e995b547a07b6cd42bff9803003f4f91c51751db30d772f53cb7f504b0304140000000800b252ca5cd386ae715f0200000807000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d95db6ee23010865f25ca039013091485485b5ad44abb6a55d4edb58109b148ecaced40bb4fbf6327b00192a85c80c79e6f0e7ff0243e72b1971980b23e8b9cc9b99d2955ce1c476e3228881cf112189ea45c1444a129768e2c0590ad818adcf15d37720a42999dc466ef552431af544e19bc0a4b564541c4d73de4fc38b73dfbb4f1467799321b4e129764072b50ef2502683ae7385b5a009394334b403ab77f78b3656008e3f19bc251b6d6966e66cdf95e1bcfdbb9edda3a3603eb6b55e6b44ea778f91352b5803cc780be6d918da2077845b7b9bde64af1429f63a18a28dc4a05ff0bac4e0a39a0335653de78d7519aa8bacd3f4dc5f6ff8e7459edf5a9f6a511177b5f13090b9e7fd0adcae6f6d4b6b690922a576ffcf8048d60a109b8e1b934dfd6b176f6b0934d25b19e86c6c40565f52ff93c29dd26dc1ec26f08ff86f07a88a021821b62dc438c1b627c43443d44d810e1b7fb881a22aa1f412d9911fc812892c4821f2da1dd319c5e98c7669a409d29d37fe09512784a91530942103b0a2369dbd934d4fd30b5c860b3b79e5907b9f80ef952a90ef46118fdc07b005beb89574276d08fc3f4cb0184c28bd7cb2f87f9155e9cea8a7350ecb3e2fe5971df041a9b407a801c9271e44d26b173682becf72472ef66aedf256c1fe04d666ed825a7dfaa603a7243b7f5f12eab796cfbba231daf7dbceccb8d4353025303b2046759822e59a6c1952c7dfa6b59a22e59fa009425b8eb9225b890251c9425b89025bc96a52ff7802c4eebaeea37c42f227694492bc7818bb37d34c15120eaa9581b38dacdedafe7b25966f8a602a11df03ce55c9d0d3d12ce2fbfe41f504b0304140000000800b252ca5ca51eb1745e0400005211000018000000786c2f776f726b7368656574732f7368656574332e786d6ccd98db8eda4810865fa5e49556c945c660734a16903c7673d080616d93512e3dd00cded86ec76e864c9e7ecb07bcacd38dd048917203eec35f55dd5f5799667862e9d7ec402987ef51186723e5c079f24955b3ed81467e76c7121ae3c89ea591cfb1993eab5992527f5788a250d55aad9e1af941ac8c8745df3a1d0fd99187414cd72964c728f2d3d77b1ab2d348692be70e27783ef0a2431d0f13ff99ba946f12146053adedec8288c659c06248e97ea418ed4fd341a128667c0ee829bb78867c314f8c7dcd1bf3dd486929b9ed98c2ab9b8441e98eb36441f7dca46188063505fc2d0f5ee81aa78d9427c6398bf2710c94fb1cbbf629fb41e3d2290d294ec668929f6697562aabf932bf55112bffad280febf2f91cfba4d85c5cfb939f5193858fc18e1f460aae7447f7fe31e40e3bcd68b561ddc2e0968559f109a772721b57b23d66184fa546c7511097dffef7f34e5f2a3a12855629b4a6a2d79228f44aa137159acc47a752747e8a4ae6a35b29ba4d85ae4b14bd4ad1fbc94757a2e8578a7e09addce40291e5737f3c4cd909d27c3a9acb1f0ad0c5b2914c10e747dee5298e06a8e36314d1a1cad152de56b795eafeba6a9db27ff09881c97622b5799bdaf62391dabaae36f2531cf05781925c57ced831cd04b2c975d923662c5834dba641926796c0c2f4ba0587262ce5e062b61e1b01a8c8ab86a6d5d0b4c25ea7b09757ad9771a7d7ee0f86eacb25244de26f616a5abbd5e9b65a2238321559cf4d98ac1c70c87a619864496c0f561358ddbbab05f108b8e6cc26738b3840fedeccd7c5f83bfd4e7ff80ceee3dc3367536238ef616ec3c3ccf0e65f8c19d82bc79b8145a60e31dcb93d05d7c391950defac0d4eb2df8bf8cb029c7be06ed66b342962af5d6c56ebff1b359159b45626ccad7b115199c44f9294bdd0dd158c7a8d511762ec3730ca8ecdc796ded1742e62284dad99e1920f6db04c17fef4a3e42fb089f7b8721e60b39e3a8645c0b02d28676960ae6ccf592d16c471cfe3221ed2da81bb67e67233472a62a25f6122b38a2f97e215163fc38e6d45f93a95496f60d3a9d974846c3e36d87424aea6458ae97d718ac9546708de8ce4885420aea54ea62eb85f5c8f2cc1f00061fca1758d82d37914bb0dc7b8ff60813d5d8067d80f30319ca58895ccf392102fcfbf29b189632c44b02eb7a251692632b311be77909408924c7203a46e0da92b8234d01a90ba6faa8332d56f53076501e679b734f0c038b0c618f168c8f2af7b25ffae5997d44499e406a4bd1a694f88b4dd40da7b135299eab7412a0b10a3b2eddc4859b4311c626d16d821a2dabb92a8320737545599f406bafd9a6e5f48576fd0edbfa9aaca54bfbeaaca3cdf5055fb576049b781c634f543a8aa2bde09f801bee1cffb1438f523113c99a91be00d6a7803e12bb1d3803778133c99ead7c39379be01dee0622bba0d784db3c505ae602173981d9fa28073310cf5e20e97ffd7b0f4d3e720ce20c4abfb4869ddf5b1f8a6e5fdba6c709614b7c2f2865f3c1ea8bfa3693e01c7f78cf1ba915f15ebbf51c6ff02504b0304140000000800b252ca5cb2f963c69f0200003805000018000000786c2f776f726b7368656574732f7368656574342e786d6c7d545d739a4014fd2b77b6339de42141d1a499549c5961154605ca9264f24874551a60e9b2c6a4bfbebba0d4b6da17ddfb71ee9e73977b073b2e5eab0d6312def3aca82cb491b2bc378c6ab16179525df392152ab2e2224fa432c5daa84ac192650dca33c3ec746e8d3c490b341cd4be500c077c2bb3b460a1806a9be789f818b18cef2cd445074794ae37b27618c34199ac1965f2a15400651a6d9d659ab3a24a790182ad2c84bbf7a37e8da8331e53b6ab8ecea0c5bc70feaa0d6f69a10ed2b50b061fb4ccd2e63ac9cb195b499b65992a68224816327d63a14ab3d00b9792e73aae88ca442ad74af09fac682e651953c98a4df94f7653655f55cbfcb1678c7e2bd2b48ecf07eee3bab94afb4b52319b674fe9526e2c748760c956c9369311dfb96cdfb09bbae0826755fd0bbb26f9b68360b1ad149f3d5a5d9ca745f39fbc1f3a7d84e8f6cf20cc3dc26ca83757d5449d4426c381e03b103a5d95d3875aae857aaab7164a0bfdf0540a154d154e0e43c1bfabb60d0ca98a6997b1d80347ff07ba7c2b2a98f1f59a2dff441b8a42cbc36c7998670a3d8493083b0462978063530308758cf184027da63199038e6146a24fe60d06ec3b6d54b9718447570ef89319c4d89fc21847f353429a9bf508bc0dcdeec0783bc1b3d7f23c2798849e0de320828884336c9339f16308c6108c68302331016abb3ef11c1201f9f6e08575fca277dd9b3e027df262db9d101c5d82e7c3d4c5b1f78c5df0832876c121938860eaf913a0b18a043e5c380f2ac9bf3c25a77724e7eeb49a7eaba67feedd5d4cc95557771c3e2779f9157c123f05d1140eefa19bdd649960077e1c0533f50ef4103fc5ac7fc4acf31733e3e81bd51b659e88755a5490a90155bbe0fa8b1a1dd14c5163a855507ff5cd1cd7c78dda6c4ce804155f712e5b438f42bb2c87bf00504b0304140000000800b252ca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b0304140000000800b252ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800b252ca5c989c0e5265010000f30200000f000000786c2f776f726b626f6f6b2e786d6c8d926f4bc3400cc6bf4ab90f60e79c82c30ae2f00f888a137d7d6b531b777729b9d4a99fde5ccbb43018bebae649fabbe4c99d6d88d72ba275f6e95d88732e4c23d2cef33c960d781b0fa885a0b99ad85bd190df72aa6b2c614165e721483e9d4c4e7206670529c406db6806da7f58b165b0556c00c4bb01e52d06737eb6edec91b37c1c9140996e4a6a525e1036f1af2085d907465ca143f92a4cffedc0641e037afc86aa301393c5863637c4f84d41ac5b964cce15e67048bc000b963bf232b5f96c57b157c4ae9ed2cc85399928b0468ed257f47cab4d7e80160f512774854e801756e09aa96b31bcf5181d231fcdd15bb13db3603d1466d9796ff92b35a1e26d3534244a1a8dc773d404df560373fcff850884ca86124688e91ec47407f1aaf6664fd0124b1c418ef6408e7620babc775dde1830db03980de66c1da9a0c600d5bda2624ae87e4a7d1ce9e82d99ce8e0f4f750f9d7397aa3d843bb2d5afc5dbf771fe03504b0304140000000800b252ca5c49ca0b6ec2000000b10300001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73cd93390e83301045af62f9004c58421101551ada2817b06058c462cb3351c2ed8348019652a441a1b2fe587eff15e3e486bde2568fd4b486c46be8474a65c36c2e0054343828f2b4c171bea9b41d14cfd1d66054d1a91a21389d62b05b86cc922d53dc2783bf107555b5055e75f11870e42f60786adb5183c852dc95ad915309af7e1d132c87efcd6429f23295362f7d29e0df468163141cc028748cc20318458e51b4a711f1d423ad3a9fecf49ff7ece7f92daef54bfc0cddd58d1709707e68f606504b0304140000000800b252ca5cd393bfe42801000072050000130000005b436f6e74656e745f54797065735d2e786d6ccd54cb4ec33010fc9528d72a712988036a7a01aed0033f60924d63d52f79b725fd7b360e8d042a2d552ad18b2d7b6767c63b92e76f3b0f98b4465b2cd286c83f088165034662ee3c58aed42e18497c0c2be165b9962b10b3e9f45e94ce1258caa8e34817f327a8e54653f2dcf2352a678b3480c63479ec819d56914aefb52a25715d6c6df54325fb52c8b93362b0511e270c4813715022967e55d837be6e21045541b294815ea4619868b540da69c0fc38c70197aeae5509952b37865b72f40164850d00199df7a49313d2c443867ebd196d20d21c5564e832388f9c5a80f3f5f6b174dd99672208a44e3c729064eed12f842ef10aaabf8af3843f5c58c74c50c46dfc98bfe73cf09f6b64762d466eafc5c8dd7f1a79776e7de92fa0db7323951d0c88f8d52e3e01504b01021403140000000800b252ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800b252ca5c771e4d3405010000fa0100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800b252ca5c995c9c23100600009c2700001300000000000000000000008001f7010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800b252ca5ce8faa0faab02000058090000180000000000000000000000808138080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800b252ca5cd386ae715f020000080700001800000000000000000000008081190b0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800b252ca5ca51eb1745e040000521100001800000000000000000000008081ae0d0000786c2f776f726b7368656574732f7368656574332e786d6c504b01021403140000000800b252ca5cb2f963c69f02000038050000180000000000000000000000808142120000786c2f776f726b7368656574732f7368656574342e786d6c504b01021403140000000800b252ca5c81a25029e20200002a0d00000d0000000000000000000000800117150000786c2f7374796c65732e786d6c504b01021403140000000800b252ca5cb747eb8ac0000000160200000b00000000000000000000008001241800005f72656c732f2e72656c73504b01021403140000000800b252ca5c989c0e5265010000f30200000f000000000000000000000080010d190000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800b252ca5c49ca0b6ec2000000b10300001a000000000000000000000080019f1a0000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800b252ca5cd393bfe428010000720500001300000000000000000000008001991b00005b436f6e74656e745f54797065735d2e786d6c504b0506000000000c000c0010030000f21c00000000	9	\N	2026-06-10 10:21:36.79779+00	2026-06-10 10:21:36.820097+00	2026-06-10 10:21:36.832597+00
adb05b41-c807-4fec-ba62-ea93d7781daa	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_mandays	success	{"preset": "weekly", "date_to": "2026-06-14", "date_from": "2026-06-08", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_mandays_2026-06-08_2026-06-14.xlsx	\\x504b03041400000008005a5bca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008005a5bca5c01b09d0e01010000f601000011000000646f6350726f70732f636f72652e786d6ca591cb4ec33010457f25ca3e719c882cacd41b102b2a21a8046267d9d3d6103f640f4af2f738699b8260c7d29e738feed89df44cba008fc17908a82166a3e96d64d26ff223a26784447904236299089b867b178cc0740c07e285fc1007207555b5c4000a2550905958f8d5989f954aae4aff19fa45a024811e0c588c8496945c598460e29f8165b29263d42b350c4339340b971a51f2ba7d785eca17da46145642ce3b25990c20d0053e6fe4a7b1efc8b7cb19408d3df0f428ef2031db0aabc414b327f02ee0029f80ee5cf3940595a5320c270f9bfc3279696eef76f739afabba2daab6a0d58e5256b7eca6799b4d3ff257a1714aeff53f8c1701efc8af2fe65f504b03041400000008005a5bca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008005a5bca5c6e389403cf010000e103000018000000786c2f776f726b7368656574732f7368656574312e786d6c95536d6bdb3010fe2b423fa04a5cf642b10d49c6b6c006a1c95af65189cfb1a82c79d2254ef7eb77921cd783aeb02ff6bd3d77cfbd28efad7bf20d00b24bab8d2f7883d8dd09e10f0db4d2dfd80e0c796aeb5a89a4baa3f09d03594550ab45369bbd17ad54869779b46d5c99db136a6560e3983fb5ad74cf4bd0b62ff89c5f0df7ead860348832efe411b6803f3a02902ac63c956ac178650d7350177c31bf5b661111231e14f47e22b3d0ccdedaa7a0acab82cf78c86d805db69d56a9dcf38b88b6fb0635ae40eb8287c4f280ea0c1b42147c6f116d1b6912699448b6dad9df601201d040d1c4ac8be1946b887dc59972855a6fb80778e290382dc2bc7e0dadf397d184fea6f275089fe39668887be96165f5a3aab029f847ce2aa8e549e3bdedbfc230f97731e1c16a1fbfac4fc1f3196787932742039a0ab7caa4bfbc5c573645dcfe03910d88b432914a45a29f24ca3277b6672e8453ba20c476d3660aae4cb8a02d3af22ac261b958edd60febddcf5c20650b36711890cbb7915f9c3415db5994fa6fb0200a238f6ce491c56cd9ff664b54a6e0f028cee52c17e7693d31994138fdefd21d95f14cd381d0d1de7ca0d5b8b4a5a4d071c5e6d2a144b1a127082e0490bfb61647258c7a7cd5e51f504b03041400000008005a5bca5c760e844cec010000d904000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d945f6fda3010c0bf8ae5f711a0c0a62a8914a06868d022423bf5d1c0855875eccc364bdb4fbf731c58350ae325f19def77ffec735829fd6272004b5e0b214d44736bcbdb20309b1c0a665aaa04893b99d205b328ea5d604a0d6c5b438508baedf620281897340e6bdd42c7a1da5bc1252c3431fba260fa6d08425511edd08362c977b9ad15411c966c0729d8c712011483a39f2d2f401aae24d1904534e9dc4e3c515b3c71a8cc873571c5ac957a71c2741bd13675be2590b7b414dc87b3aa9c41664720043aec52c23696ff86059a4574adac5585dbc7442db3a8cab47a07e983820034c66cca136befa5f1eacafcd5644cff56e4d2fab83ee43ea99b8bb5af998191123ff9d6e611fd46c91632b61776a9aaefd034ac5f3bdc2861ea2fa9bc71a74dc9666f309f86c6c00597fecf5e0f9dbe86e83644f784e89d216e1ae2e6ea18bd86e89d10fd3344bf21fa57c71834c4c01f816f59ddf031b32c0eb5aa8876e6e8ce2dea63f37724a25cba0b9c5a8dbb1c391ba7b3d6fd43185874e514c1a6c18697b164b49a3e4d57cf9f90a3ff047c1c7eb9408f2fd3f3e47e9c3ca79f807797c1d5c32a9991f3f8e432bebc9b27cb1fff8001f6fa70f37df3ddc8cf99de716988c009c2616d7dc5b3d5fe9a7b0167b50ee407ad5ee6f8f4807606b89f29658f823be3e36b16ff01504b03041400000008005a5bca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b03041400000008005a5bca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008005a5bca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b03041400000008005a5bca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008005a5bca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008005a5bca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008005a5bca5c01b09d0e01010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008005a5bca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008005a5bca5c6e389403cf010000e1030000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008005a5bca5c760e844cec010000d90400001800000000000000000000008081390a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008005a5bca5c7bb6dee0b8020000080c00000d000000000000000000000080015b0c0000786c2f7374796c65732e786d6c504b010214031400000008005a5bca5cb747eb8ac0000000160200000b000000000000000000000080013e0f00005f72656c732f2e72656c73504b010214031400000008005a5bca5c698cf10e450100006a0200000f0000000000000000000000800127100000786c2f776f726b626f6f6b2e786d6c504b010214031400000008005a5bca5cab5e722eb40000008d0200001a0000000000000000000000800199110000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008005a5bca5ca5e11b581f010000600400001300000000000000000000008001851200005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000d51300000000	0	\N	2026-06-10 11:26:53.779279+00	2026-06-10 11:26:53.793646+00	2026-06-10 11:26:53.804177+00
5147128b-8644-4d6e-a588-8ea1820cb8e3	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project	success	{"preset": "monthly", "date_to": "2026-06-30", "date_from": "2026-06-01", "project_id": "990a41da-ac0f-4d80-ac04-ed20e47265e4"}	project_2026-06-01_2026-06-30.xlsx	\\x504b03041400000008003653ca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008003653ca5cb57727c400010000f301000011000000646f6350726f70732f636f72652e786d6ca591b14ec33010865f25ca9e9c93d20e56ea05c40412824a456c967d6d0d716cd98792be3d4edaa620d818edffbb4fffd98df25cb9804fc1790c643066836dbbc8955fe70722cf01a23aa095b14c4497c29d0b56523a863d78a93ee41ea1666c0516496a49124661e167637e566a352bfd6768278156802d5aec28425556706509838d7f0e4cc94c0ed1cc54dff765bf98b8d4a882d7c78797a97c61ba48b253988b462bae024a72418c1bf9e3d036f0ed7204c8508b223dca3b2acab62662f68cde059ac853da9c3b9e065167a909a7a3c7757e49b68bdbbbcd7d2e6a56af0ab62a2ab6a918af97fc66f9369a7ecc5f85d669b333ff305e04a2815fff2bbe00504b03041400000008003653ca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008003653ca5cd6d9047826020000cc05000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d54dd929a30147e950cf7154445bb83ccac54bb76a65d46b7f53aca51d20d1c9ac4b27bd787e813f6499a04a55e00dd197e7272f2fd9c644ec20ac5b3cc001479c97921e74ea65479e7baf290414ee5004b2874e68822a74a87e2e4ca52004d2d28e7aeef79819b5356385168e712118578569c15900822cf794ec5eb0238567367e85c2736ec94293be14661494fb005f5b5d4001dba0d4fca722824c3820838ce9dfbe1dd62661176c5370695bc191353cc1ef1d904eb74ee78c6137038284341f5ef27c4c0b961d24e7e5c489d7fa206793bbed2af6cfddade9e4a8891ef58aab2b9a3cda470a467ae36583dc0a5a689253c2097f64baa7ab11f38e470960af30b5a0be7aca8fff4e5ba193788b1d781f02f08bfb65e4b59a31fa8a25128b022c22cd7746660cbb570ed8f15e66cb64ae82cd338152502bfeb4d223b26816ca044a14257696293760ffad5840deba8611d5956bf83b58dc8e216a337f8e831306e0c8c7b0d5ce8da1c8c3b201fe3e1fba1370a3c8ffcf9f59b2c93754c568f1b12c7bb2d491eeeb74bb25eafedd497d592249bc74fcbf8a9c7eba4f13ae9f70a8261da6675d281f03d3f78e7e9674814926b34f27acc048d99e03f1b07125af72de840e458a88cbff6684f1bed69aff6132aca6d271393926d2ea61dd8beda678dfeec0dfa199e45abf4ac4b7ad02aeede34a5b9e53e53716285241c8e9ac61b4cf5e98afadaa80385a5edd33d2addf67698e9db168459a0f34744d504a6f79b0b3cfa0b504b03041400000008003653ca5c54b763da320200009806000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d956d6fdb2010c7bf0ae203d4699e5bd996daa45d5a6d539468eb6b629f63566c3cc04db34fdfc390ac5a9ccc6f120eeef7e780bb73b893ea55e70086bc17a2d411cd8da96e83402739144c5fc90a4a5cc9a42a9841536d035d296069031522e8f77ae3a060bca471d8cc2d551ccada085ec252115d170553fb7b107217d16b7a9858f16d6e9a89200e2bb68535981f15026806479d9417506a2e4ba2208be8ddf5edb3231a8f9f1c76fad398d8c36ca47cb5c6531ad11eb5da2590fdba12dc6d6764f5153233032150b04f094b0c7f8325ba4574238d91855dc7400d33389529f9074ab7290840678ca63af1762a5ed51ef3b78f98fe3d910debf3f810fb6373b978f60dd33093e285a7268fe894921432560bb392bb05f80b1b35828914baf9253be77cdda324a935c6e369dcb8e0a5fb67ef879bee42f43dd1ef4c0c3c31e84c0c3d313c21a6678891274627c4e80c31f6c4b87354134f4c4e88c11962ea89e909313c43dc78e2a63361c3754fd873c9e41ebf499d39332c0e95dc11650114b48326019be7c08ce1a52dc5b551b8ca9133f1435109b9070803836a762e483c797f99c4eddaa8d965eaced60637fb16727e995cc85ae916ece132f6827d80cc41278a57b65e5b141e2f2baca092ca9035f680ba2d802fffc3dfb0be41b5908b2e243973d14f97e1a592bfb04391994cdbe8e76ef47756fc4307986087c6e532ce76ec6f4c6d79a989c00688bdf66a8285a85c977206b6da268b5d9f6c86397e394059075ccfa43447c326f6f163147f00504b03041400000008003653ca5cfdd7243cc5020000900c00000d000000786c2f7374796c65732e786d6cdd576d6f9b3010fe2b881f3042c8589892481b5aa449db54a9fdb0af261862c92fcc982ae9af9fcf2640da1e6d27f5cb889af8eef173cf9d7d36eaa635674e6f8f949ae024b86cb7e1d198e67314b5872315a4fda01a2a2d52292d88b1a6aea3b6d194942d90048f968b451a09c264b8dbc84eec85698383eaa4d9868b3088769b4ac9d1b50abdc3ce258206f7846fc39c705668e62713c1f8d9fb97ce73505ce9c0d86ce8368c9dab7df013e2de8454fb588249a59d37f232febbe809d7f4d50b1371c427a5ebc216b9d8bb67ca703fad6532ce87d293d03b769b861843b5dc5bc3939cf729d68fefce8d2dbdd6e41c2f3f86af67b48ab31244eb7c9a6ebc5f7dfbb476710a14892651073df763cb2a942ea91e0a8bc38b6bb7e1b432c0d7ac3eba81518d5352c62801a392915a49e22bbfd0fa818d7da09cdf4253feaeae044e55e0bbeb7be91a0b56f832b459f5431fa63740601ace079fc45dfd5bdc86dd2bf3b5b3054967ffe994a1379a56ece4ec53352680858fdf37fcf27dc32763f8e5a3f0a469f8f90b67b514d4efddab15771b72e10547a5d983558323073d1506f7541b7600fb6027d0fe909faa7e9387fd75bb7dd53a8337803b671bfe82bb8c4f2a2d3ac60d93bd75646549e5d30eb2f10d29ec6d7925606795b4221d377703b80dc7f14f5ab24e64c3ac1b588c7ed638fe01c7254ec7bbc58a3159d2132df3deb467f4eab0fac7311e43930be92984b23c884000a25a681a28cbf350adffb1ae355e9707d10cd7cf436b9cb5c6599ef72c94bb0faa85b032fb2025675992a429babc79fe7c1a39ba86690a7f48403443e0a05aa0f6d6959f698099b679a137d05d9e6d1bb4e49916454b9e5979809035044e96210d806a0107dd14b4a32009440b5a0d612509ec339a217acc67a02c43216852a47bd3145ba8143ec87ea1872849b20c810044d248121482033b03a1694022289424fe45fae87d165dde73d1f83fc8ee2f504b03041400000008003653ca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008003653ca5cc70e0c5a480100006f0200000f000000786c2f776f726b626f6f6b2e786d6c8d91d14ec3300c457fa5ca07d0ad82494c2b2f4cc024046843e3396dddd55a12578ebbb17d3d49ab412524c453ea6bf7e45e677124de1744fbe4d31ae7e79cab46a49da7a92f1bb0da5f510b2ef46a62ab2594bc4ba9aeb18425959d0527693699cc5206a305c9f9065baf06da7f58be65d0956f00c49a0165353a75b7b8387be3241d572450c69ba21a952dc2d1ff0cc43239a0c7020dca2957fdb70195587468f10c55ae262af10d1d9f88f14c4eb4d9944cc6e46a3a34b6c082e52f79136dbeebc2f78ae8621d33e76a3609c01ad94b3fd1f375307980303c549dd0031a015e6a8147a6ae45b7eb3121463acad1afe272264e5bc8d5a6b356f3299a08e2aa1a0c49208de2f11c438357d5c01cffff117693aca125163f82647f40b2c1d8c54d05353aa85e02cec746d84d191e261ebd9decfa667a1b76d019731fb457f74cbafa8e77799bbb2f504b03041400000008003653ca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008003653ca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008003653ca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008003653ca5cb57727c400010000f30100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008003653ca5c995c9c23100600009c2700001300000000000000000000008001f2010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008003653ca5cd6d9047826020000cc050000180000000000000000000000808133080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008003653ca5c54b763da320200009806000018000000000000000000000080818f0a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008003653ca5cfdd7243cc5020000900c00000d00000000000000000000008001f70c0000786c2f7374796c65732e786d6c504b010214031400000008003653ca5cb747eb8ac0000000160200000b00000000000000000000008001e70f00005f72656c732f2e72656c73504b010214031400000008003653ca5cc70e0c5a480100006f0200000f00000000000000000000008001d0100000786c2f776f726b626f6f6b2e786d6c504b010214031400000008003653ca5cab5e722eb40000008d0200001a0000000000000000000000800145120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008003653ca5ca5e11b581f010000600400001300000000000000000000008001311300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000811400000000	0	\N	2026-06-10 10:25:45.31641+00	2026-06-10 10:25:45.32775+00	2026-06-10 10:25:45.339081+00
aa41531a-3b1f-43ad-9f8a-fb402129cb85	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_mandays	success	{"preset": "monthly", "date_to": "2026-06-30", "date_from": "2026-06-01", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_mandays_2026-06-01_2026-06-30.xlsx	\\x504b0304140000000800a15aca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800a15aca5cd87db1dd01010000f601000011000000646f6350726f70732f636f72652e786d6ca591cb4ec33010457f25ca3eb19d4a5958a93754aca884a012889d654f5b43fc903d28e9dfe3a46d0a821d4b7bce3dba63772a70e5233c461f20a281548cb67789abb02e8f88811392d411ac4c75265c1eee7db412f3311e4890ea431e803494b6c4024a2d5192495885c5585e945a2dcaf019fb59a015811e2c384c84d58cdc588468d39f8179b29063320b350c433dac662e3762e475fbf03c97af8c4b289d8252745a711541a28f62da289cc6be23df2e27000df620f2a3bc83c2622b9d96a7543c41f01167f80c74979ae72ce82297e1780ab02eaf9397d5dd66775f8a86366d45db8ad11d63bc619c366f93e947fe26b45e9bbdf987f12a101df9f5c5e20b504b0304140000000800a15aca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800a15aca5c6e389403cf010000e103000018000000786c2f776f726b7368656574732f7368656574312e786d6c95536d6bdb3010fe2b423fa04a5cf642b10d49c6b6c006a1c95af65189cfb1a82c79d2254ef7eb77921cd783aeb02ff6bd3d77cfbd28efad7bf20d00b24bab8d2f7883d8dd09e10f0db4d2dfd80e0c796aeb5a89a4baa3f09d03594550ab45369bbd17ad54869779b46d5c99db136a6560e3983fb5ad74cf4bd0b62ff89c5f0df7ead860348832efe411b6803f3a02902ac63c956ac178650d7350177c31bf5b661111231e14f47e22b3d0ccdedaa7a0acab82cf78c86d805db69d56a9dcf38b88b6fb0635ae40eb8287c4f280ea0c1b42147c6f116d1b6912699448b6dad9df601201d040d1c4ac8be1946b887dc59972855a6fb80778e290382dc2bc7e0dadf397d184fea6f275089fe39668887be96165f5a3aab029f847ce2aa8e549e3bdedbfc230f97731e1c16a1fbfac4fc1f3196787932742039a0ab7caa4bfbc5c573645dcfe03910d88b432914a45a29f24ca3277b6672e8453ba20c476d3660aae4cb8a02d3af22ac261b958edd60febddcf5c20650b36711890cbb7915f9c3415db5994fa6fb0200a238f6ce491c56cd9ff664b54a6e0f028cee52c17e7693d31994138fdefd21d95f14cd381d0d1de7ca0d5b8b4a5a4d071c5e6d2a144b1a127082e0490bfb61647258c7a7cd5e51f504b0304140000000800a15aca5c760e844cec010000d904000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d945f6fda3010c0bf8ae5f711a0c0a62a8914a06868d022423bf5d1c0855875eccc364bdb4fbf731c58350ae325f19def77ffec735829fd6272004b5e0b214d44736bcbdb20309b1c0a665aaa04893b99d205b328ea5d604a0d6c5b438508baedf620281897340e6bdd42c7a1da5bc1252c3431fba260fa6d08425511edd08362c977b9ad15411c966c0729d8c712011483a39f2d2f401aae24d1904534e9dc4e3c515b3c71a8cc873571c5ac957a71c2741bd13675be2590b7b414dc87b3aa9c41664720043aec52c23696ff86059a4574adac5585dbc7442db3a8cab47a07e983820034c66cca136befa5f1eacafcd5644cff56e4d2fab83ee43ea99b8bb5af998191123ff9d6e611fd46c91632b61776a9aaefd034ac5f3bdc2861ea2fa9bc71a74dc9666f309f86c6c00597fecf5e0f9dbe86e83644f784e89d216e1ae2e6ea18bd86e89d10fd3344bf21fa57c71834c4c01f816f59ddf031b32c0eb5aa8876e6e8ce2dea63f37724a25cba0b9c5a8dbb1c391ba7b3d6fd43185874e514c1a6c18697b164b49a3e4d57cf9f90a3ff047c1c7eb9408f2fd3f3e47e9c3ca79f807797c1d5c32a9991f3f8e432bebc9b27cb1fff8001f6fa70f37df3ddc8cf99de716988c009c2616d7dc5b3d5fe9a7b0167b50ee407ad5ee6f8f4807606b89f29658f823be3e36b16ff01504b0304140000000800a15aca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b0304140000000800a15aca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800a15aca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b0304140000000800a15aca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800a15aca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800a15aca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800a15aca5cd87db1dd01010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800a15aca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800a15aca5c6e389403cf010000e1030000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800a15aca5c760e844cec010000d90400001800000000000000000000008081390a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800a15aca5c7bb6dee0b8020000080c00000d000000000000000000000080015b0c0000786c2f7374796c65732e786d6c504b01021403140000000800a15aca5cb747eb8ac0000000160200000b000000000000000000000080013e0f00005f72656c732f2e72656c73504b01021403140000000800a15aca5c698cf10e450100006a0200000f0000000000000000000000800127100000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800a15aca5cab5e722eb40000008d0200001a0000000000000000000000800199110000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800a15aca5ca5e11b581f010000600400001300000000000000000000008001851200005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000d51300000000	0	\N	2026-06-10 11:21:02.605067+00	2026-06-10 11:21:02.701087+00	2026-06-10 11:21:02.720694+00
34d89959-41a2-4806-9d82-04e4a0ede0db	9f946201-e71e-4356-b830-2dddae74e9f9	project_mandays	success	{"preset": "daily", "date_to": "2026-06-10", "date_from": "2026-06-10", "project_id": "5a119e5f-cdf8-42b3-bc96-95fd7a03025e"}	project_mandays_2026-06-10_2026-06-10.xlsx	\\x504b03041400000008002b5bca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b03041400000008002b5bca5cca25179a01010000f601000011000000646f6350726f70732f636f72652e786d6ca591cb4ec33010457f25ca3e71ec8a2cacd41b102b2a21a8046267d9d3d6103f640f4af3f738699b8260c7d29e738feed89d0a5cf9088fd1078868201547dbbbc455589707c4c00949ea0056a63a132e0f773e5a89f918f72448f521f74058d3b4c4024a2d5192495885c5589e955a2dcaf019fb59a015811e2c384c84d6945c598468d39f8179b290c764166a18867a58cd5c6e44c9ebe6e1792e5f1997503a05a5e8b4e22a82441fc5b451188f7d47be5d4e001aec41e447790785c5463a2dc7543c41f01167f80474e79aa72ce82297e13806589797c9cbeaf66e7b5f0ad6b0b66ada8a365b4a39bbe18cbd4da61ff9abd07a6d76e61fc68b4074e4d7178b2f504b03041400000008002b5bca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b03041400000008002b5bca5cb32b51635b0200006006000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d55516fda3010fe2b96dfdb4042d7a9229120640c0d0a02d6698f060cb1ead8996da0ddafdfd90e296540fb02b6efbebbefbeb32fedbd54cf3aa7d4a097820b1de3dc98f22108f432a705d1b7b2a4022c6ba90a6260ab36812e15252b072a7810361a5f8282308193b63b9ba8a42db7863341270ae96d5110f5daa55cee63dcc4878329dbe4c61d0449bb241b3aa3e6670900d806759c152ba8d04c0aa4e83ac69de643afe510cee389d1bd3e5a235bcc42ca67bb19ac62dcc036b6a0e8655672e6d3bdbe2d8d2c87746d52ca798cbb21466469d88e4e0011e3853446168e269036c4c0d95ac9bf5478029453f00666a573875895ef19a38f65735d315770cfc173ea58bdfe54a5e337696c7dc7eb8308df5c9740c405d13495fc175b993cc65f315ad135d9723395fbefb452fece055c4aaedd2fda7be7e63d46cbad0642151a12174cf87ff27268d93122ba80082b44788a082f21a20a117d3a47ab42f86b11f8729c183d6248d256728f9475877076e124f5dd8f3113f696ce8c022b039c493ae97cf03498ff6e0706a2d9b3605921bbd791d9a8d168de64a3096a9e01a71f81276178773323c2e452e7e8c716dec89930bdeb61fa8a88159a4b43f87b700032d45a84b516a18b165e8836cab2f9e0b18ffad96336ed0ccf49720a755d73f57a8b1d0abb0404d91d17719cf6d4e31dd3a8661a5d65da1ba7281d0f8719746ffc788e6874994e1a5d2aa2177d9668ab26daba4af462833ccbd6957c9eeb871ebdff3dc213cec1d1f3b0937744d486098d38cc279899b7f73019941f127e03b3cddd393fa7dc32872f0055d601ec6b294dbdb1afb0fea824ff00504b03041400000008002b5bca5c6fafd3604b020000c106000018000000786c2f776f726b7368656574732f7368656574322e786d6c9d955d73a2301486ff4a26f72b0ad5ee74801954ec3a8b1fa3b63bbd8c1a2453206c88daf6d7ef4940cba8b09dde6892739ef77c100ef6918bd73ca254a2b7244e73074752660f86916f229a90bcc5339a8225e4222112b66267e499a064aba12436cc76bb672484a5d8b5f5d95cb836dfcb98a5742e50be4f1222defb34e6470777f0e960c17691d407866b67644797543e6500c0d638eb6c5942d39cf114091a3ad8eb3c8c2c4d688f67468f79658d54316bce5fd566bc75701b2bed94a2f76516b3229ce459404339a0710c8226466423d981cec1cdc16b2e254f941d129544c25128f8074d8ba034a6e00cd96457de854aa9aacafc5b668c3f2b526955d7a7dc47bab950fb9ae474c0e33f6c2b2307ffc4684b43b28fe5821f7fd1b2615d2db8e171ae7fd1b170eeb431daec73c8a7a42170c2d2e29fbc9d3a5d25ee6b08b324cc2f1356495857445d567725717745746b886e4974bf1ca35712bde211142dd30d1f12495c5bf02312ca1de4d4423fb6e28e3898a5ea022fa5002b034ebacba0359dd986042975606c4aacdf8c7983d5f879bc7ab9410efe13f0a9ffa3811e36d3136f3af45e963740bf195ccd565e80eaf15133bef027dee2f7056840afcf0d37cf0d37b5869a1c07b7631b876a57cd1afde16c8006b320f0a133b3e9adae7e9b1c36e4e337d8469711f57dab966c9d4bb62a32e645c956dda3f4fdd578fa881efda9bff0825b357f1f1d5a0d4537d84697213f8b362a2f991aed1322762ccd510c93128672eb1ede61518cb3620333595fa862a0ea65049f182a9403d843cee579a3c29cbf5aee3f504b03041400000008002b5bca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b03041400000008002b5bca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b03041400000008002b5bca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b03041400000008002b5bca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b03041400000008002b5bca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b010214031400000008002b5bca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b010214031400000008002b5bca5cca25179a01010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b010214031400000008002b5bca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b010214031400000008002b5bca5cb32b51635b02000060060000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b010214031400000008002b5bca5c6fafd3604b020000c10600001800000000000000000000008081c50a0000786c2f776f726b7368656574732f7368656574322e786d6c504b010214031400000008002b5bca5c7bb6dee0b8020000080c00000d00000000000000000000008001460d0000786c2f7374796c65732e786d6c504b010214031400000008002b5bca5cb747eb8ac0000000160200000b00000000000000000000008001291000005f72656c732f2e72656c73504b010214031400000008002b5bca5c698cf10e450100006a0200000f0000000000000000000000800112110000786c2f776f726b626f6f6b2e786d6c504b010214031400000008002b5bca5cab5e722eb40000008d0200001a0000000000000000000000800184120000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b010214031400000008002b5bca5ca5e11b581f010000600400001300000000000000000000008001701300005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000c01400000000	2	\N	2026-06-10 11:25:22.613553+00	2026-06-10 11:25:22.635714+00	2026-06-10 11:25:22.646344+00
a10a07ac-3259-4027-9add-fc7f42f00520	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_mandays	success	{"preset": "daily", "date_to": "2026-06-11", "date_from": "2026-06-11", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_mandays_2026-06-11_2026-06-11.xlsx	\\x504b0304140000000800605bca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800605bca5c4bb38ba301010000f601000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301486ff4ae97d9ba4830aa1cb8de29503d181e25d48ceb668f34172a4ebbf37edb64ed13b2f93f3bc0fef493a15b8f2111ea30f10d1402a8eb67789abb02e0f88811392d401ac4c75265c1eee7cb412f331ee4990ea43ee813494b6c4024a2d5192495885c5589e955a2dcaf019fb59a015811e2c384c84d58c5c598468d39f8179b290c764166a18867a58cd5c6ec4c8ebe6e1792e5f1997503a05a5e8b4e22a82441fc5b451188f7d47be5d4e001aec41e447790785c5463a2dc7543c41f01167f80474e79aa72ce82297e13806589797c9cbeaf66e7b5f8a86366d45db8ad12d63bcb9e194be4da61ff9abd07a6d76e61fc68b4074e4d7178b2f504b0304140000000800605bca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800605bca5c6e389403cf010000e103000018000000786c2f776f726b7368656574732f7368656574312e786d6c95536d6bdb3010fe2b423fa04a5cf642b10d49c6b6c006a1c95af65189cfb1a82c79d2254ef7eb77921cd783aeb02ff6bd3d77cfbd28efad7bf20d00b24bab8d2f7883d8dd09e10f0db4d2dfd80e0c796aeb5a89a4baa3f09d03594550ab45369bbd17ad54869779b46d5c99db136a6560e3983fb5ad74cf4bd0b62ff89c5f0df7ead860348832efe411b6803f3a02902ac63c956ac178650d7350177c31bf5b661111231e14f47e22b3d0ccdedaa7a0acab82cf78c86d805db69d56a9dcf38b88b6fb0635ae40eb8287c4f280ea0c1b42147c6f116d1b6912699448b6dad9df601201d040d1c4ac8be1946b887dc59972855a6fb80778e290382dc2bc7e0dadf397d184fea6f275089fe39668887be96165f5a3aab029f847ce2aa8e549e3bdedbfc230f97731e1c16a1fbfac4fc1f3196787932742039a0ab7caa4bfbc5c573645dcfe03910d88b432914a45a29f24ca3277b6672e8453ba20c476d3660aae4cb8a02d3af22ac261b958edd60febddcf5c20650b36711890cbb7915f9c3415db5994fa6fb0200a238f6ce491c56cd9ff664b54a6e0f028cee52c17e7693d31994138fdefd21d95f14cd381d0d1de7ca0d5b8b4a5a4d071c5e6d2a144b1a127082e0490bfb61647258c7a7cd5e51f504b0304140000000800605bca5c760e844cec010000d904000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d945f6fda3010c0bf8ae5f711a0c0a62a8914a06868d022423bf5d1c0855875eccc364bdb4fbf731c58350ae325f19def77ffec735829fd6272004b5e0b214d44736bcbdb20309b1c0a665aaa04893b99d205b328ea5d604a0d6c5b438508baedf620281897340e6bdd42c7a1da5bc1252c3431fba260fa6d08425511edd08362c977b9ad15411c966c0729d8c712011483a39f2d2f401aae24d1904534e9dc4e3c515b3c71a8cc873571c5ac957a71c2741bd13675be2590b7b414dc87b3aa9c41664720043aec52c23696ff86059a4574adac5585dbc7442db3a8cab47a07e983820034c66cca136befa5f1eacafcd5644cff56e4d2fab83ee43ea99b8bb5af998191123ff9d6e611fd46c91632b61776a9aaefd034ac5f3bdc2861ea2fa9bc71a74dc9666f309f86c6c00597fecf5e0f9dbe86e83644f784e89d216e1ae2e6ea18bd86e89d10fd3344bf21fa57c71834c4c01f816f59ddf031b32c0eb5aa8876e6e8ce2dea63f37724a25cba0b9c5a8dbb1c391ba7b3d6fd43185874e514c1a6c18697b164b49a3e4d57cf9f90a3ff047c1c7eb9408f2fd3f3e47e9c3ca79f807797c1d5c32a9991f3f8e432bebc9b27cb1fff8001f6fa70f37df3ddc8cf99de716988c009c2616d7dc5b3d5fe9a7b0167b50ee407ad5ee6f8f4807606b89f29658f823be3e36b16ff01504b0304140000000800605bca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b0304140000000800605bca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800605bca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b0304140000000800605bca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800605bca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800605bca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800605bca5c4bb38ba301010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800605bca5c995c9c23100600009c2700001300000000000000000000008001f3010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800605bca5c6e389403cf010000e1030000180000000000000000000000808134080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800605bca5c760e844cec010000d90400001800000000000000000000008081390a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800605bca5c7bb6dee0b8020000080c00000d000000000000000000000080015b0c0000786c2f7374796c65732e786d6c504b01021403140000000800605bca5cb747eb8ac0000000160200000b000000000000000000000080013e0f00005f72656c732f2e72656c73504b01021403140000000800605bca5c698cf10e450100006a0200000f0000000000000000000000800127100000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800605bca5cab5e722eb40000008d0200001a0000000000000000000000800199110000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800605bca5ca5e11b581f010000600400001300000000000000000000008001851200005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000d51300000000	0	\N	2026-06-10 11:27:00.812948+00	2026-06-10 11:27:00.825052+00	2026-06-10 11:27:00.833395+00
fb8dc457-1ebd-42ed-82fc-03ff4adf4fd7	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_mandays	success	{"preset": "weekly", "date_to": "2026-06-07", "date_from": "2026-06-01", "project_id": "dc7a5e96-2808-4842-8924-b03e9c51c4a6"}	project_mandays_2026-06-01_2026-06-07.xlsx	\\x504b0304140000000800575bca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800575bca5cb3b42d7c02010000f601000011000000646f6350726f70732f636f72652e786d6ca591cb4ec33010457f25ca3e719ca22059a937205654425009c4ceb2a7ad217ec81e94e4ef71d23605c1ae4b7bce3dba63b7d233e9023c05e721a086980da6b39149bfce0f889e1112e5018c8865226c1aee5c3002d331ec8917f253ec81d455d51003289440412661e117637e522ab928fd57e8668192043a306031125a527261118289ff06e6c9420e512f54dff765bf9ab9d48892b7cde3cb5cbed036a2b01272de2ac96400812ef069233f0e5d4b7e5c4e006aec80a747f90089d9465825c6983d83770167f808b4a79ac72ca82c9561387a58e7e7c9ebeaee7efb90f3baaa9ba26a0a5a6d296575c36e6edf27d3affc45689cd23b7d85f12ce02df9f3c5fc1b504b0304140000000800575bca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800575bca5c6e389403cf010000e103000018000000786c2f776f726b7368656574732f7368656574312e786d6c95536d6bdb3010fe2b423fa04a5cf642b10d49c6b6c006a1c95af65189cfb1a82c79d2254ef7eb77921cd783aeb02ff6bd3d77cfbd28efad7bf20d00b24bab8d2f7883d8dd09e10f0db4d2dfd80e0c796aeb5a89a4baa3f09d03594550ab45369bbd17ad54869779b46d5c99db136a6560e3983fb5ad74cf4bd0b62ff89c5f0df7ead860348832efe411b6803f3a02902ac63c956ac178650d7350177c31bf5b661111231e14f47e22b3d0ccdedaa7a0acab82cf78c86d805db69d56a9dcf38b88b6fb0635ae40eb8287c4f280ea0c1b42147c6f116d1b6912699448b6dad9df601201d040d1c4ac8be1946b887dc59972855a6fb80778e290382dc2bc7e0dadf397d184fea6f275089fe39668887be96165f5a3aab029f847ce2aa8e549e3bdedbfc230f97731e1c16a1fbfac4fc1f3196787932742039a0ab7caa4bfbc5c573645dcfe03910d88b432914a45a29f24ca3277b6672e8453ba20c476d3660aae4cb8a02d3af22ac261b958edd60febddcf5c20650b36711890cbb7915f9c3415db5994fa6fb0200a238f6ce491c56cd9ff664b54a6e0f028cee52c17e7693d31994138fdefd21d95f14cd381d0d1de7ca0d5b8b4a5a4d071c5e6d2a144b1a127082e0490bfb61647258c7a7cd5e51f504b0304140000000800575bca5c760e844cec010000d904000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d945f6fda3010c0bf8ae5f711a0c0a62a8914a06868d022423bf5d1c0855875eccc364bdb4fbf731c58350ae325f19def77ffec735829fd6272004b5e0b214d44736bcbdb20309b1c0a665aaa04893b99d205b328ea5d604a0d6c5b438508baedf620281897340e6bdd42c7a1da5bc1252c3431fba260fa6d08425511edd08362c977b9ad15411c966c0729d8c712011483a39f2d2f401aae24d1904534e9dc4e3c515b3c71a8cc873571c5ac957a71c2741bd13675be2590b7b414dc87b3aa9c41664720043aec52c23696ff86059a4574adac5585dbc7442db3a8cab47a07e983820034c66cca136befa5f1eacafcd5644cff56e4d2fab83ee43ea99b8bb5af998191123ff9d6e611fd46c91632b61776a9aaefd034ac5f3bdc2861ea2fa9bc71a74dc9666f309f86c6c00597fecf5e0f9dbe86e83644f784e89d216e1ae2e6ea18bd86e89d10fd3344bf21fa57c71834c4c01f816f59ddf031b32c0eb5aa8876e6e8ce2dea63f37724a25cba0b9c5a8dbb1c391ba7b3d6fd43185874e514c1a6c18697b164b49a3e4d57cf9f90a3ff047c1c7eb9408f2fd3f3e47e9c3ca79f807797c1d5c32a9991f3f8e432bebc9b27cb1fff8001f6fa70f37df3ddc8cf99de716988c009c2616d7dc5b3d5fe9a7b0167b50ee407ad5ee6f8f4807606b89f29658f823be3e36b16ff01504b0304140000000800575bca5c7bb6dee0b8020000080c00000d000000786c2f7374796c65732e786d6cdd56dd6e9b30147e15c4038c103616a624d2861669d236556a2f766b822196fcc38ca9923efd7c6c2790b687b6d3ae4694e0733e7fe7df90756f4e9cde1e2835d15170d96fe28331dda724e9f7072a48ff4e75545aa4515a106345dd267da729a97b20099e2c178b3c1184c978bb9683d809d3477b3548b3891771946cd78d92a32a8bbdc2ee258246f7846fe292705669e63713c1f8c9eb974eb3575ce9c8d868e8264e9daa7ff01bd22042a8c196605269a74dbc1bff5b05c2c4a26e2b1be162e7ae17180171b7deee609c5f676415db75478ca15aeeace0494efb140bebbb5367336a3539a5cb0ff1eb19bde2ac06a76d394d24ddbdfffa71e5ec5428924cac5efcb99b4dab52baa6fa92581a9f55db35a78d01be66edc12d8cea9c27658c12b0aa196995243ef3332d2caced3de5fc1666ed5773e5e0d8447e68bed56e5ea0c2e7a58d2a2cbd99208083a9396f7c6237fb3bbb1dbb57e6cb6013924efe3d28436f346dd8d1c9c7660c00339f8ee6978fcc93aee3a7cf9cb552509ffdab3d6ed7e4cc8b0e4ab307eb0d8613ba1247f7541bb607796f37d030fdc7068f72f96f8a9084ba4fba7bd5db8b3682b3be897fc233844f6c5403e386c9201d585d53f9b4c5d6be21957d4a5d39b0bb6ada90819bbb0bb889c7f50f5ab34114975d379058d835aebfc33ca7f9f858b0ce98ace991d66510ed21ba3a4dfe728cc7d0e459f21442591e442000515f681828cbf3505fff635e2b3c2f0fa211ae9e8756386b85b33cef59a8741fd417c22aec85a45c145996e76879cbf2f9304ab486790e5fc4201a2170505fe0edad959f198099b1796136d02ecf8e0d9af2cc88a229cf541e20a486c0290a6400505fc0419b824e140481f88251435859067d4623448ff90c54142804438a4c6f9e6385cae183f40b3d44595614080420124696a1101cd819080d030241a12cf32fd247efb3e4fc9e4bc6fffedb3f504b0304140000000800575bca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800575bca5c698cf10e450100006a0200000f000000786c2f776f726b626f6f6b2e786d6c8d91dd4ec3300c855fa5ca03d0ae82494ceb6e988049fc89a1dda78dbb5a4be2ca4937b6a7276955a88484b84a7d6c7f3d27599e880f25d121f934daba0517a2f1be5da4a9ab1a30d25d510b36f46a62237d28799f525d63056baa3a03d6a77996cd53062d3d92750db64e0cb4ffb05ccb20956b00bcd103ca48b462b51c9dbd71924e2bf250c53f45352a3b8493fb198865724487256af4e742f4df1a4462d0a2c10ba8426422710d9d1e89f142d64bbdad98b42ec46c68ec803d56bfe46db4f9214bd72b5e96ef317321e65900d6c8cef7133d5f06934708c343d579ba47ed81d7d2c30353d7a2ddf79810239de4e8af623c132b0d14e2595a25cf2e9a08e2460d867c204de2f1024383376a604ef7b79d3192cf93fdfc8ffd7cf0341a5150a305f512482e36c2b554e14de2d13bc9af6f66b7217ea7f55dd05eed1349f59d6c7c96d517504b0304140000000800575bca5cab5e722eb40000008d0200001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73c5924d0a83301046af127200476de9a2a8ab6edc162f1074fcc1c484cc94eaed2bba50a18b6ea4abf04dc8fb1e4c92276ac59d1da8ed1c89d1e88152d932bb3b00952d1a45817538cc37b5f546f11c7d034e95bd6a10e230bc81df336496ec99a2981cfe42b475dd95f8b0e5cbe0c05fc0f0b6bea71691a528946f905309a3dec604cb110533598abc4aa5cfab480af8b7517c308acf34229e34d2a6b3e643ffe5cc7e9edfe256bfc475785ccb759180c3efcb3e504b0304140000000800575bca5ca5e11b581f01000060040000130000005b436f6e74656e745f54797065735d2e786d6cc554cb4ec33010fc95c8d72a76e981036a7aa15ca1077ec0249bc68a5ff26e4bfaf76c125a09545aaa20718915efeccc78c7f2f2f51001b3ce598f856888e283525836e034ca10c173a50ec969e2dfb4555197adde825acce7f7aa0c9ec0534e3d87582dd750eb9da5eca9e36d34c117228145913d8ec05eab103a466b4a4d5c577b5f7d53c93f1524770e186c4cc4190344a6ce4a0ca51f158e8d2f7b48c954906d74a267ed18a63aab900e16505ee638e332d4b529a10ae5ce718bc4984057d80090b372249d5d91261e328cdfbbc906069a8b8a0cdda41091534b70bbde3196be3b8f4c0489cc95439e24997bf209a14fbc82eab7e23ce1f790da211354c3327dcc5f733ef1df6a64f19f46de4268fffac2f7ab74daf89301353c2cab0f504b01021403140000000800575bca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800575bca5cb3b42d7c02010000f60100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800575bca5c995c9c23100600009c2700001300000000000000000000008001f4010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800575bca5c6e389403cf010000e1030000180000000000000000000000808135080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800575bca5c760e844cec010000d904000018000000000000000000000080813a0a0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800575bca5c7bb6dee0b8020000080c00000d000000000000000000000080015c0c0000786c2f7374796c65732e786d6c504b01021403140000000800575bca5cb747eb8ac0000000160200000b000000000000000000000080013f0f00005f72656c732f2e72656c73504b01021403140000000800575bca5c698cf10e450100006a0200000f0000000000000000000000800128100000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800575bca5cab5e722eb40000008d0200001a000000000000000000000080019a110000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800575bca5ca5e11b581f010000600400001300000000000000000000008001861200005b436f6e74656e745f54797065735d2e786d6c504b0506000000000a000a0084020000d61300000000	0	\N	2026-06-10 11:26:47.373616+00	2026-06-10 11:26:47.388033+00	2026-06-10 11:26:47.398235+00
d8661076-fa2d-44fe-a035-d80b00e38e88	9f946201-e71e-4356-b830-2dddae74e9f9	employee	success	{"preset": "weekly", "date_to": "2026-06-07", "date_from": "2026-06-01", "employee_id": "e5ce164a-f805-4970-80be-cbd21533d1d0"}	employee_2026-06-01_2026-06-07.xlsx	\\x504b0304140000000800b65dca5c46c74d4895000000cd00000010000000646f6350726f70732f6170702e786d6c4dcf4d0bc2300c06e0bf5276b7998a1ea40e443d8a9ebccf2e7585b6296d84faefed043f6e7979c81ba22e892226b69845f12ee46d3332c70d40d623fa3ecbcaa18aa1e47bae31dd818cb11a0fa41f1e03c3a26dd78085310c38cce2b7b0e9d42e466775cf964277b23a5126c3e258343ab1271fabdc1c0a10e77a253e8b134b39972b05ff8b53cb15539ee6ca6ffc6405bf07ba17504b0304140000000800b65dca5c3564593406010000fa01000011000000646f6350726f70732f636f72652e786d6ca5915d4bc3301885ff4ae97d9bb6abbd085d6efc00414174a0781792775b305f24ef6cfbef6dbbad53f4cecbe43ce7e184b4c253e1023c05e721a08298f446db48855fa77b444f0989620f86c77c24ec186e5d301cc763d811cfc507df01a98aa22106904b8e9c4cc2cc2fc6f4a4946251fa43d0b3400a021a0c588ca4cc4b72611182897f16e66421fba816aaebbabc5bcddcb8a8246f8f0f2ff3f84cd988dc0a48592b05150138bac0a617f9a1d72df9763901a85003bbb7527d2a79e03ab9355ebb01207906ef02ce8523d49ea61efb20937110c5c1c33a3d27afabeb9bcd5dcaaaa26ab2a2c9ca625396b4bea275fd3e997ef42f42e3a4daaa7f18cf02d6925fdfccbe00504b0304140000000800b65dca5c995c9c23100600009c27000013000000786c2f7468656d652f7468656d65312e786d6ced5a5b73da38147eefafd07867f66d0bc63681b6b413736976dbb49984ed4e1f8511588d6c796491847fbf473610cb960ded924dba9b3c042ce9fbce4547e7e83879f3ee2e62e8868894f27860d92fdbd6bbb72fdee057322411413019a7aff0c00aa54c5eb55a6900c3387dc91312c3dc828b084b7814cbd65ce05b1a2f23d6eab4dbdd5684696ca1184764607d5e2c6840d054515a6f5f20b4e51f33f815cb548d65a30113574126b988b4f2f96cc5fcdade3e65cfe93a1d32816e301b58207fce6fa7e44e5a88e154c2c4c06a673f566bc7d1d2488082c97d9405ba49f6a3d31508320d3b3a9d58ce767cf6c4ed9f8ccada74346d1ae0e3f17838b6cbd28b701c04e051bb9ec29df46cbfa44109b4a369d064d8f6daae91a6aa8d534fd3f77ddfeb9b689c0a8d5b4fd36b77ddd38e89c6add0780dbef14f87c3ae89c6abd074eb692627fdae6ba4e916684246e3eb7a1215b5e540d32000587076d6ccd203965e29fa75941ad91dbbdd415cf058ee398911fec6c504d669d219963446729d90050e0037c4d14c507caf41b68ae0c292d25c90d6cf29b5501a089ac881f5478221c5dcaffdf597bbc9a4337a9d7d3ace6b947f69ab01a7edbb9bcf93fc73e8e49fa793d74d42ce70bc2c09f1fb235b6187276e3b13723a1c67427ccff6f691a52532cfeff90aeb4e3c671f5696b05dcfcfe49e8c7223bbddf6587df64f476e23d7a9c0b322d7944624459fc82dbae41138b5490d32133f089d86986a501c02a4093196a186f8b4c6ac11e0137db7be08c8df8d88f7ab6f9a3d57a15849da84f810461ae29c73e673d16cfb07a546d1f655bcdca3975815019718df34aa352cc5d67895c0f1ad9c3c1d1312cd940b06418697242612a9397e4d4813fe2ba5dafe9cd340f0942f24fa4a918f69b323a77426cde8331ac146af1b758768d23c7afe05f99c350a1c911b1d02671bb346218469bbf01eaf248e9aadc2112b423e6219361a72b51681b671a984605a12c6d1784ed2b411fc59ac35933e60c8eccd9175ced6910e11925e37423e62ce8b9011bf1e86384a9aeda2715804fd9e5ec349c1e882cb66fdb87e86d5336c2c8ef747d4174ae40f26a73fe9323407a39a5909bd84566a9faa87343ea81e320a05f1b91e3ee57a780a3796c6bc50ae827b01ffd1da37c2abf882c0397f2e7dcfa5efb9f43da1d2b737237d67c1d38b5bde466e5bc4fbae31dad7342e28635772cdc8c754af9329d8399fc0ecfd683e9ef1edfad92484af9a592d2316904b81b34124b8fc8bcaf02ac409e8645b2509cb54d365378a129e421b6ee953f54a95d7e5afb928b83c5be4e9afa1743e2ccff93c5fe7b4cd0b3343b7724beab694beb526384af4b1cc704e1ecb0c3b673c921db677a01d35fbf65d76e423a530539743b81a42be036dba9ddc3a389e9891b90ad352906fc3f9e9c5781ae239d904b97d98576de7d8d1d1fbe7c151b0a3ef3c961dc788f2a221eea18698cfc34387797b5f986795c65034146d6cac242c46b760b8d7f12c14e064602da00783af5102f2525560315bc6032b90a27c4c8c45e870e7975c5fe3d192e3dba665b56eaf2977196d225239c269981367abcade65b1c1551dcf555bf2b0be6a3db4154ecffe59adc89f0c114e160b1248639417a64aa2f31953bee72b49c45538bf4533b6129718bce3e6c7714e53b81276b60f0232b9bb39a97a653167a6f2df2d0c092c5b885912e24d5dedd5e79b9cae7a2276fa9777c160f2fd70c9470fe53be75ff45d43ae7ef6dde3fa6e933b484c9c79c5110174450223951c06161732e450ee9290061301cd94c944f0028264a61c8098fa0bbdf20cb92915cead3e397f452c83864e5ed22512148ab00c05211772e3efef936a778cd7fa2c816d84543264d517ca4389c13d337243d85425f3aeda260b85dbe254cdbb1abe26604bc37a6e9d2d27ffdb5ed43db4173d46f3a399e01eb387739b7ab8c245acff58d61ef932df3970db3ade035ee6132c43a47ec17d8a8a8011ab62bebaaf4ff9259c3bb47bf181209bfcd6dba4f6dde00c7cd4ab5aa5642b113f4b077c1f9206638c5bf4345f8f1462ada6b1adc6da310c798058f30ca16638df87459a1a33d58bac398d0a6f41d540e53fdbd40d68f60d341c91055e3199b636a3e44e0a3cdcfeef0db0c2c48ee1ed8bbf01504b0304140000000800b65dca5c415b0ea1a80200005709000018000000786c2f776f726b7368656574732f7368656574312e786d6c8d96dd6e9b3018866fc5e27ce527bfad92486db669d5542d6af773ecc047f06a6c669bd29ced227685bb92d926251cd85ea4106cf0fb7e0f185eb3eab87896158042af3565721d554a3537712cf30a6a2caf78034c9f29b9a8b1d25d7188652300175654d3384b92795c63c2a2cdca1edb89cd8ab78a12063b81645bd7581cef80f26e1da5d1db814772a8943d106f560d3ec013a86f8d16e86e3cf814a4062609674840b98e6ed39bbb74662576c877029d1cb591b99a3de7cfa6735faca3c44001855c190fac772fb0054a8d9546f975728dce558d72dc7eb3ff686f80e6db63095b4e7f904255eb6819a1024adc52f5c8bb4f70baa81e31e754da7fd4f583b37984f2562a5e9fd4ba704d58bfc7af6f7763a498261e457652643d7a5fca82bec70a6f5682774898e1dace34ece55ab9e623cc4cce9312fa2cd13ab5b967057921458b29fa5037941f01d023345ca855acb4bf1915e77ad3be83f964309f58f3cc63ee32b2babbc9e538018ee9c0310d72b8ad7a92a947f38499aab8acd0e7563fb50188d90031bb08026d79e12499f9840fbb2c9b0508e603c13c48f0a52c49ee2c3df728b615308649a0f662a8bd08d6de8120bc70d55e78145992cddf25fa9722c5d1d05b04609603cc320c234082f3b95c7a141dc0333d064a5f0fa5af83a56f9502566096032af051ba18ae3dd234503e4dceef7b1204f8ca957eb94c5c42812ade0a27833171ca975749e8514c47b993fe670ef84f9dcef284e284f085d62444909d09b20bd249a2bfbfffe8b5695f133d356e0e9f437046ce21995e92923d076e1ac15f3c18bed00cde8e7346a6e1901c63083073e3c1f0256612c238a7641a8ec931462170e97c4d535f563a19e2d1f2683e381eb03810261185529b24570bed26fa05bcef28ded81573cf955e806db3d21f3e20cc007dbee45c0d1db30a0fdf529b7f504b0304140000000800b65dca5c1825d0c534020000f105000018000000786c2f776f726b7368656574732f7368656574322e786d6c8d94ed6e9b3014866f05710131d07c741120ad69a356dad4aad1d6df4e38042bc666b609edae7ec786646c81a8f991f8e33cafcf79639fb891eaa00b00e3bd975ce8c42f8ca99684e85d0125d5135981c09d5caa921a9caa3dd195029a39a8e4240a82392929137e1abbb51795c6b2369c0978519eaecb92aa8f3be0b249fcd03f2dbcb27d61dc0249e38aee6103e64785004ec95927632508cda4f014e489ff355cae2347b8889f0c1add1b7bb698ad94073b79ca123ff0adb600ef635371d61e6764f50d72b302ce5110d5e8ceb023bc6058e26fa531b2b4fb98a8a1069772257f83680f050e188cd95417d1ad4aa76acbfcd565ecffadc8a6d51f9f725f3b73b1f62dd5b092fc8d65a648fc5bdfcb20a73537afb27984ceb09913dc49aeddb7d7b4c12156b2ab35e6d3d17870c944fb4bdf4f4ef7896084883a22ba20c211e2a6236e2e88e90831ed88e905311f21661d31fb741df38e98b77f416b9933fc9e1a9ac64a369eb2e1286707ee6f7345a0cf4cd80bbc310a771972264508626250c9cec9aea3eeae53ab027607ef490c90abcf90cfb51940efafa36ff80e20f31e65adf400fd709d7e3e8232f8f046f9f5757e830fa7fe8f2368f6d9f1e8ec78e484a64ec83690633a9d878b454c8e7d87a39183822fcb201a32760c0817cb60366467d4cbe07612cc82de27fc379b877e6c30b17afdedf5d8d9d834350833640be95d4adb0abf53b567427b1c3b0b36b1c902efbc6a9f7f3bc11ee6ae79db80dcb0c0960cca06e07e2ea5394fecdd3f77f9f40f504b0304140000000800b65dca5c213cd57bc0030000e40b000018000000786c2f776f726b7368656574732f7368656574332e786d6cb5965b93a2381480ffca29b66a6be6611ae5a23db36a154244aa1518c0e99a475aa3b2038485d84eefafdf70d17135b1bab66a5f94907ce724f9089cd191943faa3dc6147e66695e8da53da5c51759aed67b9cc5d5032970ce7ab6a4cc62ca9ae54eae8a12c79b06ca5259e9f506721627b9341935f7fc723222079a2639f64ba80e5916976f539c92e358ea4ba71b41b2dbd3e6863c1915f10e8798ae0a06b0a67c8eb349329c5709c9a1c4dbb164f4bfd87a433423be25f8585d5c43bd9817427ed40d6733967a521d3bc7f0161669d2a6a3a458e02d35719ab2808a04f19a26afd867c3c6d20ba19464753f9b288d29bbb52dc9df386f93e214b3c16c36c5cde8364a17b55ee65fdd8ca55f2baaa775797d9afbacd95cb6f697b8c226499f930ddd8fa5470936781b1f521a90e31c771bd6ae7f4dd2aaf985633bb8cf56b23e546c3e1dcd126749defec73f4f3b7d49680242e908e59a18f40484da11ea4d8ea180d03a42bb214439f48ed06f88470131e888c10da10b8861470c5b69ed26378aac98c69351498e50d6c359b8faa211dd2c9b9949f2fa910f69c97a13c6d10983f048a62c52dd96d71d35bd4ff925f9933d6660920d8f36df47bb71c6a3adfbb4513fc5097de390e83e392787b2e260b3fbd8333bb160e16a5d26457db23811ecfb11025c909242c84eebe16a0232f37596a69ca5294d3cad8957bfb55e27daa03f7c1cc9af97921441be85a928fd9ea6f77a3c39220af98e09332f8000f90bc3444be446e0cdc09b86de0245084273ee22c74201a0af2bc76ffa3fa80fead337089f9dc89cdbc8083e82e3c2d3dc889cefc61c5c2f88e660213b4046e8b8368411ebf15cf860add820f723cfbf68824e04e1caf759489e7be562b37affdea89928a2e599e058539e5111121745495ef1e68e46f5ac51e56a1c5e69143d369f7baaa6a894e75078b4e646883ef5c13243f83dce8a3fc045d1b3173cc1cab703c34260b816b4a314303d370abcc50205e1a99fe743f8ee60bb67d6b8592be53951ef381145651f97e61396ef6043d6bcf36a8bd077b8d1ce6e34ae9bcf576e34412abb3962ea907fc444d449423447b522195068c9333b84f07b18a12518113019bf29bad1783af5b2db46604c3f59e0da0b880cf7096646b0e4b912655e2214d5e7cf462e0a8c054fd6e5565cbd6966a2b019fbee30533c4922e41d92f4b3249d2b49bb92a4ff274922eaff9724cafc0e49fac556e85792aec3362545e34294b03abc6409a57c19f245555157bfcbb8dc257905292b2659ddfa306451cbb6e26b1bac6c6dea94b6e66c2ef7ac0ac7653d80f56f09a1e7465dbc9c0bfbc93f504b0304140000000800b65dca5c1281471e9b0200003805000018000000786c2f776f726b7368656574732f7368656574342e786d6c7d545d6fda3014fd2b579e34b50f6b20d06eea0892490c8980244b42ab3eba60206b12678e29ed7efdec0432a6415fc0f7e35c9f739d7b077b2e5eaa2d6312def2aca82cb495b2bc378c6ab96539ad6e78c90a1559739153a94cb131aa5230baaa417966989dce9d91d3b440c341ed0bc570c077324b0b160aa876794ec5fb88657c6fa12e3a3aa274b395b5c3180e4aba6131938b52019469b4755669ce8a2ae50508b6b610eede8ffa35a2ce7848d9be3a398316f3ccf98b36bc95853a48d72e18bcc7659636d7495eced85ada2ccb544113015dcaf495852acd42cf5c4a9eebb8222aa954aeb5e0bf59d15cca32a692159bf2bfeca6caa1aa96f9ebc018fd55a4699d9e8fdcc7757395f6675a319b678fe94a6e2df40dc18aade92e9311dfbbecd0b0dbbae0926755fd0bfb26f9ae8360b9ab149f035a5d9ca745f34fdf8e9d3e4174fb1710e6016136d49bab6aa20e957438107c0f42a7ab72fa50cbb5504ff5d64269a11f3e964245538593c350f09faa6d0343aa62da652c0fc0d1c74097ef440533bed9b0d5bf6843516879982d0ff342a1453889b04320710938766c00891d633c89217e8a1332079cc08c449fcc5b0cd877daa872e3088fbe38e04f6690607f0a631ccdcf09696ed623f03aecf606c6eb199ebd96e725c124f46c18071144249c619bcc899f403086601407339210886dd7279e4322203f165e58c7af7a37bde903c48f5e62bb1382a36bf07c98ba38f19eb00b7e10252e386412111c7bfe04e24445021fae9c854af2afcfc9e99dc8e99c57d36fd5f42fbdbb8b63f2a5ab3b0e9f695e7e079f248f413485e37be866375926d8819f44c14cbd437c8c9f63d6ff809971f28dea8d32a762931615646a40d52eb8f9aa46473453d4186a15d45f7d33c7f571ab361b133a41c5d79ccbd6d0a3d02ecbe11f504b0304140000000800b65dca5c81a25029e20200002a0d00000d000000786c2f7374796c65732e786d6cdd57df6f9b3010fe5710ef1d494859980069438b34699b2ab50f7d75822196fc83195325fdebe7c31448daa3ddb4becc51827d9fbfefeeecb35192c69c38bd3d506abca3e0b249fd8331f5a72068f6072a48f341d5545aa4545a106387ba0a9a5a53523440123c582d16512008937e96c8566c8569bcbd6aa549fde560f2dce35b618dd1daf79c5cae0a9afa27dbae84b82a0adf0bb224e845b2a45472d45afbce601589a0de03e1a99f13ce769a75b49208c64fcebeea2c7bc595f68c4d834228606a1edd84653f841c7b2dc1a4d22e00e7c6fdee7ac2397dfdca441c7141e96a97fa8bc5b66b5346f780d419e743eaa1ef0c59521363a8965b3b70a4cefa1cebfb77a7daa65e69725aaeaefdb7331ac559014eab7c1aee72bbfefa71d3e9ec502498a80efeba874d6ba77441f5597d385396705a1ae06b561dba8e5175e74919a304f40a462a2589cbfc89d677acf69e727e0bd57c5f9e39389693e25b40e9c9a16ba3eabb4ea61f8083a99c139fe85eff9d6ecd1e94f9d2da846437fed52a436f342dd9b11b1fcb31004c7ef9bef2abf7950f47f9d5853ca96b7efacc592505757bf7668f59429e78de4169f668bdc191839af2bd07aa0ddbc3786f27d0fe901fcb8b28fb7be99f6e62d0d7cda43acf6a73b07a70a9a5fe4fb816f94463d7326e98ec47075614543e2f51ab6fc8cedee3670eecac8296a4e5e66e00537fecffa0056b453cccba81c4fa5963ff3b9cc765345e5ed61993053dd222ef87f61238bb0d5ceb1897d0e4c67b0ea12c07221080a82f340c94e578a8afff31af0d9e9703d108372f431b9cb5c1598ef72294771fd417c28a6d43528ee3308c227479f3fce53072740da308be88201a2170505fe0ed4f577ea60066cae695da407779b66cd094674a144d7966e50142d61038718c1400ea0b38e8a6a015054120bea0d4105618c23ea311a2c77c068a6314822245aa378ab0858ae083ec177a88c2308e110840248c30442138b033101a0604824261e85ea417efb3e0e93d178cff8eb2df504b0304140000000800b65dca5cb747eb8ac0000000160200000b0000005f72656c732f2e72656c739d924b6e02310c40af12655f4ca9c40231acd8b043880bb889e7a399c49163c4f4f68dd8c02068114bff9e9e2daf0f34a0761c73dba56cc630c45cd95635ad00b26b29609e71a2582a354b402da13490d0f5d8102ce6f325c82dc36ed6b74c73fc49f40a91ebba73b465770a14f501f8aec39a234a435ad97180334bffcddccf0ad49a9dafacecfca735f0a6ccf3f52090a24745702cf491a44c8b7694af3e9eddbea4f3a56362b478dfe8fff3d0a8143df9bf9d30a589d2d74509266fb0f905504b0304140000000800b65dca5c989c0e5265010000f30200000f000000786c2f776f726b626f6f6b2e786d6c8d926f4bc3400cc6bf4ab90f60e79c82c30ae2f00f888a137d7d6b531b777729b9d4a99fde5ccbb43018bebae649fabbe4c99d6d88d72ba275f6e95d88732e4c23d2cef33c960d781b0fa885a0b99ad85bd190df72aa6b2c614165e721483e9d4c4e7206670529c406db6806da7f58b165b0556c00c4bb01e52d06737eb6edec91b37c1c9140996e4a6a525e1036f1af2085d907465ca143f92a4cffedc0641e037afc86aa301393c5863637c4f84d41ac5b964cce15e67048bc000b963bf232b5f96c57b157c4ae9ed2cc85399928b0468ed257f47cab4d7e80160f512774854e801756e09aa96b31bcf5181d231fcdd15bb13db3603d1466d9796ff92b35a1e26d3534244a1a8dc773d404df560373fcff850884ca86124688e91ec47407f1aaf6664fd0124b1c418ef6408e7620babc775dde1830db03980de66c1da9a0c600d5bda2624ae87e4a7d1ce9e82d99ce8e0f4f750f9d7397aa3d843bb2d5afc5dbf771fe03504b0304140000000800b65dca5c49ca0b6ec2000000b10300001a000000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73cd93390e83301045af62f9004c58421101551ada2817b06058c462cb3351c2ed8348019652a441a1b2fe587eff15e3e486bde2568fd4b486c46be8474a65c36c2e0054343828f2b4c171bea9b41d14cfd1d66054d1a91a21389d62b05b86cc922d53dc2783bf107555b5055e75f11870e42f60786adb5183c852dc95ad915309af7e1d132c87efcd6429f23295362f7d29e0df468163141cc028748cc20318458e51b4a711f1d423ad3a9fecf49ff7ece7f92daef54bfc0cddd58d1709707e68f606504b0304140000000800b65dca5cd393bfe42801000072050000130000005b436f6e74656e745f54797065735d2e786d6ccd54cb4ec33010fc9528d72a712988036a7a01aed0033f60924d63d52f79b725fd7b360e8d042a2d552ad18b2d7b6767c63b92e76f3b0f98b4465b2cd286c83f088165034662ee3c58aed42e18497c0c2be165b9962b10b3e9f45e94ce1258caa8e34817f327a8e54653f2dcf2352a678b3480c63479ec819d56914aefb52a25715d6c6df54325fb52c8b93362b0511e270c4813715022967e55d837be6e21045541b294815ea4619868b540da69c0fc38c70197aeae5509952b37865b72f40164850d00199df7a49313d2c443867ebd196d20d21c5564e832388f9c5a80f3f5f6b174dd99672208a44e3c729064eed12f842ef10aaabf8af3843f5c58c74c50c46dfc98bfe73cf09f6b64762d466eafc5c8dd7f1a79776e7de92fa0db7323951d0c88f8d52e3e01504b01021403140000000800b65dca5c46c74d4895000000cd000000100000000000000000000000800100000000646f6350726f70732f6170702e786d6c504b01021403140000000800b65dca5c3564593406010000fa0100001100000000000000000000008001c3000000646f6350726f70732f636f72652e786d6c504b01021403140000000800b65dca5c995c9c23100600009c2700001300000000000000000000008001f8010000786c2f7468656d652f7468656d65312e786d6c504b01021403140000000800b65dca5c415b0ea1a802000057090000180000000000000000000000808139080000786c2f776f726b7368656574732f7368656574312e786d6c504b01021403140000000800b65dca5c1825d0c534020000f10500001800000000000000000000008081170b0000786c2f776f726b7368656574732f7368656574322e786d6c504b01021403140000000800b65dca5c213cd57bc0030000e40b00001800000000000000000000008081810d0000786c2f776f726b7368656574732f7368656574332e786d6c504b01021403140000000800b65dca5c1281471e9b02000038050000180000000000000000000000808177110000786c2f776f726b7368656574732f7368656574342e786d6c504b01021403140000000800b65dca5c81a25029e20200002a0d00000d0000000000000000000000800148140000786c2f7374796c65732e786d6c504b01021403140000000800b65dca5cb747eb8ac0000000160200000b00000000000000000000008001551700005f72656c732f2e72656c73504b01021403140000000800b65dca5c989c0e5265010000f30200000f000000000000000000000080013e180000786c2f776f726b626f6f6b2e786d6c504b01021403140000000800b65dca5c49ca0b6ec2000000b10300001a00000000000000000000008001d0190000786c2f5f72656c732f776f726b626f6f6b2e786d6c2e72656c73504b01021403140000000800b65dca5cd393bfe428010000720500001300000000000000000000008001ca1a00005b436f6e74656e745f54797065735d2e786d6c504b0506000000000c000c0010030000231c00000000	5	\N	2026-06-10 11:45:44.648994+00	2026-06-10 11:45:44.699241+00	2026-06-10 11:45:44.717171+00
\.


--
-- Data for Name: job_codes; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.job_codes (id, code, name, description, is_active, created_by, created_at, updated_at) FROM stdin;
2f8b1c3d-aeb9-48ad-9503-6c60c546ddcd	J-615-2	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
ae5f3535-f0ab-49e8-8537-ef1b3367744e	J-639-1	EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN)	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
1a94b72d-a9d0-47d7-9479-57bce04ea2f2	J-665-3	PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
b3c8f2fb-6809-496c-be4a-baf3123cf9ad	J-665-4	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
071c99dc-4e06-4659-9dd0-1ce892c7e061	J-665-5	CYBER SECURITY IMPLEMENTATION AND UPGRADE OF HONEYWELL WELLHEADS SCADA SYSTEM IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
54f56aeb-c900-4741-8e9e-d71d178258e1	J-665-6	UPGRADE AND INTEGRATION OF FIRE & GAS SYSTEM AT NGL-1 PLANT, MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
3104a4d9-2f6a-489c-900d-cebdb8451d81	J-670-6	EPIC FOR FLOWLINES IN DUKHAN FIELDS (2019 - 2022) PART A	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
40edbcc8-50b2-426a-a12c-df5e0cfffb5f	J-670-8	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
9d12d51b-02fb-4573-9b5c-9fb243e27d16	J-670-9	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
ffb9acd3-328d-4c2d-a6e8-9b03bf68b762	J-671	MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
5ab9ebc9-8db6-47e3-b292-c37ce14719fb	J-671 -1	MISCELLANEOUS INSTRUMENT PCRS AT NGL-1 PLANT IN MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
2eb9f4f3-0f64-4c4d-a946-fbb09b1b976c	J-700-1	EPIC FOR IMPERVIOUS STORMWATER DRAINAGE AT HWTC - MESAIEED	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
8a72895b-059c-4376-8be4-c5785d92478b	J-701-3	MISCELLANEOUS INSTRUMENTATION MOCS (2021) IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
c1a0c8c7-7692-4e89-b50f-888fb9bc1ef5	J-703-1	EPIC FOR WORKSHOP MODIFICATION AND OTHER MISCELLANEOUS WORKS FOR GRP IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
c326fe8e-81b4-47b3-8dfa-d4d67d687089	J-704-2	MISCELLANEOUS PIPELINE MOCS IMESAIEED FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
f16db359-0f1d-4ef4-92a2-06f8eb49728d	J-706-3	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
7be06116-4e79-4c6c-a312-cd42ed6b69de	J-707-4	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE (DPFU) PHASE 1A - PACKAGE 2	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
10238d7f-c7ed-48e7-9945-3c0540823748	J-707-6	EPIC OF NEW MP STEAM BOILER, NEW DM WATER PLANT AND ASSOCOATED FACILITIES AT QP REFINERY	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
7e9e4a31-a487-46ee-ae06-5f6583ea8660	J-710-3	REHABILITATION OF CRUDE OIL TANKS IN QP MESAIEED TANK FARM	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
7d9f48b3-3e61-4d3d-ae79-8b01e87af0c9	J-721-6	EPIC FOR CYBERSECURITY IMPLEMENTATION FOR ABB CONTROL SYSTEM IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
ec0efadd-4091-4129-8ad7-d94a82fe47d1	J-722	EPIC OF POLICE STATION EXTENSION AND MODIFICATION WORKS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
f83a8fb9-4374-4d90-a072-bc576cbaf29d	J-722-1	EPIC OF EXTENSION OF JABEL  MCC ELECTRICAL BUILDING AND UPS RELOCATION IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
2472b4dd-48fc-4102-b017-3c42c2b25a14	J-728-2	PROVISION OF KAHRAMAA POWER AT VARIOUS GAS DISTRIBUTION STATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
f271ae56-be91-4042-b4e5-3e81b33b033e	J-729-2	EPIC FOR CCWS PHASE III FOR NFE PROJECT	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
13310c77-bbf0-4b87-bdf3-d0a18711292c	J-740	MISCELLANEOUS INSTRUMENTATION PCRS (2019) IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
d59ae6b5-8c69-47f5-b6b6-aa50cd2f8895	J-740-2	IMPLEMENTATION OF INSTRUMENT PCRSΓÇÖ IN NGL-3 AT MESAIEED OPERATIONS.	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
9406c1d8-7e4c-4eb8-9b74-139eb4cb38b9	J-740-3	MISCELLANEOUS ELECTRICAL PCRS (2020) IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
83df5188-d7f3-4189-9653-2e53ebbb212c	J-740-4	EPIC FOR VARIOUS PIPELINE MOCS IN DUKHAN	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
2f5699ba-d816-4d90-91e7-80bce593a757	J-740-5	EPIC FOR MISCELLANEOUS ELECTRICAL MOCS (2022) DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
1b72cf35-4ca2-43aa-9f20-2a1800161023	J-740-6	EPIC FOR VARIOUS PIPELINE MOCS IN DUKHAN	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
a4647bc4-b8ca-44f4-9794-7ed6e5f074fc	J-740-7	MISCELLANEOUS ANALYZERS AND GAS CHROMATOGRAPHS IN NGL-3, NGL-4, STATION-S AND STATION-V IN MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
89bcc869-0928-4d4e-b2dd-6e714735ee94	J-740-8	EXECUTION OF VARIOUS MODIFICATION WORKS AT NGL PLANTS IN MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
9b9f1f44-aa80-4f31-ae00-3e8418861d09	J-740-9	UPGRADE OF EMERGENCY DIESEL GENERATORS IN TANK FARM & TERMINAL SUB-STATIONS, SWITCHBOARD REPLACEMENT & PROVIDING NEW DIESEL GENERATOR AT ARAB-D SUBSTATION, MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
2ccef091-e624-4de9-867c-09155702bf4e	J-759	INSTALLATION OF WONDERWARE OPC SERVERS ALONG WITH FIREWALLS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
7fb75d8f-c0be-44b0-85c9-ba54f9b78be7	J-766	CYBER SECURITY IMPLEMENTATION FOR EMERSON CONTROL SYSTEMS IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
723558ae-a23b-425e-ab2c-6302866d537e	J-778	NFE PROJECT-CAMP WASTE WATER TREATMENT PLANT	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
9093e029-0c88-4f86-841e-75468a0fd436	J-781	REPLACAMENT OF UPS UNITS AND BATTERY CHARGERS IN NGL,TANK FARM, AND GDS, MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
18f923e2-9907-49f1-ab88-d56e7eb04deb	J-781-1	EPIC FOR INSTALLATION OF FLARE GAS FLOWMETERS IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
422ba39e-0a06-4e93-a04a-a00c138dd1b1	J-781-2	SAP CMMS - LEAK DETECTION SYSTEM FOR CRITICAL PIPELINES IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
65d1cfbd-7123-4813-bcab-994e6432f824	J-782	EPIC FFOR CYBER SECURITY IMPLEMENTATION FOR CCC TURBINE AND COMPRESSOR CONTROL SYSTEM IN DUKHAN	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
9b4de00c-d728-455f-8d3d-8d7187202c74	J-785	MAINTENANCE SUPPORT SERVICES OF VARIOUS PLANT ASSETS ON CALL-OFF BASIS FOR OD(M), OE(M) & OT(M) MESAIEED OPERATIONS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
b725c310-58b0-4231-8f96-306244500635	J-786	CYBER SECURITY IMPLEMENTATION & AUTOMATION UPGRADE FOR YOKOGAWA CONTROL SYSTEM IN DUKHAN FIELDS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
f3e1a540-39de-4107-8c84-8ea47509e63f	J-786-1	REPLACEMENT OF MODICON PLCS AT GDS, MESAIEED	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
577bc490-a2d3-46f1-8bc0-c9fea78d42a5	J-789	INSTALLATION OF PIG LAUNCHER / RECEIVER FOR THIRD PARTY GAS INTERCONNECTING FACILITY (TPGIF)	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
c5ff0b88-2a61-464c-b77a-fefc428cbf29	P-364	EPIC FOR PHASE 1 OF NEW NGL SUPPORT CAMPUS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	P389	4399-GALFAR - EPIC FOR WELLS HOOK-UP 2022-2026 PART-1	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
4ef28eb2-189e-43c7-a77d-7d46ef2828ef	P398	MAINTENANCE DATA ACQUISITION FOR DUKHAN OPERATIONS ON CALL-OFF BASIS	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
cffd004b-9085-4e47-9df9-9e022b6ce0e8	P407-1	EPIC OF UPGRADE OF F&G DETECTION SYSTEM FOR BATTERY ROOMS, WORKSHOPS, SECURITY GUARD ROOMS AND INSTRUMENT AIR COMPRESSOR SHELTER AT ALL FACILITIES WITHIN DUKHAN	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
48511043-c0b8-49a6-9182-b1c095be2545	P407-2	EPIC FOR ENHANCEMENT OF STATION S_PROJECT NO 4504	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
559f6b2e-4509-4459-b575-3a96d7d0b5a9	P407-3	CONSTRUCTION FOR UPGRADATION OF EXISTING REFINERY CHEMICAL STORE	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
6970c8fd-040f-4ddc-ab4e-4310cf5fcec8	P408-1	EPIC FOR SOUTH CHANNEL NAVIGATION LEADING LIGHTS AT RAS LAFFAN PORT	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
05679e47-37d2-45ca-a20b-33e5ffff87ed	P408-2	EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
64852bd0-1cae-44bd-b6da-3cdd533d82d9	P-412	CMMS DATA ACQUISITION AND UPDATE SERVICES FOR CHEMICAL PLANT ASSETS AT QATARENERGY REFINERY, MESAIEED	\N	t	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00
\.


--
-- Data for Name: leave_requests; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.leave_requests (id, employee_id, leave_type, start_date, end_date, reason, status, manager_id, manager_comment, created_by, updated_by, created_at, updated_at) FROM stdin;
76980090-de7d-4166-8261-0f98d1e6694e	e5ce164a-f805-4970-80be-cbd21533d1d0	sick	2026-06-05	2026-06-11	\N	cancelled	\N	\N	9f946201-e71e-4356-b830-2dddae74e9f9	9f946201-e71e-4356-b830-2dddae74e9f9	2026-06-05 06:21:34.053575+00	2026-06-05 08:28:18.554494+00
92c66e68-184b-4ad3-8e2f-9c77adcf000c	e5ce164a-f805-4970-80be-cbd21533d1d0	casual	2026-06-05	2026-06-06	\N	approved	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	\N	9f946201-e71e-4356-b830-2dddae74e9f9	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-05 08:28:46.637435+00	2026-06-06 06:57:01.244638+00
8b13793a-0fe4-48e1-b90b-9728bd893b08	d595afe7-1dd9-4c83-ba17-d8fc11a14724	sick	2026-06-06	2026-06-06	\N	approved	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	\N	67188c2e-7217-40da-8222-7ff7b0cdc8b0	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 07:16:03.137303+00	2026-06-06 07:16:40.389879+00
4c6d3ce5-e0a9-4337-8778-559e7b8395e5	e5ce164a-f805-4970-80be-cbd21533d1d0	sick	2026-06-06	2026-06-07	\N	approved	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	\N	9f946201-e71e-4356-b830-2dddae74e9f9	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 09:21:18.625121+00	2026-06-06 09:24:22.779508+00
cfe8e83d-7d2b-44dd-8dfa-85e685270d86	e5ce164a-f805-4970-80be-cbd21533d1d0	casual	2026-06-12	2026-06-13	\N	approved	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	\N	9f946201-e71e-4356-b830-2dddae74e9f9	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-11 06:12:28.135449+00	2026-06-11 06:13:25.264849+00
\.


--
-- Data for Name: maintenance_plants; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.maintenance_plants (id, code, description, planning_plant_id, is_active, created_at) FROM stdin;
5bdf2865-7bbc-4bff-ab09-f558060adf50	ARBC	Arab "C"	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
bd17676a-60e9-41f5-9ca6-ee33bc1e7081	ARBD	Arab "D"	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
146926a4-e8c0-4f3c-ac2a-e077c4460705	BRT6	Berth 6 Rfnry Export Import	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
d619adb6-96b0-41a2-9d8e-4936892066f4	CLS1	PWI Cluster 1 Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
3edbd787-ad2d-4f1f-9796-a91c65e3d270	CLS2	PWI Cluster 2 Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
18ca04fa-7427-49c8-b14f-d6ab7b8c2234	CLS3	PWI Cluster 3 Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
2235ed80-fd4c-42af-9688-1527e0c627a7	CSMD	COMMUNITY SERVICES	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
85fe2ef6-c52f-43a0-af38-162e119b422e	DCPS	Dukhan Cathodic Prtctn Satns	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
b18a369d-47a5-496c-bb51-383cdaa9cf21	DKDSP	\N	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
314c823f-0296-411d-8984-4045478e9ebb	DKFL	Dukhan - Field Support Logistics	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
c9820961-ea2f-4009-bd40-fed4c3a241d2	DKPS	Dukhan Power Plant	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
41f1c339-a5aa-4b6d-a0d1-206ad3dcea77	DKPW	Power Dist Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
84fd72b1-8589-4456-a905-ecd7d8993877	DKSP	Dukhan Sewage Plant	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
dfcac669-6a17-4e22-b16a-7be1e39bb0da	DKSS	Dukhan Support Services	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
f38939e9-21c1-4a32-8d52-beab56662bd4	DYAB	DIYAB	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
8f0b072d-b788-4a2f-8bf3-c83f0f775aee	FAHM	Fahahil Main	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
5a11dce9-c8d0-4fb5-b333-bbbc39f940cf	FAHN	Fahahil North	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
a3f7e6c4-09b8-4c66-97bd-2a0fe8d1329e	FAHS	Fahahil South	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
b1f19523-ad0a-48ae-8957-1de4ecf9af47	FHGL	Fahahil North Gas Lift Comp	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
b6319155-85e4-4243-b8b2-4291cbf3e455	FHNF	Fahahil North Field	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
803d2637-3af1-4f9e-a9da-af6fc8c45cdb	FHSP	Fahahil Stripping Plant	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
c24ba33b-3d47-458b-9056-ee3cd5a7ca8e	GDSP	Gas Flowlines - Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
5dc211d0-777b-42f1-b265-166759771bea	GSMD	GENERAL SERVICES	fdced83e-3244-44ba-b47d-d7f6652687e7	t	2026-06-17 04:01:40.475401+00
d4cb9493-0993-4924-b3d5-282aca1e2006	GSU1	\N	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
9be45e4e-eb21-4091-b833-3b4fa6ab52fd	HLUL	Halul  Island	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
f3a6b6b7-0dea-4e8b-8686-d3680fac62c8	JALM	Jaleha Main	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
6e65eb35-07b3-412a-870b-b3d8cf461c46	KAHM	Khatiyah Main	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
59c8c479-76d4-4cf2-95d4-d759d823a1df	KAHN	Khatiyah North	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
f5efb296-1f58-44cc-988a-ca20cd7a666e	KAHS	Khatiyah South	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
f5e94550-5f6f-4716-a771-bf3efd0fb02d	KSFSS	\N	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
1b2b15e4-a040-496e-871d-8d23b3b2ae51	KUFA	Khuff Gas Station A	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
b5537005-e444-4ff1-afbe-c409a5e32253	KUFB	Khuff Gas Station B	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
83903940-d5e6-4d1c-a2d6-02dadd79739e	KUFC	Khuff Gas Station C	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
a40d4e5b-3cbb-4ce1-b45b-c44d9623607b	KUFD	Khuff Gas Station D	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
dbca21bb-f782-4920-9841-29f8458e69da	KUFE	Khuff Gas Station E	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
300f7468-ed08-4349-94f9-b79c8a977055	KUFG	Khuff Gas Station G	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
0297cfd3-01ce-4f8f-b759-3b006123a0d8	KUFH	Khuff Gas Station H	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
6fef8766-f78f-4d4c-b037-8ec79f98ba40	KUFL	Khuff Gas Stations L	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
ef130655-58c5-4f87-9815-39656d94e6d7	LBVS	Dukhan Line Break Valve Statns	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
45d4ce9c-4e9c-4827-8150-7a275fcfee7e	MHWC	MIC WASTE MANAGEMENT	90af4aa2-6a57-4134-9a7d-29353043918d	t	2026-06-17 04:01:40.475401+00
130220a7-f39c-4dc4-b1f4-340ed446cf30	MICM	MIC INFRASTRUCTURE	90af4aa2-6a57-4134-9a7d-29353043918d	t	2026-06-17 04:01:40.475401+00
6df84fd1-d19c-4def-adef-c6d3cd52af15	MICS	Mesaieed Industrial City	90af4aa2-6a57-4134-9a7d-29353043918d	t	2026-06-17 04:01:40.475401+00
9f595282-ec5f-4a51-b368-b0c8b652c390	MPRT	Mesaieed Port	90af4aa2-6a57-4134-9a7d-29353043918d	t	2026-06-17 04:01:40.475401+00
3f1a644f-c30e-4a66-aa50-4a5becc20367	MROP	Marine Operations	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
b9969a50-b4eb-42b0-a7a0-1db7b45b8f11	MSTP	MIC INFRASTRUCTURE	90af4aa2-6a57-4134-9a7d-29353043918d	t	2026-06-17 04:01:40.475401+00
848cb7cb-571d-433c-ac78-2a1b42cb8601	NFAO	North Field Alpha	c057785e-51f3-4033-b44e-e53bbf587812	t	2026-06-17 04:01:40.475401+00
35e6e9f4-df82-4a68-9ce9-cce5f9f98483	NGCF	Mesaieed Common Facilities	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
fbdc236f-6dc4-44dc-baab-24035b4f7e13	NGCU	Mesaieed Common Utilities	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
f3447543-adc2-4296-804e-de5a6014710f	NGDS	NGL Gas Distribution Stations	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
b0bfd990-1fca-4c6c-9438-6fbbd8d8ae55	NGL1	NGL1 Mesaieed	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
a0a18740-32b4-4b8c-8a94-4cfc2127e985	NGL2	NGL2 Mesaieed	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
8be884c9-97e5-443d-85d5-aa17c9aa5487	NGL3	NGL3 Mesaieed	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
2ea27bc9-f235-4e5c-a1a5-ca5e1974b944	NGL4	NGL4 Mesaieed	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
8a3d28b0-661f-4c68-be76-89e51d115751	NGSF	NGL  Gas Sweetening  Facility	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
607a3114-6291-4b94-abf7-8936014f558f	NGSL	NGL  Storage & Loading	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
8e94c420-1ae0-40de-8b9e-fe746d39cc7c	NGTT	Oil Tank Farm & Terminal	7f465943-84d3-41e7-819b-04a804cf11fc	t	2026-06-17 04:01:40.475401+00
a818692c-16ff-49f3-832a-95709b4b1c17	ODSP	Oil Flowlines - Dukhan	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
e44e8624-a603-4450-80ef-5ec5afa4deca	OESS	OPERATION ENGINEERING SUPPORT SYSTEM	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
1abfe6fa-72cc-4eff-ba10-60591522cdf0	OFST	Offsite Tank Frm & Gnrl Bldngs	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
6c38d77c-a3ff-41f5-b3ee-658242165afa	OSCW	OSER Cooling Water Facility	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
a7c34ea3-1aa1-40db-9f7b-72161844e367	OSDK	OSER Dukhan	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
fc5d4004-bab5-49bd-a0d3-3075262328a1	OSDO	OSER Doha	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
9c78beff-4170-4499-8b36-dadc7e91a285	OSHL	OSER Halul	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
ffe6ab15-cdb8-488d-94d1-b7c75c53ea5d	OSMI	OSER Meassaieed Indus City	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
740f65af-c523-4062-b77f-83a148d6c14c	OSMR	OSER Refinery	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
59e43265-4586-495c-a815-f26ab3b7a53a	OSRL	OSER Ras Laffan Indus City	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
3254a845-5893-403c-a468-bed3542999ea	PNTN	Khuff Point N	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
3690ff84-b502-4a3a-9751-b2dd222264ec	PNTU	Khuff Point U	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
96e697d5-770c-4664-a10e-e4a71acbfc2c	PS02	PS2 Maydan Mahzam	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
c809e6ff-1853-42da-b30c-fd9c54555a28	PS03	PS3 Bul Hanine	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
87305699-23bd-40a5-982d-68788979b146	PW01	Powered Water Inj Station 1	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
aebc3955-9df4-418f-b068-359be7fdf4cd	PW02	Powered Water Inj Station 2	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
f95be253-08df-4a1a-bd94-ef1624e874df	PW03	Powered Water Inj Station 3	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
0716d593-c84f-4505-8c71-4945c2b6b792	PW04	Powered Water Inj Station 4	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
3490c930-7b82-4bfc-ba07-3f51931f8d1d	PW05	Powered Water Inj Station 5	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
4ed34c90-1512-4732-802d-5ec3b70f454c	PW06	Powered Water Inj Station 6	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
a715fa07-7620-4f09-bc0c-95a5bf75d335	PW07	Powered Water Inj Station 7	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
379a991e-cd41-44b2-94ed-687e93a940ed	PW08	Powered Water Inj Station 8	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
9ebc7b80-d83a-492e-bc6d-148f42ad7c28	PW09	Powered Water Inj Station 9	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
832910dc-e6d2-4aa3-9eca-beee3d2e3832	PWRM	Power Water Injecn Ring Main	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
ef92b405-d0bf-4329-87e1-636276b54a3f	QATX	AQP- Caltex Joint Venture Co	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
6e49ce95-d238-4afc-9985-c4ced23b684f	QPSFA	CHEMICAL STORES	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
519b6894-5d80-4d0b-adee-ad93be9a67fa	RAC1	Ras Laffan Accom Camp 1	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
6e8093a4-e204-4ce9-b972-7e4ed298830a	RAC2	Ras Laffan Accom Camp 2	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
3c59a8af-c03a-4e2f-b254-2204bfda82de	RCON	Condensate Refinery	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
51fc84be-f29b-4d06-8c5b-66ed80dcc0ac	RCSF	Ras Laffan Common Seawater Fac	dc45b6cc-6302-4676-8483-c5b4eceef971	t	2026-06-17 04:01:40.475401+00
10c733ad-a9d6-43ca-8544-65131560cfee	REF1	Refinery 1	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
c7c1405c-94c1-459c-afb6-fb2277029a0c	REF2	Refinery 2	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
640e70bf-cdfb-4a8d-916d-db8159ca0225	RFCC	Refinery Fluid Catalytic Conve	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
638071b3-d597-435f-9b17-e7c1dadf08f2	RFLS	Refinery Facilities	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
5daa5c7d-bb56-48b1-9860-6f8d95505835	RLAB	Refinery Linear Alkyl Benzene	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
323c828d-c471-4a16-a314-5cb2f0e2ebfb	RLIN	Ras Laffan Infrastructure	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
bdc942fc-f266-435f-9577-4acddbe71683	RLIW	RAS LAFFAN INFRASTRUCTURE WEST	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
fec16380-e69f-494e-86eb-9f5e0d1908e0	RLPG	LPG Bottling Plants No.1 & 2	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
182f9f64-3fbf-4333-bd14-582064d5c748	RPRT	Ras Laffan Port	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
2d72c579-5455-40a6-a5d3-421a1b28d499	RUTL	Refinery Utilities	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
7a9f17a6-659f-4dac-8a47-f37e728be6f4	RWTP	RAS LAFFAN WASTEWATER TREATMENT PLANTS	8df65887-0b51-48ff-8e5c-a088cf46bc56	t	2026-06-17 04:01:40.475401+00
a2ea5aec-bbb4-4486-9c38-f225c8f9d02a	UMBA	Umm Bab Oil Pumping Station	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
f0c4cc3a-7690-4802-9e39-fef5d21745d6	UMBB	Umm Bab Oil Pumping Station	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
5cd93178-eaf5-4348-8708-706392a28273	UMBC	Umm Bab Oil Pumping Station	1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	t	2026-06-17 04:01:40.475401+00
98c54c2f-fa48-43fa-9c7b-8a0e837b6fe3	VSSL	Offshore Vessels/WorkBoats	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
4affc99e-0b09-48c9-a757-c38d12ce93d2	WQOD	Qatar Fuel Co WOQOD Doha Depot	1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	t	2026-06-17 04:01:40.475401+00
9ac56281-4391-411c-afcf-3d7bc9d2ec0f	WSHP	Marine Dept Workshops	8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	t	2026-06-17 04:01:40.475401+00
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.notifications (id, user_id, type, title, message, entity_type, entity_id, is_read, created_at, target_url, severity, resolved_at) FROM stdin;
48e65012-cbaa-4e29-86e6-26bc18a84704	67188c2e-7217-40da-8222-7ff7b0cdc8b0	task_assigned	New task assigned	Task: monthly attendance report	task	8b878fe9-d4b1-47fc-af85-bfa898d98458	t	2026-06-11 08:29:59.465251+00	/tasks/8b878fe9-d4b1-47fc-af85-bfa898d98458	INFO	\N
7864672f-3da4-459b-bb5e-1a1580d96dbf	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	leave_submitted	Sam Employee submitted a leave request	Sam Employee requested sick leave from 2026-06-04 to 2026-06-04.	leave_request	5243acc3-a52e-4e14-bd3f-e2854ac3c28d	t	2026-06-03 09:43:37.776334+00	\N	INFO	\N
ff28d519-2177-4859-9375-31a6f1b98672	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-08.	daily_work_report	6f01a62f-c5d8-4e07-82db-9daafb3f11ae	t	2026-06-11 09:22:37.834879+00	/work-reports/6f01a62f-c5d8-4e07-82db-9daafb3f11ae	INFO	\N
c4e3c6d3-b3c4-4887-ad1a-3488223fe7b8	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	leave_submitted	Sam Employee submitted a leave request	Sam Employee requested casual leave from 2026-06-20 to 2026-06-22.	leave_request	075d8d8e-4ab8-46da-a263-848868e7d7a5	t	2026-06-03 09:38:38.630635+00	\N	INFO	\N
c60e38e8-e654-4fb0-a114-af5b99b9591a	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to dummy	You have been added to project dummy (9002) as lead.	project	fb1f7cb7-8e06-45e6-bf3f-ac35d68a3e6f	t	2026-06-04 04:00:54.537286+00	\N	INFO	\N
439626dc-3d4d-40ea-9325-5e6a98f1f6bb	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as lead.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-04 05:20:40.623482+00	\N	INFO	\N
2913a5b9-468f-4125-b642-0609ffa4d614	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as qc.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-15 10:30:24.720227+00	/projects/5be2de87-8430-4395-9102-3a7fdc76eb48	INFO	\N
7080518c-a848-489c-bda1-42fdaa0fbc6f	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-16.	daily_work_report	4b4c4614-7680-487e-b2d5-2be890c5e55f	t	2026-06-16 10:43:00.621325+00	/work-reports/4b4c4614-7680-487e-b2d5-2be890c5e55f	INFO	\N
9a96d4a0-ad83-4495-9ab4-85bea362f31a	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	leave_submitted	Sam Employee submitted a leave request	Sam Employee requested sick leave from 2026-06-04 to 2026-06-05.	leave_request	2157b6a0-c24f-410d-93ba-d561e5d08700	t	2026-06-04 06:30:20.219665+00	\N	INFO	\N
486ee4b4-b7a2-45f9-b6fb-adf54eb4a23d	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as lead.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-04 05:35:27.392672+00	\N	INFO	\N
1cb26e7f-841e-494f-94ff-d89da032111a	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	You have been added to project EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1 (GC19101900) as team_lead.	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	t	2026-06-17 04:21:07.852122+00	/projects/dc7a5e96-2808-4842-8924-b03e9c51c4a6	INFO	\N
5e8e2e1a-49fe-4b30-9668-9429d8a56880	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	You have been added to project EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1 (GC19101900) as contributor.	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	t	2026-06-17 04:21:11.982865+00	/projects/dc7a5e96-2808-4842-8924-b03e9c51c4a6	INFO	\N
5dfaa078-8641-42fb-b3c9-7ae9d343fcb4	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	Holiday: weekend	weekend on 2026-06-07.	calendar_event	0610ab04-08e1-4e57-a790-170077999ffb	t	2026-06-05 05:20:07.523344+00	\N	INFO	\N
1e784824-7f85-4f1b-aced-d74d7415f50a	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	Holiday: weekend	weekend on 2026-06-07.	calendar_event	0610ab04-08e1-4e57-a790-170077999ffb	t	2026-06-05 05:20:07.523344+00	\N	INFO	\N
488580a0-e89a-423c-bdea-fe60c8d06a54	67188c2e-7217-40da-8222-7ff7b0cdc8b0	task_assigned	New task assigned	Task: demo task 2	task	7764733e-1d76-436c-ae83-a3c217daf9fe	t	2026-06-18 06:47:08.839255+00	/tasks/7764733e-1d76-436c-ae83-a3c217daf9fe	INFO	\N
8a4d7693-18d7-4b17-8f32-2928ce039d49	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN)	You have been added to project EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN) (LC22104500) as team_lead.	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	t	2026-06-05 06:50:24.539407+00	/projects/1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	INFO	\N
32264988-8381-4a10-a0dc-90275643bbd2	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as team_lead.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-11 09:41:23.027792+00	/projects/5be2de87-8430-4395-9102-3a7fdc76eb48	INFO	\N
ab561bc2-1801-4b2e-8050-a54e9e53c7d4	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	You have been added to project EPC OF METALLURGY UPGRADE OF OFF GAS PIPING (PIP-3144 - QC-TSU-088) as team_lead.	project	305f8d94-a201-4efe-b088-6afc4313c23b	t	2026-06-15 09:02:27.206621+00	/projects/305f8d94-a201-4efe-b088-6afc4313c23b	INFO	\N
f78925eb-6f75-4094-bcae-cd0cddfee65b	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	You have been added to project PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE (903423t) as team_lead.	project	5b205a69-8cce-4b2d-93e1-c81be16b79a6	t	2026-06-05 08:21:19.51649+00	/projects/5b205a69-8cce-4b2d-93e1-c81be16b79a6	INFO	\N
b7913275-20bd-4812-b640-c8d4a4459d8c	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	You have been added to project UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS (LT21109600) as contributor.	project	4b350de2-1c20-4576-980c-f03eacbceb57	t	2026-06-15 09:34:45.975757+00	/projects/4b350de2-1c20-4576-980c-f03eacbceb57	INFO	\N
4c359338-44c8-48f2-b92e-2a72a097d613	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-17.	daily_work_report	f7d3ce46-cc82-4ee9-8932-527bc3c5981e	t	2026-06-18 07:17:48.21974+00	/work-reports/f7d3ce46-cc82-4ee9-8932-527bc3c5981e	INFO	\N
f6f7026f-e3d2-4957-9b20-d9eb1059abc1	9f946201-e71e-4356-b830-2dddae74e9f9	report_rejected	Your work report was sent back	Your work report for 2026-06-17 was sent back for changes. Note: demo	daily_work_report	a3c9606e-98b4-4497-a5bd-0cb956142d48	t	2026-06-18 07:15:23.88711+00	/work-reports/a3c9606e-98b4-4497-a5bd-0cb956142d48	INFO	\N
aaadee9d-0d74-4ba2-b11f-c7e439227010	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	You have been added to project EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1 (GC19101900) as team_lead.	project	dc7a5e96-2808-4842-8924-b03e9c51c4a6	t	2026-06-18 08:02:19.776415+00	/projects/dc7a5e96-2808-4842-8924-b03e9c51c4a6	INFO	\N
04936747-5c49-4e15-8350-c63f88906f10	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	NUMERIC_BENCHMARK	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT benchmark shortfall	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT benchmark shortfall. Pending 31.00 tags.	activity_master	7394cca9-e79d-4cce-9b28-826a487702e0	t	2026-06-18 08:00:46.079744+00	/work-reports/f7d3ce46-cc82-4ee9-8932-527bc3c5981e	WARNING	\N
1b22937a-d7bc-4a9d-a2b7-6ebff2f810ab	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_edit_requested	NAINAR B requested to edit a report	NAINAR B asked to edit their work report for 2026-06-17. Reason: i want to edit the tags count	daily_work_report	f7d3ce46-cc82-4ee9-8932-527bc3c5981e	t	2026-06-18 10:44:54.52736+00	/work-reports/f7d3ce46-cc82-4ee9-8932-527bc3c5981e	INFO	\N
0292d029-1873-4b63-a237-a124a69ae3ac	67188c2e-7217-40da-8222-7ff7b0cdc8b0	calendar_event_created	CDC Holiday: company holiday	company holiday on 2026-06-21.	calendar_event	9182970d-a93e-4a2d-8f71-148947792034	f	2026-06-20 06:27:35.00123+00	\N	INFO	\N
48f76381-98c5-4288-b6e8-b2f5c9a6c446	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as team_lead.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-11 09:41:46.125552+00	/projects/5be2de87-8430-4395-9102-3a7fdc76eb48	INFO	\N
d855b320-2802-4d79-b2d6-3b0092d56533	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	You have been added to project UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS (LT21109600) as qc.	project	4b350de2-1c20-4576-980c-f03eacbceb57	t	2026-06-15 09:39:12.76059+00	/projects/4b350de2-1c20-4576-980c-f03eacbceb57	INFO	\N
d6f2e8df-53e8-48d1-86cc-97a79edf118d	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	You have been added to project SAP CMMS SERVICES FOR HALUL LER-1 PROJECT (GC17104400) as qc.	project	95515988-270a-4bd2-81c6-59e50d49c91f	t	2026-06-15 10:17:17.378161+00	/projects/95515988-270a-4bd2-81c6-59e50d49c91f	INFO	\N
a94abcb8-df0e-4aaa-b675-d65182f6ea09	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	leave_submitted	EMP 1 submitted a leave request	EMP 1 requested sick leave from 2026-06-06 to 2026-06-06.	leave_request	8b13793a-0fe4-48e1-b90b-9728bd893b08	t	2026-06-06 07:16:03.144869+00	/attendance?tab=leave&id=8b13793a-0fe4-48e1-b90b-9728bd893b08	INFO	\N
e6567a61-721b-41f2-92e2-91fa55bbf4ec	67188c2e-7217-40da-8222-7ff7b0cdc8b0	NUMERIC_BENCHMARK	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER benchmark shortfall	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER benchmark shortfall. Pending 80.00 tags.	activity_master	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	t	2026-06-16 10:43:50.373799+00	/work-reports/079ace61-a9cf-436e-a717-fa621baea3b0	WARNING	\N
be0419cf-d346-48d6-b6b6-8a3d9783a160	67188c2e-7217-40da-8222-7ff7b0cdc8b0	leave_approved	Your leave request was approved	Your leave request (2026-06-06 to 2026-06-06) has been approved.	leave_request	8b13793a-0fe4-48e1-b90b-9728bd893b08	t	2026-06-06 07:16:40.39705+00	/attendance?tab=leave&id=8b13793a-0fe4-48e1-b90b-9728bd893b08	INFO	\N
8056605f-4616-450b-8862-289264bb4e53	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	You have been added to project PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE (GC19107200) as team_lead.	project	c500c890-f911-4483-a62d-3ce63e6f0116	t	2026-06-06 07:17:22.494277+00	/projects/c500c890-f911-4483-a62d-3ce63e6f0116	INFO	\N
cf441d79-c901-4344-8559-7d9e8870e4c4	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	You have been added to project EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC (8002) as contributor.	project	5be2de87-8430-4395-9102-3a7fdc76eb48	t	2026-06-15 09:50:48.587998+00	/projects/5be2de87-8430-4395-9102-3a7fdc76eb48	INFO	\N
21187d78-a549-4380-8e03-d5fa954d55e5	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	You have been added to project SAP CMMS SERVICES FOR HALUL LER-1 PROJECT (GC17104400) as contributor.	project	95515988-270a-4bd2-81c6-59e50d49c91f	t	2026-06-15 10:17:06.501041+00	/projects/95515988-270a-4bd2-81c6-59e50d49c91f	INFO	\N
088c2787-8bf0-4b4d-9dff-36ead9af5f02	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	report_rejected	Your work report was sent back	Your work report for 2026-06-16 was sent back for changes. Note: demo send back	daily_work_report	69a61cb8-b7be-45e3-8d00-503fc8143d11	t	2026-06-18 07:15:58.273128+00	/work-reports/69a61cb8-b7be-45e3-8d00-503fc8143d11	INFO	\N
87478f33-3bd7-4023-8316-8f943c9cc07f	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_edit_requested	NAINAR B requested to edit a report	NAINAR B asked to edit their work report for 2026-06-17. Reason: tags count missing	daily_work_report	667b08ee-7959-43f4-956c-00bce5bbc5b5	t	2026-06-19 07:08:27.903281+00	/work-reports/667b08ee-7959-43f4-956c-00bce5bbc5b5	INFO	\N
622d4ae2-594b-4a80-858b-db45db023211	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	You have been added to project UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM (GC22103700) as contributor.	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	t	2026-06-06 09:08:27.948274+00	/projects/5a119e5f-cdf8-42b3-bc96-95fd7a03025e	INFO	\N
93dcb92d-6b2c-4978-976c-d4b132164f7c	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	You have been added to project PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE (GC19107200) as contributor.	project	c500c890-f911-4483-a62d-3ce63e6f0116	t	2026-06-06 07:17:25.861394+00	/projects/c500c890-f911-4483-a62d-3ce63e6f0116	INFO	\N
da65b955-2efd-4fde-9865-cd2871555ea0	9f946201-e71e-4356-b830-2dddae74e9f9	leave_approved	Your leave request was approved	Your leave request (2026-06-05 to 2026-06-06) has been approved.	leave_request	92c66e68-184b-4ad3-8e2f-9c77adcf000c	t	2026-06-06 06:57:01.253702+00	/attendance?tab=leave&id=92c66e68-184b-4ad3-8e2f-9c77adcf000c	INFO	\N
2978959e-8200-4be0-bd29-8f541dd22906	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN)	You have been added to project EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN) (LC22104500) as qc.	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	t	2026-06-09 04:06:17.413299+00	/projects/1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	INFO	\N
6153d1a7-9922-4a01-b982-96d27e458285	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	Holiday: corona leave	corona leave on 2026-06-11.	calendar_event	6e2f3672-3631-4ef7-b41d-7a35a9fea3c6	t	2026-06-09 04:20:30.388422+00	\N	INFO	\N
c529644d-20f4-410d-b1f4-d2925031fd70	9f946201-e71e-4356-b830-2dddae74e9f9	project_assigned	You were assigned to MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	You have been added to project MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS (LC20101600) as contributor.	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	t	2026-06-09 04:25:57.814795+00	/projects/82a42b81-d6c1-443e-a2e8-442c84f44a77	INFO	\N
10744e18-6023-4284-9939-57073cc811f6	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	Holiday: corona leave	corona leave on 2026-06-11.	calendar_event	6e2f3672-3631-4ef7-b41d-7a35a9fea3c6	t	2026-06-09 04:20:30.388422+00	\N	INFO	\N
254d0410-018c-4fc1-aac2-cf36b29a0ae9	9f946201-e71e-4356-b830-2dddae74e9f9	leave_approved	Your leave request was approved	Your leave request (2026-06-06 to 2026-06-07) has been approved.	leave_request	4c6d3ce5-e0a9-4337-8778-559e7b8395e5	t	2026-06-06 09:24:22.787253+00	/attendance?tab=leave&id=4c6d3ce5-e0a9-4337-8778-559e7b8395e5	INFO	\N
d0f8acd8-c7bd-4924-ab66-7ac7c2345ff1	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	calendar_event_created	Holiday: corona leave	corona leave on 2026-06-11.	calendar_event	6e2f3672-3631-4ef7-b41d-7a35a9fea3c6	t	2026-06-09 04:20:30.388422+00	\N	INFO	\N
88d57a5f-0fc2-46bf-87ed-2c5cb0d37d73	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN)	You have been added to project EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN) (LC22104500) as contributor.	project	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	t	2026-06-09 04:06:01.603627+00	/projects/1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	INFO	\N
43b46d9a-5607-43cb-9d06-9ef894f53344	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	You have been added to project UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM (GC22103700) as team_lead.	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	t	2026-06-06 09:08:20.512635+00	/projects/5a119e5f-cdf8-42b3-bc96-95fd7a03025e	INFO	\N
685c2834-2cdb-453d-9ed4-b01ca1f0d6d5	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	You have been added to project MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS (LC20101600) as team_lead.	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	t	2026-06-09 04:25:53.888775+00	/projects/82a42b81-d6c1-443e-a2e8-442c84f44a77	INFO	\N
b1cd5c2c-6736-492b-93d9-0a2446e9d6b0	67188c2e-7217-40da-8222-7ff7b0cdc8b0	calendar_event_created	Holiday: corona leave	corona leave on 2026-06-11.	calendar_event	6e2f3672-3631-4ef7-b41d-7a35a9fea3c6	t	2026-06-09 04:20:30.388422+00	\N	INFO	\N
744ed6df-eb85-4e09-9620-4a5f6d649e46	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	project_assigned	You were assigned to MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	You have been added to project MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS (LC20101600) as team_lead.	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	t	2026-06-09 04:26:03.319324+00	/projects/82a42b81-d6c1-443e-a2e8-442c84f44a77	INFO	\N
570b6537-69de-426d-ad9f-2641b6983866	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-15.	daily_work_report	079ace61-a9cf-436e-a717-fa621baea3b0	t	2026-06-16 10:43:50.383713+00	/work-reports/079ace61-a9cf-436e-a717-fa621baea3b0	INFO	\N
44423703-74be-4837-9b12-e1a1662a697e	9f946201-e71e-4356-b830-2dddae74e9f9	task_assigned	New task assigned	Task: prepare monthly report	task	f70e3ef9-0ed2-4079-a27d-b0dbde12494c	t	2026-06-09 10:26:54.829271+00	/tasks/f70e3ef9-0ed2-4079-a27d-b0dbde12494c	INFO	\N
b8ace49a-a3dd-4e7a-a9fa-714e1ec3d0ea	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_edit_requested	NAINAR B requested to edit a report	NAINAR B asked to edit their work report for 2026-06-17. Reason: demo request\n	daily_work_report	f7d3ce46-cc82-4ee9-8932-527bc3c5981e	t	2026-06-18 07:17:13.683131+00	/work-reports/f7d3ce46-cc82-4ee9-8932-527bc3c5981e	INFO	\N
60a42bad-652d-42a0-9c57-33945f4c04d1	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-17.	daily_work_report	f7d3ce46-cc82-4ee9-8932-527bc3c5981e	t	2026-06-18 10:45:12.818221+00	/work-reports/f7d3ce46-cc82-4ee9-8932-527bc3c5981e	INFO	\N
36adab0a-0d9e-48f1-91ed-b653915b87ca	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	task_assigned	New task assigned	Task: do the attendance corrections	task	64b9cac8-e7e9-45e6-9710-a48476e7f793	t	2026-06-09 10:51:34.528645+00	/tasks/64b9cac8-e7e9-45e6-9710-a48476e7f793	INFO	\N
0c0f5c58-4c98-4549-b716-ee254c06b251	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	project_assigned	You were assigned to PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	You have been added to project PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE (GC19107200) as qc.	project	c500c890-f911-4483-a62d-3ce63e6f0116	t	2026-06-09 09:22:31.195151+00	/projects/c500c890-f911-4483-a62d-3ce63e6f0116	INFO	\N
1b066274-306e-4252-8977-f194e265f438	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	You have been added to project MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS (LC20101600) as qc.	project	82a42b81-d6c1-443e-a2e8-442c84f44a77	t	2026-06-09 08:17:54.715136+00	/projects/82a42b81-d6c1-443e-a2e8-442c84f44a77	INFO	\N
1e416db8-2e3a-4e3d-8b5b-ca4ecb638071	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-17.	daily_work_report	667b08ee-7959-43f4-956c-00bce5bbc5b5	t	2026-06-19 07:08:34.052557+00	/work-reports/667b08ee-7959-43f4-956c-00bce5bbc5b5	INFO	\N
872b2a5b-5aee-49f2-af6e-f531b6a21683	9f946201-e71e-4356-b830-2dddae74e9f9	task_assigned	New task assigned	Task: make the MTL preparation	task	74cdf95d-20e4-461d-9385-f658ac4dfc87	t	2026-06-10 04:15:25.512166+00	/tasks/74cdf95d-20e4-461d-9385-f658ac4dfc87	INFO	\N
cd19b649-8e0d-4667-9de0-4f62aef9974b	9f946201-e71e-4356-b830-2dddae74e9f9	task_assigned	New task assigned	Task: prepare demo	task	feeec907-4e2e-48ac-ad3b-eff5ade1f5b3	t	2026-06-10 05:22:33.006141+00	/tasks/feeec907-4e2e-48ac-ad3b-eff5ade1f5b3	INFO	\N
47c21c73-bb55-4236-b59d-2584a7e420d1	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_requested	EMP 1 requested to edit a report	EMP 1 asked to edit their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:50:48.046521+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
f28f3ec5-8760-4808-ac3e-62a2faeba868	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_requested	EMP 1 requested to edit a report	EMP 1 asked to edit their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:56:43.649964+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
055d8e2c-1953-447a-ac1d-2293d4b975c8	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_edit_requested	EMP 1 requested to edit a report	EMP 1 asked to edit their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:56:43.655294+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
71ace2d6-c3c0-4632-9cc9-dad6fa0053ac	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:56:30.803307+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
d61ddac3-92f9-486a-a218-11e704a1e723	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:50:46.282825+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
896c467e-de70-4944-bb10-653b1792009f	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_edit_requested	EMP 1 requested to edit a report	EMP 1 asked to edit their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:50:48.052684+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
da0f9680-06c5-40ec-a921-2f57a0b13563	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-05.	daily_work_report	902005ed-f761-480d-a79e-fdcf887f5339	t	2026-06-11 05:54:15.830448+00	/work-reports/902005ed-f761-480d-a79e-fdcf887f5339	INFO	\N
0f1b5613-9f61-47cc-a419-c8959c4a2a08	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-11.	daily_work_report	33fc388e-7d77-439d-98a9-bdf7d2998a5f	t	2026-06-11 05:53:58.873144+00	/work-reports/33fc388e-7d77-439d-98a9-bdf7d2998a5f	INFO	\N
1cf7722d-0696-46c0-8480-bfc9719282b3	67188c2e-7217-40da-8222-7ff7b0cdc8b0	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:57:06.746625+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
09ad772b-14f0-4c09-98c4-2c535192d15c	67188c2e-7217-40da-8222-7ff7b0cdc8b0	report_rejected	Your work report was sent back	Your work report for 2026-06-05 was sent back for changes. Note: the tags count missing\n	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 05:54:36.943932+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
eab16f61-d5c8-4741-8363-ac02b22630d8	67188c2e-7217-40da-8222-7ff7b0cdc8b0	project_assigned	You were assigned to UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	You have been added to project UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM (GC22103700) as contributor.	project	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	t	2026-06-10 10:58:52.213164+00	/projects/5a119e5f-cdf8-42b3-bc96-95fd7a03025e	INFO	\N
4c38117f-374b-4135-a8ce-c66e71464dab	9f946201-e71e-4356-b830-2dddae74e9f9	leave_approved	Your leave request was approved	Your leave request (2026-06-12 to 2026-06-13) has been approved.	leave_request	cfe8e83d-7d2b-44dd-8dfa-85e685270d86	t	2026-06-11 06:13:25.270303+00	/attendance?tab=leave&id=cfe8e83d-7d2b-44dd-8dfa-85e685270d86	INFO	\N
5d3c0a8c-f7e1-4e18-bb85-40128d2fe650	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	report_submitted	EMP 1 submitted a work report	EMP 1 submitted their work report for 2026-06-05.	daily_work_report	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	t	2026-06-11 06:18:46.516016+00	/work-reports/7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	INFO	\N
b8df0c4a-54dc-4af1-8be9-47277c72aa90	9f946201-e71e-4356-b830-2dddae74e9f9	report_rejected	Your work report was sent back	Your work report for 2026-06-07 was sent back for changes. Note: tags count missing\n	daily_work_report	0126062f-7271-4517-a871-2cca379255a5	t	2026-06-11 06:22:16.730653+00	/work-reports/0126062f-7271-4517-a871-2cca379255a5	INFO	\N
35b3385f-23e0-4413-b7a0-cb8d3e1b7cdc	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-11.	daily_work_report	33fc388e-7d77-439d-98a9-bdf7d2998a5f	t	2026-06-11 06:21:48.630271+00	/work-reports/33fc388e-7d77-439d-98a9-bdf7d2998a5f	INFO	\N
2412b4f3-266c-4cb7-9be5-3b80c1a3cba4	9f946201-e71e-4356-b830-2dddae74e9f9	report_edit_granted	Edit access granted	You can now edit and resubmit your work report for 2026-06-07.	daily_work_report	0126062f-7271-4517-a871-2cca379255a5	t	2026-06-11 07:01:01.805658+00	/work-reports/0126062f-7271-4517-a871-2cca379255a5	INFO	\N
69958401-6087-4738-942e-a286645b3caa	9f946201-e71e-4356-b830-2dddae74e9f9	task_assigned	New task assigned	Task: demo task	task	096b7ae9-b916-49c0-8b6c-d916e8416fd0	t	2026-06-11 07:29:49.726724+00	/tasks/096b7ae9-b916-49c0-8b6c-d916e8416fd0	INFO	\N
0e57d6e4-e849-40d1-bdbf-8c13e0fac2bb	67188c2e-7217-40da-8222-7ff7b0cdc8b0	calendar_event_created	Working Day: Required	Required on 2026-06-27.	calendar_event	1eba6b39-2252-41a1-9004-cacfbc56e2ec	f	2026-06-20 06:28:17.002877+00	\N	INFO	\N
2f56fd2f-7c99-483c-b005-682cd6e573a5	67188c2e-7217-40da-8222-7ff7b0cdc8b0	calendar_event_created	Natural Hazard: tsunami	tsunami on 2026-06-22.	calendar_event	1436013b-24a5-489d-af82-6f01804863bc	f	2026-06-20 06:28:41.340531+00	\N	INFO	\N
bce68cdf-e68a-4f14-a5a7-a44e9bb36e70	67188c2e-7217-40da-8222-7ff7b0cdc8b0	calendar_event_created	Holiday: pongal	pongal on 2026-06-30.	calendar_event	6025d4c0-e16f-4176-8155-841c4d61725d	f	2026-06-20 06:29:18.767296+00	\N	INFO	\N
51d2ae8b-34cc-4c42-a4ce-614ee18991c3	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	CDC Holiday: company holiday	company holiday on 2026-06-21.	calendar_event	9182970d-a93e-4a2d-8f71-148947792034	t	2026-06-20 06:27:35.00123+00	\N	INFO	\N
81cb67e4-88fb-4b7b-a7e4-809eb1eb67ad	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	Working Day: Required	Required on 2026-06-27.	calendar_event	1eba6b39-2252-41a1-9004-cacfbc56e2ec	t	2026-06-20 06:28:17.002877+00	\N	INFO	\N
8ea0c222-a845-4fb3-b806-08a5f076b358	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	Natural Hazard: tsunami	tsunami on 2026-06-22.	calendar_event	1436013b-24a5-489d-af82-6f01804863bc	t	2026-06-20 06:28:41.340531+00	\N	INFO	\N
e6a4c2b5-b0b5-41b9-bf65-ae10577e0ef5	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	calendar_event_created	Holiday: pongal	pongal on 2026-06-30.	calendar_event	6025d4c0-e16f-4176-8155-841c4d61725d	t	2026-06-20 06:29:18.767296+00	\N	INFO	\N
f4b58421-b8f4-4f44-9277-5448bea7f476	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	CDC Holiday: company holiday	company holiday on 2026-06-21.	calendar_event	9182970d-a93e-4a2d-8f71-148947792034	t	2026-06-20 06:27:35.00123+00	\N	INFO	\N
421ee868-f0cf-49b5-893c-0e31ccc42636	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	Working Day: Required	Required on 2026-06-27.	calendar_event	1eba6b39-2252-41a1-9004-cacfbc56e2ec	t	2026-06-20 06:28:17.002877+00	\N	INFO	\N
359e67c4-4ce5-484c-93d7-afcf8445c2a4	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	Natural Hazard: tsunami	tsunami on 2026-06-22.	calendar_event	1436013b-24a5-489d-af82-6f01804863bc	t	2026-06-20 06:28:41.340531+00	\N	INFO	\N
31f972a8-9c3e-40be-a2d9-04cf78b35cab	9f946201-e71e-4356-b830-2dddae74e9f9	calendar_event_created	Holiday: pongal	pongal on 2026-06-30.	calendar_event	6025d4c0-e16f-4176-8155-841c4d61725d	t	2026-06-20 06:29:18.767296+00	\N	INFO	\N
44dec56d-20d2-449a-8c4b-5dd6f29d7fe7	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	calendar_event_created	CDC Holiday: company holiday	company holiday on 2026-06-21.	calendar_event	9182970d-a93e-4a2d-8f71-148947792034	t	2026-06-20 06:27:35.00123+00	\N	INFO	\N
b09ff5f9-198f-402b-88c1-edc995ac80b4	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	calendar_event_created	Working Day: Required	Required on 2026-06-27.	calendar_event	1eba6b39-2252-41a1-9004-cacfbc56e2ec	t	2026-06-20 06:28:17.002877+00	\N	INFO	\N
197f4ae1-fbec-450d-aa04-a98827cefde4	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	calendar_event_created	Natural Hazard: tsunami	tsunami on 2026-06-22.	calendar_event	1436013b-24a5-489d-af82-6f01804863bc	t	2026-06-20 06:28:41.340531+00	\N	INFO	\N
7b9f815e-07f5-482c-9339-917cb4170198	b9a8554b-4498-4a20-b204-0b5fa4efe7aa	calendar_event_created	Holiday: pongal	pongal on 2026-06-30.	calendar_event	6025d4c0-e16f-4176-8155-841c4d61725d	t	2026-06-20 06:29:18.767296+00	\N	INFO	\N
\.


--
-- Data for Name: offices; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.offices (id, name, timezone, shift_start, shift_end, break_minutes, is_active, created_at, updated_at) FROM stdin;
42019185-c95d-4a26-b1c9-2acb1a467d3c	Chennai	Asia/Kolkata	09:00:00	17:30:00	30	t	2026-06-03 05:03:17.977548+00	2026-06-03 05:03:17.977548+00
a75cf253-dddb-4a3f-a33f-006dcc7c95b5	Hyderabad	Asia/Kolkata	09:00:00	17:30:00	60	t	2026-06-03 05:03:17.977548+00	2026-06-03 05:03:17.977548+00
3d90ad52-0d01-44eb-a25b-713ddca502ad	Qatar	Asia/Qatar	09:00:00	18:00:00	60	t	2026-06-03 05:03:17.977548+00	2026-06-03 05:03:17.977548+00
\.


--
-- Data for Name: planning_plants; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.planning_plants (id, code, description, is_active, created_at) FROM stdin;
fdced83e-3244-44ba-b47d-d7f6652687e7	1200	Qatar Petroleum - Doha	t	2026-06-17 04:01:40.475401+00
1db61b21-16c9-49b8-b8e9-cdc1e96ec83d	2300	Dukhan Planning Plant	t	2026-06-17 04:01:40.475401+00
7f465943-84d3-41e7-819b-04a804cf11fc	2400	Messaieed Planning Plant	t	2026-06-17 04:01:40.475401+00
1eab0cd6-e88e-4612-8f6d-5085c2b9c81d	2500	Refinery Planning Plant	t	2026-06-17 04:01:40.475401+00
8f9a4d94-209a-4480-9a31-c5ae6a20cbfa	2600	Offshore Planning Plant	t	2026-06-17 04:01:40.475401+00
8df65887-0b51-48ff-8e5c-a088cf46bc56	2700	Ras Laffan Planning Plant	t	2026-06-17 04:01:40.475401+00
90af4aa2-6a57-4134-9a7d-29353043918d	2800	Mesaieed Industrial City	t	2026-06-17 04:01:40.475401+00
c057785e-51f3-4033-b44e-e53bbf587812	2900	North Field Alpha	t	2026-06-17 04:01:40.475401+00
dc45b6cc-6302-4676-8483-c5b4eceef971	3000	Ras Laffan Common Cooling Water	t	2026-06-17 04:01:40.475401+00
\.


--
-- Data for Name: project_activities; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_activities (id, project_id, activity_type_id, activity_type_name, title, status, assigned_to_id, assigned_to_name, target_date, closed_date, remarks, sort_order, created_by, created_at, updated_at) FROM stdin;
8225388a-e23a-440e-be54-2cce265e9564	305f8d94-a201-4efe-b088-6afc4313c23b	c323a1ee-3cda-4cf2-ae6b-2db27bc02aee	ADMIN SUPPORT	FMTL DATA SEPARATION	open	\N	\N	2026-06-16	\N	\N	1	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 11:58:34.149329+00	2026-06-15 11:58:34.149329+00
ffe85ee3-c3ba-4521-ab0f-689849e4ea8f	5be2de87-8430-4395-9102-3a7fdc76eb48	f2d640ff-6d91-4750-9f16-c3785b29a9be	PLANNING & SCHEDULING	planning and scheduling	closed	\N	\N	2026-06-18	2026-06-16	\N	2	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 11:59:59.131051+00	2026-06-16 04:04:04.64589+00
\.


--
-- Data for Name: project_deliverables; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_deliverables (id, project_id, name, description, target_date, owner_employee_id, status, completion_date, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: project_managers; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_managers (id, project_id, user_id, created_by, created_at) FROM stdin;
\.


--
-- Data for Name: project_members; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_members (id, project_id, employee_id, role, created_by, created_at, updated_at) FROM stdin;
ac78b1f2-0a05-48d5-8b97-e19fb9d413c9	fb1f7cb7-8e06-45e6-bf3f-ac35d68a3e6f	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	team_lead	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 04:00:54.528629+00	2026-06-04 04:00:54.528629+00
6de896c4-f364-4e36-ba97-c09da5a0eddf	5b205a69-8cce-4b2d-93e1-c81be16b79a6	e5ce164a-f805-4970-80be-cbd21533d1d0	team_lead	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-05 08:21:19.508632+00	2026-06-05 08:21:19.508632+00
30425fa3-51c6-43f4-9d32-8d125c566c37	c500c890-f911-4483-a62d-3ce63e6f0116	d595afe7-1dd9-4c83-ba17-d8fc11a14724	team_lead	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 07:17:22.483371+00	2026-06-06 07:17:22.483371+00
0e36daf7-108b-4adf-874f-5f0b81a881d0	c500c890-f911-4483-a62d-3ce63e6f0116	e5ce164a-f805-4970-80be-cbd21533d1d0	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 07:17:25.8548+00	2026-06-06 07:17:25.8548+00
05cb4dbe-1f59-4276-b77c-45f049dbf018	82a42b81-d6c1-443e-a2e8-442c84f44a77	d595afe7-1dd9-4c83-ba17-d8fc11a14724	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-09 08:17:54.704166+00	2026-06-09 08:17:54.704166+00
0ca9c333-5550-451f-9158-78449bea7510	c500c890-f911-4483-a62d-3ce63e6f0116	3107987e-7e92-4e89-97f3-1d5275e65485	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-09 09:22:31.179207+00	2026-06-09 09:22:31.179207+00
df2ab786-4034-4e89-96eb-54aa8cae8274	1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	3107987e-7e92-4e89-97f3-1d5275e65485	team_lead	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-09 04:06:01.595168+00	2026-06-10 07:25:32.479872+00
1d6990b3-9fcb-4c9a-9513-1ef22859ef08	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	3107987e-7e92-4e89-97f3-1d5275e65485	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-06 09:08:20.500868+00	2026-06-10 10:58:43.817321+00
9422e0b9-1b9b-4c6a-aaa9-b2905951b5d2	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	d595afe7-1dd9-4c83-ba17-d8fc11a14724	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-10 10:58:52.202521+00	2026-06-10 10:58:52.202521+00
ff2a5925-92d4-4058-b43f-5be877739d3e	5be2de87-8430-4395-9102-3a7fdc76eb48	e5ce164a-f805-4970-80be-cbd21533d1d0	team_lead	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-11 09:41:46.117623+00	2026-06-11 09:41:46.117623+00
36de7bc1-c3b5-4abd-9657-d607cd937e4f	305f8d94-a201-4efe-b088-6afc4313c23b	3107987e-7e92-4e89-97f3-1d5275e65485	team_lead	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 09:02:27.192578+00	2026-06-15 09:02:27.192578+00
b9de5eda-6b38-46f8-b871-7d5e2e18acdb	4b350de2-1c20-4576-980c-f03eacbceb57	3107987e-7e92-4e89-97f3-1d5275e65485	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 09:34:45.964436+00	2026-06-15 09:34:45.964436+00
3b1f0e6d-a5e9-4e5b-a86e-b34c6ab65320	4b350de2-1c20-4576-980c-f03eacbceb57	e5ce164a-f805-4970-80be-cbd21533d1d0	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 09:39:12.744502+00	2026-06-15 09:39:12.744502+00
a8fd857b-e87a-4c5a-8fff-b2eab5a02d54	5be2de87-8430-4395-9102-3a7fdc76eb48	3107987e-7e92-4e89-97f3-1d5275e65485	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 09:50:48.574802+00	2026-06-15 09:50:48.574802+00
05a490f0-1981-478a-b9f1-ff9a0d3bfb6c	95515988-270a-4bd2-81c6-59e50d49c91f	3107987e-7e92-4e89-97f3-1d5275e65485	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 10:17:06.489919+00	2026-06-15 10:17:06.489919+00
f858d195-8cd3-4c32-87c1-75b8e09c7666	95515988-270a-4bd2-81c6-59e50d49c91f	e5ce164a-f805-4970-80be-cbd21533d1d0	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 10:17:17.371165+00	2026-06-15 10:17:17.371165+00
65fa3a59-48d5-4d0e-8627-71d373b30261	5be2de87-8430-4395-9102-3a7fdc76eb48	d595afe7-1dd9-4c83-ba17-d8fc11a14724	qc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-15 10:30:24.704471+00	2026-06-15 10:30:24.704471+00
e2b5dfa1-131b-41ef-b3fc-d6ce96a55ae2	dc7a5e96-2808-4842-8924-b03e9c51c4a6	d595afe7-1dd9-4c83-ba17-d8fc11a14724	contributor	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-17 04:21:11.976509+00	2026-06-17 04:21:11.976509+00
\.


--
-- Data for Name: project_planned_date_changes; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_planned_date_changes (id, project_id, old_date, new_date, changed_by, reason, changed_at) FROM stdin;
1c829e7d-28ee-43e4-bf79-755222f9b1c4	4b350de2-1c20-4576-980c-f03eacbceb57	\N	2026-06-24	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	vss	2026-06-15 09:34:38.74737+00
b37acbb4-80f1-4d88-8e20-a75befae5f0f	95515988-270a-4bd2-81c6-59e50d49c91f	2026-06-16	2026-06-19	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	requires verification	2026-06-15 10:15:20.01127+00
695f1aab-0340-400a-937b-9d8f346f7321	95515988-270a-4bd2-81c6-59e50d49c91f	2026-06-19	2026-06-16	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	demo	2026-06-15 10:15:48.237236+00
\.


--
-- Data for Name: project_submission_items; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_submission_items (id, submission_id, activity_type_id, activity_label, quantity, unit) FROM stdin;
4fa888e6-8d84-486a-a346-afc160fbcbce	58adb554-4871-43af-b649-afa8c29d2403	\N	FMTL	2	200
f9d68e39-6775-4d94-896e-1456ea6e7db9	98c3eff3-9976-4607-9584-fcc45b75334d	\N	MTL	1	30
1ac2fdb9-5687-4d52-9163-caa8c88aeaf2	f4204853-3983-442d-8baa-6b699bb05224	\N	FMTL tag population	10	20
825524e2-1285-45eb-966c-01010e65ecca	e48be19a-1245-4510-9264-639a3a3c730a	\N	MTL data tags	1	23
\.


--
-- Data for Name: project_submissions; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_submissions (id, project_id, submission_date, period_start, period_end, status, notes, submitted_by, reviewed_by, reviewed_at, review_note, created_at, updated_at) FROM stdin;
58adb554-4871-43af-b649-afa8c29d2403	04ec228b-b327-43b0-8098-0312571e101b	2026-06-23	2026-06-01	2026-06-10	draft	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	\N	\N	\N	2026-06-15 09:47:43.560013+00	2026-06-15 09:47:43.560013+00
98c3eff3-9976-4607-9584-fcc45b75334d	95515988-270a-4bd2-81c6-59e50d49c91f	2026-06-24	2026-06-09	2026-06-15	draft	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	\N	\N	\N	2026-06-15 10:16:28.424563+00	2026-06-15 10:16:28.424563+00
f4204853-3983-442d-8baa-6b699bb05224	5be2de87-8430-4395-9102-3a7fdc76eb48	2026-06-18	2026-06-15	2026-06-17	submitted	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	\N	\N	\N	2026-06-15 10:30:59.339057+00	2026-06-15 10:31:03.65008+00
e48be19a-1245-4510-9264-639a3a3c730a	5be2de87-8430-4395-9102-3a7fdc76eb48	2026-06-26	2026-06-01	2026-06-17	submitted	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	\N	\N	\N	2026-06-15 10:31:54.263369+00	2026-06-16 04:04:22.040178+00
\.


--
-- Data for Name: project_timeline_events; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.project_timeline_events (id, project_id, event_type, actor_id, actor_name, details, created_at) FROM stdin;
d858d6fb-b629-4290-a1f5-e62f63e76141	4b350de2-1c20-4576-980c-f03eacbceb57	planned_date_changed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"reason": "vss", "new_date": "2026-06-24", "old_date": null}	2026-06-15 09:34:38.74737+00
9437596a-677f-4680-be70-4ad2fdd783ae	4b350de2-1c20-4576-980c-f03eacbceb57	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "contributor", "employee_name": "NAINAR B"}	2026-06-15 09:34:45.964436+00
c3722404-5ed7-4c5c-8ba8-55409274c698	4b350de2-1c20-4576-980c-f03eacbceb57	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "qc", "employee_name": "Santhosh Kumar"}	2026-06-15 09:39:12.744502+00
596a7a0c-eba1-4747-a143-fe8bbfc9563e	04ec228b-b327-43b0-8098-0312571e101b	submission_created	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"period_end": "2026-06-10", "period_start": "2026-06-01", "submission_id": "58adb554-4871-43af-b649-afa8c29d2403"}	2026-06-15 09:47:43.560013+00
10d04d98-da71-4ebe-aff7-92cf7a829625	5be2de87-8430-4395-9102-3a7fdc76eb48	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "contributor", "employee_name": "NAINAR B"}	2026-06-15 09:50:48.574802+00
2017449d-737d-41b2-89fa-b3d962c98d0a	5be2de87-8430-4395-9102-3a7fdc76eb48	submission_created	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"period_end": "2026-06-23", "period_start": "2026-06-09", "submission_id": "dd99ac0f-07e9-4066-a273-c8bb75be8c43"}	2026-06-15 09:51:22.70435+00
9847a13d-4f01-472f-9dfb-2cc45d944fff	95515988-270a-4bd2-81c6-59e50d49c91f	planned_date_changed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"reason": "requires verification", "new_date": "2026-06-19", "old_date": "2026-06-16"}	2026-06-15 10:15:20.01127+00
96f894e4-c4bb-492f-b54b-f32ff56e4f56	95515988-270a-4bd2-81c6-59e50d49c91f	planned_date_changed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"reason": "demo", "new_date": "2026-06-16", "old_date": "2026-06-19"}	2026-06-15 10:15:48.237236+00
67257347-2675-4c66-934c-64d295a3cf27	95515988-270a-4bd2-81c6-59e50d49c91f	submission_created	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"period_end": "2026-06-15", "period_start": "2026-06-09", "submission_id": "98c3eff3-9976-4607-9584-fcc45b75334d"}	2026-06-15 10:16:28.424563+00
59e13fc7-4d42-4eaf-a5a5-be550feeca75	95515988-270a-4bd2-81c6-59e50d49c91f	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "contributor", "employee_name": "NAINAR B"}	2026-06-15 10:17:06.489919+00
b321e83b-3e86-4671-8751-4be6d4f112d6	95515988-270a-4bd2-81c6-59e50d49c91f	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "qc", "employee_name": "Santhosh Kumar"}	2026-06-15 10:17:17.371165+00
47da2ff4-c27c-490e-96a7-4777eb21ff95	5be2de87-8430-4395-9102-3a7fdc76eb48	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "qc", "employee_name": "EMP 1"}	2026-06-15 10:30:24.704471+00
e9f1dae5-fe42-4888-8a31-cc8db7e3ddef	5be2de87-8430-4395-9102-3a7fdc76eb48	submission_created	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"period_end": "2026-06-17", "period_start": "2026-06-15", "submission_id": "f4204853-3983-442d-8baa-6b699bb05224"}	2026-06-15 10:30:59.339057+00
968df071-1cc3-4ad3-ad61-f076b52bc633	5be2de87-8430-4395-9102-3a7fdc76eb48	submission_updated	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"new": "submitted", "old": "draft", "field": "status", "submission_id": "f4204853-3983-442d-8baa-6b699bb05224"}	2026-06-15 10:31:03.646637+00
be3a3f9f-a745-4582-9032-2babacb3e92b	5be2de87-8430-4395-9102-3a7fdc76eb48	submission_created	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"period_end": "2026-06-17", "period_start": "2026-06-01", "submission_id": "e48be19a-1245-4510-9264-639a3a3c730a"}	2026-06-15 10:31:54.263369+00
1cacf473-1e06-44ac-a5a8-43d4e9a8a1f5	5be2de87-8430-4395-9102-3a7fdc76eb48	submission_updated	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"new": "submitted", "old": "draft", "field": "status", "submission_id": "e48be19a-1245-4510-9264-639a3a3c730a"}	2026-06-16 04:04:22.036678+00
be4d0bbc-aef9-468c-add9-4a89b4664b91	dc7a5e96-2808-4842-8924-b03e9c51c4a6	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "team_lead", "employee_name": "Santhosh Kumar"}	2026-06-17 04:21:07.840323+00
cf3a4b58-24d2-475d-86e3-02ef3784712a	dc7a5e96-2808-4842-8924-b03e9c51c4a6	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "contributor", "employee_name": "EMP 1"}	2026-06-17 04:21:11.976509+00
902c5060-7714-48e5-b450-e395e734b2b8	dc7a5e96-2808-4842-8924-b03e9c51c4a6	member_removed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "team_lead", "employee_name": "Santhosh Kumar"}	2026-06-18 06:59:18.52505+00
3f94e13f-6c59-4932-8f87-c1de8da4b14a	82a42b81-d6c1-443e-a2e8-442c84f44a77	member_removed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "contributor", "employee_name": "Santhosh Kumar"}	2026-06-18 06:59:25.991573+00
59c50167-8699-48f6-ba4b-84593a1a1a8b	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	member_removed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "team_lead", "employee_name": "Santhosh Kumar"}	2026-06-18 06:59:49.406318+00
40249b49-fb56-456f-9e67-f0a494e14831	dc7a5e96-2808-4842-8924-b03e9c51c4a6	member_added	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "team_lead", "employee_name": "Santhosh Kumar"}	2026-06-18 08:02:19.765192+00
ec88cba4-e6b2-4a3e-bb3e-c3aca78cee1b	dc7a5e96-2808-4842-8924-b03e9c51c4a6	member_removed	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	{"role": "team_lead", "employee_name": "Santhosh Kumar"}	2026-06-18 08:16:37.534586+00
\.


--
-- Data for Name: projects; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.projects (id, code, name, client, description, status, start_date, planned_completion_date, created_by, updated_by, created_at, updated_at, deleted_at, job_code_id, actual_completion_date, maintenance_plant_id) FROM stdin;
5b205a69-8cce-4b2d-93e1-c81be16b79a6	903423t	PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	\N	\N	archived	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-05 08:21:11.249164+00	2026-06-06 04:02:27.235873+00	\N	\N	\N	\N
c500c890-f911-4483-a62d-3ce63e6f0116	GC19107200	PHASE-1 DCS & NETWORK UPGRADE AND PHASE-2 CONTROLLERS UPGRADE	HONEYWELL	\N	archived	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-09 09:22:47.710172+00	\N	1a94b72d-a9d0-47d7-9479-57bce04ea2f2	\N	\N
95515988-270a-4bd2-81c6-59e50d49c91f	GC17104400	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GALFAR	\N	active	2026-06-11	2026-06-16	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-15 10:15:48.237236+00	\N	9d12d51b-02fb-4573-9b5c-9fb243e27d16	2026-06-26	\N
5be2de87-8430-4395-9102-3a7fdc76eb48	8002	EPIC OF EXTENSION OF JABEL MCC ELECTRICAL BUILDING AND UPS RELOCATION IN DUKHAN FIELDS	QATARENERGY	\N	archived	2025-02-11	2026-03-12	2173ab41-9c1b-4d0c-b100-e69e754116cc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 05:20:35.217465+00	2026-06-16 10:37:42.544733+00	\N	2f8b1c3d-aeb9-48ad-9503-6c60c546ddcd	\N	\N
cf741978-06de-4e69-810a-ccfc17e50d5e	TEST-JC-001	Job Code Combobox Test	BCEC	\N	archived	\N	\N	2173ab41-9c1b-4d0c-b100-e69e754116cc	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 05:22:30.757887+00	2026-06-04 05:22:30.894119+00	\N	2f8b1c3d-aeb9-48ad-9503-6c60c546ddcd	\N	\N
251208c7-9947-4ff3-b3c9-a4dd0aee33df	TEST-UI-001	Combobox Test Project	Test Client	\N	archived	\N	\N	2173ab41-9c1b-4d0c-b100-e69e754116cc	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 05:22:18.824755+00	2026-06-05 06:39:34.922414+00	\N	\N	\N	\N
fb1f7cb7-8e06-45e6-bf3f-ac35d68a3e6f	9002	dummy	DD	this is for testing	archived	2026-06-04	2026-06-25	2173ab41-9c1b-4d0c-b100-e69e754116cc	2173ab41-9c1b-4d0c-b100-e69e754116cc	2026-06-04 04:00:33.996358+00	2026-06-04 04:03:20.287319+00	\N	\N	\N	\N
1f6198c9-1a1a-4e52-bf0c-bbaf41be051a	LC22104500	EPIC FOR REPLACEMENT OF OBSOLETE SCHNEIDER EQUIPMENT (3.3KV SWITCHGEAR) IN KHATIYAH NORTH DEGREASING STATION (DUKHAN)	IMCO	\N	archived	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-11 07:06:31.951952+00	\N	ae5f3535-f0ab-49e8-8537-ef1b3367744e	\N	\N
dc7a5e96-2808-4842-8924-b03e9c51c4a6	GC19101900	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	BCEC	\N	active	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-17 04:21:00.516188+00	\N	2f8b1c3d-aeb9-48ad-9503-6c60c546ddcd	\N	18ca04fa-7427-49c8-b14f-d6ab7b8c2234
4d307a7c-3e46-4f6d-a89b-e73d7e536669	GC191008A0	EPIC FOR FLOWLINES IN DUKHAN FIELDS (2019 - 2022) PART A	GALFAR	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	3104a4d9-2f6a-489c-900d-cebdb8451d81	\N	\N
305f8d94-a201-4efe-b088-6afc4313c23b	PIP-3144 - QC-TSU-088	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	GALFAR	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	40edbcc8-50b2-426a-a12c-df5e0cfffb5f	\N	\N
82a42b81-d6c1-443e-a2e8-442c84f44a77	LC20101600	MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	NEW ERA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	ffb9acd3-328d-4c2d-a6e8-9b03bf68b762	\N	\N
5fcd8c85-8d33-4cfb-9d70-2f039c268605	LC20105500	MISCELLANEOUS INSTRUMENT PCRS AT NGL-1 PLANT IN MESAIEED OPERATIONS	NEW ERA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	5ab9ebc9-8db6-47e3-b292-c37ce14719fb	\N	\N
4312006d-3428-4302-9279-d77f446f2d09	LC17106200	EPIC FOR IMPERVIOUS STORMWATER DRAINAGE AT HWTC - MESAIEED	ALMANA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	2eb9f4f3-0f64-4c4d-a946-fbb09b1b976c	\N	\N
7b9615fa-51ce-46f7-b3bd-4bd39ab0297c	GC21103800	MISCELLANEOUS INSTRUMENTATION MOCS (2021) IN DUKHAN FIELDS	PETROSERV	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	8a72895b-059c-4376-8be4-c5785d92478b	\N	\N
337f4c6a-8c1d-49d3-aac7-8a8f336d1219	LC16106400	EPIC FOR WORKSHOP MODIFICATION AND OTHER MISCELLANEOUS WORKS FOR GRP IN DUKHAN FIELDS	ALMANA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	c1a0c8c7-7692-4e89-b50f-888fb9bc1ef5	\N	\N
dc7c8d65-f961-465d-a14f-5e21c43cded1	GC19102200	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE (DPFU) PHASE 1A - PACKAGE 2	DOPET	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	7be06116-4e79-4c6c-a312-cd42ed6b69de	\N	\N
f7828246-7d17-4166-bbbe-5778dd388122	GC19100700	EPIC OF NEW MP STEAM BOILER, NEW DM WATER PLANT AND ASSOCOATED FACILITIES AT QP REFINERY	DOPET	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	10238d7f-c7ed-48e7-9945-3c0540823748	\N	\N
e8986f97-7e32-4eb7-a7c6-8162b8c9b995	GC18105000	REHABILITATION OF CRUDE OIL TANKS IN QP MESAIEED TANK FARM	TRAGS	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	7e9e4a31-a487-46ee-ae06-5f6583ea8660	\N	\N
77672b85-0391-4fc1-a050-2404f1b2f7fe	GC21103200	EPIC FOR CYBERSECURITY IMPLEMENTATION FOR ABB CONTROL SYSTEM IN DUKHAN FIELDS	ABB	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	7d9f48b3-3e61-4d3d-ae79-8b01e87af0c9	\N	\N
39df9373-9bca-44df-912b-79514acd6d67	LC15101600	EPIC OF EXTENSION OF JABEL  MCC ELECTRICAL BUILDING AND UPS RELOCATION IN DUKHAN FIELDS	ALWAHA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	f83a8fb9-4374-4d90-a072-bc576cbaf29d	\N	\N
bf929d29-d550-4734-94f3-2f449eee0b0a	LC21104100	PROVISION OF KAHRAMAA POWER AT VARIOUS GAS DISTRIBUTION STATIONS	VOLTAGE	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	2472b4dd-48fc-4102-b017-3c42c2b25a14	\N	\N
8d123eed-da28-4fda-a469-44047a336314	GC10108000	EPIC FOR PHASE 1 OF NEW NGL SUPPORT CAMPUS	DIPLOMAT	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	c5ff0b88-2a61-464c-b77a-fefc428cbf29	\N	\N
990a41da-ac0f-4d80-ac04-ed20e47265e4	GC19103600	EPIC FOR CCWS PHASE III FOR NFE PROJECT	MEDGULF	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	f271ae56-be91-4042-b4e5-3e81b33b033e	\N	\N
0accb5f9-e332-4ca7-8c35-afde4fa8af66	GC19108000	MISCELLANEOUS INSTRUMENTATION PCRS (2019) IN DUKHAN FIELDS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	13310c77-bbf0-4b87-bdf3-d0a18711292c	\N	\N
87618b80-8e0f-42cd-a790-980b7b8cb236	LC20104600	IMPLEMENTATION OF INSTRUMENT PCRSΓÇÖ IN NGL-3 AT MESAIEED OPERATIONS.	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	d59ae6b5-8c69-47f5-b6b6-aa50cd2f8895	\N	\N
591503db-d2ed-48ce-80cb-bd5b2013186d	GC21101800	MISCELLANEOUS ELECTRICAL PCRS (2020) IN DUKHAN FIELDS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	9406c1d8-7e4c-4eb8-9b74-139eb4cb38b9	\N	\N
8a6a1ce1-bc3b-4c7f-8c41-9fe67636f0f3	GC21106500	EPIC FOR VARIOUS PIPELINE MOCS IN DUKHAN	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	83df5188-d7f3-4189-9653-2e53ebbb212c	\N	\N
c7bbebae-a346-4b9c-aa74-2135cb3fb5f7	GC21108400	EPIC FOR MISCELLANEOUS ELECTRICAL MOCS (2022) DUKHAN FIELDS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	2f5699ba-d816-4d90-91e7-80bce593a757	\N	\N
cbd200a6-782e-4cce-aa81-776f8c2c14bc	GC22105400	EPIC FOR VARIOUS PIPELINE MOCS IN DUKHAN	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	1b72cf35-4ca2-43aa-9f20-2a1800161023	\N	\N
c90de444-67cc-4142-8ff8-f05c91c04f3e	GC22100800	MISCELLANEOUS ANALYZERS AND GAS CHROMATOGRAPHS IN NGL-3, NGL-4, STATION-S AND STATION-V IN MESAIEED OPERATIONS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	a4647bc4-b8ca-44f4-9794-7ed6e5f074fc	\N	\N
66f006f5-63ca-41cd-8f05-ca678d9eb6ba	GC22106300	EXECUTION OF VARIOUS MODIFICATION WORKS AT NGL PLANTS IN MESAIEED OPERATIONS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	89bcc869-0928-4d4e-b2dd-6e714735ee94	\N	\N
f945c156-1bf3-4da9-8c3c-47b7f8387ffb	LC22102700	UPGRADE OF EMERGENCY DIESEL GENERATORS IN TANK FARM & TERMINAL SUB-STATIONS, SWITCHBOARD REPLACEMENT & PROVIDING NEW DIESEL GENERATOR AT ARAB-D SUBSTATION, MESAIEED OPERATIONS	PETROCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	9b9f1f44-aa80-4f31-ae00-3e8418861d09	\N	\N
d9daab5d-c2b6-4bc8-b8a9-a60a36be970c	MC21102500	INSTALLATION OF WONDERWARE OPC SERVERS ALONG WITH FIREWALLS	L&T	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	2ccef091-e624-4de9-867c-09155702bf4e	\N	\N
32b0fc69-0190-48e0-9ef5-748bee724ef8	GC21103300	CYBER SECURITY IMPLEMENTATION FOR EMERSON CONTROL SYSTEMS IN DUKHAN FIELDS	EMERSON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	7fb75d8f-c0be-44b0-85c9-ba54f9b78be7	\N	\N
12ceb9c1-015f-4e57-b3db-58aac3c35257	LTC-C-NFE-3945-18	NFE PROJECT-CAMP WASTE WATER TREATMENT PLANT	METITO	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	723558ae-a23b-425e-ab2c-6302866d537e	\N	\N
6c0ccbbc-194e-4b02-9a4a-7046c25e9e22	LC20105700	REPLACAMENT OF UPS UNITS AND BATTERY CHARGERS IN NGL,TANK FARM, AND GDS, MESAIEED OPERATIONS	MEKDAM	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	9093e029-0c88-4f86-841e-75468a0fd436	\N	\N
cfc567c3-7c3b-43b5-92c1-951cd4452e04	GC21103500	EPIC FOR INSTALLATION OF FLARE GAS FLOWMETERS IN DUKHAN FIELDS	MEKDAM	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	18f923e2-9907-49f1-ab88-d56e7eb04deb	\N	\N
973d9426-4ef3-4b2c-a55e-1bbc1787ab42	GC21105700	SAP CMMS - LEAK DETECTION SYSTEM FOR CRITICAL PIPELINES IN DUKHAN FIELDS	MEKDAM	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	422ba39e-0a06-4e93-a04a-a00c138dd1b1	\N	\N
b831ef51-66b9-4351-8d97-6312897a95b2	LC21109700	EPIC FFOR CYBER SECURITY IMPLEMENTATION FOR CCC TURBINE AND COMPRESSOR CONTROL SYSTEM IN DUKHAN	EPSILON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	65d1cfbd-7123-4813-bcab-994e6432f824	\N	\N
e77cf369-d25d-41f9-9e69-911bb6008fa4	GC221072B0	MAINTENANCE SUPPORT SERVICES OF VARIOUS PLANT ASSETS ON CALL-OFF BASIS FOR OD(M), OE(M) & OT(M) MESAIEED OPERATIONS	DESCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	9b4de00c-d728-455f-8d3d-8d7187202c74	\N	\N
55152a0c-a2e6-499a-9523-a433544878d3	GC21105600	CYBER SECURITY IMPLEMENTATION & AUTOMATION UPGRADE FOR YOKOGAWA CONTROL SYSTEM IN DUKHAN FIELDS	YOKOGAWA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	b725c310-58b0-4231-8f96-306244500635	\N	\N
7c10768c-ea51-43ea-b4c7-5c8f155460c7	E345328000	REPLACEMENT OF MODICON PLCS AT GDS, MESAIEED	YOKOGAWA	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	f3e1a540-39de-4107-8c84-8ea47509e63f	\N	\N
42abed1e-9ee6-4348-b9db-bcee70a08a12	FMP2000-2400	INSTALLATION OF PIG LAUNCHER / RECEIVER FOR THIRD PARTY GAS INTERCONNECTING FACILITY (TPGIF)	DESCON	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	577bc490-a2d3-46f1-8bc0-c9fea78d42a5	\N	\N
00ecd146-fbd3-4ef3-ae73-3b8d414c5fe0	GC22101600	4399-GALFAR - EPIC FOR WELLS HOOK-UP 2022-2026 PART-1	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
5a119e5f-cdf8-42b3-bc96-95fd7a03025e	GC22103700	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	HONEYWELL	\N	active	2025-02-12	2026-06-26	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-15 04:18:11.804286+00	\N	b3c8f2fb-6809-496c-be4a-baf3123cf9ad	\N	\N
4b350de2-1c20-4576-980c-f03eacbceb57	LT21109600	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	TEYSEER	\N	active	2026-06-09	2026-06-24	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-15 09:34:38.74737+00	\N	f16db359-0f1d-4ef4-92a2-06f8eb49728d	2026-06-30	\N
04ec228b-b327-43b0-8098-0312571e101b	GC21106900	CYBER SECURITY IMPLEMENTATION AND UPGRADE OF HONEYWELL WELLHEADS SCADA SYSTEM IN DUKHAN FIELDS	HONEYWELL	\N	active	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-15 09:40:18.76397+00	\N	071c99dc-4e06-4659-9dd0-1ce892c7e061	\N	\N
ea284bd5-f7b7-4ac1-acfe-73f89448268a	LC21106100	MISCELLANEOUS PIPELINE MOCS IMESAIEED FIELDS	ALMUFTAH	\N	active	2025-02-12	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-15 09:37:54.493255+00	\N	c326fe8e-81b4-47b3-8dfa-d4d67d687089	2026-06-30	\N
c18758f9-ac48-4012-b015-226f3260b69e	GC15103200	EPIC OF POLICE STATION EXTENSION AND MODIFICATION WORKS	ALWAHA	\N	active	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-16 10:30:07.239859+00	\N	ec0efadd-4091-4129-8ad7-d94a82fe47d1	\N	\N
920eece2-9bb2-4bb0-8947-fc87f7deb6a5	GC24101900	UPGRADE AND INTEGRATION OF FIRE & GAS SYSTEM AT NGL-1 PLANT, MESAIEED OPERATIONS	HONEYWELL	\N	active	\N	\N	\N	e2e3cab0-71ef-44c4-afc2-0ae62f43001b	2026-06-04 03:59:32.59002+00	2026-06-17 05:08:28.391937+00	\N	54f56aeb-c900-4741-8e9e-d71d178258e1	\N	b0bfd990-1fca-4c6c-9438-6fbbd8d8ae55
52f9aba5-1cdb-4a07-8d08-0509820e08d8	GC21104100	4311-EPIC FOR AUTOMATION UPGRADE FOR NGL STOREAGE & LOADING FACILITIES, MESAIEED	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
6486bd6c-9354-4b50-ac44-806fc5738cd7	GC21102500	4329-EPIC FOR LPB-31 FACILITIES & CSF OIL SPILL BOOM AT RLC	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
9a72a98a-0bab-4849-87ec-1bc5a7d4cd81	GC22104900	4460-DUKHAN PRODUCTION FACILITIES UPGRADE (DPFU) ΓÇô PHASE 1B	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
a37f4586-82c7-4cdc-bcbc-e6cdbb48ca99	GC20103000	4222-EPIC FOR FACILITIES MODIFICATIONS AT RG PLANT	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
9ff7cb16-4a16-4927-ae3a-0cccf168081d	GC22101000	4400-EPIC FOR BERTH 6 FIRE PROTECTION WORKS AT MESAIEED PORT	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
1de9e73a-3e17-4811-b1b1-6c435590a4e9	GC21107800	4373-MITIGATION OF HYDROCARBON EMISSIONS FROM QP REFINERY	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
82de2ece-d885-4d38-8ece-0b67e2b7db42	GC22101700	4428-CONSOLIDATED PL-PIPING  WORK	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
357f56e2-e3ad-4876-aa1f-21a537171d64	GC21107300	4391-NEW EFFLUENT WATER TREATMENT PLANT FOR NGL AT MESAIEED	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
3d35718c-09b8-4051-8e53-024bc98c4bd5	GC21109100	4186-MODIFICATIONS IN EXISTING CHEMICAL STORE AT DUKHAN	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	0a60e0a6-ce64-4cab-ab46-d9c905cd14bc	\N	\N
7c6ab7e2-b28e-48a0-9b4a-688516c04c0a	LC21107300	MAINTENANCE DATA ACQUISITION FOR DUKHAN OPERATIONS ON CALL-OFF BASIS	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	4ef28eb2-189e-43c7-a77d-7d46ef2828ef	\N	\N
ee7b0337-584b-48e4-bac4-5a5657f87ab7	8241033758	EPIC OF UPGRADE OF F&G DETECTION SYSTEM FOR BATTERY ROOMS, WORKSHOPS, SECURITY GUARD ROOMS AND INSTRUMENT AIR COMPRESSOR SHELTER AT ALL FACILITIES WITHIN DUKHAN	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	cffd004b-9085-4e47-9df9-9e022b6ce0e8	\N	\N
59a302e0-7c33-4f4b-a701-6a414371a332	8241036595	EPIC FOR ENHANCEMENT OF STATION S_PROJECT NO 4504	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	48511043-c0b8-49a6-9182-b1c095be2545	\N	\N
ba676f9e-f5d3-4d18-8df1-606528d2c783	8241038143	CONSTRUCTION FOR UPGRADATION OF EXISTING REFINERY CHEMICAL STORE	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	559f6b2e-4509-4459-b575-3a96d7d0b5a9	\N	\N
574c81c8-adf3-4a8e-aeff-7b709e51c541	8241035701	EPIC FOR SOUTH CHANNEL NAVIGATION LEADING LIGHTS AT RAS LAFFAN PORT	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	6970c8fd-040f-4ddc-ab4e-4310cf5fcec8	\N	\N
92ecffce-ad61-4208-8c5e-84e2d95bbfff	8241036921	EPIC FOR TRAFFIC SIGNAL AT SHAQAB STREET, RLC	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	05679e47-37d2-45ca-a20b-33e5ffff87ed	\N	\N
0fb40a97-0935-4da8-8f6f-d32e01b485e6	LC24107700	CMMS DATA ACQUISITION AND UPDATE SERVICES FOR CHEMICAL PLANT ASSETS AT QATARENERGY REFINERY, MESAIEED	QATARENERGY	\N	active	\N	\N	\N	\N	2026-06-04 03:59:32.59002+00	2026-06-04 03:59:32.59002+00	\N	64852bd0-1cae-44bd-b6da-3cdd533d82d9	\N	\N
\.


--
-- Data for Name: tasks; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.tasks (id, title, description, assigned_to_employee_id, assigned_by_employee_id, status, priority, due_date, created_at, updated_at, project_id) FROM stdin;
096b7ae9-b916-49c0-8b6c-d916e8416fd0	demo task	demo	e5ce164a-f805-4970-80be-cbd21533d1d0	44659769-37c8-4b98-b5b0-4e1e6a7f7d2d	completed	high	2026-06-12	2026-06-11 07:29:49.719656+00	2026-06-11 07:30:14.696189+00	\N
8b878fe9-d4b1-47fc-af85-bfa898d98458	monthly attendance report	make the attendance for may month	d595afe7-1dd9-4c83-ba17-d8fc11a14724	e5ce164a-f805-4970-80be-cbd21533d1d0	completed	high	2026-06-11	2026-06-11 08:29:59.441863+00	2026-06-11 08:30:52.479279+00	5a119e5f-cdf8-42b3-bc96-95fd7a03025e
7764733e-1d76-436c-ae83-a3c217daf9fe	demo task 2	\N	d595afe7-1dd9-4c83-ba17-d8fc11a14724	e5ce164a-f805-4970-80be-cbd21533d1d0	completed	high	2026-06-18	2026-06-18 06:47:08.82661+00	2026-06-18 06:47:37.690452+00	dc7a5e96-2808-4842-8924-b03e9c51c4a6
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.users (id, email, password_hash, role, is_active, last_login_at, created_at, updated_at, deleted_at) FROM stdin;
67188c2e-7217-40da-8222-7ff7b0cdc8b0	emp1@gmail.com	$2b$12$6CAX4NVEHmZ8mo9gzEGHT.wftDfIzVGSzzGgWL3NKVDo9HRw/XLkO	employee	t	2026-06-19 12:03:35.239538+00	2026-06-06 07:14:27.257313+00	2026-06-19 12:03:35.035034+00	\N
e2e3cab0-71ef-44c4-afc2-0ae62f43001b	manager@coreops.local	$2b$12$NLCyibk1QQInCCyPg9U6vuwk3kp64aSQ8syUqtp.kSiGualtL/Cse	project_manager	t	2026-06-20 13:09:36.272206+00	2026-06-03 08:29:38.753384+00	2026-06-20 13:09:36.055635+00	\N
9f946201-e71e-4356-b830-2dddae74e9f9	santhoshkumar29948@gmail.com	$2b$12$8lLdCuMvCMueXNpcxKjzUeZV2idjsh1r8/GkZmPbttY7hTZ.4hsGW	employee	t	2026-06-20 14:02:36.147056+00	2026-06-05 04:58:27.645626+00	2026-06-20 14:02:35.934381+00	\N
b9a8554b-4498-4a20-b204-0b5fa4efe7aa	nainar@gmail.com	$2b$12$LA281vkngNGBYXLsYefmz.FUU7nCS.x.iolX1FP8L.tR4.gAm/ywy	employee	t	2026-06-20 14:12:32.606733+00	2026-06-06 05:02:43.603708+00	2026-06-20 14:12:32.394021+00	\N
\.


--
-- Data for Name: work_report_tasks; Type: TABLE DATA; Schema: public; Owner: wms
--

COPY public.work_report_tasks (id, report_id, project_id, description, minutes_spent, created_at, activity_type, tags_count, docs_count, bom_count, spares_count, project_name, project_code, project_job_code_code, task_id, task_title, task_minutes_spent, sub_activity_id, sub_activity_name, activity_name, benchmark_value_snapshot, benchmark_period_days_snapshot, benchmark_type_snapshot, deficit, productivity_pct, completed_date, relevant_count_field_snapshot, started_date, due_date, is_completed, maintenance_plant_id, maintenance_plant_code, maintenance_plant_description, planning_plant_code, planning_plant_description) FROM stdin;
635b88c7-68d1-40ad-aa95-d64d8044a6f2	48ca50a7-8b2b-4332-987f-a5c385e04a22	95515988-270a-4bd2-81c6-59e50d49c91f		480	2026-06-18 09:46:43.425995+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	80	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	20.00	80.00	\N	tags	\N	\N	f	85fe2ef6-c52f-43a0-af38-162e119b422e	DCPS	Dukhan Cathodic Prtctn Satns	2300	Dukhan Planning Plant
7ef6df85-b14f-4d21-99e2-974fd218d8d1	a857ac14-1c15-43d8-b6a2-b74e189a4ea0	4b350de2-1c20-4576-980c-f03eacbceb57		480	2026-06-18 09:49:02.938248+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)	0	998	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	f85a2563-1ee5-4c8b-b33a-81105dc68b37	DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)	DOC IDB	1000.00	1	NUMERIC	2.00	99.80	\N	docs	\N	\N	f	d619adb6-96b0-41a2-9d8e-4936892066f4	CLS1	PWI Cluster 1 Dukhan	2300	Dukhan Planning Plant
e445c822-c3b4-41e4-8a65-7db99755ae67	bf096e33-db9d-4f2c-a6aa-900334d4d621	4b350de2-1c20-4576-980c-f03eacbceb57		480	2026-06-18 09:57:06.425051+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	120	0	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	0.00	120.00	\N	tags	\N	\N	f	d619adb6-96b0-41a2-9d8e-4936892066f4	CLS1	PWI Cluster 1 Dukhan	2300	Dukhan Planning Plant
e866fd5e-c087-4d78-85f3-418e58a7234f	2e8faded-23b5-42a3-a9c7-eceb63df3698	95515988-270a-4bd2-81c6-59e50d49c91f		480	2026-06-20 08:45:10.607596+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)	0	1100	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	f85a2563-1ee5-4c8b-b33a-81105dc68b37	DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)	DOC IDB	1000.00	1	NUMERIC	0.00	110.00	\N	docs	\N	\N	f	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
5222ce5b-2921-4ddb-9ed4-d61a45b1ad26	aac55b99-c681-4d9e-ad73-5b4f150fda1d	95515988-270a-4bd2-81c6-59e50d49c91f		240	2026-06-19 04:41:14.477151+00	MTL / MTL-ASSET PHOTO DATA POPULATION	100	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	8d8ee379-b82e-42a3-8033-87b5b6d9dd45	MTL-ASSET PHOTO DATA POPULATION	MTL	100.00	1	NUMERIC	0.00	100.00	\N	tags	\N	\N	f	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
9f6a4839-9664-418b-903c-b7e2e6b96b31	4b4c4614-7680-487e-b2d5-2be890c5e55f	82a42b81-d6c1-443e-a2e8-442c84f44a77		480	2026-06-16 10:42:42.011906+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	0	0	0	0	MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	LC20101600	J-671	\N	\N	\N	574b5630-ba34-452b-8da6-214395b87ab4	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	DOC IDB	\N	1	TASK_BASED	\N	\N	2026-06-16	\N	2026-06-16	2026-06-16	t	\N	\N	\N	\N	\N
48bcce98-5f01-4acd-aec2-1a7d81d25cd2	46de0335-6e37-4c6b-841e-cb6c0b4b5400	95515988-270a-4bd2-81c6-59e50d49c91f		240	2026-06-18 09:55:32.158932+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	0	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	574b5630-ba34-452b-8da6-214395b87ab4	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	DOC IDB	\N	1	TASK_BASED	\N	\N	2026-06-20	\N	2026-06-12	2026-06-12	t	2235ed80-fd4c-42af-9688-1527e0c627a7	CSMD	COMMUNITY SERVICES	2300	Dukhan Planning Plant
ad41b0d7-e497-43ae-8d0e-4e489e170770	79e757e0-5b64-4f65-aa10-4df6846dc1d9	305f8d94-a201-4efe-b088-6afc4313c23b		540	2026-06-20 12:18:49.653826+00	MTL / MTL-ASSET PHOTO MERGING	130	0	0	0	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	PIP-3144 - QC-TSU-088	J-670-8	\N	\N	\N	d0f4b938-7602-42b6-8056-c0838197f643	MTL-ASSET PHOTO MERGING	MTL	160.00	1	NUMERIC	30.00	81.25	\N	tags	\N	\N	f	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
d666685c-78a1-4dc5-b61e-9571f5118a34	aac55b99-c681-4d9e-ad73-5b4f150fda1d	4b350de2-1c20-4576-980c-f03eacbceb57		240	2026-06-19 04:41:14.477151+00	PM IDB / PM IDB-ADDRESSING MAITENANCE TYPE PM/IM/SD/CM AND ISOLATION REQUIRED TAG	0	0	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	073fc79e-4042-4084-9075-fb9294e4ff08	PM IDB-ADDRESSING MAITENANCE TYPE PM/IM/SD/CM AND ISOLATION REQUIRED TAG	PM IDB	\N	1	TASK_BASED	\N	\N	2026-06-20	\N	2026-06-19	2026-06-19	t	3edbd787-ad2d-4f1f-9796-a91c65e3d270	CLS2	PWI Cluster 2 Dukhan	2300	Dukhan Planning Plant
450f1798-fc1d-4ea6-9bbf-177e674752a5	7981001e-8a6b-468e-959a-4490412a7f33	95515988-270a-4bd2-81c6-59e50d49c91f		480	2026-06-20 12:17:06.895038+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT	140	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	7394cca9-e79d-4cce-9b28-826a487702e0	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT	FMTL	120.00	1	NUMERIC	0.00	116.67	\N	tags	\N	\N	f	2235ed80-fd4c-42af-9688-1527e0c627a7	CSMD	COMMUNITY SERVICES	2300	Dukhan Planning Plant
7d80dacc-b0f4-4795-a764-80b2835a1609	5bf88bb7-a198-4cf8-8dfc-1250ee54ae09	5a119e5f-cdf8-42b3-bc96-95fd7a03025e		420	2026-06-20 12:21:04.547713+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	0	0	0	0	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	GC22103700	J-665-4	\N	\N	\N	574b5630-ba34-452b-8da6-214395b87ab4	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	DOC IDB	\N	1	TASK_BASED	\N	\N	2026-06-20	\N	2026-06-15	2026-06-15	t	bd17676a-60e9-41f5-9ca6-ee33bc1e7081	ARBD	Arab "D"	2300	Dukhan Planning Plant
a29d85b9-e4f0-4f62-a942-f08c3d1f68b4	70e0d64d-88e0-4000-859d-041a4b4c150b	95515988-270a-4bd2-81c6-59e50d49c91f		360	2026-06-20 12:26:12.53462+00	FMTL / FMTL-CRS CORRECTION	0	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	409e399c-0a5c-43bf-8c81-f2672aa31ae7	FMTL-CRS CORRECTION	FMTL	\N	1	TASK_BASED	\N	\N	\N	\N	2026-06-20	2026-06-20	f	85fe2ef6-c52f-43a0-af38-162e119b422e	DCPS	Dukhan Cathodic Prtctn Satns	2300	Dukhan Planning Plant
e4843a52-8d43-4035-918a-1c20ca6a7b4a	38e574b4-5a1c-4fc3-b3f6-9b7bac7f7e81	305f8d94-a201-4efe-b088-6afc4313c23b		\N	2026-06-20 12:59:32.957144+00	DOC IDB / DOC IDB-DOC MATRIX WITH FMTL DATA MIGRATION&POPULATION	0	0	0	0	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	PIP-3144 - QC-TSU-088	J-670-8	\N	\N	\N	0258b58a-c7e3-4c5b-92c8-ca361557c010	DOC IDB-DOC MATRIX WITH FMTL DATA MIGRATION&POPULATION	DOC IDB	\N	\N	\N	\N	\N	2026-06-20	\N	2026-06-02	2026-06-02	t	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
a4b9b9f6-7986-4f74-b860-0a5b47a56e39	f148fe94-2dcd-4e8b-b9e3-00f82877a3e6	95515988-270a-4bd2-81c6-59e50d49c91f		\N	2026-06-20 13:00:01.633956+00	BOM IDB / BOM IDB-CRS CORRECTION	0	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	79845b09-05f9-4b1b-bf6c-64d99b926a87	BOM IDB-CRS CORRECTION	BOM IDB	\N	1	TASK_BASED	\N	\N	2026-06-20	\N	2026-06-03	2026-06-03	t	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
bbc76416-91cd-4209-8ce0-631b7ede829c	14f751dc-8c69-4142-838d-f9e7397b72c7	95515988-270a-4bd2-81c6-59e50d49c91f		\N	2026-06-20 13:12:17.60513+00	DEMOLITION / DEMOLITION-CRS CORRECTION	0	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	8f513dd8-bff6-4cd3-a5f1-c29e7cf6f499	DEMOLITION-CRS CORRECTION	DEMOLITION	\N	\N	\N	\N	\N	2026-06-20	\N	2026-06-08	2026-06-08	t	b18a369d-47a5-496c-bb51-383cdaa9cf21	DKDSP	\N	2300	Dukhan Planning Plant
4bec13b9-db24-4c84-8329-2d32d2ace159	7463d3ea-7e1d-4cc7-a55a-7885ee3fc14f	5a119e5f-cdf8-42b3-bc96-95fd7a03025e	working on tag estimation	540	2026-06-11 06:18:45.094875+00	TAG ESTIMATION	0	0	0	0	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	GC22103700	J-665-4	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N
5b3e5652-d569-49eb-a85a-a0077721a0db	6f01a62f-c5d8-4e07-82db-9daafb3f11ae	5a119e5f-cdf8-42b3-bc96-95fd7a03025e		228	2026-06-11 09:22:30.101629+00	ADMIN SUPPORT	0	0	0	0	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	GC22103700	J-665-4	8b878fe9-d4b1-47fc-af85-bfa898d98458	monthly attendance report	350	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	f	\N	\N	\N	\N	\N
6e3c421a-d774-4315-97fa-d8be2968d142	079ace61-a9cf-436e-a717-fa621baea3b0	5a119e5f-cdf8-42b3-bc96-95fd7a03025e		480	2026-06-16 10:43:44.378027+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	20	0	0	0	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	GC22103700	J-665-4	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	80.00	20.00	\N	tags	\N	\N	f	\N	\N	\N	\N	\N
4b453e1c-b180-4c6e-8a61-cb487055e59d	d6e40df2-543a-4731-b87c-60ed0e446670	dc7a5e96-2808-4842-8924-b03e9c51c4a6		480	2026-06-18 05:15:26.347966+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT	100	0	0	0	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	GC19101900	J-615-2	\N	\N	\N	7394cca9-e79d-4cce-9b28-826a487702e0	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT	FMTL	120.00	1	NUMERIC	20.00	83.33	\N	tags	\N	\N	f	2235ed80-fd4c-42af-9688-1527e0c627a7	CSMD	COMMUNITY SERVICES	2300	Dukhan Planning Plant
8dc4b816-9b54-4a70-b9a7-48178bd73332	219d4a01-c2cd-47aa-8d1b-c4ac3659cdc3	82a42b81-d6c1-443e-a2e8-442c84f44a77		480	2026-06-18 05:17:42.540199+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	120	0	0	0	MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	LC20101600	J-671	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	0.00	120.00	\N	tags	\N	\N	f	b0bfd990-1fca-4c6c-9438-6fbbd8d8ae55	NGL1	NGL1 Mesaieed	2400	Messaieed Planning Plant
0c868bf7-ebc0-4e4b-8a32-659be8b4d9d8	845859b5-f91a-4956-88db-5d262cf1f97e	82a42b81-d6c1-443e-a2e8-442c84f44a77		480	2026-06-18 05:19:24.599916+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	80	0	0	0	MISCELLANEOUS INSTRUMENT PCRS AT NGL AND TERMINAL OPERATIONS	LC20101600	J-671	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	20.00	80.00	\N	tags	\N	\N	f	b0bfd990-1fca-4c6c-9438-6fbbd8d8ae55	NGL1	NGL1 Mesaieed	2400	Messaieed Planning Plant
ef934766-71e8-4370-87a2-0304b732c8ea	9155dd7a-3d33-4b74-9978-7c8a058fcc15	4b350de2-1c20-4576-980c-f03eacbceb57		240	2026-06-18 09:47:36.185032+00	MTL / MTL-ASSET PHOTO MERGING	100	0	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	d0f4b938-7602-42b6-8056-c0838197f643	MTL-ASSET PHOTO MERGING	MTL	160.00	1	NUMERIC	60.00	62.50	\N	tags	\N	\N	f	85fe2ef6-c52f-43a0-af38-162e119b422e	DCPS	Dukhan Cathodic Prtctn Satns	2300	Dukhan Planning Plant
c2ade246-86fa-402a-8a8f-3eac67869ee9	dfb9c1ae-3383-4a43-8acb-9bd0226569a0	305f8d94-a201-4efe-b088-6afc4313c23b		480	2026-06-20 12:17:50.796219+00	MTL / MTL-ASSET PHOTO MERGING	140	0	0	0	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	PIP-3144 - QC-TSU-088	J-670-8	\N	\N	\N	d0f4b938-7602-42b6-8056-c0838197f643	MTL-ASSET PHOTO MERGING	MTL	160.00	1	NUMERIC	20.00	87.50	\N	tags	\N	\N	f	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
fde01736-9c71-49fe-849f-96d54ae9c578	f2aeef12-1011-4f4b-8cd6-3cea27d607ec	5a119e5f-cdf8-42b3-bc96-95fd7a03025e		480	2026-06-20 12:19:24.564036+00	MTL / MTL-ASSET PHOTO MERGING	200	0	0	0	UPGRADE THE DCS/ ESD/FGS SYSTEM AT LER#25A AND ESD/FGS AT ARAB-D NGL TANK FARM	GC22103700	J-665-4	\N	\N	\N	d0f4b938-7602-42b6-8056-c0838197f643	MTL-ASSET PHOTO MERGING	MTL	160.00	1	NUMERIC	0.00	125.00	\N	tags	\N	\N	f	bd17676a-60e9-41f5-9ca6-ee33bc1e7081	ARBD	Arab "D"	2300	Dukhan Planning Plant
225ed91b-afb9-467a-903d-5a92437ccb03	c65a2c33-ff92-4a55-9703-e0aadb0e9b0a	4b350de2-1c20-4576-980c-f03eacbceb57		\N	2026-06-20 13:00:50.635623+00	INITIAL IDB / INITIAL IDB-AUDIT QUERY WITH REPORT	0	0	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	f45e92df-33e9-40d3-afe0-03e8a6463dba	INITIAL IDB-AUDIT QUERY WITH REPORT	INITIAL IDB	\N	\N	\N	\N	\N	2026-06-20	\N	2026-06-13	2026-06-14	t	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
f4a4af30-fdf1-43a3-a9a0-8bf7e4fd4279	46de0335-6e37-4c6b-841e-cb6c0b4b5400	4b350de2-1c20-4576-980c-f03eacbceb57		240	2026-06-18 09:55:32.158932+00	FMTL / FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	100	0	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	fff4443a-8ec0-4d2c-8892-ac34d3ae2aab	FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER	FMTL	100.00	1	NUMERIC	0.00	100.00	\N	tags	\N	\N	f	2235ed80-fd4c-42af-9688-1527e0c627a7	CSMD	COMMUNITY SERVICES	2300	Dukhan Planning Plant
0690b904-488d-4817-bcb4-bc344ef1be0d	09849a5f-e738-4ab4-bdeb-14f4fba589af	4b350de2-1c20-4576-980c-f03eacbceb57		\N	2026-06-20 13:13:10.56397+00	DOC IDB / DOC IDB-REWORK	0	400	0	0	UPGRADE OF GE MARK-VIE TURBINE CONTROL SYSTEM AND CYBER SECURITY IMPLEMENTATION IN DUKHAN FIELDS	LT21109600	J-706-3	\N	\N	\N	1cad4e7a-edbb-4b13-8f21-8cd130092001	DOC IDB-REWORK	DOC IDB	500.00	1	NUMERIC	100.00	80.00	\N	docs	\N	\N	f	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
02fe0847-d70c-4833-91ce-75f35e024524	431de1dd-90c4-44f8-bbe5-49ec2193602f	305f8d94-a201-4efe-b088-6afc4313c23b		480	2026-06-18 10:41:59.661587+00	FLOC/EQPT-IDB(PMEQM) / HIERARCHY DATA POPULATION MIGRATION OF FMTL/MTL DATA	0	0	0	0	EPC OF METALLURGY UPGRADE OF OFF GAS PIPING	PIP-3144 - QC-TSU-088	J-670-8	\N	\N	\N	d901c1af-665d-423a-b904-5bc1810b7172	HIERARCHY DATA POPULATION MIGRATION OF FMTL/MTL DATA	FLOC/EQPT-IDB(PMEQM)	\N	1	TASK_BASED	\N	\N	2026-06-19	\N	2026-06-01	2026-06-01	t	8e5fef37-0554-4959-aa6b-d907cb865562	DKDP	Dukhan Water Storage & Dist	2300	Dukhan Planning Plant
41224f7b-f667-4664-8fd0-14bab4fa513c	9155dd7a-3d33-4b74-9978-7c8a058fcc15	95515988-270a-4bd2-81c6-59e50d49c91f		240	2026-06-18 09:47:36.185032+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	0	0	0	0	SAP CMMS SERVICES FOR HALUL LER-1 PROJECT	GC17104400	J-670-9	\N	\N	\N	574b5630-ba34-452b-8da6-214395b87ab4	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	DOC IDB	\N	1	TASK_BASED	\N	\N	2026-06-18	\N	2026-06-16	2026-06-16	t	f38939e9-21c1-4a32-8d52-beab56662bd4	DYAB	DIYAB	2300	Dukhan Planning Plant
43a2b2d6-205b-49cb-99d6-05640cf5161f	219d4a01-c2cd-47aa-8d1b-c4ac3659cdc3	dc7a5e96-2808-4842-8924-b03e9c51c4a6		480	2026-06-18 05:17:42.540199+00	DOC IDB / DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	0	0	0	0	EPIC FOR DUKHAN PRODUCTION FACILITIES UPGRADE PHASE1A ΓÇô PACKAGE 1	GC19101900	J-615-2	\N	\N	\N	574b5630-ba34-452b-8da6-214395b87ab4	DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)	DOC IDB	\N	1	TASK_BASED	\N	\N	\N	\N	2026-06-18	2026-06-18	f	d619adb6-96b0-41a2-9d8e-4936892066f4	CLS1	PWI Cluster 1 Dukhan	2300	Dukhan Planning Plant
\.


--
-- Name: activity_master activity_master_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.activity_master
    ADD CONSTRAINT activity_master_pkey PRIMARY KEY (id);


--
-- Name: activity_types activity_types_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.activity_types
    ADD CONSTRAINT activity_types_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: attendance_records attendance_emp_date_uq; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_emp_date_uq UNIQUE (employee_id, attendance_date);


--
-- Name: attendance_records attendance_records_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_records_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: company_calendar_events company_calendar_events_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.company_calendar_events
    ADD CONSTRAINT company_calendar_events_pkey PRIMARY KEY (id);


--
-- Name: daily_work_reports daily_work_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.daily_work_reports
    ADD CONSTRAINT daily_work_reports_pkey PRIMARY KEY (id);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: export_jobs export_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.export_jobs
    ADD CONSTRAINT export_jobs_pkey PRIMARY KEY (id);


--
-- Name: job_codes job_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.job_codes
    ADD CONSTRAINT job_codes_pkey PRIMARY KEY (id);


--
-- Name: leave_requests leave_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.leave_requests
    ADD CONSTRAINT leave_requests_pkey PRIMARY KEY (id);


--
-- Name: maintenance_plants maintenance_plants_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.maintenance_plants
    ADD CONSTRAINT maintenance_plants_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: offices offices_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.offices
    ADD CONSTRAINT offices_pkey PRIMARY KEY (id);


--
-- Name: planning_plants planning_plants_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.planning_plants
    ADD CONSTRAINT planning_plants_pkey PRIMARY KEY (id);


--
-- Name: project_activities project_activities_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_activities
    ADD CONSTRAINT project_activities_pkey PRIMARY KEY (id);


--
-- Name: project_deliverables project_deliverables_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_deliverables
    ADD CONSTRAINT project_deliverables_pkey PRIMARY KEY (id);


--
-- Name: project_managers project_managers_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_managers
    ADD CONSTRAINT project_managers_pkey PRIMARY KEY (id);


--
-- Name: project_managers project_managers_uq; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_managers
    ADD CONSTRAINT project_managers_uq UNIQUE (project_id, user_id);


--
-- Name: project_members project_members_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_pkey PRIMARY KEY (id);


--
-- Name: project_members project_members_uq; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_uq UNIQUE (project_id, employee_id);


--
-- Name: project_planned_date_changes project_planned_date_changes_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_planned_date_changes
    ADD CONSTRAINT project_planned_date_changes_pkey PRIMARY KEY (id);


--
-- Name: project_submission_items project_submission_items_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submission_items
    ADD CONSTRAINT project_submission_items_pkey PRIMARY KEY (id);


--
-- Name: project_submissions project_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submissions
    ADD CONSTRAINT project_submissions_pkey PRIMARY KEY (id);


--
-- Name: project_timeline_events project_timeline_events_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_timeline_events
    ADD CONSTRAINT project_timeline_events_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: work_report_tasks work_report_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_pkey PRIMARY KEY (id);


--
-- Name: daily_work_reports work_reports_emp_date_uq; Type: CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.daily_work_reports
    ADD CONSTRAINT work_reports_emp_date_uq UNIQUE (employee_id, report_date);


--
-- Name: activity_master_active_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX activity_master_active_idx ON public.activity_master USING btree (is_active);


--
-- Name: activity_master_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX activity_master_code_uq ON public.activity_master USING btree (code) WHERE ((is_active = true) AND (code IS NOT NULL));


--
-- Name: activity_master_level_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX activity_master_level_idx ON public.activity_master USING btree (level);


--
-- Name: activity_master_parent_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX activity_master_parent_idx ON public.activity_master USING btree (parent_id);


--
-- Name: activity_types_active_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX activity_types_active_idx ON public.activity_types USING btree (is_active);


--
-- Name: activity_types_category_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX activity_types_category_idx ON public.activity_types USING btree (category);


--
-- Name: activity_types_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX activity_types_code_uq ON public.activity_types USING btree (code) WHERE ((is_active = true) AND (code IS NOT NULL));


--
-- Name: attendance_date_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX attendance_date_idx ON public.attendance_records USING btree (attendance_date);


--
-- Name: attendance_employee_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX attendance_employee_idx ON public.attendance_records USING btree (employee_id, attendance_date);


--
-- Name: audit_action_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX audit_action_idx ON public.audit_logs USING btree (action);


--
-- Name: audit_actor_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX audit_actor_idx ON public.audit_logs USING btree (actor_user_id, created_at);


--
-- Name: audit_created_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX audit_created_idx ON public.audit_logs USING btree (created_at DESC);


--
-- Name: audit_entity_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX audit_entity_idx ON public.audit_logs USING btree (entity_type, entity_id);


--
-- Name: cal_event_date_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX cal_event_date_idx ON public.company_calendar_events USING btree (event_date);


--
-- Name: cal_event_type_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX cal_event_type_idx ON public.company_calendar_events USING btree (event_type, event_date);


--
-- Name: employees_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX employees_code_uq ON public.employees USING btree (employee_code) WHERE (deleted_at IS NULL);


--
-- Name: employees_manager_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX employees_manager_idx ON public.employees USING btree (manager_id) WHERE (deleted_at IS NULL);


--
-- Name: employees_office_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX employees_office_idx ON public.employees USING btree (office_id) WHERE (deleted_at IS NULL);


--
-- Name: employees_reporting_pm_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX employees_reporting_pm_idx ON public.employees USING btree (reporting_pm_id) WHERE (deleted_at IS NULL);


--
-- Name: employees_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX employees_status_idx ON public.employees USING btree (status) WHERE (deleted_at IS NULL);


--
-- Name: employees_user_id_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX employees_user_id_uq ON public.employees USING btree (user_id) WHERE ((user_id IS NOT NULL) AND (deleted_at IS NULL));


--
-- Name: employees_work_email_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX employees_work_email_uq ON public.employees USING btree (work_email) WHERE ((work_email IS NOT NULL) AND (deleted_at IS NULL));


--
-- Name: export_jobs_requester_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX export_jobs_requester_idx ON public.export_jobs USING btree (requested_by, created_at DESC);


--
-- Name: job_codes_active_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX job_codes_active_idx ON public.job_codes USING btree (is_active);


--
-- Name: job_codes_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX job_codes_code_uq ON public.job_codes USING btree (code) WHERE (is_active = true);


--
-- Name: leave_employee_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX leave_employee_idx ON public.leave_requests USING btree (employee_id, start_date);


--
-- Name: leave_manager_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX leave_manager_idx ON public.leave_requests USING btree (manager_id, status);


--
-- Name: leave_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX leave_status_idx ON public.leave_requests USING btree (status);


--
-- Name: maintenance_plants_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX maintenance_plants_code_uq ON public.maintenance_plants USING btree (code) WHERE (is_active = true);


--
-- Name: maintenance_plants_planning_plant_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX maintenance_plants_planning_plant_idx ON public.maintenance_plants USING btree (planning_plant_id);


--
-- Name: notif_created_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX notif_created_idx ON public.notifications USING btree (created_at);


--
-- Name: notif_unread_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX notif_unread_idx ON public.notifications USING btree (user_id) WHERE (is_read = false);


--
-- Name: notif_user_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX notif_user_idx ON public.notifications USING btree (user_id, created_at);


--
-- Name: offices_name_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX offices_name_uq ON public.offices USING btree (name);


--
-- Name: planning_plants_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX planning_plants_code_uq ON public.planning_plants USING btree (code) WHERE (is_active = true);


--
-- Name: project_activities_assignee_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_activities_assignee_idx ON public.project_activities USING btree (assigned_to_id);


--
-- Name: project_activities_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_activities_project_idx ON public.project_activities USING btree (project_id);


--
-- Name: project_activities_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_activities_status_idx ON public.project_activities USING btree (status);


--
-- Name: project_deliverables_owner_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_deliverables_owner_idx ON public.project_deliverables USING btree (owner_employee_id);


--
-- Name: project_deliverables_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_deliverables_project_idx ON public.project_deliverables USING btree (project_id);


--
-- Name: project_deliverables_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_deliverables_status_idx ON public.project_deliverables USING btree (status);


--
-- Name: project_managers_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_managers_project_idx ON public.project_managers USING btree (project_id);


--
-- Name: project_managers_user_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_managers_user_idx ON public.project_managers USING btree (user_id);


--
-- Name: project_members_employee_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_members_employee_idx ON public.project_members USING btree (employee_id);


--
-- Name: project_members_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_members_project_idx ON public.project_members USING btree (project_id);


--
-- Name: project_planned_date_changes_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_planned_date_changes_project_idx ON public.project_planned_date_changes USING btree (project_id);


--
-- Name: project_submission_items_submission_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_submission_items_submission_idx ON public.project_submission_items USING btree (submission_id);


--
-- Name: project_submissions_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_submissions_project_idx ON public.project_submissions USING btree (project_id);


--
-- Name: project_submissions_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_submissions_status_idx ON public.project_submissions USING btree (status);


--
-- Name: project_timeline_events_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX project_timeline_events_project_idx ON public.project_timeline_events USING btree (project_id, created_at);


--
-- Name: projects_code_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX projects_code_uq ON public.projects USING btree (code) WHERE (deleted_at IS NULL);


--
-- Name: projects_job_code_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX projects_job_code_idx ON public.projects USING btree (job_code_id) WHERE (deleted_at IS NULL);


--
-- Name: projects_maintenance_plant_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX projects_maintenance_plant_idx ON public.projects USING btree (maintenance_plant_id);


--
-- Name: projects_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX projects_status_idx ON public.projects USING btree (status) WHERE (deleted_at IS NULL);


--
-- Name: tasks_assigned_by_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX tasks_assigned_by_idx ON public.tasks USING btree (assigned_by_employee_id);


--
-- Name: tasks_assigned_to_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX tasks_assigned_to_idx ON public.tasks USING btree (assigned_to_employee_id, status);


--
-- Name: tasks_due_date_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX tasks_due_date_idx ON public.tasks USING btree (due_date);


--
-- Name: tasks_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX tasks_project_idx ON public.tasks USING btree (project_id);


--
-- Name: users_email_uq; Type: INDEX; Schema: public; Owner: wms
--

CREATE UNIQUE INDEX users_email_uq ON public.users USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: work_report_tasks_maintenance_plant_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_report_tasks_maintenance_plant_idx ON public.work_report_tasks USING btree (maintenance_plant_id);


--
-- Name: work_report_tasks_project_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_report_tasks_project_idx ON public.work_report_tasks USING btree (project_id);


--
-- Name: work_report_tasks_report_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_report_tasks_report_idx ON public.work_report_tasks USING btree (report_id);


--
-- Name: work_report_tasks_sub_activity_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_report_tasks_sub_activity_idx ON public.work_report_tasks USING btree (sub_activity_id);


--
-- Name: work_report_tasks_task_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_report_tasks_task_idx ON public.work_report_tasks USING btree (task_id);


--
-- Name: work_reports_date_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_reports_date_idx ON public.daily_work_reports USING btree (report_date);


--
-- Name: work_reports_employee_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_reports_employee_idx ON public.daily_work_reports USING btree (employee_id, report_date);


--
-- Name: work_reports_status_idx; Type: INDEX; Schema: public; Owner: wms
--

CREATE INDEX work_reports_status_idx ON public.daily_work_reports USING btree (status);


--
-- Name: activity_master activity_master_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.activity_master
    ADD CONSTRAINT activity_master_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: activity_master activity_master_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.activity_master
    ADD CONSTRAINT activity_master_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.activity_master(id) ON DELETE RESTRICT;


--
-- Name: attendance_records attendance_records_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.attendance_records
    ADD CONSTRAINT attendance_records_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: audit_logs audit_logs_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: daily_work_reports daily_work_reports_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.daily_work_reports
    ADD CONSTRAINT daily_work_reports_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: employees employees_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: employees employees_office_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_office_id_fkey FOREIGN KEY (office_id) REFERENCES public.offices(id) ON DELETE SET NULL;


--
-- Name: employees employees_reporting_pm_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_reporting_pm_id_fkey FOREIGN KEY (reporting_pm_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: employees employees_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: export_jobs export_jobs_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.export_jobs
    ADD CONSTRAINT export_jobs_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: leave_requests leave_requests_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.leave_requests
    ADD CONSTRAINT leave_requests_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: leave_requests leave_requests_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.leave_requests
    ADD CONSTRAINT leave_requests_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: maintenance_plants maintenance_plants_planning_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.maintenance_plants
    ADD CONSTRAINT maintenance_plants_planning_plant_id_fkey FOREIGN KEY (planning_plant_id) REFERENCES public.planning_plants(id) ON DELETE RESTRICT;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_activities project_activities_activity_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_activities
    ADD CONSTRAINT project_activities_activity_type_id_fkey FOREIGN KEY (activity_type_id) REFERENCES public.activity_types(id) ON DELETE SET NULL;


--
-- Name: project_activities project_activities_assigned_to_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_activities
    ADD CONSTRAINT project_activities_assigned_to_id_fkey FOREIGN KEY (assigned_to_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: project_activities project_activities_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_activities
    ADD CONSTRAINT project_activities_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: project_activities project_activities_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_activities
    ADD CONSTRAINT project_activities_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_deliverables project_deliverables_owner_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_deliverables
    ADD CONSTRAINT project_deliverables_owner_employee_id_fkey FOREIGN KEY (owner_employee_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: project_deliverables project_deliverables_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_deliverables
    ADD CONSTRAINT project_deliverables_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_managers project_managers_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_managers
    ADD CONSTRAINT project_managers_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_managers project_managers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_managers
    ADD CONSTRAINT project_managers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_members project_members_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: project_members project_members_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_members
    ADD CONSTRAINT project_members_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_planned_date_changes project_planned_date_changes_project_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_planned_date_changes
    ADD CONSTRAINT project_planned_date_changes_project_fk FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_planned_date_changes project_planned_date_changes_user_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_planned_date_changes
    ADD CONSTRAINT project_planned_date_changes_user_fk FOREIGN KEY (changed_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: project_submission_items project_submission_items_activity_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submission_items
    ADD CONSTRAINT project_submission_items_activity_fk FOREIGN KEY (activity_type_id) REFERENCES public.activity_types(id) ON DELETE SET NULL;


--
-- Name: project_submission_items project_submission_items_submission_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submission_items
    ADD CONSTRAINT project_submission_items_submission_fk FOREIGN KEY (submission_id) REFERENCES public.project_submissions(id) ON DELETE CASCADE;


--
-- Name: project_submissions project_submissions_project_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submissions
    ADD CONSTRAINT project_submissions_project_fk FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: project_submissions project_submissions_reviewer_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submissions
    ADD CONSTRAINT project_submissions_reviewer_fk FOREIGN KEY (reviewed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: project_submissions project_submissions_submitter_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_submissions
    ADD CONSTRAINT project_submissions_submitter_fk FOREIGN KEY (submitted_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: project_timeline_events project_timeline_events_actor_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_timeline_events
    ADD CONSTRAINT project_timeline_events_actor_fk FOREIGN KEY (actor_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: project_timeline_events project_timeline_events_project_fk; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.project_timeline_events
    ADD CONSTRAINT project_timeline_events_project_fk FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: projects projects_job_code_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_job_code_id_fkey FOREIGN KEY (job_code_id) REFERENCES public.job_codes(id) ON DELETE SET NULL;


--
-- Name: projects projects_maintenance_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_maintenance_plant_id_fkey FOREIGN KEY (maintenance_plant_id) REFERENCES public.maintenance_plants(id) ON DELETE SET NULL;


--
-- Name: tasks tasks_assigned_by_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_assigned_by_employee_id_fkey FOREIGN KEY (assigned_by_employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: tasks tasks_assigned_to_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_assigned_to_employee_id_fkey FOREIGN KEY (assigned_to_employee_id) REFERENCES public.employees(id) ON DELETE RESTRICT;


--
-- Name: tasks tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;


--
-- Name: work_report_tasks work_report_tasks_maintenance_plant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_maintenance_plant_id_fkey FOREIGN KEY (maintenance_plant_id) REFERENCES public.maintenance_plants(id) ON DELETE SET NULL;


--
-- Name: work_report_tasks work_report_tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE RESTRICT;


--
-- Name: work_report_tasks work_report_tasks_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.daily_work_reports(id) ON DELETE CASCADE;


--
-- Name: work_report_tasks work_report_tasks_sub_activity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_sub_activity_id_fkey FOREIGN KEY (sub_activity_id) REFERENCES public.activity_master(id) ON DELETE SET NULL;


--
-- Name: work_report_tasks work_report_tasks_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: wms
--

ALTER TABLE ONLY public.work_report_tasks
    ADD CONSTRAINT work_report_tasks_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict P6EdF1tqrKdR81IHsqwREd9WMa6ljgMm1FcfgvAd4xThsV0MmdZNR4mcVKoOPTs

