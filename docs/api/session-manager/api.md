# KVDBClient

The `KVDBSessionManager` (accessed as `kvdb.KVDBClient`) class provides a context manager interface for managing sessions with the KVDB server. It keeps track and registration of all active sessions and provides a simple interface for managing session operations. It inherits from a `ProxyObject` Singleton to lazily initialize and prevent multiple instances of the session manager.

---

## API Reference

::: kvdb.client.KVDBSessionManager
    options:
        filters: ["!c", "!ctx", "!logger"]
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

        