:::scrape_do.proxy_client
    options:
        members_order: source
        filters:
            - "!SyncSessionValidator"
            - "!SyncClientEventHooks"
