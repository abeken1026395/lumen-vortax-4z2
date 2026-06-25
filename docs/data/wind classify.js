// 風向き判定ヘルパー（stadium_orientation.json + weather.json を突き合わせる）
// head_deg: 各場のスタート→1M方位（向かい風になる風向）。stadium_orientation.json 参照。
// windDeg: 風が吹いてくる方位(0=北)。weather.json の deg。
// windMs : 風速 m/s。weather.json の wind。
// 出典: ひつじのボートレース分析(公式データ2014-2022) https://hitsuzi-boatrace.com/wind-direction-no1-win/
// ※買い目は出さない。コース有利度の「傾向」までを表示する用途。

function angDiff(a, b) {
  const d = Math.abs(a - b) % 360;
  return Math.min(d, 360 - d);
}

// 返り値: {type:'向かい風'|'追い風'|'横風'|'弱風', strength:'弱'|'中'|'強'|'非常に強',
//          rough:boolean(荒れ目安), hint:傾向の一言}
function classifyWind(headDeg, windDeg, windMs) {
  if (windMs == null || windMs < 1) {
    return { type: '弱風', strength: '弱', rough: false, hint: '風の影響は小さい' };
  }
  const d = angDiff(windDeg, headDeg);
  let type;
  if (d <= 45) type = '向かい風';
  else if (d >= 135) type = '追い風';
  else type = '横風';

  let strength;
  if (windMs < 2) strength = '弱';
  else if (windMs < 3) strength = '中';
  else if (windMs < 5) strength = '強';
  else strength = '非常に強';

  // 荒れ目安: 風速3m以上で外寄り、5m以上で水面悪化（公式・分析の一般傾向）
  const rough = windMs >= 5 || (type !== '横風' && windMs >= 4);

  // 傾向の一言（買い目ではなく有利度の方向）
  let hint = '';
  if (type === '向かい風') {
    hint = windMs < 3 ? 'イン有利は残りやすい'
                      : 'インの加速が鈍り、アウト・まくりが利きやすい';
  } else if (type === '追い風') {
    hint = windMs < 3 ? '軽い追い風はイン・差しが安定しやすい'
                      : 'ターンが流れやすく、差し場が空きやすい';
  } else {
    hint = windMs < 3 ? '影響は小さめ'
                      : '横風で艇が振られ、技量差が出やすい';
  }
  return { type, strength, rough, hint };
}

// 例:
// const o = ORIENT['14'];              // 鳴門 head_deg=135
// const w = weather['14'].hourly[i];   // {deg:158, wind:5.6, ...}
// classifyWind(o.head_deg, w.deg, w.wind)
//  -> {type:'向かい風', strength:'非常に強', rough:true, hint:'インの加速が鈍り…'}
