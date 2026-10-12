/* Caro Online - Service Worker
   Cho phép cài thành app trên iOS/Android và chơi lại khi yếu mạng.
   Mọi request WebSocket đều bỏ qua, chỉ cache file tĩnh.

   *** QUAN TRỌNG KHI CẬP NHẬT GAME ***
   Trình duyệt coi sw.js là "manifest" của bộ nhớ đệm. Nếu bạn sửa file
   styles.css / game.js / index.html thì PHẢI đổi VERSION bên dưới
   (vd: v1 -> v2), nếu không người dùng sẽ vẫn thấy bản cũ do cache.
   Không cần đổi VERSION khi chỉ sửa nội dung file sw.js. */

const VERSION = 'caro-online-v1';
const STATIC_CACHE = VERSION + '-static';

const PRECACHE = [
  './',
  'index.html',
  'styles.css',
  'game.js',
  'manifest.json',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // không đụng tới WebSocket hay request cross-origin
  if (req.method !== 'GET') return;
  if (req.url.indexOf(self.location.origin) !== 0) return;

  // điều hướng (mở trang): network trước, cache dự phòng
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put('index.html', copy));
          return res;
        })
        .catch(() => caches.match('index.html'))
    );
    return;
  }

  // file tĩnh: cache trước, network nếu thiếu
  event.respondWith(
    caches.match(req).then((hit) => {
      if (hit) return hit;
      return fetch(req).then((res) => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(req, copy));
        }
        return res;
      });
    })
  );
});
