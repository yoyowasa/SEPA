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

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

import requests
import requests_oauthlib

# ロガーの設定
logger = logging.getLogger(__name__)

# 定数
TWITTER_API_URL = "https://api.twitter.com/2/tweets"
REQUEST_TIMEOUT = 10


@dataclass
class SignalMessage:
    symbol: str
    side: Literal["ENTRY", "EXIT"]
    price: float
    qty: int
    comment: Optional[str] = None


class SNSNotifier:
    """X / Discord へシグナル投稿"""

    def __init__(self) -> None:
        # X (Twitter) 認証情報
        self._tw_auth = None
        api_key = os.getenv("TWITTER_API_KEY")
        api_secret = os.getenv("TWITTER_API_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_secret = os.getenv("TWITTER_ACCESS_SECRET")

        if all((api_key, api_secret, access_token, access_secret)):
            self._tw_auth = requests_oauthlib.OAuth1(
                api_key,
                api_secret,
                access_token,
                access_secret,
            )

        self.discord_url = os.getenv("DISCORD_WEBHOOK_URL")

    # ──────────────────────────────
    # 公開 API
    # ──────────────────────────────
    def post(self, msg: SignalMessage) -> None:
        """各 SNS へ投稿"""
        text = self._format_text(msg)

        posted_successfully = False
        if self._tw_auth:
            try:
                self._post_twitter(text)
                posted_successfully = True
            except RuntimeError as e:
                logger.error("Twitterへの投稿に失敗しました: %s", e)

        if self.discord_url:
            try:
                self._post_discord(text)
                posted_successfully = True
            except RuntimeError as e:
                logger.error("Discordへの投稿に失敗しました: %s", e)

        if not posted_successfully:
            logger.warning("⚠️  SNSへの投稿がありませんでした。コンソールに出力します:\n%s", text)

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
        payload = {"text": text}
        resp = requests.post(
            TWITTER_API_URL, auth=self._tw_auth, json=payload, timeout=REQUEST_TIMEOUT
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Twitter post failed: {resp.text}")
        logger.info("✅ Tweeted: %s", text)

    def _post_discord(self, text: str) -> None:
        """Discord Webhook へ投稿"""
        resp = requests.post(
            self.discord_url,
            json={"content": text},
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Discord post failed: {resp.text}")
        logger.info("✅ Discord posted: %s", text)
