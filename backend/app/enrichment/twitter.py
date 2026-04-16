"""Twitter/X enrichment via twscrape.

Fetches a public profile and recent timeline without the official API.
twscrape uses Twitter's internal GraphQL endpoints; requires a burner
account (username + password, or cookie-based auth which is more stable).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from twscrape import API, gather


async def _build_api(username: str, password: str, cookies: str) -> API:
    """Bootstrap a twscrape API instance with a single pooled account.

    Uses a throwaway SQLite db in a temp dir so concurrent pipeline runs
    don't share state and there's no leftover file to clean up.
    """
    db_path = Path(tempfile.mkdtemp()) / "accounts.db"
    api = API(str(db_path))

    if cookies:
        cookie_dict: dict = json.loads(cookies)
        # twscrape accepts cookies as a dict directly
        await api.pool.add_account(
            username, password, email="", email_password="", cookies=cookie_dict
        )
    else:
        await api.pool.add_account(username, password, email="", email_password="")
        await api.pool.login_all()

    return api


async def enrich_twitter(
    handle: str,
    username: str,
    password: str,
    cookies: str,
    max_tweets: int = 20,
) -> dict:
    """Return a plain dict with profile info and recent tweets.

    On any failure (user not found, auth error, rate-limit) returns a dict
    with an ``error`` key so callers can handle it without exceptions.
    """
    try:
        api = await _build_api(username, password, cookies)
        user = await api.user_by_login(handle)
    except Exception as exc:
        return {"error": "api_error", "handle": handle, "detail": str(exc)}

    if user is None:
        return {"error": "user_not_found", "handle": handle}

    try:
        tweets_raw = await gather(api.user_tweets(user.id, limit=max_tweets))
    except Exception as exc:
        tweets_raw = []
        tweet_error = str(exc)
    else:
        tweet_error = None

    recent_tweets = [
        {
            "text": t.rawContent,
            "date": t.date.isoformat(),
            "likes": t.likeCount,
            "retweets": t.retweetCount,
            "reply_to": t.inReplyToTweetId,
        }
        for t in tweets_raw
    ]

    return {
        "handle": handle,
        "display_name": user.displayname,
        "bio": user.rawDescription,
        "location": user.location,
        "followers": user.followersCount,
        "following": user.friendsCount,
        "tweets_count": user.statusesCount,
        "created_at": user.created.isoformat() if user.created else None,
        "verified": getattr(user, "verified", False) or getattr(user, "blue", False),
        "protected": getattr(user, "protected", False),
        "profile_url": f"https://x.com/{handle}",
        "recent_tweets": recent_tweets,
        "tweet_fetch_error": tweet_error,
    }
