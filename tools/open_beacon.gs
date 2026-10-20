/**
 * 店ごとの見本が開かれたら記録する（候補リストのスプレッドシートに付ける GAS）。
 * 見本のページ（housecleaning/beacon.js）が ?s=合言葉&p=booking|report でここを呼ぶ。
 * 記録先：「開封ログ」シート（1回ごとに1行）と、「候補」シートの「最初に開いた日時」「開いた回数」。
 * ※メールの安全確認ソフトが代わりに開くこともあるため、送った直後の1回だけの開封は割り引いて見る。
 */
function doGet(e) {
  var p = (e && e.parameter) || {};
  var slug = String(p.s || '').replace(/[^a-z0-9]/g, '').slice(0, 20);
  var page = String(p.p || '').replace(/[^a-z]/g, '').slice(0, 10);
  if (!slug) return done_();
  var lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    var ss = SpreadsheetApp.getActive();
    var log = ss.getSheetByName('開封ログ') || ss.insertSheet('開封ログ');
    if (log.getLastRow() === 0) log.appendRow(['日時', '合言葉', 'ページ']);
    log.appendRow([new Date(), slug, page]);

    var sh = ss.getSheetByName('候補');
    var vals = sh.getDataRange().getValues();
    var head = vals[0];
    var cb = head.indexOf('完成品のURL（予約フォーム）'), cr = head.indexOf('完成品のURL（レポート）');
    var cf = head.indexOf('最初に開いた日時'), cn = head.indexOf('開いた回数');
    var key = '/s/' + slug + '/';
    for (var r = 1; r < vals.length; r++) {
      if (String(vals[r][cb]).indexOf(key) < 0 && String(vals[r][cr]).indexOf(key) < 0) continue;
      if (cf >= 0 && !vals[r][cf]) sh.getRange(r + 1, cf + 1).setValue(new Date());
      if (cn >= 0) sh.getRange(r + 1, cn + 1).setValue((Number(vals[r][cn]) || 0) + 1);
      break;
    }
  } finally {
    lock.releaseLock();
  }
  return done_();
}

function done_() {
  return ContentService.createTextOutput('ok');
}
