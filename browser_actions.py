"""Browser actions used only after the eye-operated review screen approves them."""
from urllib.parse import quote, urlencode, urljoin, urlparse
import webbrowser


class BrowserActions:
    def __init__(self, open_url=None, gmail_account_index=0):
        if not isinstance(gmail_account_index, int) or gmail_account_index < 0:
            raise ValueError("gmail_account_index must be a nonnegative integer (0 for the first account).")
        self.open_url = open_url or webbrowser.open
        self.gmail_account_index = gmail_account_index

    def _open(self, url, success):
        if not self.open_url(url):
            raise RuntimeError("The default browser did not open. Check its Windows settings.")
        return success

    def open_youtube(self):
        return self._open("https://www.youtube.com/", "Opened YouTube.")

    def search_youtube(self, query):
        url = "https://www.youtube.com/results?search_query=" + quote(query)
        return self._open(url, "Opened YouTube search results for: " + query)

    def play_youtube(self, query):
        """Find the first public search result; fall back to search if unavailable."""
        url = self.first_youtube_video(query)
        if url:
            return self._open(url, "Opened the first YouTube video for: " + query)
        return self.search_youtube(query) + " Select a result to play it."

    def first_youtube_video(self, query):
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto("https://www.youtube.com/results?search_query=" + quote(query),
                              wait_until="domcontentloaded", timeout=12000)
                    href = page.locator("ytd-video-renderer a#video-title").first.get_attribute(
                        "href", timeout=7000)
                finally:
                    browser.close()
            url = urljoin("https://www.youtube.com", href or "")
            parsed = urlparse(url)
            if parsed.hostname in ("www.youtube.com", "youtube.com") and parsed.path == "/watch":
                return url
        except Exception:
            # A missing browser binary, consent page or site change still leaves
            # a usable search link. Never claim the video played in that case.
            pass
        return None

    def open_google(self):
        return self._open("https://www.google.com/", "Opened Google.")

    def search_google(self, query):
        return self._open("https://www.google.com/search?q=" + quote(query),
                          "Opened Google search results for: " + query)

    def open_calendar(self):
        return self._open("https://calendar.google.com/", "Opened Google Calendar.")

    def open_gmail(self):
        return self._open(self.gmail_base(), "Opened Gmail in your browser.")

    def gmail_base(self):
        return f"https://mail.google.com/mail/u/{self.gmail_account_index}/"

    def compose_gmail(self, contact, draft):
        """Open a prefilled web compose; never invoke a Windows mailto handler."""
        params = urlencode({"view": "cm", "fs": "1", "to": contact.get("email", ""),
                            "su": draft["subject"], "body": draft["body"]})
        return self._open(self.gmail_base() + "?" + params,
                          "Opened Gmail compose in your browser. Check the message and choose Send in Gmail.")
