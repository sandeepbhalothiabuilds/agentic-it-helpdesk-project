-- Case 4: IT Service Desk Agentic Assist
-- PostgreSQL schema with audit fields and updated_at triggers

CREATE SCHEMA IF NOT EXISTS case4;
SET search_path TO case4, public;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TABLE IF EXISTS action_requests CASCADE;
DROP TABLE IF EXISTS vpn_profiles CASCADE;
DROP TABLE IF EXISTS iam_accounts CASCADE;
DROP TABLE IF EXISTS service_tickets CASCADE;
DROP TABLE IF EXISTS devices CASCADE;
DROP TABLE IF EXISTS runbook_rules CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL,
    location TEXT NOT NULL,
    manager TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    identity_verification_level TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE devices (
    device_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_name TEXT NOT NULL,
    device_type TEXT NOT NULL,
    os TEXT NOT NULL,
    encryption_status TEXT NOT NULL,
    vpn_client_version TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    compliance_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_devices_updated_at
BEFORE UPDATE ON devices
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE service_tickets (
    ticket_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    category TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_updated TIMESTAMPTZ NOT NULL,
    assigned_group TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_service_tickets_updated_at
BEFORE UPDATE ON service_tickets
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE iam_accounts (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    directory_account TEXT NOT NULL UNIQUE,
    account_status TEXT NOT NULL,
    mfa_enabled BOOLEAN NOT NULL,
    last_password_change DATE NOT NULL,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_iam_accounts_updated_at
BEFORE UPDATE ON iam_accounts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE vpn_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    vpn_status TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    last_successful_login TIMESTAMPTZ NOT NULL,
    certificate_status TEXT NOT NULL,
    device_compliance TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_vpn_profiles_updated_at
BEFORE UPDATE ON vpn_profiles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE action_requests (
    request_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    confirmation_status TEXT NOT NULL,
    execution_status TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    outcome_notes TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TRIGGER trg_action_requests_updated_at
BEFORE UPDATE ON action_requests
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE runbook_rules (
    rule_id TEXT PRIMARY KEY,
    workflow TEXT NOT NULL,
    required_verification TEXT NOT NULL,
    confirmation_required TEXT NOT NULL,
    destructive_action_block TEXT NOT NULL,
    sla_target_minutes INTEGER NOT NULL,
    policy_version TEXT NOT NULL,
    owner_team TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS case4.audit_logs (
    audit_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES case4.action_requests(request_id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL DEFAULT 'system',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT NOT NULL DEFAULT 'system',
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);


CREATE TRIGGER trg_runbook_rules_updated_at
BEFORE UPDATE ON runbook_rules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
