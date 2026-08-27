-- Connect to the customers database
\c customers;

-- Customers table: contains fake PII for exfiltration demo
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    ssn VARCHAR(11) NOT NULL,
    credit_card VARCHAR(19) NOT NULL,
    address TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
