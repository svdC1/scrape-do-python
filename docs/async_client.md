:::scrape_do.async_client
    options:
        members_order: source
        filters:
            - "!AsyncSessionValidator"
            - "!AsyncClientEventHooks"

:::scrape_do.async_client.AsyncClientEventHooks
    options:
        separate_signature: true
        show_signature_annotations: true
        heading_level: 3

:::scrape_do.async_client.AsyncSessionValidator
    options:
        separate_signature: true
        heading_level: 3
     