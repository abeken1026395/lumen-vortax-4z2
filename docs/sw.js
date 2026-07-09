/* データ攻め ポータル Service Worker
   方針: ネットワーク優先（オンライン時は常に最新の出走表/データ）＋オフライン時はキャッシュ。
   出走表・払戻などは日々更新されるため、stale を掴ませない network-first にする。 */
var CACHE = "lumen-vortax-4z2-v2";
var SHELL = [
  "./", "./racers/", "./manifest.json",
  "./icon180.png", "./icon192.png", "./icon512.png"
];

self.addEventListener("install", function (e) {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function (c) { return c.addAll(SHELL).catch(function () {}); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (ks) {
      return Promise.all(ks.map(function (k) { if (k !== CACHE) return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  e.respondWith(
    fetch(req).then(function (res) {
      var cp = res.clone();
      caches.open(CACHE).then(function (c) { c.put(req, cp); }).catch(function () {});
      return res;
    }).catch(function () {
      return caches.match(req).then(function (m) { return m || caches.match("./racers/"); });
    })
  );
});
