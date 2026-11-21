"""Real-PostgreSQL checks for the processing database role models.

Uses the test server's administrator from PROCESSING_DB_* (scripts/check.py
service/docker modes). Skipped unless that login is a superuser. Every object
is uniquely named and dropped afterwards.
"""

import os
import sys
from pathlib import Path
from unittest import mock
from uuid import uuid4

import psycopg
from psycopg import errors, sql
from django.test import SimpleTestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import provision_database  # noqa: E402


def admin_options():
    return {
        "host": os.environ.get("PROCESSING_DB_HOST", "127.0.0.1"),
        "port": os.environ.get("PROCESSING_DB_PORT", "5432"),
        "user": os.environ.get("PROCESSING_DB_USER", ""),
        "password": os.environ.get("PROCESSING_DB_PASSWORD", ""),
        "connect_timeout": 5,
        "autocommit": True,
    }


class ProvisionDatabaseTests(SimpleTestCase):
    databases = set()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            with psycopg.connect(dbname="postgres", **admin_options()) as connection:
                superuser = connection.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]
        except psycopg.Error:
            superuser = False
        if not superuser:
            raise cls.skipException("Requires a disposable PostgreSQL superuser in PROCESSING_DB_*.")

    def setUp(self):
        prefix = f"sf_prov_{uuid4().hex[:10]}"
        self.database = prefix
        self.runtime, self.migrator, self.owner = f"{prefix}_rt", f"{prefix}_mg", f"{prefix}_ow"
        self.passwords = {self.runtime: uuid4().hex, self.migrator: uuid4().hex}
        self.addCleanup(self.drop_objects)

    def drop_objects(self):
        with psycopg.connect(dbname="postgres", **admin_options()) as connection:
            connection.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(self.database)))
            for role in (self.runtime, self.migrator, self.owner):
                connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))

    def provision(self, *, split=True):
        options = admin_options()
        env = {
            "PROCESSING_DB_NAME": self.database,
            "PROCESSING_DB_USER": self.runtime,
            "PROCESSING_DB_PASSWORD": self.passwords[self.runtime],
            "PROCESSING_DB_ADMIN_USER": options["user"],
            "PROCESSING_DB_ADMIN_PASSWORD": options["password"],
            "PROCESSING_APPLICATION_DB": "studyforge",
            "PROCESSING_DB_HOST": options["host"],
            "PROCESSING_DB_PORT": options["port"],
            "PROCESSING_DB_MIGRATOR": self.migrator if split else "",
            "PROCESSING_DB_MIGRATOR_PASSWORD": self.passwords[self.migrator] if split else "",
            "PROCESSING_DB_OWNER": self.owner,
        }
        with mock.patch.dict(os.environ, env), mock.patch("builtins.print"):
            provision_database.provision()

    def connect(self, role, **extra):
        options = {**admin_options(), "user": role, "password": self.passwords[role], **extra}
        return psycopg.connect(dbname=self.database, **options)

    def migrate_as_owner(self):
        # Same mechanism the migration job uses: PGOPTIONS="-c role=<owner>".
        with self.connect(self.migrator, options=f"-c role={self.owner}") as connection:
            connection.execute("CREATE TABLE execution_probe (id bigserial PRIMARY KEY, status text NOT NULL)")

    def test_split_roles_are_least_privilege(self):
        self.provision()
        self.migrate_as_owner()

        with psycopg.connect(dbname=self.database, **admin_options()) as connection:
            attributes = dict(connection.execute(
                "SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname = ANY(%s)",
                ([self.runtime, self.migrator, self.owner],),
            ).fetchall())
            table_owner = connection.execute(
                "SELECT tableowner FROM pg_tables WHERE tablename = 'execution_probe'"
            ).fetchone()[0]
            database_owner = connection.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
            ).fetchone()[0]
        self.assertEqual(attributes, {self.runtime: True, self.migrator: True, self.owner: False})
        self.assertEqual((table_owner, database_owner), (self.owner, self.owner))

        with self.connect(self.runtime) as connection:
            connection.execute("INSERT INTO execution_probe (status) VALUES ('RUNNING')")
            connection.execute("UPDATE execution_probe SET status = 'SUCCEEDED'")
            self.assertEqual(connection.execute("SELECT status FROM execution_probe").fetchone()[0], "SUCCEEDED")
            for statement in (
                "DELETE FROM execution_probe",
                "TRUNCATE execution_probe",
                "DROP TABLE execution_probe",
                "ALTER TABLE execution_probe ADD COLUMN x int",
                "CREATE TABLE runtime_table (id int)",
                f"SET ROLE {self.owner}",
            ):
                with self.subTest(runtime=statement), self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute(statement)

        with self.connect(self.migrator) as connection:
            # Without SET ROLE the migrator inherits nothing from the owner.
            for statement in ("CREATE TABLE migrator_table (id int)", "SELECT 1 FROM execution_probe"):
                with self.subTest(migrator=statement), self.assertRaises(errors.InsufficientPrivilege):
                    connection.execute(statement)

    def test_rerun_rotates_passwords_and_keeps_grants(self):
        self.provision()
        self.migrate_as_owner()
        self.passwords = {role: uuid4().hex for role in self.passwords}
        self.provision()
        with self.connect(self.runtime) as connection:
            connection.execute("INSERT INTO execution_probe (status) VALUES ('RUNNING')")
        with self.connect(self.migrator, options=f"-c role={self.owner}") as connection:
            connection.execute("ALTER TABLE execution_probe ADD COLUMN note text")

    def test_refuses_unmarked_existing_role(self):
        with psycopg.connect(dbname="postgres", **admin_options()) as connection:
            connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(self.owner)))
        with self.assertRaisesMessage(ValueError, "Refusing to reuse"):
            self.provision()

    def test_split_requires_distinct_roles(self):
        self.migrator = self.runtime
        with self.assertRaisesMessage(ValueError, "must be different"):
            self.provision()

    def test_single_owner_mode_is_unchanged(self):
        self.provision(split=False)
        with self.connect(self.runtime) as connection:
            connection.execute("CREATE TABLE single_owner_probe (id int)")
            owner = connection.execute(
                "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()"
            ).fetchone()[0]
        self.assertEqual(owner, self.runtime)
