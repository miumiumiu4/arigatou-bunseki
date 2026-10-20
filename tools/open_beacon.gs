/**
 * 店ごとの見本からの知らせを受けて、候補リストのスプレッドシートに書く（候補シートに付ける GAS）。
 *  - 開いた（GET ?s=合言葉&p=booking|report）：「開封ログ」と、候補の「最初に開いた日時」「開いた回数」
 *  - 「見ました」フォーム（POST kind=mita）：「返事ログ」と、候補の「返事」「返事の内容」「聞き取りで分かった入口」「月の申込件数」
 * 候補シートに列がなければ、一番右に足す。
 * ※メールの安全確認ソフトが代わりに開くこともあるため、1回だけの開封は割り引いて見る。
 */
var COLS = ['完成品のURL（予約フォーム）', '完成品のURL（レポート）', '最初に開いた日時', '開いた回数',
            '返事', '返事の内容', '聞き取りで分かった入口', '月の申込件数'];

function doGet(e) {
  var p = (e && e.parameter) || {};
  var slug = clean_(p.s, /[^a-z0-9]/g, 20), page = clean_(p.p, /[^a-z]/g, 10);
  if (!slug) return done_();
  withLock_(function (ss) {
    log_(ss, '開封ログ', ['日時', '合言葉', 'ページ'], [new Date(), slug, page]);
    var hit = findRow_(ss, slug);
    if (!hit) return;
    if (!hit.get('最初に開いた日時')) hit.set('最初に開いた日時', new Date());
    hit.set('開いた回数', (Number(hit.get('開いた回数')) || 0) + 1);
  });
  return done_();
}

function doPost(e) {
  var p = (e && e.parameter) || {};
  if (p.kind !== 'mita') return done_();
  var slug = clean_(p.s, /[^a-z0-9]/g, 20);
  var cut = function (x) { return String(x || '').replace(/[\r\n\t]/g, ' ').slice(0, 80); };
  var inlet = cut(p['in']), n = cut(p.n), q = cut(p.q), c = cut(p.c);
  if (!slug) return done_();
  withLock_(function (ss) {
    log_(ss, '返事ログ', ['日時', '合言葉', '予約の受け方', '月の申込の数', '気になった所', '連絡先'], [new Date(), slug, inlet, n, q, c]);
    var hit = findRow_(ss, slug);
    if (!hit) return;
    hit.set('返事', '見ました（フォーム ' + Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm') + '）');
    hit.set('返事の内容', '気になった所：' + (q || 'なし') + (c ? '／連絡先：' + c : ''));
    if (inlet) hit.set('聞き取りで分かった入口', inlet);
    if (n) hit.set('月の申込件数', n);
  });
  return done_();
}

function clean_(x, re, len) { return String(x || '').replace(re, '').slice(0, len); }

function withLock_(fn) {
  var lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try { fn(SpreadsheetApp.getActive()); } finally { lock.releaseLock(); }
}

function log_(ss, name, head, row) {
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (sh.getLastRow() === 0) sh.appendRow(head);
  sh.appendRow(row);
}

// 候補シートで、完成品の URL にこの合言葉が入っている行を探す。列がなければ足す。
function findRow_(ss, slug) {
  var sh = ss.getSheetByName('候補');
  var head = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  COLS.forEach(function (c) {
    if (head.indexOf(c) < 0) { sh.getRange(1, head.length + 1).setValue(c); head.push(c); }
  });
  var vals = sh.getRange(1, 1, sh.getLastRow(), head.length).getValues();
  var cb = head.indexOf(COLS[0]), cr = head.indexOf(COLS[1]), key = '/s/' + slug + '/';
  for (var r = 1; r < vals.length; r++) {
    if (String(vals[r][cb]).indexOf(key) < 0 && String(vals[r][cr]).indexOf(key) < 0) continue;
    var row = r + 1;
    return {
      get: function (c) { return vals[row - 1][head.indexOf(c)]; },
      set: function (c, v) { sh.getRange(row, head.indexOf(c) + 1).setValue(v); }
    };
  }
  return null;
}

function done_() {
  return ContentService.createTextOutput('ok');
}
