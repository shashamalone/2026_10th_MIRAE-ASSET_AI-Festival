\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    base_name text;
    bases text[] := ARRAY['meta','raw','enriched','relations','vec','core'];
BEGIN
    FOREACH base_name IN ARRAY bases LOOP
        IF to_regnamespace(base_name || '_prev') IS NULL THEN
            RAISE EXCEPTION 'rollback schema missing: %_prev', base_name;
        END IF;
        IF to_regnamespace(base_name || '_failed') IS NOT NULL THEN
            RAISE EXCEPTION 'previous failed schema is preserved: %_failed', base_name;
        END IF;
    END LOOP;
    FOREACH base_name IN ARRAY bases LOOP
        IF to_regnamespace(base_name) IS NOT NULL THEN
            EXECUTE format('ALTER SCHEMA %I RENAME TO %I', base_name, base_name || '_failed');
        END IF;
        EXECUTE format('ALTER SCHEMA %I RENAME TO %I', base_name || '_prev', base_name);
    END LOOP;
END
$$;
COMMIT;
