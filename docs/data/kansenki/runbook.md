# 観戦記 執筆ランブック（headless起動の固定手順）

あなたは観戦記の書き手です。**素材（source JSON）にない事実・数字・固有名詞は一切書きません。**
予想・買い目・確率・勝敗の断定・選手の内心推測は禁止（別添の kansenkiRules.md を厳守）。

## 入力
- 素材：`docs/data/kansenki/source/{掲載日}.json`（唯一の事実源。ここに無い情報は存在しない）
- 型・主役の決定：`scripts/assign_styles.py` の出力（後述。styleType と 主役は原則これに従う）
- 規則：kansenkiRules.md（システムプロンプトに添付済み。§2事実性／§3内心／§5構成／§5.5第2部／§6型辞書／§9自己検査）

## 手順
1. `python scripts/assign_styles.py docs/data/kansenki/source/{掲載日}.json --out /tmp/assign.json` を実行し、
   各場の `styleType`／`protagonist`（主役候補）／`killerHints`／`hasTodayProgram` を得る。
2. **全場を1セッションで**執筆する（場間の書き出し・締め・型をずらす）。主役は assign の `protagonist` に従う。
   - `protagonistForcedAlternate=true`：3日連続主役を避けて代替主役に差し替え済み。その代替を主役に書く。
   - `mustChangeAngle=true`：代替候補が居らず被りが続く場（弱small番組等）。主役は同じでよいが、
     前日と**切り口（書き出し・締め・柱にする事実）を必ず変える**。
   - `protagonistRepeatsPrevDay=true`（上記に該当しない）：物語ラインの継続（連勝の継続/途切れ等）として回収するか切り口を変える。
3. 各記事は既存と同じ構造の JSON を `docs/data/kansenki/articles/{掲載日}-{jcd}.json` に書く：
   `{date, jcd, venue, title, body, styleType, killerElement, glossaryTerms, racersMentioned[{name,toban}]}`
   - `styleType` は assign の指定に従う（材料がどうしても許さない場合のみ変更し、killerElement にその旨を記す）。
   - 数字は素材のまま（丸めない）。配当は円。相対表現には必ず比較軸を添える
     （機力→今節平均比／配当→当場年間万舟率／ST→通期平均比／得点率→ボーダー比）。
   - **万舟レースの1着選手名は書かない**（組番・配当・決まり手は可）。
   - `racersMentioned` の toban は source（focusRacers/localRacers/scoreRank）に実在するものだけ。
   - yomi=null の選手に読み仮名を付けない。
4. **第2部「きょうの注目」**：`hasTodayProgram=true` の場のみ、kansenkiRules §5.5 に従って第2部を書く。
   `hasTodayProgram=false` の場は第1部（前日振り返り）のみ。無理に第2部を作らない。
5. **既存記事は上書きしない**：`articles/{掲載日}-{jcd}.json` が既に存在する場は書かない（skip）。
6. §9自己検査を全問通す。→ `python scripts/lintKansenki.py docs/data/kansenki/articles/{掲載日}-*.json` を実行し、
   **全場 PASS になるまで**該当記事を直す。PASS しない場は「書かない」（そのファイルを消して持ち越す）。
7. 仕上げに `python scripts/lintKansenki.py --coverage {掲載日}` で網羅を確認（0本の日はSKIP＝正常）。

## 禁止
- source にない事実の補筆、取材風・空気風の描写（「関係者によると」等）。
- PR作成・マージ・push・ネットワークアクセス（この工程はローカル執筆と lint のみ。公開は人が行う）。
- assign が示す styleType を理由なく無視すること（型のブレは品質劣化の主因）。

## 完了条件
- `articles/{掲載日}-*.json` が lint 全場 PASS。1本でも FAIL の場は当該ファイルを残さず終了（持ち越し）。
