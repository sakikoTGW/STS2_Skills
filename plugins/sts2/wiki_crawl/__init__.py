"""Crawl slaythespire.wiki.gg into bundled + user STS2 knowledge."""

from plugins.sts2.wiki_crawl.crawler import crawl_manifest, crawl_page
from plugins.sts2.wiki_crawl.integrate import integrate_all
from plugins.sts2.wiki_crawl.lookup import wiki_facts_for_state

__all__ = ["crawl_manifest", "crawl_page", "integrate_all", "wiki_facts_for_state"]
