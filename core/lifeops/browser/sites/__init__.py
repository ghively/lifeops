"""Registered site adapters, keyed by the ``store`` value callers pass.

A store's key is also its browser profile directory name
(``RealBrowserWorker._open_context``), so adding an entry here is what makes
a store both automatable and isolated from every other one.
"""

from __future__ import annotations

from lifeops.browser.sites.amazon import AmazonSiteAdapter
from lifeops.browser.sites.base import SiteAdapter
from lifeops.browser.sites.instacart import InstacartSiteAdapter

SITE_ADAPTERS: dict[str, SiteAdapter] = {
    adapter.store: adapter
    for adapter in (AmazonSiteAdapter(), InstacartSiteAdapter())
}

__all__ = ["SITE_ADAPTERS", "AmazonSiteAdapter", "InstacartSiteAdapter", "SiteAdapter"]
