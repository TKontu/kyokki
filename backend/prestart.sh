#! /usr/bin/env bash

# Let the DB start
sleep 10;
# Run migrations
python -m app.db.init_db