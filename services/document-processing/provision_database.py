"""Explicit, repeatable setup of the service database on an existing server.

Only the one-shot provisioning container receives administrator credentials.
Existing databases/roles are reused only if marked as managed by this script.

Two role models are supported:

* Single owner (default): PROCESSING_DB_USER logs in and owns the database.
* Least-privilege split (set PROCESSING_DB_MIGRATOR and
  PROCESSING_DB_MIGRATOR_PASSWORD): a NOLOGIN owner (PROCESSING_DB_OWNER,
  default ``<database>_owner``) owns the database and its tables; the migrator
  logs in and must ``SET ROLE`` to the owner to run migrations (for example
  ``PGOPTIONS="-c role=<owner>"``); PROCESSING_DB_USER is the runtime login
  with only CONNECT, schema USAGE, table SELECT/INSERT/UPDATE and sequence
  USAGE/SELECT.
"""

import os
import re
import sys

import psycopg
from psycopg import sql

MARKER = "studyforge-document-processing-foundation"
ROLE_ATTRIBUTES = sql.SQL("NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT")


def required(name):
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Missing {name}.")
    return value


def check_identifier(name):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) or name.startswith("pg_"):
        raise ValueError("Processing database/role names must be simple lowercase PostgreSQL identifiers.")


def existing_role(connection, name, *, can_login, member_of=()):
    """Return True if a managed role exists; refuse anything unexpected."""
    row = connection.execute(
        "SELECT shobj_description(r.oid, 'pg_authid'), rolsuper, rolcreatedb, "
        "rolcreaterole, rolreplication, rolbypassrls, rolcanlogin, "
        "ARRAY(SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
        "WHERE m.member = r.oid ORDER BY g.rolname) "
        "FROM pg_roles r WHERE rolname = %s", (name,),
    ).fetchone()
    if row is None:
        return False
    if row[:7] != (MARKER, False, False, False, False, False, can_login) or row[7] not in ([], sorted(member_of)):
        raise ValueError("Refusing to reuse an unmarked, privileged, or role-member account.")
    return True


def create_role(connection, name, *, login):
    connection.execute(sql.SQL("CREATE ROLE {} {} {}").format(
        sql.Identifier(name), sql.SQL("LOGIN" if login else "NOLOGIN"), ROLE_ATTRIBUTES,
    ))
    connection.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(sql.Identifier(name), sql.Literal(MARKER)))


def set_password(connection, name, password):
    # Reruns can explicitly rotate a managed role's password.
    connection.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(name), sql.Literal(password)))


def provision():
    database = required("PROCESSING_DB_NAME")
    role = required("PROCESSING_DB_USER")
    password = required("PROCESSING_DB_PASSWORD")
    admin = required("PROCESSING_DB_ADMIN_USER")
    application_db = required("PROCESSING_APPLICATION_DB")
    migrator = os.environ.get("PROCESSING_DB_MIGRATOR", "")
    split = bool(migrator)
    owner = os.environ.get("PROCESSING_DB_OWNER", f"{database}_owner") if split else role
    migrator_password = required("PROCESSING_DB_MIGRATOR_PASSWORD") if split else ""
    roles = (role, owner, migrator) if split else (role,)
    for name in (database, *roles):
        check_identifier(name)
    if database in {application_db, "postgres", "template0", "template1"} or admin in roles:
        raise ValueError("Processing must use a separate database and role.")
    if len(set(roles)) != len(roles):
        raise ValueError("Processing owner, migrator and runtime roles must be different.")

    connection_options = {
        "host": required("PROCESSING_DB_HOST"),
        "port": os.environ.get("PROCESSING_DB_PORT", "5432"),
        "user": admin,
        "password": required("PROCESSING_DB_ADMIN_PASSWORD"),
        "connect_timeout": 5,
        "autocommit": True,
    }
    if os.environ.get("PROCESSING_DB_SSLMODE"):
        connection_options["sslmode"] = os.environ["PROCESSING_DB_SSLMODE"]
    if os.environ.get("PROCESSING_DB_SSLROOTCERT"):
        connection_options["sslrootcert"] = os.environ["PROCESSING_DB_SSLROOTCERT"]
    with psycopg.connect(dbname="postgres", **connection_options) as connection:
        existing_db = connection.execute(
            "SELECT pg_get_userbyid(datdba), shobj_description(oid, 'pg_database') "
            "FROM pg_database WHERE datname = %s", (database,),
        ).fetchone()
        if existing_db and existing_db != (owner, MARKER):
            raise ValueError("Refusing to modify an existing database not owned and marked by this setup.")

        with connection.transaction():
            if split:
                if not existing_role(connection, owner, can_login=False):
                    create_role(connection, owner, login=False)
                if not existing_role(connection, migrator, can_login=True, member_of=(owner,)):
                    create_role(connection, migrator, login=True)
                if not existing_role(connection, role, can_login=True):
                    create_role(connection, role, login=True)
                # The migrator must SET ROLE explicitly; it never inherits ownership.
                connection.execute(sql.SQL("GRANT {} TO {} WITH INHERIT FALSE, SET TRUE").format(
                    sql.Identifier(owner), sql.Identifier(migrator),
                ))
                set_password(connection, migrator, migrator_password)
            elif not existing_role(connection, role, can_login=True):
                create_role(connection, role, login=True)
            set_password(connection, role, password)
        if not existing_db:
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(owner),
            ))
            connection.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(database), sql.Literal(MARKER),
            ))
        connection.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
        if split:
            connection.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                sql.Identifier(database), sql.Identifier(migrator), sql.Identifier(role),
            ))

    with psycopg.connect(dbname=database, **connection_options) as connection:
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        if split:
            grants = {
                "owner": sql.Identifier(owner),
                "runtime": sql.Identifier(role),
            }
            for statement in (
                "GRANT USAGE ON SCHEMA public TO {runtime}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE ON TABLES TO {runtime}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public "
                "GRANT USAGE, SELECT ON SEQUENCES TO {runtime}",
                # Reruns after migrations also cover tables that already exist.
                "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {runtime}",
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {runtime}",
            ):
                connection.execute(sql.SQL(statement).format(**grants))
    print("Processing database and restricted role" + ("s are" if split else " are") + " ready.")


if __name__ == "__main__":
    try:
        provision()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except psycopg.Error:
        # Do not expose SQL containing credentials or connection details.
        print("Processing database setup failed; check administrator access and server availability.", file=sys.stderr)
        raise SystemExit(1)
