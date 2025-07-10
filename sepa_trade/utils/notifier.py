"""
notifier.py

取引シグナルを SNS に自動投稿するユーティリティ。
現在サポート：
    - X (旧 Twitter) v2 API
    - Discord Webhook

環境変数
---------
# X (Twitter)
TWITTER_BEARER_TOKEN      : 読み書き用ベアラートークン
TWITTER_API_KEY           : API Key
TWITTER_API_SECRET        : API Secret
TWITTER_ACCESS_TOKEN      : Access Token
TWITTER_ACCESS_SECRET     : Access Secret

# Discord
DISCORD_WEBHOOK_URL       : Webhook URL
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import requests
import requests_oauthlib


@dataclass
class SignalMessage:
    symbol: str
    side: str            # "ENTRY" or "EXIT"
    price: float
    qty: int
    comment: Optional[str] = None


class SNSNotifier:
    """X / Discord へシグナル投稿"""

    def __init__(self) -> None:
        # X (Twitter) 認証情報
        self._tw_auth = None
        if os.getenv("TWITTER_API_KEY"):
            self._tw_auth = requests_oauthlib.OAuth1(
                os.getenv("TWITTER_API_KEY"),
                os.getenv("TWITTER_API_SECRET"),
                os.getenv("TWITTER_ACCESS_TOKEN"),
                os.getenv("TWITTER_ACCESS_SECRET"),
            )

        self.discord_url = os.getenv("DISCORD_WEBHOOK_URL")

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def post(self, msg: SignalMessage) -> None:
        """各 SNS へ投稿"""
        text = self._format_text(msg)

        if self._tw_auth:
            self._post_twitter(text)
        if self.discord_url:
            self._post_discord(text)

        if not self._tw_auth and not self.discord_url:
            print("⚠️  SNS 設定なし：以下のメッセージを投稿せず印刷")
            print(text)

    # ──────────────────────────────
    # 内部投稿メソッド
    # ──────────────────────────────
    def _format_text(self, msg: SignalMessage) -> str:
        base = f"{msg.side}: {msg.symbol} x{msg.qty} @{msg.price:.2f}"
        if msg.comment:
            base += f" | {msg.comment}"
        base += "  #SEPA"  # ハッシュタグ
        return base

    def _post_twitter(self, text: str) -> None:
        """X v2 API でツイート"""
        url = "https://api.twitter.com/2/tweets"
        payload = {"text": text}
        resp = requests.post(url, auth=self._tw_auth, json=payload, timeout=10)
        if resp.status_code >= 400:
            raise RuntimeError(f"Twitter post failed: {resp.text}")
        print("✅ Tweeted")

    def _post_discord(self, text: str) -> None:
        """Discord Webhook へ投稿"""
        resp = requests.post(
            self.discord_url,
            json={"content": text},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Discord post failed: {resp.text}")
        print("✅ Discord posted")
