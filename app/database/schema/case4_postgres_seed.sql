-- Case 4: IT Service Desk Agentic Assist
-- Seed data only
SET search_path TO case4, public;

INSERT INTO users (user_id, employee_id, full_name, department, location, manager, email, status, identity_verification_level, created_at, created_by, updated_at, updated_by, is_active) VALUES
('U7001', 'E10231', 'Maya Patel', 'Finance', 'New York', 'R. Singh', 'maya.patel@company.example', 'Active', 'Standard', '2025-04-10 08:00:00+00', 'seed_loader', '2025-04-10 08:00:00+00', 'seed_loader', TRUE),
('U7002', 'E11892', 'Carlos Mendez', 'Operations', 'Dallas', 'J. Carter', 'carlos.mendez@company.example', 'Locked', 'Standard', '2025-04-10 08:07:00+00', 'seed_loader', '2025-04-10 08:09:00+00', 'seed_loader', TRUE),
('U7003', 'E12773', 'Alina Novak', 'Analytics', 'London', 'P. Shah', 'alina.novak@company.example', 'Active', 'High', '2025-04-10 08:14:00+00', 'seed_loader', '2025-04-10 08:18:00+00', 'seed_loader', TRUE),
('U7004', 'E13554', 'Noah Kim', 'Claims', 'Toronto', 'T. Wallace', 'noah.kim@company.example', 'VPN Suspended', 'Standard', '2025-04-10 08:21:00+00', 'seed_loader', '2025-04-10 08:27:00+00', 'seed_loader', TRUE),
('U7005', 'E14208', 'Priya Iyer', 'HR', 'Singapore', 'N. Das', 'priya.iyer@company.example', 'Active', 'Standard', '2025-04-10 08:28:00+00', 'seed_loader', '2025-04-10 08:36:00+00', 'seed_loader', TRUE),
('U7006', 'E15390', 'Ethan Brooks', 'IT Operations', 'Austin', 'M. Chen', 'ethan.brooks@company.example', 'Active', 'High', '2025-04-10 08:35:00+00', 'seed_loader', '2025-04-10 08:45:00+00', 'seed_loader', TRUE),
('U7007', 'E16421', 'Fatima Hassan', 'Finance', 'Dubai', 'S. Ali', 'fatima.hassan@company.example', 'Locked', 'Standard', '2025-04-10 08:42:00+00', 'seed_loader', '2025-04-10 08:54:00+00', 'seed_loader', TRUE),
('U7008', 'E17533', 'Lucas Meyer', 'Sales', 'Berlin', 'K. Vogel', 'lucas.meyer@company.example', 'Active', 'Standard', '2025-04-10 08:49:00+00', 'seed_loader', '2025-04-10 09:03:00+00', 'seed_loader', TRUE),
('U7009', 'E18644', 'Sofia Rossi', 'Marketing', 'Milan', 'G. Bianchi', 'sofia.rossi@company.example', 'Active', 'Standard', '2025-04-10 08:56:00+00', 'seed_loader', '2025-04-10 09:12:00+00', 'seed_loader', TRUE),
('U7010', 'E19755', 'Daniel Okafor', 'Support', 'Lagos', 'A. Adeyemi', 'daniel.okafor@company.example', 'VPN Suspended', 'Standard', '2025-04-10 09:03:00+00', 'seed_loader', '2025-04-10 09:21:00+00', 'seed_loader', TRUE),
('U7011', 'E20866', 'Hana Suzuki', 'Procurement', 'Tokyo', 'Y. Tanaka', 'hana.suzuki@company.example', 'Active', 'High', '2025-04-10 09:10:00+00', 'seed_loader', '2025-04-10 09:30:00+00', 'seed_loader', TRUE),
('U7012', 'E21977', 'Oliver Grant', 'Legal', 'Chicago', 'L. Johnson', 'oliver.grant@company.example', 'Active', 'Standard', '2025-04-10 09:17:00+00', 'seed_loader', '2025-04-10 09:39:00+00', 'seed_loader', TRUE);

INSERT INTO devices (device_id, user_id, device_name, device_type, os, encryption_status, vpn_client_version, last_seen, compliance_status, created_at, created_by, updated_at, updated_by, is_active) VALUES
('D9001', 'U7001', 'NY-FIN-WS01', 'Laptop', 'Windows 11', 'Encrypted', '5.8.2', '2025-04-10 08:20:00+00', 'Compliant', '2025-04-10 09:40:00+00', 'seed_loader', '2025-04-10 09:42:00+00', 'seed_loader', TRUE),
('D9002', 'U7002', 'DAL-OPS-WS02', 'Laptop', 'Windows 11', 'Encrypted', '5.8.2', '2025-04-10 07:45:00+00', 'Compliant', '2025-04-10 09:45:00+00', 'seed_loader', '2025-04-10 09:47:00+00', 'seed_loader', TRUE),
('D9003', 'U7003', 'LON-ANL-WS03', 'Laptop', 'macOS 14', 'Encrypted', '5.7.9', '2025-04-10 07:50:00+00', 'Compliant', '2025-04-10 09:50:00+00', 'seed_loader', '2025-04-10 09:52:00+00', 'seed_loader', TRUE),
('D9004', 'U7004', 'TOR-CLA-WS04', 'Laptop', 'Windows 10', 'Encrypted', '5.7.5', '2025-04-08 19:30:00+00', 'Non-Compliant', '2025-04-10 09:55:00+00', 'seed_loader', '2025-04-10 09:57:00+00', 'seed_loader', TRUE),
('D9005', 'U7005', 'SG-HR-WS05', 'Laptop', 'Windows 11', 'Encrypted', '5.8.1', '2025-04-10 09:10:00+00', 'Compliant', '2025-04-10 10:00:00+00', 'seed_loader', '2025-04-10 10:02:00+00', 'seed_loader', TRUE),
('D9006', 'U7006', 'AUS-IT-WS06', 'Laptop', 'Windows 11', 'Encrypted', '5.8.3', '2025-04-10 09:30:00+00', 'Compliant', '2025-04-10 10:05:00+00', 'seed_loader', '2025-04-10 10:07:00+00', 'seed_loader', TRUE),
('D9007', 'U7007', 'DXB-FIN-WS07', 'Laptop', 'Windows 10', 'Encrypted', '5.6.8', '2025-04-09 12:15:00+00', 'Compliant', '2025-04-10 10:10:00+00', 'seed_loader', '2025-04-10 10:12:00+00', 'seed_loader', TRUE),
('D9008', 'U7008', 'BER-SLS-WS08', 'Laptop', 'Windows 11', 'Encrypted', '5.8.0', '2025-04-10 06:40:00+00', 'Compliant', '2025-04-10 10:15:00+00', 'seed_loader', '2025-04-10 10:17:00+00', 'seed_loader', TRUE),
('D9009', 'U7009', 'MIL-MKT-WS09', 'Laptop', 'Windows 11', 'Encrypted', '5.8.2', '2025-04-10 10:05:00+00', 'Compliant', '2025-04-10 10:20:00+00', 'seed_loader', '2025-04-10 10:22:00+00', 'seed_loader', TRUE),
('D9010', 'U7010', 'LOS-SUP-WS10', 'Laptop', 'Windows 10', 'Encrypted', '5.7.2', '2025-04-08 18:10:00+00', 'Non-Compliant', '2025-04-10 10:25:00+00', 'seed_loader', '2025-04-10 10:27:00+00', 'seed_loader', TRUE),
('D9011', 'U7011', 'TKY-PRC-WS11', 'Laptop', 'Windows 11', 'Encrypted', '5.8.4', '2025-04-10 05:50:00+00', 'Compliant', '2025-04-10 10:30:00+00', 'seed_loader', '2025-04-10 10:32:00+00', 'seed_loader', TRUE),
('D9012', 'U7012', 'CHI-LEG-WS12', 'Laptop', 'Windows 11', 'Encrypted', '5.8.1', '2025-04-10 11:25:00+00', 'Compliant', '2025-04-10 10:35:00+00', 'seed_loader', '2025-04-10 10:37:00+00', 'seed_loader', TRUE);

INSERT INTO service_tickets (ticket_id, user_id, status, priority, category, created_at, last_updated, assigned_group, summary, created_by, updated_by, is_active) VALUES
('SD9001', 'U7002', 'New', 'High', 'Account Lockout', '2025-04-10 09:04:00+00', '2025-04-10 09:04:00+00', 'IAM Support', 'Workstation locked after too many failed attempts.', 'seed_loader', 'seed_loader', TRUE),
('SD9002', 'U7004', 'In Progress', 'High', 'VPN Access', '2025-04-10 07:50:00+00', '2025-04-10 08:15:00+00', 'Network Access', 'VPN access denied for user connecting from hotel network.', 'seed_loader', 'seed_loader', TRUE),
('SD9003', 'U7001', 'Resolved', 'Medium', 'Password Reset', '2025-04-08 15:12:00+00', '2025-04-08 15:30:00+00', 'IAM Support', 'Password reset request completed after identity verification.', 'seed_loader', 'seed_loader', TRUE),
('SD9004', 'U7005', 'New', 'Low', 'Password Reset', '2025-04-10 09:30:00+00', '2025-04-10 09:30:00+00', 'IAM Support', 'User requested password reset after expiration.', 'seed_loader', 'seed_loader', TRUE),
('SD9005', 'U7006', 'In Progress', 'Critical', 'VPN Access', '2025-04-10 09:45:00+00', '2025-04-10 10:05:00+00', 'Network Access', 'Executive user unable to connect to VPN during travel.', 'seed_loader', 'seed_loader', TRUE),
('SD9006', 'U7003', 'Resolved', 'Medium', 'Device Compliance', '2025-04-09 11:20:00+00', '2025-04-09 11:50:00+00', 'Endpoint Security', 'Device passed compliance review after policy update.', 'seed_loader', 'seed_loader', TRUE),
('SD9007', 'U7007', 'Escalated', 'High', 'Account Lockout', '2025-04-09 14:20:00+00', '2025-04-09 14:55:00+00', 'IAM Support', 'Repeated failed logins triggered lockout and escalation.', 'seed_loader', 'seed_loader', TRUE),
('SD9008', 'U7008', 'Pending Customer', 'Medium', 'Remote Access', '2025-04-10 08:35:00+00', '2025-04-10 08:35:00+00', 'Service Desk', 'Awaiting device compliance confirmation from user.', 'seed_loader', 'seed_loader', TRUE),
('SD9009', 'U7009', 'Resolved', 'Low', 'Password Reset', '2025-04-10 06:50:00+00', '2025-04-10 07:10:00+00', 'IAM Support', 'Password reset completed via standard workflow.', 'seed_loader', 'seed_loader', TRUE),
('SD9010', 'U7010', 'In Progress', 'High', 'VPN Access', '2025-04-08 18:25:00+00', '2025-04-08 19:00:00+00', 'Network Access', 'VPN suspended because certificate expired.', 'seed_loader', 'seed_loader', TRUE),
('SD9011', 'U7011', 'New', 'Medium', 'Identity Verification', '2025-04-10 10:15:00+00', '2025-04-10 10:15:00+00', 'Service Desk', 'High-assurance verification required for privileged access.', 'seed_loader', 'seed_loader', TRUE),
('SD9012', 'U7012', 'Resolved', 'Medium', 'Account Lockout', '2025-04-10 11:00:00+00', '2025-04-10 11:25:00+00', 'IAM Support', 'Account unlocked after manager verification.', 'seed_loader', 'seed_loader', TRUE);

INSERT INTO iam_accounts (user_id, directory_account, account_status, mfa_enabled, last_password_change, failed_login_count, locked_until, created_at, created_by, updated_at, updated_by, is_active) VALUES
('U7001', 'jpatel', 'Active', TRUE, '2025-03-22', 0, NULL, '2025-04-10 11:20:00+00', 'seed_loader', '2025-04-10 11:21:00+00', 'seed_loader', TRUE),
('U7002', 'cmendez', 'Locked', TRUE, '2025-03-28', 7, '2025-04-10 10:04:00+00', '2025-04-10 11:24:00+00', 'seed_loader', '2025-04-10 11:25:00+00', 'seed_loader', TRUE),
('U7003', 'anovak', 'Active', TRUE, '2025-03-30', 0, NULL, '2025-04-10 11:28:00+00', 'seed_loader', '2025-04-10 11:29:00+00', 'seed_loader', TRUE),
('U7004', 'nokim', 'Active', FALSE, '2025-03-15', 1, NULL, '2025-04-10 11:32:00+00', 'seed_loader', '2025-04-10 11:33:00+00', 'seed_loader', TRUE),
('U7005', 'piyer', 'Active', TRUE, '2025-04-01', 0, NULL, '2025-04-10 11:36:00+00', 'seed_loader', '2025-04-10 11:37:00+00', 'seed_loader', TRUE),
('U7006', 'ebrooks', 'Active', TRUE, '2025-03-25', 0, NULL, '2025-04-10 11:40:00+00', 'seed_loader', '2025-04-10 11:41:00+00', 'seed_loader', TRUE),
('U7007', 'fhassan', 'Locked', TRUE, '2025-03-20', 5, '2025-04-09 17:10:00+00', '2025-04-10 11:44:00+00', 'seed_loader', '2025-04-10 11:45:00+00', 'seed_loader', TRUE),
('U7008', 'lmeyer', 'Active', TRUE, '2025-03-18', 1, NULL, '2025-04-10 11:48:00+00', 'seed_loader', '2025-04-10 11:49:00+00', 'seed_loader', TRUE),
('U7009', 'srossi', 'Active', TRUE, '2025-04-02', 0, NULL, '2025-04-10 11:52:00+00', 'seed_loader', '2025-04-10 11:53:00+00', 'seed_loader', TRUE),
('U7010', 'dokafor', 'Active', FALSE, '2025-03-10', 2, NULL, '2025-04-10 11:56:00+00', 'seed_loader', '2025-04-10 11:57:00+00', 'seed_loader', TRUE),
('U7011', 'hsuzuki', 'Active', TRUE, '2025-04-03', 0, NULL, '2025-04-10 12:00:00+00', 'seed_loader', '2025-04-10 12:01:00+00', 'seed_loader', TRUE),
('U7012', 'ogrant', 'Active', TRUE, '2025-03-29', 0, NULL, '2025-04-10 12:04:00+00', 'seed_loader', '2025-04-10 12:05:00+00', 'seed_loader', TRUE);

INSERT INTO vpn_profiles (user_id, vpn_status, profile_name, last_successful_login, certificate_status, device_compliance, created_at, created_by, updated_at, updated_by, is_active) VALUES
('U7001', 'Enabled', 'Corp-Standard', '2025-04-10 08:05:00+00', 'Valid', 'Pass', '2025-04-10 13:00:00+00', 'seed_loader', '2025-04-10 13:01:00+00', 'seed_loader', TRUE),
('U7002', 'Enabled', 'Corp-Standard', '2025-04-09 17:20:00+00', 'Valid', 'Pass', '2025-04-10 13:04:00+00', 'seed_loader', '2025-04-10 13:05:00+00', 'seed_loader', TRUE),
('U7003', 'Enabled', 'Corp-Restricted', '2025-04-10 07:15:00+00', 'Valid', 'Pass', '2025-04-10 13:08:00+00', 'seed_loader', '2025-04-10 13:09:00+00', 'seed_loader', TRUE),
('U7004', 'Denied', 'Corp-Standard', '2025-04-08 19:30:00+00', 'Expired', 'Fail', '2025-04-10 13:12:00+00', 'seed_loader', '2025-04-10 13:13:00+00', 'seed_loader', TRUE),
('U7005', 'Enabled', 'Corp-Standard', '2025-04-10 09:00:00+00', 'Valid', 'Pass', '2025-04-10 13:16:00+00', 'seed_loader', '2025-04-10 13:17:00+00', 'seed_loader', TRUE),
('U7006', 'Enabled', 'Corp-Executive', '2025-04-10 09:20:00+00', 'Valid', 'Pass', '2025-04-10 13:20:00+00', 'seed_loader', '2025-04-10 13:21:00+00', 'seed_loader', TRUE),
('U7007', 'Denied', 'Corp-Standard', '2025-04-09 16:55:00+00', 'Valid', 'Pass', '2025-04-10 13:24:00+00', 'seed_loader', '2025-04-10 13:25:00+00', 'seed_loader', TRUE),
('U7008', 'Enabled', 'Corp-Standard', '2025-04-10 06:40:00+00', 'Valid', 'Pass', '2025-04-10 13:28:00+00', 'seed_loader', '2025-04-10 13:29:00+00', 'seed_loader', TRUE),
('U7009', 'Enabled', 'Corp-Standard', '2025-04-10 10:00:00+00', 'Valid', 'Pass', '2025-04-10 13:32:00+00', 'seed_loader', '2025-04-10 13:33:00+00', 'seed_loader', TRUE),
('U7010', 'Denied', 'Corp-Standard', '2025-04-08 18:10:00+00', 'Expired', 'Fail', '2025-04-10 13:36:00+00', 'seed_loader', '2025-04-10 13:37:00+00', 'seed_loader', TRUE),
('U7011', 'Enabled', 'Corp-Privileged', '2025-04-10 05:50:00+00', 'Valid', 'Pass', '2025-04-10 13:40:00+00', 'seed_loader', '2025-04-10 13:41:00+00', 'seed_loader', TRUE),
('U7012', 'Enabled', 'Corp-Standard', '2025-04-10 11:25:00+00', 'Valid', 'Pass', '2025-04-10 13:44:00+00', 'seed_loader', '2025-04-10 13:45:00+00', 'seed_loader', TRUE);

INSERT INTO action_requests (request_id, user_id, action_type, requested_at, confirmation_status, execution_status, evidence_ref, outcome_notes, created_at, created_by, updated_at, updated_by, is_active) VALUES
('AR1001', 'U7002', 'Unlock Account', '2025-04-10 09:10:00+00', 'Confirmed', 'Completed', 'RB1101', 'Unlocked after employee_id and manager verification.', '2025-04-10 14:40:00+00', 'seed_loader', '2025-04-10 14:41:00+00', 'seed_loader', TRUE),
('AR1002', 'U7004', 'VPN Re-enable', '2025-04-10 07:55:00+00', 'Confirmed', 'Blocked', 'RB1102', 'Blocked because device compliance failed.', '2025-04-10 14:46:00+00', 'seed_loader', '2025-04-10 14:47:00+00', 'seed_loader', TRUE),
('AR1003', 'U7001', 'Password Reset', '2025-04-08 15:15:00+00', 'Confirmed', 'Completed', 'RB1101', 'Reset completed after identity verification.', '2025-04-10 14:52:00+00', 'seed_loader', '2025-04-10 14:53:00+00', 'seed_loader', TRUE),
('AR1004', 'U7005', 'Password Reset', '2025-04-10 09:35:00+00', 'Confirmed', 'Completed', 'RB1101', 'Reset completed via standard process.', '2025-04-10 14:58:00+00', 'seed_loader', '2025-04-10 14:59:00+00', 'seed_loader', TRUE),
('AR1005', 'U7006', 'VPN Re-enable', '2025-04-10 09:50:00+00', 'Confirmed', 'Completed', 'RB1102', 'VPN re-enabled after executive approval.', '2025-04-10 15:04:00+00', 'seed_loader', '2025-04-10 15:05:00+00', 'seed_loader', TRUE),
('AR1006', 'U7007', 'Unlock Account', '2025-04-09 14:30:00+00', 'Pending', 'Blocked', 'RB1101', 'Verification incomplete, waiting for manager response.', '2025-04-10 15:10:00+00', 'seed_loader', '2025-04-10 15:11:00+00', 'seed_loader', TRUE),
('AR1007', 'U7008', 'Remote Access Review', '2025-04-10 08:40:00+00', 'Confirmed', 'Completed', 'RB1102', 'Remote access permitted after compliance confirmation.', '2025-04-10 15:16:00+00', 'seed_loader', '2025-04-10 15:17:00+00', 'seed_loader', TRUE),
('AR1008', 'U7009', 'Password Reset', '2025-04-10 06:55:00+00', 'Confirmed', 'Completed', 'RB1101', 'Standard reset completed.', '2025-04-10 15:22:00+00', 'seed_loader', '2025-04-10 15:23:00+00', 'seed_loader', TRUE),
('AR1009', 'U7010', 'VPN Re-enable', '2025-04-08 18:30:00+00', 'Confirmed', 'Blocked', 'RB1102', 'Blocked because certificate expired.', '2025-04-10 15:28:00+00', 'seed_loader', '2025-04-10 15:29:00+00', 'seed_loader', TRUE),
('AR1010', 'U7011', 'Identity Verification', '2025-04-10 10:20:00+00', 'Confirmed', 'Completed', 'RB1104', 'High-assurance verification passed.', '2025-04-10 15:34:00+00', 'seed_loader', '2025-04-10 15:35:00+00', 'seed_loader', TRUE),
('AR1011', 'U7012', 'Unlock Account', '2025-04-10 11:05:00+00', 'Confirmed', 'Completed', 'RB1101', 'Unlocked after manager verification.', '2025-04-10 15:40:00+00', 'seed_loader', '2025-04-10 15:41:00+00', 'seed_loader', TRUE),
('AR1012', 'U7003', 'Device Compliance Review', '2025-04-09 11:25:00+00', 'Confirmed', 'Completed', 'RB1103', 'Device review completed and recorded.', '2025-04-10 15:46:00+00', 'seed_loader', '2025-04-10 15:47:00+00', 'seed_loader', TRUE);

INSERT INTO runbook_rules (rule_id, workflow, required_verification, confirmation_required, destructive_action_block, sla_target_minutes, policy_version, owner_team, created_at, created_by, updated_at, updated_by, is_active) VALUES
('RB1101', 'Account Lockout', 'employee_id + manager_name', 'Yes', 'No password reset without confirmation', 15, 'v1.0', 'IAM Support', '2025-04-10 16:20:00+00', 'seed_loader', '2025-04-10 16:21:00+00', 'seed_loader', TRUE),
('RB1102', 'VPN Access', 'employee_id + device_name', 'Yes', 'No VPN enable if device compliance fails', 30, 'v1.0', 'Network Access', '2025-04-10 16:23:00+00', 'seed_loader', '2025-04-10 16:24:00+00', 'seed_loader', TRUE),
('RB1103', 'Device Compliance', 'employee_id + device compliance result', 'Yes', 'No access enable if device fails compliance', 20, 'v1.0', 'Endpoint Security', '2025-04-10 16:26:00+00', 'seed_loader', '2025-04-10 16:27:00+00', 'seed_loader', TRUE),
('RB1104', 'Identity Verification', 'employee_id + manager_name + email verification', 'Yes', 'No privileged action without high assurance', 25, 'v1.0', 'Service Desk', '2025-04-10 16:29:00+00', 'seed_loader', '2025-04-10 16:30:00+00', 'seed_loader', TRUE),
('RB1105', 'Password Reset', 'employee_id + email verification', 'Yes', 'No reset if identity verification incomplete', 15, 'v1.0', 'IAM Support', '2025-04-10 16:32:00+00', 'seed_loader', '2025-04-10 16:33:00+00', 'seed_loader', TRUE),
('RB1106', 'Remote Access', 'employee_id + vpn_profile + device_name', 'Yes', 'No remote access if profile denied', 30, 'v1.0', 'Network Access', '2025-04-10 16:35:00+00', 'seed_loader', '2025-04-10 16:36:00+00', 'seed_loader', TRUE),
('RB1107', 'Ticket Creation', 'employee_id + issue_category', 'No', 'No duplicate ticket if active ticket exists', 10, 'v1.0', 'Service Desk', '2025-04-10 16:38:00+00', 'seed_loader', '2025-04-10 16:39:00+00', 'seed_loader', TRUE),
('RB1108', 'Ticket Priority Assignment', 'category + impact + urgency', 'No', 'No priority escalation without matrix match', 10, 'v1.0', 'Service Desk', '2025-04-10 16:41:00+00', 'seed_loader', '2025-04-10 16:42:00+00', 'seed_loader', TRUE),
('RB1109', 'Escalation Routing', 'category + assigned_group', 'No', 'No escalation without routing rule', 20, 'v1.0', 'Service Desk', '2025-04-10 16:44:00+00', 'seed_loader', '2025-04-10 16:45:00+00', 'seed_loader', TRUE),
('RB1110', 'Audit Logging', 'request_id + user_id + action', 'No', 'No action without audit entry', 5, 'v1.0', 'Platform Operations', '2025-04-10 16:47:00+00', 'seed_loader', '2025-04-10 16:48:00+00', 'seed_loader', TRUE);
