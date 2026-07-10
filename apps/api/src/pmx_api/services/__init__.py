"""Domain services — the pure(-ish) logic layer between routers and models.

Kept deliberately thin: services own transactions and orchestration; routers
own HTTP shapes and auth; models own persistence. Services never import from
routers.
"""
