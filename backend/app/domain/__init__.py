"""Pure domain rules: no session, no I/O, and no import from services, crud or api.

Shared by `app.crud` and `app.services`; `tests/test_layering.py` enforces the boundary.
"""
