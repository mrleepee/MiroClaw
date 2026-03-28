"""Root test configuration.

Patches app.services.__init__ to prevent importing Zep-dependent modules
during local_graph tests. This allows the local_graph module to be tested
independently before the full Zep replacement is complete.
"""

import sys
import types

# Create a stub for app.services that doesn't import Zep-dependent modules
# This only affects test imports — production code uses the real __init__.py
_services_stub = types.ModuleType("app.services")
_services_stub.__path__ = []  # type: ignore[attr-defined]

# Only intercept if zep_cloud isn't installed
try:
    import zep_cloud  # noqa: F401
except ImportError:
    # Replace app.services with a stub that allows subpackage imports
    # but doesn't trigger the Zep-importing __init__.py
    if "app.services" not in sys.modules:
        # Ensure app package exists
        if "app" not in sys.modules:
            app_stub = types.ModuleType("app")
            app_stub.__path__ = []  # type: ignore[attr-defined]
            sys.modules["app"] = app_stub

        # Point app.services to the real path but skip __init__ imports
        import os
        services_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "app", "services"
        )
        _services_stub.__path__ = [services_path]  # type: ignore[attr-defined]
        sys.modules["app.services"] = _services_stub
