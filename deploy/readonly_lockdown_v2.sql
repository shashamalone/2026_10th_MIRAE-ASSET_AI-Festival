\set ON_ERROR_STOP on

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA meta,raw,enriched,relations,vec,core FROM agent_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA meta,raw,enriched,relations,vec,core FROM agent_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA meta,raw,enriched,relations,vec,core FROM agent_reader;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA meta,raw,enriched,relations,vec,core FROM agent_reader;

GRANT USAGE ON SCHEMA meta,raw,enriched,relations,vec,core TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA meta,raw,enriched,relations,vec,core TO agent_reader;
ALTER ROLE agent_reader SET default_transaction_read_only = on;
ALTER ROLE agent_reader SET statement_timeout = '2s';
