\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    base_name text;
    bases text[] := ARRAY['meta','raw','enriched','relations','vec','core'];
BEGIN
    FOREACH base_name IN ARRAY bases LOOP
        IF to_regnamespace(base_name || '_next') IS NULL THEN
            RAISE EXCEPTION 'required stage schema missing: %_next', base_name;
        END IF;
        IF to_regnamespace(base_name || '_prev') IS NOT NULL THEN
            RAISE EXCEPTION 'preserved rollback schema already exists: %_prev', base_name;
        END IF;
    END LOOP;
    FOREACH base_name IN ARRAY bases LOOP
        IF to_regnamespace(base_name) IS NOT NULL THEN
            EXECUTE format('ALTER SCHEMA %I RENAME TO %I', base_name, base_name || '_prev');
        END IF;
        EXECUTE format('ALTER SCHEMA %I RENAME TO %I', base_name || '_next', base_name);
    END LOOP;
END
$$;
COMMIT;
