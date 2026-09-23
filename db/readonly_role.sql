-- Run once as the database owner. Replace the password, then use this role's connection string for
-- the API (Hyperdrive), so a leaked API secret cannot change any data.
CREATE ROLE api_reader LOGIN PASSWORD 'change-me';
GRANT USAGE ON SCHEMA public TO api_reader;
GRANT SELECT ON snapshots TO api_reader;
