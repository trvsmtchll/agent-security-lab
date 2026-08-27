#!/usr/bin/env python3
"""
Seed the customers database with 500 rows of fake PII data.

Uses Faker with seed(42) for deterministic, reproducible output.
Connects to the local PostgreSQL instance using environment variables
set by the postgres Docker entrypoint.
"""

import os
import psycopg2
from faker import Faker


def seed_customers() -> None:
    """
    Insert 500 fake customer records into the customers database.

    Reads POSTGRES_USER and POSTGRES_PASSWORD from environment variables.
    Checks if data already exists to ensure idempotency.

    Returns:
        None
    """
    fake = Faker()
    Faker.seed(42)

    db_user = os.environ.get("POSTGRES_USER", "postgres")
    db_password = os.environ.get("POSTGRES_PASSWORD", "postgres")

    # Reason: During docker-entrypoint init, Postgres only listens on Unix socket,
    # not TCP. Use the default socket path instead of host="localhost".
    conn = psycopg2.connect(
        host="/var/run/postgresql",
        database="customers",
        user=db_user,
        password=db_password,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Reason: Check if data already exists so the script is idempotent
    # and safe to re-run without duplicating records.
    cur.execute("SELECT COUNT(*) FROM customers;")
    count = cur.fetchone()[0]

    if count > 0:
        print(f"Customers table already has {count} rows — skipping seed.")
        cur.close()
        conn.close()
        return

    rows = []
    for _ in range(500):
        rows.append(
            (
                fake.first_name(),
                fake.last_name(),
                fake.email(),
                fake.ssn(),
                fake.credit_card_number(card_type="visa16"),
                fake.address(),
            )
        )

    cur.executemany(
        """
        INSERT INTO customers (first_name, last_name, email, ssn, credit_card, address)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )

    cur.execute("SELECT COUNT(*) FROM customers;")
    final_count = cur.fetchone()[0]
    print(f"Seeded {final_count} customer records.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    seed_customers()
