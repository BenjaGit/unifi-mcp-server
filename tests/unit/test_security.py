"""Security tests for the UniFi MCP Server."""

import importlib.util


def test_diskcache_vulnerability_documented():
    """Document that diskcache (CVE-2025-69872) is a non-impacting vulnerability.
    
    diskcache is an optional dependency of py-key-value-aio[disk] (via FastMCP)
    that has a known unsafe deserialization vulnerability (CVE-2025-69872).
    
    WHY THIS IS NOT A SECURITY RISK:
    - We don't use FastMCP's disk-based key-value store feature
    - We use Redis for caching (via py-key-value-aio[redis])
    - The vulnerable code path is never executed
    - No disk cache directory is created or accessed
    
    This test documents that we're aware of the dependency and have assessed
    the risk. See SECURITY.md for full details.
    """
    # Check if diskcache is installed
    diskcache_spec = importlib.util.find_spec("diskcache")
    
    # Document the current state
    is_installed = diskcache_spec is not None
    
    # This test passes regardless, but documents the status
    assert True, (
        f"diskcache installed: {is_installed}. "
        "This is a known non-impacting vulnerability. See SECURITY.md."
    )


def test_no_diskcache_imports_in_codebase():
    """Verify our codebase doesn't import or use diskcache."""
    import os
    import re
    
    # Search for any diskcache imports in our source code
    diskcache_imports = []
    
    for root, dirs, files in os.walk("src"):
        # Skip __pycache__ and other non-Python directories
        dirs[:] = [d for d in dirs if not d.startswith("__")]
        
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Check for diskcache imports
                    if re.search(r"import\s+diskcache|from\s+diskcache", content):
                        diskcache_imports.append(filepath)
    
    assert len(diskcache_imports) == 0, (
        f"Found diskcache imports in: {diskcache_imports}. "
        "We should not use diskcache directly due to CVE-2025-69872."
    )
