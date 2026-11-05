-- Run once as the database owner. The API's public role (readonly_role.sql) must stay read-only, so
-- the account tables get their own login with just enough permission to sign people in and keep lists.
-- Use this role's connection string for the ACCOUNTS_HYPERDRIVE binding in api/wrangler.jsonc.
CREATE ROLE api_accounts LOGIN PASSWORD 'change-me';
GRANT USAGE ON SCHEMA public TO api_accounts;
GRANT SELECT, INSERT, UPDATE, DELETE ON users, sessions, user_preferences, saved_lists TO api_accounts;
