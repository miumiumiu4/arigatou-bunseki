// 店ごとの見本が開かれた日時を記録する。URL の最後に ?nolog を付けると記録しない（送る前の確認用）。
(function () {
  var GAS = ''; // 開封を記録する GAS のウェブアプリの URL（https://script.google.com/macros/s/…/exec）
  window.ARIGATOU_GAS = GAS; // 「見ました」フォーム（mita.js）も同じ受け口に送る
  var d = document.currentScript && document.currentScript.dataset;
  if (!GAS || !d || /[?&]nolog/.test(location.search)) return;
  new Image().src = GAS + '?s=' + encodeURIComponent(d.shop) + '&p=' + encodeURIComponent(d.page) + '&t=' + Date.now();
})();
