"""glossary.json のセルフ検証。

- JSONとして壊れていないか
- "_meta" と既存45語のキー・yomi・desc・alias(追記のみ許可)が変更前と一致するか
- 全エントリが {yomi(str), desc(str), alias(任意 list[str])} の形か
- desc に禁止語が含まれていないか
- キー重複・alias衝突がないか
"""
import json
import sys

GLOSSARY_PATH = "docs/data/kansenki/glossary.json"

ORIGINAL_META = {
    "purpose": "観戦記カードのglossaryTermsチップから引く用語辞書。事実定義のみ。予想・確率・煽り・射幸を促す表現は入れない。",
    "note": "yomi=ふりがな、desc=1〜2文の事実定義。記事に出た語＋基礎語＋場内用語に限定。無い語はチップtap無効（捏造しない）。",
}

ORIGINAL_ENTRIES = {
    "万舟": {"yomi": "まんしゅう", "desc": "3連単の払戻金が1万円以上になること。高配当の目安として使われる。"},
    "逃げ": {"yomi": "にげ", "desc": "1コースの艇がそのまま先頭で1マークを回り、1着になる決まり手。"},
    "差し": {"yomi": "さし", "desc": "先に回ろうとする艇の内側に入り込み、抜いて先行する決まり手。"},
    "まくり": {"yomi": "まくり", "desc": "外側の艇が外から回り込み、内の艇を一気に抜き去る決まり手。"},
    "まくり差し": {"yomi": "まくりざし", "desc": "まくりで外へ持ち出した先行艇のさらに内を差す、まくりと差しの複合的な決まり手。"},
    "抜き": {"yomi": "ぬき", "desc": "1マークでは先行できず、2マーク以降の周回で前の艇を抜いて1着になること。"},
    "最内差し": {"yomi": "さいうちさし", "desc": "1マークの最も内側（ブイぎわ）を突いて差す形。空いた最内を鋭く突く。"},
    "当地勝率": {"yomi": "とうちしょうりつ", "desc": "その選手が、その競走場だけで挙げた着順を点数化した勝率。場との相性の目安。"},
    "全国勝率": {"yomi": "ぜんこくしょうりつ", "desc": "全国すべての競走場での着順を点数化した勝率。選手の総合的な地力の目安。"},
    "2連率": {"yomi": "にれんりつ", "desc": "出走のうち1着か2着に入った割合（2連対率）。連に絡む安定度の目安。", "alias": ["当地2連率", "全国2連率", "節2連率", "今節2連率"]},
    "3連率": {"yomi": "さんれんりつ", "desc": "出走のうち3着までに入った割合（3連対率）。着に残る安定度の目安。", "alias": ["当地3連率", "全国3連率"]},
    "平均ST": {"yomi": "へいきんえすてぃー", "desc": "スタートのタイミングの平均値。スタートラインを0とし、数字が小さいほど速い踏み込み。", "alias": ["ST"]},
    "イン": {"yomi": "いん", "desc": "1コース（最も内側の進入位置）のこと。1マークまでの距離が最短で有利とされる。"},
    "カド": {"yomi": "かど", "desc": "スタート隊形で内側に固まった艇の一番外＝多くは4コース。まくりを仕掛けやすい位置。"},
    "コース": {"yomi": "こーす", "desc": "スタート時の進入位置（1〜6）。枠番と一致するとは限らず、進入で入れ替わることがある。"},
    "進入": {"yomi": "しんにゅう", "desc": "スタート前に各艇が取る並び順。枠なり以外に、前づけ等でコースが入れ替わることがある。"},
    "スタート隊形": {"yomi": "すたーとたいけい", "desc": "スタート時の6艇の並び方。内が詰まって外が張り出す形など、隊形で展開が変わる。"},
    "ピット": {"yomi": "ぴっと", "desc": "各艇が発走前に待機する係留場所。ここを出てから進入・スタートへ向かう。"},
    "ターンマーク": {"yomi": "たーんまーく", "desc": "水面に浮かぶ折り返しの目印。スタンド側の第1コーナーが1マーク、対岸が2マーク。"},
    "1マーク": {"yomi": "いちまーく", "desc": "スタンド側にある最初のターンマーク。最初の折り返しで、勝負の分かれ目になりやすい。"},
    "2マーク": {"yomi": "にまーく", "desc": "1マークの対岸にある2つ目のターンマーク。バックストレッチを挟んで折り返す。"},
    "ホームストレッチ": {"yomi": "ほーむすとれっち", "desc": "スタンド前の直線水面。スタートが切られ、各艇が最初に走り抜ける区間。"},
    "バックストレッチ": {"yomi": "ばっくすとれっち", "desc": "ホームの対岸にある直線水面。1マークと2マークをつなぐ区間。"},
    "スタートライン": {"yomi": "すたーとらいん", "desc": "大時計が0秒を指す瞬間に各艇が越えるべき仮想の線。早すぎるとフライングになる。"},
    "大時計": {"yomi": "おおどけい", "desc": "スタンド側に設置された発走用の時計。針が0を指す瞬間がスタートの基準になる。"},
    "出足": {"yomi": "であし", "desc": "低速からの加速の伸び。ターンの立ち上がりや握った時の反応に関わるモーターの気配。"},
    "伸び足": {"yomi": "のびあし", "desc": "直線での最高速の伸び。まくりや逃げ切りに関わるモーターの気配。"},
    "回り足": {"yomi": "まわりあし", "desc": "ターンでの安定感と旋回性能。差しやまくり差しのしやすさに関わる気配。"},
    "節": {"yomi": "せつ", "desc": "初日から最終日まで続く1開催のまとまり。多くは4〜6日間で行われる。"},
    "日目": {"yomi": "にちめ", "desc": "節の中の何日目か。初日・2日目…と進み、予選から準優・優勝戦へ移る。"},
    "予選": {"yomi": "よせん", "desc": "節の前半で行われるレース。ここでの得点で準優進出の順位が決まる。"},
    "準優": {"yomi": "じゅんゆう", "desc": "準優勝戦。予選上位の選手が集まり、勝ち上がると優勝戦に進める重要な一戦。"},
    "優出": {"yomi": "ゆうしゅつ", "desc": "優勝戦出場のこと。準優で規定の着に入り、最終日の優勝戦に進むこと。"},
    "予選ボーダー": {"yomi": "よせんぼーだー", "desc": "準優に進める順位の得点ライン。この得点率を上回れるかが予選終盤の焦点になる。"},
    "企画レース": {"yomi": "きかくれーす", "desc": "場が独自に組む番組。進入やメンバーを一定の型にした、その場の名物レースを指す。"},
    "F": {"yomi": "えふ（ふらいんぐ）", "desc": "フライング。スタートラインを早く越える発走事故。減点や斡旋停止など重いペナルティがつく。"},
    "L": {"yomi": "える（しゅっちょ）", "desc": "出遅れ。スタートで規定の時間内にラインへ届かない発走事故。ペナルティの対象になる。"},
    "モーター2連率": {"yomi": "もーたーにれんりつ", "desc": "そのモーターを使った出走のうち2着以内に入った割合。機力（エンジンの調子）の目安。"},
    "チルト": {"yomi": "ちると", "desc": "モーターの取り付け角度の調整。上げると伸び寄り、下げると出足寄りになる傾向がある。"},
    "ペラ": {"yomi": "ぺら", "desc": "プロペラのこと。選手が叩いて調整し、出足や伸びといった足の質を左右する。"},
    "イン先頭決着率": {"yomi": "いんせんとうけっちゃくりつ", "desc": "1コースが先頭で1マークを回って決着した割合。その場のインの強さを示す指標。", "alias": ["イン先頭決着"]},
    "荒れ率": {"yomi": "あれりつ", "desc": "このサイトで、3連単が一定配当以上になったレースの割合。水面の荒れやすさの目安。"},
    "E30": {"yomi": "いーさんまる", "desc": "エタノールを30%混ぜた燃料。導入場ではモーターの出方が変わる場合があるとされる。"},
    "節平均": {"yomi": "せつへいきん", "desc": "その節に出走しているモーターの2連率の平均値。個々の機力を平均と比べる基準に使う。"},
    "まくり率": {"yomi": "まくりりつ", "desc": "その選手の直近の1着のうち、まくりで勝った割合。前へ出て押し切る型かどうかの目安。"},
}

FORBIDDEN_WORDS = [
    "予想", "確率", "買い目", "的中", "回収", "有利", "おすすめ", "狙い目",
    "勝て", "儲か", "損", "危険", "必勝", "鉄板",
]


def fail(msg):
    print(f"NG: {msg}")
    sys.exit(1)


def main():
    with open(GLOSSARY_PATH, encoding="utf-8") as f:
        text = f.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        fail(f"JSONとして読み込めない: {e}")

    if data.get("_meta") != ORIGINAL_META:
        fail("_meta が変更前と一致しない")

    for key, orig in ORIGINAL_ENTRIES.items():
        if key not in data:
            fail(f"既存語が消えている: {key}")
        cur = data[key]
        if cur.get("yomi") != orig["yomi"]:
            fail(f"{key} の yomi が変更されている")
        if cur.get("desc") != orig["desc"]:
            fail(f"{key} の desc が変更されている")
        orig_alias = orig.get("alias")
        if orig_alias is not None:
            cur_alias = cur.get("alias") or []
            for a in orig_alias:
                if a not in cur_alias:
                    fail(f"{key} の alias から既存の '{a}' が消えている")

    all_keys = [k for k in data.keys() if k != "_meta"]
    if len(all_keys) != len(set(all_keys)):
        fail("キーが重複している")

    alias_owner = {}
    for key, entry in data.items():
        if key == "_meta":
            continue
        if not isinstance(entry, dict):
            fail(f"{key} のエントリが dict でない")
        yomi = entry.get("yomi")
        desc = entry.get("desc")
        if not isinstance(yomi, str) or not yomi:
            fail(f"{key} の yomi が str でない/空")
        if not isinstance(desc, str) or not desc:
            fail(f"{key} の desc が str でない/空")
        alias = entry.get("alias")
        if alias is not None:
            if not isinstance(alias, list) or not all(isinstance(a, str) for a in alias):
                fail(f"{key} の alias が list[str] でない")
            for a in alias:
                if a in all_keys:
                    fail(f"{key} の alias '{a}' が他のキーと衝突している")
                if a in alias_owner and alias_owner[a] != key:
                    fail(f"alias '{a}' が {alias_owner[a]} と {key} で重複している")
                alias_owner[a] = key
        if key not in ORIGINAL_ENTRIES:
            for word in FORBIDDEN_WORDS:
                if word in desc:
                    fail(f"{key} の desc に禁止語 '{word}' が含まれている")

    added = len(all_keys) - len(ORIGINAL_ENTRIES)
    print(f"OK: 全チェック通過。総語数={len(all_keys)}（既存{len(ORIGINAL_ENTRIES)} + 追加{added}）")


if __name__ == "__main__":
    main()
