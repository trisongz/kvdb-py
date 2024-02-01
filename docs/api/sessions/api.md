# KVDBSession

Sessions are the underlying object that contains the state of a single `KVDB` connection to a server. This session contains both asynchronous and synchronous methods for interacting with the server, as well as methods for managing the session itself.

The underlying connection pools are managed by the `KVDBClient` class, which is a singleton that manages all sessions. This allows you to create multiple sessions with different configurations, but still share the same underlying connection pool, unless there is any configuration differences that would require a new connection pool.

---

## API Reference

::: kvdb.components.session.KVDBSession
    rendering:
        show_root_heading: true
        show_source: true
        show_api_link: true
        show_inheritance: true
        show_inherited_methods: true
        show_inherited_attributes: true
        show_inherited_properties: true
        show_inherited_slots: true
        show_inherited_events: true
        show_inherited_class: true
        show_inherited_class_tree: true
        show_inherited_class_tree_link: true
        show_inherited_class_tree_root: true
