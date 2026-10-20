// 店ごとの見本に「見ました」フォームを出す。答えは GAS の受け口（beacon.js の GAS）へ送り、候補シートの同じ行に入る。
// 項目は4つだけ（コンテンツ/共通/letter_v2_番頭さん.md の最後の節）。増やさない。
(function () {
  var me = document.currentScript, shop = me.dataset.shop;
  var box = document.createElement('section');
  box.id = 'mita';
  box.innerHTML =
    '<style>#mita{max-width:720px;margin:32px auto;padding:20px 16px;border:2px solid #1f6f8b;border-radius:14px;background:#fff;color:#1d2b33;font-size:15px;line-height:1.7}' +
    '#mita h2{margin:0 0 4px;font-size:20px}#mita p{margin:0 0 12px;color:#5b6b74}#mita fieldset{border:0;margin:0 0 14px;padding:0}' +
    '#mita legend{font-weight:700;margin-bottom:6px}#mita label{display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;font-weight:normal}' +
    '#mita input[type=text]{width:100%;font-size:16px;padding:10px;border:1px solid #c9d5db;border-radius:8px}' +
    '#mita button{width:100%;padding:14px;border:0;border-radius:10px;background:#1f6f8b;color:#fff;font-size:17px;cursor:pointer}' +
    '#mita .done{display:none;font-size:17px;font-weight:700;color:#1f6f8b}#mita .err{color:#b3412e;font-size:14px}</style>' +
    '<h2>見ました（3つだけ教えてください）</h2><p>答えていただくと、三浦から1営業日以内にご連絡します。連絡先は空でもかまいません。</p>' +
    '<form><fieldset><legend>今の予約の受け方</legend>' + radios('in', ['電話', 'LINE', 'ポータル（くらしのマーケット等）', '自社フォーム', '紙']) + '</fieldset>' +
    '<fieldset><legend>月の申込の数</legend>' + radios('n', ['〜10', '11〜30', '31〜100', '101〜']) + '</fieldset>' +
    '<fieldset><legend>気になった所（いくつでも）</legend>' + checks('q', ['曜日の山', '同じ訪問で追加', '再来のお便り', 'とくになし']) + '</fieldset>' +
    '<fieldset><legend>連絡先（任意・メールか電話番号のどちらか1つ）</legend><input type="text" name="c" maxlength="80" autocomplete="email"></fieldset>' +
    '<button type="submit">送る</button><div class="err"></div></form>' +
    '<div class="done">ありがとうございます。三浦から1営業日以内にご連絡します。</div>';
  var foot = document.querySelector('footer');
  foot ? foot.parentNode.insertBefore(box, foot) : document.body.appendChild(box);

  function radios(n, xs) { return xs.map(function (x) { return '<label><input type="radio" name="' + n + '" value="' + x + '">' + x + '</label>'; }).join(''); }
  function checks(n, xs) { return xs.map(function (x) { return '<label><input type="checkbox" name="' + n + '" value="' + x + '">' + x + '</label>'; }).join(''); }

  var f = box.querySelector('form'), err = box.querySelector('.err');
  f.addEventListener('submit', function (e) {
    e.preventDefault();
    var fd = new FormData(f), v = function (k) { return fd.getAll(k).join('、'); };
    if (!v('in') && !v('n') && !v('q')) { err.textContent = 'どれか1つでも選んでください。'; return; }
    if (!window.ARIGATOU_GAS) { err.textContent = 'ただいま送れません。お手数ですが、お電話（080-4177-2272）でお知らせください。'; return; }
    var body = new URLSearchParams({ kind: 'mita', s: shop, page: me.dataset.page || '', in: v('in'), n: v('n'), q: v('q'), c: v('c') });
    f.querySelector('button').disabled = true;
    fetch(window.ARIGATOU_GAS, { method: 'POST', mode: 'no-cors', body: body }).then(function () {
      f.style.display = 'none'; box.querySelector('.done').style.display = 'block';
    }).catch(function () {
      f.querySelector('button').disabled = false;
      err.textContent = '送れませんでした。もう一度押すか、お電話（080-4177-2272）でお知らせください。';
    });
  });
})();
