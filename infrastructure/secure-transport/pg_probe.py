"""Try one PostgreSQL login and report the outcome without secrets.

Usage: pg_probe.py USER PASSWORD DATABASE HOST PORT SSLMODE [CA_FILE]
SSLMODE "default" leaves libpq's default (prefer), like unchanged Django.
Prints "CONNECTED ssl=<bool> <protocol>" or "REFUSED: <server reason>".
"""

import sys

import psycopg

user, password, database, host, port, sslmode, *ca = sys.argv[1:]
options = {} if sslmode == "default" else {"sslmode": sslmode}
if ca:
    options["sslrootcert"] = ca[0]
try:
    with psycopg.connect(
        host=host, port=port, user=user, password=password, dbname=database, connect_timeout=5, **options
    ) as connection:
        ssl, version = connection.execute(
            "SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
        ).fetchone()
        print(f"CONNECTED ssl={ssl} {version}")
except psycopg.OperationalError as exc:
    message = str(exc).strip().splitlines()[-1]
    print("REFUSED:", message[message.find("FATAL"):] if "FATAL" in message else message[:160])
