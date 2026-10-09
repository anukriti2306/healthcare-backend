-- Run this once as a PostgreSQL superuser (e.g. `postgres`) from psql or DBeaver.
-- It creates a dedicated role and database matching .env.example.
--
-- CREATEDB lets the role create the throw-away test database used by
-- `python manage.py test`.

CREATE ROLE healthcare_user WITH LOGIN PASSWORD 'healthcare_pass' CREATEDB;
CREATE DATABASE healthcare_db OWNER healthcare_user ENCODING 'UTF8';
