#!/usr/bin/env python3
"""店ごとの見本（予約フォーム・レポート）と1通目の下書きを、候補シートから一括で作る。

使い方：
  python3 tools/make_samples.py --candidates 候補.csv [--prices 価格.csv]
      --manifest 一覧.csv --drafts 下書き.csv [--senders a@x,b@x,...] [--per-day 30]
  python3 tools/make_samples.py --manifest 一覧.csv --remove 12   # 「不要」の店のページを消す
  python3 tools/make_samples.py --yoyaku --candidates 候補.csv [--prices 価格.csv] --manifest 一覧.csv
      # SMS 用：booking.html の代わりに参考サイトの形の yoyaku.html（4段の予約ページ）と report.html（report_template.html）を作る
      # 予約ページの「確認」で送ると report.html?from=yoyaku に移る。下に電話／メールのバナー（「見ました」フォームは出さない）

決まり：
  - 使うのは店名・★・口コミ件数・業種・地域・公表しているサービスと料金だけ。口コミの文章と写真は使わない。
  - 数字（予約件数など）はすべて架空。ページにもそう書く。
  - 優先度 A、営業お断りなし、チェーンでない、きらりん・エアタクミでない、公表アドレスがある店だけ作る。
  - URL は推測できない文字列。一覧（店名との対応）はリポジトリに入れない。
"""
import argparse, csv, datetime, html, json, os, re, secrets, shutil, string, sys, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "housecleaning")
OUT = os.path.join(DEMO, "s")
BASE_URL = "https://miumiumiu4.github.io/arigatou-bunseki/housecleaning/s/"
EXCLUDE_NAMES = ("きらりん", "エアタクミ")

# サービス列 → 予約フォームの行。区分は価格シートのメニュー区分。
HOUSE_MENU = [
    ("ac", "サービス：エアコン", "エアコン壁掛け", "エアコン（壁掛け）", 12000, "台", ""),
    ("kit", "サービス：レンジフード|サービス：キッチン", "レンジフード|キッチン", "キッチン・換気扇", 16000, "", "2"),
    ("bath", "サービス：浴室", "浴室", "浴室", 15000, "", "2"),
    ("wash", "サービス：洗面台", "洗面台", "洗面所", 8000, "", "2"),
    ("wc", "サービス：トイレ", "トイレ", "トイレ", 7000, "", "3"),
    ("wm", "サービス：洗濯機", "洗濯機", "洗濯機", 13000, "台", "2"),
]
AC_MENU = [
    ("ac", None, "エアコン壁掛け", "エアコン（壁掛け）", 12000, "台", ""),
    ("acp", None, "エアコンお掃除機能付き", "お掃除機能付きエアコン", 22000, "台", ""),
    ("out", None, "エアコン室外機", "室外機", 5000, "台", ""),
]


def yes(row, cols):
    return any(row.get(c, "").strip() == "はい" for c in cols.split("|"))


def is_aircon_only(row):
    return "エアコン" in row.get("業種", "") and not yes(row, "サービス：浴室|サービス：キッチン|サービス：トイレ")


def shop_prices(prices, no):
    got = {}
    for p in prices:
        if p.get("店番号（候補シートの番号）", "").strip() != no:
            continue
        kind = p.get("価格の種類（定額・〜から・範囲の下限・範囲の上限・要見積）", "").strip()
        val = re.sub(r"\D", "", p.get("価格（円・数字のみ）", ""))
        cat = p.get("メニュー区分（下の決まりの言葉から選ぶ）", "").strip()
        if not val or kind not in ("定額", "〜から", "範囲の下限") or cat in got:
            continue
        got[cat] = (int(val), kind != "定額", p.get("税区分（税込・税抜・不明）", "").strip())
    return got


def menu_for(row, prices):
    rows = []
    for key, svc, cats, label, default, unit, mx in (AC_MENU if is_aircon_only(row) else HOUSE_MENU):
        if svc and not yes(row, svc):
            continue
        hit = next((prices[c] for c in cats.split("|") if c in prices), None)
        if hit:
            price, frm, tax = hit
            note = f"{price:,}円{'〜' if frm else ''}{'（税抜）' if tax == '税抜' else ''}"
        else:
            price, note = default, f"{default:,}円（仮）"
        if unit:
            note = note.replace("円", f"円/{unit}", 1)
        rows.append(dict(key=key, label=label, price=price, note=note, max=mx, real=bool(hit)))
    if not rows:  # サービス欄が空なら、ハウスクリーニングの基本の形
        return menu_for({**row, **{c: "はい" for c in ("サービス：エアコン", "サービス：浴室", "サービス：キッチン", "サービス：トイレ", "サービス：洗面台")}}, prices)
    return rows


def sub1(s, old, new):
    """必ず1回だけ置き換える。見本のHTMLが変わって合わなくなったら止める。"""
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"置き換え先が {n} 個あります：{old[:40]}")
    return s.replace(old, new)


def beacon(slug, page):
    return (f'<script src="../../beacon.js" data-shop="{slug}" data-page="{page}"></script>\n'
            f'<script src="../../mita.js" data-shop="{slug}" data-page="{page}"></script>\n</body>')


def make_booking(row, menu, slug, aircon):
    s = open(os.path.join(DEMO, "booking.html"), encoding="utf-8").read()
    shop = html.escape(row["店名"].strip())
    area = html.escape(row.get("住所（市区町村まで）", "").strip() or row.get("都道府県", ""))
    kind = html.escape(row.get("業種", "").strip() or "ハウスクリーニング")
    s = sub1(s, "<title>おそうじ工房そらいろ｜ご予約（見本）</title>", f"<title>{shop}｜ご予約（見本）</title>")
    s = sub1(s, "ご提案用の見本です（架空の店）。送信はされません。",
             f"{shop}様へのご提案用の見本です。料金・メニューは{shop}様の公表内容をもとにした仮のもので、送信はされません。")
    s = sub1(s, "ハウスクリーニング｜横浜市", f"{kind}｜{area}")
    s = sub1(s, "<h1>おそうじ工房 そらいろ</h1>", f"<h1>{shop}</h1>")
    s = sub1(s, "おそうじ工房 そらいろ（架空の店）<br>", f"{shop}<br>")
    s = sub1(s, 'placeholder="例：SORA-1234"', 'placeholder="例：AB-1234"')

    first = next((m["key"] for m in menu if m["key"] == "bath"), menu[0]["key"])
    lines = []
    for m in menu:
        mx = f' max="{m["max"]}"' if m["max"] else ""
        lines.append(f'  <div class="row"><span>{m["label"]} <small>{m["note"]}</small></span>'
                     f'<input type="number" min="0"{mx} value="{1 if m["key"] == first else 0}" data-p="{m["price"]}" data-k="{m["key"]}"></div>')
    keys = {m["key"]: m for m in menu}
    set_off = 0
    if {"bath", "wash", "wc"} <= keys.keys():
        three = sum(keys[k]["price"] for k in ("bath", "wash", "wc"))
        set_off = 3000
        lines.append(f'  <label style="font-weight:normal;display:flex;gap:8px;align-items:center"><input type="checkbox" id="set" style="width:auto;margin:0">'
                     f'<b>水回り3点セット</b>（浴室・洗面所・トイレ）{three - set_off:,}円（別々なら{three:,}円・セットの値引きは例）</label>')
    real = any(m["real"] for m in menu)
    lines.append(f'  <p class="why" style="display:block">料金は{shop}様が公表している料金を入れています。（仮）とある所は見つからなかったため仮の料金です。</p>' if real
                 else '  <p class="why" style="display:block">料金はすべて仮です。公開前に正しい料金に直します。</p>')
    why = ("何台・どの種類を頼んだかで「次に案内するもの」が決まります。1台だけの方には、次回2台目の案内。2台以上の率がレポートに出ます。" if aircon
           else "何を頼んだかで「次に案内するもの」が決まります。浴室だけの方には、次回セットの案内。セット率がレポートに出ます。")
    old_menu = s[s.index('  <div class="row"><span>エアコン（壁掛け）'):s.index('  <span class="why">何を頼んだかで')]
    s = sub1(s, old_menu, "\n".join(lines) + "\n")
    s = sub1(s, "何を頼んだかで「次に案内するもの」が決まります。浴室だけの方には、次回セットの案内。セット率がレポートに出ます。", why)
    if aircon:
        s = sub1(s, '<label><input type="checkbox">エアコン</label>', '<label><input type="checkbox">浴室・水回り</label>')

    js_old = s[s.index("<script>"):s.index("</script>") + len("</script>")]
    js = f"""<script>
const nums=[...document.querySelectorAll('input[data-p]')],set=document.getElementById('set'),out=document.getElementById('sum');
const k=key=>nums.find(i=>i.dataset.k===key);
function calc(){{let s=nums.reduce((a,i)=>a+(+i.value||0)*(+i.dataset.p),0);
  if(set&&set.checked){{s-={set_off};}}
  out.textContent='¥'+Math.max(s,0).toLocaleString('ja-JP');}}
nums.forEach(i=>i.addEventListener('input',calc));
if(set)set.addEventListener('change',()=>{{if(set.checked){{['bath','wash','wc'].forEach(x=>{{if(k(x)&&!+k(x).value)k(x).value=1}})}}calc()}});
document.getElementById('whyToggle').addEventListener('change',e=>document.body.classList.toggle('nowhy',!e.target.checked));
calc();
</script>"""
    s = sub1(s, js_old, js)
    if any("（税抜）" in m["note"] for m in menu):
        s = sub1(s, "<span>概算（税込）</span>", "<span>概算</span>")
    return sub1(s, "</body>", beacon(slug, "booking"))


def make_report(row, menu, slug, aircon):
    s = open(os.path.join(DEMO, "report.html"), encoding="utf-8").read()
    raw = row["店名"].strip()
    shop = html.escape(raw)
    js_shop = raw.replace("\\", "\\\\").replace("`", "'").replace("$", "＄").replace('"', "”")
    kind = html.escape(row.get("業種", "").strip() or "ハウスクリーニング")
    star, cnt = row.get("Googleの★", "").strip(), row.get("口コミ件数", "").strip()
    seen = row.get("確認した日", "").strip()
    s = sub1(s, "<title>そらいろ予約レポート（見本）</title>", f"<title>{shop} 予約レポート（見本）</title>")
    s = sub1(s, "<body>", '<body class="sales">')
    s = sub1(s, "見本です。店も数字もすべて架空で、実在の店の結果ではありません。",
             f"{shop}様へのご提案用の見本です。数字はすべて架空で、{shop}様の実際の数字ではありません。")
    s = sub1(s, "おそうじ工房 そらいろ（架空）｜ハウスクリーニング", f"{shop}｜{kind}")
    s = sub1(s, "<h1>そらいろ予約レポート</h1>", f"<h1>{shop} 予約レポート</h1>")
    if star and cnt:
        when = f"{seen}時点・" if seen else ""
        s = sub1(s, "毎朝6時に自動で計算し直します</p>",
                 f"毎朝6時に自動で計算し直します</p>\n  <p class=\"muted\">Googleの口コミ ★{html.escape(star)}・{html.escape(cnt)}件（{when}店舗情報より）。これだけのお客様の予約を、毎朝「次の一手」に変える見本です。</p>")
    s = sub1(s, "店名・数字はすべて架空です。", "数字はすべて架空です。")

    keys = {m["key"]: m for m in menu}
    if aircon:
        ac = keys.get("ac", menu[0])["price"]
        s = sub1(s, '<div class="l">3点セット率</div><div class="v">12%</div><div class="s">浴室を頼んだ48件のうち</div>',
                 '<div class="l">2台以上の率</div><div class="v">31%</div><div class="s">エアコンを頼んだ58件のうち</div>')
        i0 = s.index('<h3>浴室だけの予約が38件</h3>')
        i1 = s.index('<span class="money">', i0)
        s = s[:i0] + ('<h3>1台だけの予約が40件</h3>\n    <div class="fact">エアコンの予約58件のうち、2台以上は18件（31%）。2台目は同じ訪問で、移動も準備も1回で済みます。</div>\n'
                      '    <div class="act"><b>予約確認の翌日に2台目のご案内</b>（メール②）。</div>\n    ') + s[i1:]
        s = sub1(s, "試算：38件の1割（4件）がセットにすると +¥48,000/月", f"試算：40件の1割（4件）が2台目を足すと +¥{ac * 4:,}/月")
        g0 = s.index('<div class="card"><h3>頼まれた場所（件）</h3>')
        g1 = s.index('</div>\n    <div class="card"><h3>第1希望の曜日（件）</h3>')
        bars = [("壁掛け 1台", 100, 40, True), ("壁掛け 2台以上", 45, 18, False), ("お掃除機能付き", 53, 21, False), ("室外機も", 23, 9, False)]
        g = '<div class="card"><h3>頼まれた内容（件）</h3>\n' + "".join(
            f'      <div class="bar"><span>{n}</span><span class="track"><span class="fill{" hi" if h else ""}" style="width:{w}%;display:block"></span></span><span class="v">{v}</span></div>\n'
            for n, w, v, h in bars) + '      <p class="note">1台だけの予約が7割。2台目のご案内がまだ出ていません。</p>'
        s = s[:g0] + g + s[g1:]
        m2_old = s[s.index('["② 3点セットのご案内"'):s.index('["③ 同じ日にもう1か所"')]
        s = sub1(s, m2_old, '''["② 2台目のご案内","予約確認の翌日・1台だけの方","{作業日}のお伺いで、もう1台ご一緒にいかがですか",
`{お名前} 様

エアコンクリーニングのご予約、ありがとうございます。

ほかのお部屋のエアコンも、同じ日にまとめてお掃除できます。
お伺いは1回で済み、お客様のご予定も一日で終わります。

　2台目以降：{2台目の料金：店主様と決めます}

ご希望の場合は、このメールに「2台目希望」とご返信ください。
当日のお申し出でも承ります。`+SIG],
''')
        s = sub1(s, "水回りの汚れは、1年ほどで目立ち始める方が多いです。", "エアコンの中は、1年ほどでほこりやカビがたまり始める方が多いです。")
    elif {"bath", "wash", "wc"} <= keys.keys():
        three = sum(keys[k]["price"] for k in ("bath", "wash", "wc"))
        s = sub1(s, "　水回り3点セット（浴室・洗面所・トイレ）27,000円\n　（別々にご依頼の場合は30,000円）",
                 f"　水回り3点セット（浴室・洗面所・トイレ）{three - 3000:,}円\n　（別々にご依頼の場合は{three:,}円）")
        s = sub1(s, "試算：38件の1割（4件）がセットにすると +¥48,000/月",
                 f"試算：38件の1割（4件）がセットにすると +¥{(keys['wash']['price'] + keys['wc']['price'] - 3000) * 4:,}/月")

    s = sub1(s, "const SIG=`\\n\\nおそうじ工房 そらいろ", f"const SIG=`\\n\\n{js_shop}")
    s = sub1(s, "ご予約ありがとうございます。おそうじ工房 そらいろです。", f"ご予約ありがとうございます。{js_shop}です。")
    s = sub1(s, "先日はおそうじ工房 そらいろにご依頼いただき", f"先日は{js_shop}にご依頼いただき")
    s = sub1(s, "【そらいろ】前回のお掃除から", f"【{js_shop}】前回のお掃除から")
    s = sub1(s, "いつもありがとうございます。おそうじ工房 そらいろです。", f"いつもありがとうございます。{js_shop}です。")
    s = sub1(s, "M.forEach((m,i)=>{const b=document.createElement('button');b.type='button';b.textContent=m[0];b.onclick=()=>show(i);tabs.append(b)});show(0);",
             "M.forEach((m,i)=>{const b=document.createElement('button');b.type='button';b.textContent=m[0];b.onclick=()=>show(i);if(i!==1&&i!==4)b.style.display='none';tabs.append(b)});show(1);")
    assert "そらいろ" not in s and "架空の店" not in s, "そらいろが残っています"
    return sub1(s, "</body>", beacon(slug, "report"))


def source_label(url):
    u = url.lower()
    for key, name in (("google.", "Googleマップの店舗情報"), ("curama", "くらしのマーケットの店舗ページ"),
                      ("meetsmore", "ミツモアの店舗ページ"), ("ouchino", "おうちのプロの店舗ページ"),
                      ("instagram", "Instagram のプロフィール")):
        if key in u:
            return name
    return "ホームページ"


def draft(row, booking_url, report_url, sender):
    shop = row["店名"].strip()
    star, cnt, seen = row.get("Googleの★", "").strip(), row.get("口コミ件数", "").strip(), row.get("確認した日", "").strip()
    ym = f"{seen[:4]}年{int(seen[5:7])}月時点" if re.match(r"\d{4}-\d{2}", seen) else "2026年10月時点"
    google = f"（★{star}・口コミ{cnt}件、{ym}）" if star and cnt else ""
    subject = f"{shop}様の予約を毎朝読む「番頭さん」の見本です"
    body = f"""{shop}
ご担当者様

突然のご連絡失礼いたします。
横浜でエアコン清掃の会社を経営している、ありがとうグループの三浦と申します。

Googleマップで{shop}様を拝見しました{google}。

予約を毎朝読んで「次の一手」と、お客様に送るメールまで出す仕組みを、
{shop}様の名前で見本にしました。数字は架空です。

予約フォーム：{booking_url}
レポート：{report_url}

同じ掃除屋として、自社で使っている仕組みです。加盟のお誘いではありません。

ご返事は「見ます」「不要」の一言で十分です。
「不要」の場合は、今後ご連絡しません。

――――――――――――――――
ありがとうグループ（エイムポイント合同会社）
代表　三浦公嗣
住所：〒220-0005 神奈川県横浜市西区北幸1-11-1 水信ビル7階
電話：080-4177-2272
メール：{sender}

今後のご案内が不要な方は、このメールに「不要」とご返信ください。
以後お送りしません。
このメールは{shop}様が{source_label(row.get('アドレスの出典URL', ''))}で
公開されているアドレスにお送りしています。
――――――――――――――――"""
    return subject, body


# ---- SMS 用の予約ページ（参考サイトの4段の形。housecleaning/yoyaku_template.html） ----
PRICE_KIND = "価格の種類（定額・〜から・範囲の下限・範囲の上限・要見積）"
SAMPLE_MENU = [  # 価格シートに行がない店の仮の料金（ページに「仮」と出す）
    ("エアコン", "サービス：エアコン", "壁掛けエアコン", 12000, "1台"),
    ("エアコン", "サービス：エアコン", "お掃除機能付きエアコン", 22000, "1台"),
    ("エアコン", "サービス：エアコン", "室外機", 5000, "1台"),
    ("水回り", "サービス：浴室", "浴室", 15000, "1か所"),
    ("水回り", "サービス：キッチン", "キッチン", 16000, "1か所"),
    ("水回り", "サービス：レンジフード", "レンジフード（換気扇）", 16000, "1台"),
    ("水回り", "サービス：洗面台", "洗面所", 8000, "1か所"),
    ("水回り", "サービス：トイレ", "トイレ", 7000, "1か所"),
]
# 1段目の切り替え（業種 → mode）。他業種の中身は土台だけ（見た目の作り込みはまだ）。
CONSULT_ITEMS = [("キッチン・水回りのリフォーム", ""), ("内装（壁紙・床）", ""), ("外壁・屋根", ""), ("増改築・間取りの変更", ""), ("修繕・その他", "")]
VISIT_ITEMS = [("部屋を借りたい", ""), ("家・土地を買いたい", ""), ("売りたい・貸したい", ""), ("その他のご相談", "")]
BUDGETS = ["〜50万円", "50〜100万円", "100〜300万円", "300万円〜", "まだ決めていない"]


def page_mode(row, forced=None):
    if forced:
        return forced
    k = row.get("業種", "")
    if re.search("不動産", k):
        return "visit"
    if re.search("リフォーム|工務店|建築|建設|塗装|リノベ", k):
        return "consult"
    return "menu"


MOBILE_COL = "携帯番号（070・080・090 で始まる物だけ）"


def yoyaku_menu(row, prices, no):
    """価格シートの行 → タブごとのメニュー。店の表記（〜から・要見積）はそのまま。税抜は税込に直して添える。"""
    tabs, real = {}, 0
    for p in prices:
        if p.get("店番号（候補シートの番号）", "").strip() != no:
            continue
        kind = p.get(PRICE_KIND, "").strip() or "定額"
        if kind == "範囲の上限":
            continue
        kind = "〜から" if kind == "範囲の下限" else kind
        cat = p.get("メニュー区分（下の決まりの言葉から選ぶ）", "").strip()
        name = p.get("メニュー名（店の表記どおり・短く）", "").strip() or cat
        val = re.sub(r"\D", "", p.get("価格（円・数字のみ）", ""))
        if not name or (not val and kind != "要見積"):
            continue
        tax = p.get("税区分（税込・税抜・不明）", "").strip()
        price = int(val) if val else 0
        sub = [x for x in (p.get("数量・単位（例 1台・1箇所・1式・1時間）", "").strip(),
                           p.get("セット・割引の条件（一言）", "").strip()) if x]
        if kind == "要見積":
            price = 0
        elif tax == "税抜":
            sub.append(f"税抜{price:,}円")
            price = int(round(price * 1.1))
        elif tax != "税込":
            sub.append("税の扱いはお店に確認中")
        tab = "エアコン" if re.search("エアコン|室外機", cat + name) else "水回り"
        tabs.setdefault(tab, []).append(dict(name=name, price=price, kind=kind, sub="・".join(sub)))
        real += 1
    if not real:
        has = [m for m in SAMPLE_MENU if yes(row, m[1])] or SAMPLE_MENU
        for tab, _, name, price, unit in has:
            tabs.setdefault(tab, []).append(dict(name=name, price=price, kind="定額", sub=f"{unit}・仮の料金"))
    order = sorted(tabs, key=lambda t: t != "エアコン")
    return [dict(label=t, items=tabs[t]) for t in order], real


def display_name(raw):
    """Googleの店名の後ろに付いた「（写真の店長が伺います）」のような添え書きは外す。"""
    s = re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", raw).strip()
    return s or raw


# 見本を見た店主様からのご連絡の窓口（予約ページとレポートの下のバナー・レポートのメール文面の署名）
CONTACT_TEL = "000-0000-0000"  # 仮。Google マップに載っている「ありがとうエアコンお掃除専門店」の番号が届いたら差し替え、下を False に
CONTACT_TEL_IS_TEMP = True
CONTACT_MAIL = "miura1@bunseki.arigatouosouji.com"
# 両ページ下部「この見本ページについて」の会社の表示。変える時はここだけ直して作り直す。
COMPANY_NAME = "エイムポイント合同会社"
COMPANY_TRADE_NAME = "ありがとうエアコンお掃除専門店"  # 屋号
COMPANY_REP = "三浦公嗣"
# 所在地は住所の文字の代わりに Google マップへのリンク。正式なリンクが決まったらここだけ差し替える（今は検索リンク）
COMPANY_MAP_URL = "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote("ありがとうエアコンお掃除専門店")


def company_lines():
    trade = f"（屋号：{html.escape(COMPANY_TRADE_NAME)}）" if COMPANY_TRADE_NAME else ""
    return (f"作った会社：<b>{html.escape(COMPANY_NAME)}</b>{trade}<br>\n"
            f"    代表：{html.escape(COMPANY_REP)}<br>\n"
            f'    所在地：<a href="{html.escape(COMPANY_MAP_URL)}" target="_blank" rel="noopener">Googleマップで見る</a><br>')


# 「データはこう溜まる」の見本シート（Google スプレッドシート・仮の数字・個人情報なし）
SHEET_URL = "https://docs.google.com/spreadsheets/d/1xQEPbSlHTzcW1Qk8cYtnBVcrsGGqtrT8bCxr3Z2tm28/edit?usp=sharing"
# バナーに出す価格（税込）。変える時はここだけ直して作り直す。
PRICE_MAIN = ("制作代金 買い切り", "110,000円（税込）")
PRICE_PLANS = [
    ("年額", "5,500円（税込）", ["顧客分析なし", "サイトの修正は年1回"]),
    ("月額", "5,500円（税込）", ["顧客分析あり", "毎月1回のレポート", "修正は月5回まで（6回目から1回2,200円）"]),
    ("月額", "33,000円（税込）", ["顧客分析", "毎日・毎週・毎月のレポート", "修正は無制限", "集客コンサル（月1回30分の Zoom あり）"]),
]
BANNER_CSS = (".contact{max-width:960px;margin:8px auto 16px;padding:0 16px}"
              ".contact .in{background:linear-gradient(135deg,var(--c),color-mix(in srgb,var(--c) 70%,#000));color:#fff;border-radius:18px;padding:22px 18px;text-align:center;box-shadow:0 6px 18px rgba(0,0,0,.12)}"
              ".contact h2{color:#fff;font-size:20px;line-height:1.5;margin:0 0 4px}"
              ".contact p{margin:0 0 14px;font-size:13.5px;opacity:.9}"
              ".contact .row{display:flex;gap:10px;flex-wrap:wrap}"
              ".contact a.cb{flex:1 1 220px;display:flex;align-items:center;justify-content:center;gap:8px;min-height:64px;border-radius:14px;"
              "text-decoration:none;font-weight:700;font-size:19px;padding:12px 14px}"
              ".contact a.tel{background:#fff;color:var(--c)}"
              ".contact a.mail{background:#f2a516;color:#3b2600}"
              ".contact small{display:block;margin-top:10px;font-size:12px;opacity:.85}"
              ".contact .price{background:#fff;color:#1c2430;border-radius:14px;padding:14px 12px;margin:10px 0 12px}"
              ".contact .tx{display:inline-block;font-size:.62em;font-weight:700}"
              ".contact .price .k{display:block;font-size:14px;font-weight:700;color:var(--c)}"
              ".contact .price .y{display:block;font-size:30px;font-weight:800;line-height:1.3;letter-spacing:.01em}"
              ".contact .plans{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0 0 16px;padding:0;list-style:none;text-align:left}"
              ".contact .plans>li{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.35);border-radius:12px;padding:10px 12px}"
              ".contact .plans .n{display:inline-block;font-size:12px;font-weight:700;background:#f2a516;color:#3b2600;border-radius:999px;padding:0 8px}"
              ".contact .plans b{display:block;font-size:18px;line-height:1.4;margin-top:4px}"
              ".contact .plans ul{margin:4px 0 0;padding-left:1.1em;font-size:13px;line-height:1.6}"
              ".contact a.toreport-link{display:block;background:#eaf6ee;color:#1d5a35;border:2px solid #7cc496;border-radius:14px;"
              "padding:14px 16px;margin:0 0 16px;text-decoration:none;box-shadow:0 3px 0 rgba(0,0,0,.15)}"
              ".contact a.toreport-link b{display:block;font-size:18px;line-height:1.45}"
              ".contact a.toreport-link span{display:block;font-size:13px;color:#3b6a4c;margin-top:4px;line-height:1.5}"
              "@media(max-width:640px){.contact .plans{grid-template-columns:1fr}.contact .price .y{font-size:26px}}")


def contact_banner(shop_plain, slug, to_report=False):
    """下のバナー：見出し→価格表（PRICE_MAIN・PRICE_PLANS）→（予約ページだけ）レポートへの導線→説明の一言→電話／メール。"""
    from urllib.parse import quote
    tel_raw = re.sub(r"[^0-9+]", "", CONTACT_TEL)
    subj = quote(f"見本について（{shop_plain}・合言葉 {slug}）")
    body = quote(f"見本を見ました。\n店名：{shop_plain}\n合言葉：{slug}\n\n（聞きたいことをお書きください）")
    tax = lambda v: html.escape(v).replace("（税込）", '<span class="tx">（税込）</span>')
    plans = "".join(
        f'<li><span class="n">{"①②③④⑤"[i]}</span><b>{html.escape(k)} {tax(v)}</b><ul>'
        + "".join(f"<li>{html.escape(x)}</li>" for x in xs) + "</ul></li>"
        for i, (k, v, xs) in enumerate(PRICE_PLANS))
    note = "<small>電話番号は準備中のため仮の番号です。メールでお問い合わせください。</small>" if CONTACT_TEL_IS_TEMP else ""
    lead = ('<a class="toreport-link" href="report.html" data-keepnolog>'
            '<b>📊 このサイトを運用した場合の分析レポートの例を見る →</b>'
            '<span>予約がどう分析され、次の一手がどう出るかを、実際の形でご覧いただけます</span></a>') if to_report else ""
    return (f'<section class="contact" aria-label="お問い合わせ"><div class="in">'
            f'<h2>気になった方は、電話かメールでご連絡ください</h2>'
            f'<div class="price"><span class="k">{html.escape(PRICE_MAIN[0])}</span><span class="y">{tax(PRICE_MAIN[1])}</span></div>'
            f'<ol class="plans">{plans}</ol>'
            f'{lead}'
            f'<p>この見本の仕組みについて、三浦がご説明します。</p>'
            f'<div class="row"><a class="cb tel" href="tel:{tel_raw}">📞 電話する</a>'
            f'<a class="cb mail" href="mailto:{CONTACT_MAIL}?subject={subj}&amp;body={body}">✉ メールで聞く</a></div>'
            f'{note}</div></section>')


PHOTO_COL = "写真（オーナー提供のURL・最大3つを「、」でつなぐ）"  # 候補シートの68列目
PHOTO_FRAME = '<div class="photo" role="img" aria-label="写真の枠"><span>お店の写真に差し替えます</span></div>'


def photo_urls(text):
    """「、」区切りの URL を最大3つ。https の URL（確認用に data:image/ も）だけを通す。"""
    out = []
    for u in re.split(r"[、\s]+", (text or "").strip()):
        if re.match(r"^(https://[^\s\"'<>]+|data:image/[a-z+]+;[^\s\"'<>]+)$", u) and u not in out:
            out.append(u)
    return out[:3]


def photo_credit(row):
    """メモ列の「写真提供：○○」から提供者名を取る。無ければ空。"""
    m = re.search(r"写真提供[:：]\s*([^、。,\n]+)", row.get("メモ", ""))
    return m.group(1).strip() if m else ""


def photo_block(urls, credit=""):
    """1枚目を上の大きな枠に、2〜3枚目を小さく横に。src は URL を参照するだけ（保存・複製しない）。"""
    if not urls:
        return PHOTO_FRAME
    back = "this.parentNode.classList.remove('has');this.remove()"
    img = lambda u, a, extra="": (f'<img src="{html.escape(u, quote=True)}" alt="{a}" loading="lazy" decoding="async" '
                                  f'referrerpolicy="no-referrer"{extra}>')
    main = (f'<div class="photo has" role="img" aria-label="お店の写真"><span>お店の写真に差し替えます</span>'
            + img(urls[0], "お店の写真", f' onerror="{back}"') + "</div>")
    thumbs = "".join(img(u, f"お店の写真{i + 2}", ' onerror="this.remove()"') for i, u in enumerate(urls[1:]))
    note = "写真：お店が公開している物を参照しています。不要ならすぐ消します" + (f"（提供：{html.escape(credit)}）" if credit else "")
    return main + f'<div class="thumbs">{thumbs}</div><p class="credit">{note}</p>'


def make_report_v2(row, slug, color):
    """SMS 用のレポート（housecleaning/report_template.html）。中身は 9/24〜30 の配信の分析（表示は仮の数字）。店名だけ差し込む。"""
    from urllib.parse import quote
    s = open(os.path.join(DEMO, "report_template.html"), encoding="utf-8").read()
    plain = display_name(row["店名"].strip())
    fill = {
        "COLOR": color, "SHOP": html.escape(plain), "SHEET_URL": html.escape(SHEET_URL),
        "BANNER_CSS": BANNER_CSS, "BANNER": contact_banner(plain, slug), "SIG_TEL": CONTACT_TEL + ("（仮）" if CONTACT_TEL_IS_TEMP else ""),
        "COMPANY": company_lines(),
        "STOP_SUBJECT": quote(f"不要（合言葉 {slug}）"),
        "STOP_BODY": quote(f"今後のご案内は不要です。\n返事：不要\n合言葉：{slug}\n（このまま送ってください）"),
        "SCRIPTS": f'<script src="../../beacon.js" data-shop="{slug}" data-page="report"></script>',
    }
    for k, v in fill.items():
        s = s.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_0-9]+\}\}", s)
    if left:
        raise SystemExit(f"差し込み残り：{left}")
    return s


def make_yoyaku(row, prices, slug, color, mode=None, photos=""):
    s = open(os.path.join(DEMO, "yoyaku_template.html"), encoding="utf-8").read()
    no = row.get("番号", "").strip()
    shop = html.escape(display_name(row["店名"].strip()))
    tel = (row.get("電話", "") or row.get(MOBILE_COL, "")).strip()
    tel_raw = re.sub(r"[^0-9+]", "", tel.translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    star, cnt, seen = row.get("Googleの★", "").strip(), row.get("口コミ件数", "").strip(), row.get("確認した日", "").strip()
    ym = f"{seen[:4]}年{int(seen[5:7])}月時点" if re.match(r"\d{4}-\d{2}", seen) else "2026年10月時点"
    try:
        star_txt = f"{float(star):.1f}"
    except ValueError:
        star_txt = star
    star_line = (f'<p class="star">Googleの口コミ <b>★{html.escape(star_txt)}</b>（{html.escape(cnt)}件・{ym}）</p>'
                 if star and cnt else "")
    city = row.get("住所（市区町村まで）", "").strip() or row.get("都道府県", "").strip()
    area = row.get("対応エリア（区名などを「、」でつなぐ）", "").strip() or (f"{city}とその周辺（お店に合わせて直します）" if city else "（お店の対応エリアを入れます）")
    hours = row.get("営業日時の特徴（年中無休・平日のみ・土日可・不明）", "").strip()
    hours = hours if hours and hours != "不明" else "（お店の営業日時を入れます）"
    mode = page_mode(row, mode)
    if mode == "menu":
        menu, real = yoyaku_menu(row, prices, no)
        page = dict(mode="menu", step="メニュー", title="メニューを選ぶ", next="希望日を選ぶ", tabs=menu,
                    lead="＋を押すと料金がその場で変わります。" + ("エアコンと水回りは、上のボタンで切りかえられます。" if len(menu) > 1 else ""),
                    note=(f"料金は{display_name(row['店名'].strip())}様が公表している料金です（税込）。「〜」はその金額から、「要見積」はお見積りになります。" if real else
                          f"料金はすべて仮です。{display_name(row['店名'].strip())}様の料金表に合わせて直します。"))
    else:
        names = [p.get("メニュー名（店の表記どおり・短く）", "").strip() for p in prices
                 if p.get("店番号（候補シートの番号）", "").strip() == no] or None
        items = [dict(name=n, price=0, kind="要見積", sub="") for n in names if n] if names else \
            [dict(name=n, price=0, kind="要見積", sub=x) for n, x in (CONSULT_ITEMS if mode == "consult" else VISIT_ITEMS)]
        page = (dict(mode="consult", step="ご相談", title="相談したい工事を選ぶ", next="希望日を選ぶ", budgets=BUDGETS,
                     lead="いくつでも選べます。お見積もりは無料です。", note="内容は仮です。お店の扱う工事に合わせて直します。", tabs=[dict(label="工事", items=items)])
                if mode == "consult" else
                dict(mode="visit", step="ご用件", title="来店の目的を選ぶ", next="来店の希望日を選ぶ", barLabel="来店の目的", single=True,
                     lead="あてはまる物を1つ選んでください。", note="内容は仮です。お店のご案内に合わせて直します。", tabs=[dict(label="目的", items=items)]))
    js = json.dumps(page, ensure_ascii=False).replace("</", "<\\/")
    from urllib.parse import quote
    fill = {
        "COLOR": color, "SHOP": shop, "TEL": html.escape(tel or "（電話番号）"), "TEL_RAW": tel_raw,
        "TEL_LABEL": "無料電話" if tel_raw.startswith(("0120", "0800")) else "電話する",
        "STAR_LINE": star_line, "AREA": html.escape(area), "AREA_EX": html.escape(city), "HOURS": html.escape(hours),
        "PAGE_JSON": js, "SLUG": slug,
        "STOP_SUBJECT": quote(f"不要（合言葉 {slug}）"),
        "STOP_BODY": quote(f"今後のご案内は不要です。\n返事：不要\n合言葉：{slug}\n（このまま送ってください）"),
        "BANNER_CSS": BANNER_CSS, "BANNER": contact_banner(display_name(row["店名"].strip()), slug, to_report=True),
        "COMPANY": company_lines(),
        "PHOTO": photo_block(photo_urls(photos), photo_credit(row)),
        "BAND_PHOTO": "写真はお店が公開している物を参照しています" if photo_urls(photos) else "写真は仮の物です",
        "SCRIPTS": f'<script src="../../beacon.js" data-shop="{slug}" data-page="yoyaku"></script>',
    }
    for k, v in fill.items():
        s = s.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z_0-9]+\}\}", s)
    if left:
        raise SystemExit(f"差し込み残り：{left}")
    return s


def has_phone(row):
    return bool(re.sub(r"\D", "", row.get(MOBILE_COL, "") or row.get("電話", "")))


ADDR_COL = "郵送用の住所（〒から番地まで・店が公表している物だけ）"
LANDING = "miumiumiu4.github.io/arigatou-bunseki/housecleaning/"
# 日本郵便 Webレター「差込データ」の1〜14列目（宛先）。差込データファイル作成ルールの項目名。
# 並びは公式のフォーマット（csv/1.csv）の1行目で確かめること（初回の Chrome プロンプトで確認）。
WL_HEAD = ["郵便番号(3桁)", "郵便番号(4桁)", "都道府県名", "市区町村名", "町域名", "丁目・番地等",
           "アパート・ビル・マンション", "会社名", "敬称(会社用)", "部署名", "敬称(部署用)", "肩書・役職", "お名前(漢字)", "敬称"]
WL_MERGE = ["宛名行", "評価", "合言葉", "差出日"]
PREFS = r"(北海道|東京都|京都府|大阪府|..県|...県)"


def split_address(text):
    """「〒233-0002 神奈川県横浜市港南区上大岡西1-2-3 ○○ビル2F」を Webレターの宛先の欄に分ける。分けられなければ None。"""
    t = re.sub(r"\s+", " ", text.replace("－", "-").replace("ー", "-").replace("−", "-")).strip()
    t = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    m = re.match(r"〒?\s*(\d{3})-?(\d{4})\s*" + PREFS + r"(.+?郡.+?[町村]|.+?市(?:.+?区)?|.+?区|.+?[町村])(.*)$", t)
    if not m:
        return None
    zip3, zip4, pref, city, rest = m.groups()
    rest = rest.strip()
    n = re.search(r"\d", rest)
    town, num = (rest[:n.start()], rest[n.start():]) if n else (rest, "")
    num, _, bldg = num.partition(" ")
    if not town and not num:
        return None
    return [zip3, zip4, pref, city, town.strip(), num.strip(), bldg.strip()]


def jp_date(d):
    d = datetime.date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.year}年{d.month}月{d.day}日"


def write_letters(folder, pairs):
    """送る日ごとに Webレターの差込データ（Shift_JIS）を書く。1行＝1通。"""
    os.makedirs(folder, exist_ok=True)
    by_day = {}
    for row, m in pairs:
        a = split_address(row.get(ADDR_COL, ""))
        name = row["店名"].strip()
        seen = row.get("確認した日", "").strip()
        when = f"、{seen[:4]}年{int(seen[5:7])}月時点" if re.match(r"\d{4}-\d{2}", seen) else ""
        star, cnt = row.get("Googleの★", "").strip(), row.get("口コミ件数", "").strip()
        merge = [f"{name}　店主様"[:50], f"★{star}・口コミ{cnt}件（Googleマップ{when}）" if star and cnt else "",
                 m["合言葉"], jp_date(m["手紙を送る日"])]
        by_day.setdefault(m["手紙を送る日"], []).append(a + [name[:35], "御中", "", "", "", "", ""] + merge)
    for day, lines in by_day.items():
        path = os.path.join(folder, f"手紙_差し込み_{day}.csv")
        with open(path, "w", encoding="shift_jis", errors="replace", newline="") as f:
            w = csv.writer(f)
            w.writerow(WL_HEAD + WL_MERGE)
            w.writerows(lines)
        print(f"手紙 {len(lines)}通：{path}", file=sys.stderr)


def load(path):
    if not path:
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


MF = ["番号", "店名", "合言葉", "予約フォームのURL", "レポートのURL", "作った日", "状態", "送り方", "手紙を送る日", "写真"]


def save_manifest(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MF)
        w.writeheader()
        w.writerows(rows)


def new_slug(taken):
    abc = "abcdefghjkmnpqrstuvwxyz23456789"  # 手紙で打ち込むので 0/o・1/l/i は使わない
    while True:
        s = "".join(secrets.choice(abc) for _ in range(8))
        if s not in taken:
            return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates")
    ap.add_argument("--prices")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--drafts")
    ap.add_argument("--senders", default="")
    ap.add_argument("--per-day", type=int, default=30)
    ap.add_argument("--letters", help="手紙の差し込みCSVを置くフォルダ（送る日ごとに1ファイル）")
    ap.add_argument("--letters-per-day", type=int, default=15)
    ap.add_argument("--letters-only", action="store_true", help="メールは使わず、全部の店を手紙で送る（2026-10-20 三浦さん「ひとまず手紙作戦オンリー」）")
    ap.add_argument("--start", default=str(datetime.date.today()))
    ap.add_argument("--remove", help="消す店の番号（カンマ区切り）")
    ap.add_argument("--yoyaku", action="store_true", help="SMS 用：booking.html の代わりに yoyaku.html（参考サイトの4段の形）を作る。メール下書き・手紙は作らない")
    ap.add_argument("--color", default="#13294b", help="--yoyaku のテーマ色（候補シートに「テーマ色」列があればそちらが先）")
    ap.add_argument("--mode", choices=["menu", "consult", "visit"], help="--yoyaku の1段目を業種によらず固定する（省くと業種から決める）")
    ap.add_argument("--photos", action="append", default=[], metavar="番号=URL、URL",
                    help="--yoyaku の写真を店ごとに指定（くり返し可。最大3つを「、」でつなぐ）。一覧.csv の「写真」列・候補シートの68列目より先。"
                         "空（番号=）にすると写真を外す")
    ap.add_argument("--only", help="作る店の番号（カンマ区切り）。省くと条件に合う全部の店")
    a = ap.parse_args()

    manifest = load(a.manifest) if os.path.exists(a.manifest) else []
    by_no = {m["番号"]: m for m in manifest}

    if a.remove:
        for no in a.remove.split(","):
            m = by_no.get(no.strip())
            if not m:
                print(f"番号 {no} は一覧にありません", file=sys.stderr)
                continue
            shutil.rmtree(os.path.join(OUT, m["合言葉"]), ignore_errors=True)
            m["状態"] = "消した"
            print(f"消しました：{m['店名']}")
        save_manifest(a.manifest, manifest)
        return

    prices = load(a.prices)
    senders = [x.strip() for x in a.senders.split(",") if x.strip()] or ["【送信元アドレス】"]
    made, skipped, drafts = [], [], []
    for row in load(a.candidates):
        no, name = row.get("番号", "").strip(), row.get("店名", "").strip()
        why = ("優先度がA以外" if row.get("優先度（A・B・C）", "").strip() != "A" else
               "営業お断り" if row.get("営業お断り（なし・あり）", "").strip() == "あり" else
               "チェーン" if row.get("チェーンか（いいえ・はい）", "").strip() == "はい" else
               "きらりん・エアタクミ" if any(x in name for x in EXCLUDE_NAMES) else
               "番号の指定外" if a.only and no not in [x.strip() for x in a.only.split(",")] else
               "返事が「不要」" if a.yoyaku and "不要" in (row.get("返事（興味あり・保留・不要・なし）", "") + row.get("返事", "")) else
               "電話番号がない" if a.yoyaku and not has_phone(row) else
               "" if a.yoyaku else
               "郵送用の住所がない（手紙だけで送る）" if a.letters_only and not split_address(row.get(ADDR_COL, "")) else
               "アドレスも郵送用の住所もない" if "@" not in row.get("店が公表しているメールアドレス", "") and not split_address(row.get(ADDR_COL, "")) else
               "以前に消した店" if by_no.get(no, {}).get("状態") == "消した" else "")
        if not no or not name or why:
            skipped.append((no, name, why or "番号か店名が空"))
            continue
        m = by_no.get(no) or {"番号": no, "店名": name, "合言葉": new_slug({x["合言葉"] for x in manifest}),
                              "作った日": str(datetime.date.today()), "状態": "作った"}
        if no not in by_no:
            manifest.append(m)
            by_no[no] = m
        slug = m["合言葉"]
        if a.yoyaku:
            d = os.path.join(OUT, slug)
            os.makedirs(d, exist_ok=True)
            color = row.get("テーマ色", "").strip()
            color = color if re.fullmatch(r"#[0-9a-fA-F]{6}", color) else a.color
            # 写真の URL：--photos ＞ 一覧.csv の「写真」列 ＞ 候補シートの68列目。参照するだけでファイルは保存しない
            given = dict(x.split("=", 1) for x in a.photos if "=" in x)
            if no in given:
                m["写真"] = given[no].strip()
            photos = m.get("写真", "") or row.get(PHOTO_COL, "")
            open(os.path.join(d, "yoyaku.html"), "w", encoding="utf-8").write(make_yoyaku(row, prices, slug, color, a.mode, photos))
            open(os.path.join(d, "report.html"), "w", encoding="utf-8").write(make_report_v2(row, slug, color))
            m["予約フォームのURL"] = BASE_URL + slug + "/yoyaku.html"
            m["レポートのURL"] = BASE_URL + slug + "/report.html"
            m["送り方"] = "SMS"
            made.append(m)
            continue
        aircon = is_aircon_only(row)
        menu = menu_for(row, shop_prices(prices, no))
        d = os.path.join(OUT, slug)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "booking.html"), "w", encoding="utf-8").write(make_booking(row, menu, slug, aircon))
        open(os.path.join(d, "report.html"), "w", encoding="utf-8").write(make_report(row, menu, slug, aircon))
        m["予約フォームのURL"] = BASE_URL + slug + "/booking.html"
        m["レポートのURL"] = BASE_URL + slug + "/report.html"
        made.append(m)

    if a.yoyaku:
        save_manifest(a.manifest, manifest)
        print(json.dumps({"作った": [{"番号": m["番号"], "URL": m["予約フォームのURL"], "確認用": m["予約フォームのURL"] + "?nolog"} for m in made],
                          "外した": [{"番号": n, "店名": s, "理由": r} for n, s, r in skipped]}, ensure_ascii=False, indent=1))
        return
    start = datetime.date.fromisoformat(a.start)
    rows = {r.get("番号", "").strip(): r for r in load(a.candidates)}
    mails = [] if a.letters_only else [m for m in made if "@" in rows[m["番号"]].get("店が公表しているメールアドレス", "")]
    letters = [m for m in made if m not in mails]
    for m in made:
        m["送り方"] = "メール" if m in mails else "手紙"
    for i, m in enumerate(letters):
        day = start + datetime.timedelta(days=i // a.letters_per_day)
        m["手紙を送る日"] = str(day)
    if a.letters and letters:
        write_letters(a.letters, [(rows[m["番号"]], m) for m in letters])
    for i, m in enumerate(mails):
        row = rows[m["番号"]]
        sender = senders[i % len(senders)]
        subj, body = draft(row, m["予約フォームのURL"], m["レポートのURL"], sender)
        drafts.append({"番号": m["番号"], "店名": m["店名"], "送る日": str(start + datetime.timedelta(days=i // a.per_day)),
                       "送信元": sender, "宛先": row["店が公表しているメールアドレス"].strip(),
                       "アドレスの出典URL": row.get("アドレスの出典URL", ""), "件名": subj, "本文": body,
                       "確認用URL（開封に数えない）": m["レポートのURL"] + "?nolog"})
    save_manifest(a.manifest, manifest)
    if a.drafts and drafts:
        with open(a.drafts, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(drafts[0].keys()))
            w.writeheader()
            w.writerows(drafts)
    print(json.dumps({"作った": len(made), "外した": [{"番号": n, "店名": s, "理由": r} for n, s, r in skipped]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
