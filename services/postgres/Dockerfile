FROM postgres:15

# Install Python for seed script
RUN apt-get update && apt-get install -y python3 python3-pip && \
    pip3 install --break-system-packages faker psycopg2-binary && \
    rm -rf /var/lib/apt/lists/*

COPY init/01-create-databases.sql /docker-entrypoint-initdb.d/01-create-databases.sql
COPY init/02-api-docs-schema.sql /docker-entrypoint-initdb.d/02-api-docs-schema.sql
COPY init/03-customers-schema.sql /docker-entrypoint-initdb.d/03-customers-schema.sql
COPY init/04-seed-customers.py /docker-entrypoint-initdb.d/04-seed-customers.py

# Make Python script executable via shell wrapper
RUN echo '#!/bin/bash\npython3 /docker-entrypoint-initdb.d/04-seed-customers.py' > /docker-entrypoint-initdb.d/04-seed-customers.sh && \
    chmod +x /docker-entrypoint-initdb.d/04-seed-customers.sh
