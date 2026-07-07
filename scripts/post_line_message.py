#!/usr/bin/env python3
"""生成済みの締切一覧メッセージを LINE Messaging API で投稿する。

- 認証: 環境変数 LINE_CHANNEL_TOKEN（チャネルアクセストークン）。未設定なら何もせず終了
  （＝トークンを登録するまでワークフローは無害にスキップされる）。
- 宛先: LINE_TARGET_ID があれば push（グループ/ルーム/ユーザーID宛）。
        無ければ broadcast（公式アカウントの友だち全員宛）。
- 本文: docs/data/deadlines_tomorrow.txt。未生成・未取得プレースホルダなら投稿しない
  （空の告知を送らない）。

LINE Notify は 2025-03 で終了。本スクリプトは Messaging API を使う。
"""

import os
import sys
import json

import requests

MSG_PATH = os.path.join("docs", "data", "deadlines_tomorrow.txt")
PLACEHOLDER = "取得できていません"

PUSH_URL = "https://api.line.me/v2/bot/message/push"
BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def main():
    token = os.environ.get("LINE_CHANNEL_TOKEN", "").strip()
    if not token:
        print("LINE_CHANNEL_TOKEN 未設定のため投稿をスキップします。")
        return 0

    if not os.path.exists(MSG_PATH):
        print("メッセージファイルが無いためスキップ: {}".format(MSG_PATH))
        return 0
    with open(MSG_PATH, encoding="utf-8") as f:
        text = f.read().strip()
    if not text or PLACEHOLDER in text:
        print("出走表が未取得（プレースホルダ）のため投稿をスキップします。")
        return 0

    target = os.environ.get("LINE_TARGET_ID", "").strip()
    headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type": "application/json",
    }
    payload = {"messages": [{"type": "text", "text": text}]}
    if target:
        payload["to"] = target
        url = PUSH_URL
        mode = "push → {}".format(target)
    else:
        url = BROADCAST_URL
        mode = "broadcast（友だち全員）"

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
    if resp.status_code == 200:
        print("LINE投稿成功（{}）".format(mode))
        return 0
    # トークンやIDの誤りなどは本文に理由が出る（トークンは出力しない）
    print("LINE投稿失敗 status={} body={}".format(resp.status_code, resp.text[:500]),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
