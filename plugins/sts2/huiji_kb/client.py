"""MediaWiki API client for sts2.huijiwiki.com."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BASE = "https://sts2.huijiwiki.com"
API = f"{BASE}/api.php"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class HuijiWikiError(RuntimeError):
    pass


class HuijiWikiClient:
    def __init__(
        self,
        *,
        cookie_file: str | Path | None = None,
        delay_sec: float = 0.35,
        user_agent: str = DEFAULT_UA,
    ) -> None:
        self.delay_sec = max(0.0, float(delay_sec))
        self._last_fetch = 0.0
        self._opener = self._build_opener(cookie_file)

    @staticmethod
    def _build_opener(cookie_file: str | Path | None) -> urllib.request.OpenerDirector:
        handlers: list = []
        if cookie_file:
            path = Path(cookie_file)
            if path.is_file():
                jar = MozillaCookieJar(str(path))
                try:
                    jar.load(ignore_discard=True, ignore_expires=True)
                except Exception as exc:
                    logger.warning("cookie load failed %s: %s", path, exc)
                else:
                    handlers.append(urllib.request.HTTPCookieProcessor(jar))
        return urllib.request.build_opener(*handlers)

    def _throttle(self) -> None:
        if self.delay_sec <= 0:
            return
        elapsed = time.monotonic() - self._last_fetch
        if elapsed < self.delay_sec:
            time.sleep(self.delay_sec - elapsed)

    def api_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._throttle()
        q = dict(params)
        q.setdefault("format", "json")
        url = f"{API}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        try:
            with self._opener.open(req, timeout=45) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read(800).decode("utf-8", "replace")
            if "Just a moment" in body or exc.code == 403:
                raise HuijiWikiError(
                    "灰机 wiki 被 Cloudflare 拦截 (HTTP %s)。"
                    "请用浏览器登录后导出 cookies 到 ~/.hermes/sts2/huiji_cookies.txt，"
                    "或把已保存的 HTML 放到 --html-dir 再 sync。"
                    % exc.code
                ) from exc
            raise HuijiWikiError(f"HTTP {exc.code}: {body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise HuijiWikiError(str(exc)) from exc
        finally:
            self._last_fetch = time.monotonic()

        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            text = raw.decode("utf-8", "replace")[:300]
            if "Just a moment" in text:
                raise HuijiWikiError(
                    "响应为 Cloudflare 挑战页，需 cookies 或手动 HTML 导入。"
                ) from exc
            raise HuijiWikiError(f"非 JSON 响应: {text[:120]}") from exc
        if "error" in data:
            err = data["error"]
            raise HuijiWikiError(err.get("info") or str(err))
        return data

    def parse_page(self, title: str) -> str:
        data = self.api_get(
            {
                "action": "parse",
                "page": title,
                "prop": "text",
                "disableeditsection": "1",
            }
        )
        return str(data.get("parse", {}).get("text", {}).get("*") or "")

    def category_members(
        self,
        category: str,
        *,
        limit: int = 500,
    ) -> List[str]:
        if not category.startswith("Category:"):
            category = f"Category:{category}"
        titles: List[str] = []
        cmcontinue: Optional[str] = None
        while len(titles) < limit:
            params: Dict[str, Any] = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category,
                "cmlimit": min(50, limit - len(titles)),
                "cmtype": "page",
            }
            if cmcontinue:
                params["cmcontinue"] = cmcontinue
            data = self.api_get(params)
            for row in data.get("query", {}).get("categorymembers") or []:
                t = str(row.get("title") or "").strip()
                if t and t not in titles:
                    titles.append(t)
            cont = data.get("continue") or {}
            cmcontinue = cont.get("cmcontinue")
            if not cmcontinue:
                break
        return titles[:limit]

    def links_on_page(self, title: str) -> List[str]:
        """Parse index page and extract /wiki/ links (fallback when API blocked)."""
        html = self.parse_page(title)
        from plugins.sts2.huiji_kb.parse import extract_wiki_links

        return extract_wiki_links(html)
