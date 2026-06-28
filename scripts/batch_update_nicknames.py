#!/usr/bin/env python3
import json
from pathlib import Path

# === ここにコピペで追加していく ===
FAN_DATA = {
    "4502": "エミちゃん",      # 遠藤エミ
    "4190": "マキちゃん",      # 長島万記
    "4885": "ちーちゃん",      # 大山千広
    "4482": "みほちゃん",      # 守屋美穂
    "4450": "ななちゃん",      # 平高奈菜
    "4804": "ひかるちゃん",    # 高田ひかる
    "4823": "ももちゃん",      # 中村桃佳
    "4530": "せいなちゃん",    # 小野生奈
    "4963": "みゆちゃん",      # 實森美祐
    "4964": "みなちゃん",      # 土屋南
    "4758": "れいかちゃん",    # 富樫麗加
    # ここに新しい行をコピペで追加（形式: "登録番号": "あだ名",）
}

def main():
    path = Path("docs/players/profile.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    
    updated = 0
    for toban, alias in FAN_DATA.items():
        if toban in data:
            current = data[toban].get("nickname", "")
            if current and alias not in current:
                data[toban]["nickname"] = f"{current}, {alias}"
            elif not current:
                data[toban]["nickname"] = alias
            print(f"✅ {toban} → {data[toban].get('nickname')}")
            updated += 1
        else:
            print(f"⚠️ {toban} はprofile.jsonに見つかりません")
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 {updated}選手更新完了！")

if __name__ == "__main__":
    main()
