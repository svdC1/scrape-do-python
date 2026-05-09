:::scrape_do.client
    options:
        members_order: source
        filters:
            - "!SyncSessionValidator"
            - "!SyncClientEventHooks"

:::scrape_do.client.SyncClientEventHooks
    options:
        separate_signature: true
        show_signature_annotations: true
        heading_level: 3

:::scrape_do.client.SyncSessionValidator
    options:
        separate_signature: true
        heading_level: 3
     