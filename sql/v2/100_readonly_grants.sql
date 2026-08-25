\set ON_ERROR_STOP on
-- agent_reader LOGIN 역할과 비밀번호는 운영자가 secret store/대화형 createuser로 만든다.
-- 이 파일은 비밀번호를 받거나 기록하지 않는다.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO agent_reader', current_database());
END
$$;
GRANT USAGE ON SCHEMA meta,raw,enriched,relations,vec,core TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA meta,raw,enriched,relations,vec,core TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA enriched GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA relations GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA vec GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT SELECT ON TABLES TO agent_reader;
ALTER ROLE agent_reader SET default_transaction_read_only = on;
ALTER ROLE agent_reader SET statement_timeout = '10s';
