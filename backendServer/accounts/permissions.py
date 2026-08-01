"""Accounts-specific permission classes.

Isolation contract: accounts imports only from accounts/, backend/, and
rest_framework/django. Identity is a leaf app — other apps import FROM
accounts, accounts does not import from other feature apps (events,
ingestion, broadcast, ...).

No accounts-specific permission classes exist yet; this module is a
placeholder so the contract has a home.
"""
