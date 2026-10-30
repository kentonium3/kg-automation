"""Vikunja image-archive release route (kentonium3/kg-automation#1087).

Shared primitives for the STAGE and ACTIVATE deploy entrypoints, the ingress
helper and the rollback helper. Entrypoint logic lives in the entrypoints;
this package holds only pure or injectable building blocks. See
``core`` for the module-level caller map.
"""
