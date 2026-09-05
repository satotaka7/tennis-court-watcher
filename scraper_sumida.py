"""墨田区公共施設予約システムのスクレイパー"""

import sys
from datetime import date
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
import jpholiday

from models import AvailableSlot

START_URL = "https://yoyaku03.city.sumida.lg.jp/user/Home"

# 時間帯別ページから空きスロットを抽出する JS
_JS_EXTRACT_TIME_SLOTS = r"""
() => {
    const results = [];
    for (const eventsContainer of document.querySelectorAll('.events > div')) {
        const dateDiv = eventsContainer.querySelector('.events-date');
        if (!dateDiv) continue;
        const m = dateDiv.textContent.match(/(\d{4})年\s*(\d+)月(\d+)日/);
        if (!m) continue;
        const dateStr = `${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`;

        for (const group of eventsContainer.querySelectorAll('.events-group')) {
            const roomEl = group.querySelector('.room-name span:not(.object-description)');
            const court = roomEl ? roomEl.textContent.trim() : '';
            if (!court) continue;

            for (const cellDiv of group.querySelectorAll('.display-cells > div')) {
                const label = cellDiv.querySelector('label');
                if (!label) continue;
                const statusSpan = label.querySelector('.sr-only');
                const status = statusSpan ? statusSpan.textContent.trim() : '';
                // 空きセルの sr-only は "N時からM時まで" 形式（"空きあり" ではない）
                if (!status || status === '空きなし') continue;

                const timeFromInput = cellDiv.querySelector('input[name*="TimeFrom"]');
                if (!timeFromInput) continue;
                const timeFromVal = parseInt(timeFromInput.value, 10);
                if (isNaN(timeFromVal)) continue;

                const hours = Math.floor(timeFromVal / 100);
                const minutes = timeFromVal % 100;
                results.push({
                    date: dateStr,
                    court,
                    time: `${hours}:${minutes.toString().padStart(2,'0')}`,
                });
            }
        }
    }
    return results;
}
"""


def fetch_availability_slots_sumida(*, slow_down_ms: int = 0) -> list[AvailableSlot]:
    """
    墨田区の硬式テニスコート（運動場・公園運動場）の空き状況を取得する。
    土日祝のみ、1週間先までを対象。
    時間帯別ページの○（空きあり）スロットを返す。
    """
    slots: list[AvailableSlot] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_down_ms)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(30000)

        try:
            # 1. ホーム
            page.goto(START_URL)
            page.wait_for_load_state("networkidle")

            # 2. 「利用目的から探す」タブ → 屋外スポーツが表示されるまで待機
            page.locator("li.tab-name:has-text('利用目的から探す')").first.click()
            page.get_by_text("屋外スポーツ", exact=True).first.wait_for(state="visible")

            # 3. 屋外スポーツ → 硬式テニスが表示されるまで待機
            page.get_by_text("屋外スポーツ", exact=True).first.click()
            page.get_by_text("硬式テニス", exact=True).first.wait_for(state="visible")

            # 4. 硬式テニス → 検索ボタンが表示されるまで待機
            page.get_by_text("硬式テニス", exact=True).first.click()
            page.get_by_role("button", name="検索").first.wait_for(state="visible")

            # 5. 検索 → 施設選択ページへ遷移
            page.get_by_role("button", name="検索").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)

            # 6. 全施設（運動場・公園運動場）をチェック
            page.wait_for_selector(
                "input[name^='SelectFacilities'][name$='.IsChecked'][type='checkbox']",
                timeout=15000
            )
            facility_cbs = page.locator(
                "input[name^='SelectFacilities'][name$='.IsChecked'][type='checkbox']"
            ).all()
            print(f"[sumida] 施設チェックボックス数: {len(facility_cbs)}", file=sys.stdout)
            for cb in facility_cbs:
                cb.check(force=True)

            # 7. 次へ進む → SelectDays へ遷移
            page.get_by_role("button", name="次へ進む").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)
            print(f"[sumida] step7後 URL: {page.url}", file=sys.stdout)
            if "AvailabilityCheckApplySelectDays" not in page.url:
                print("[sumida] SelectDaysへの遷移失敗", file=sys.stdout)
                return slots

            # 7.5. 表示期間「1週間」選択
            # Week チェックボックスは Vue のリアクティブ状態更新の問題で
            # JS から確実に操作できないため操作しない。Python 側で土日祝フィルタリングを行う。
            page.wait_for_selector(
                "input[name='SearchCondition.Week']",
                state="attached",
                timeout=15000
            )
            page.evaluate("""
() => {
    for (const lbl of document.querySelectorAll('label.custom-control-label')) {
        if (lbl.textContent.trim() === '1週間') { lbl.click(); break; }
    }
}
""")

            # 9. 表示 → グリッドのセルが描画されるまで待機（固定ウェイト不要）
            page.locator("button.btn-secondary:has-text('表示')").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)
            page.wait_for_selector(
                "form[name='myform'] tr td.startdate",
                timeout=10000
            )
            print(f"[sumida] 施設別空き状況 URL: {page.url}", file=sys.stdout)

            # 10. 対象コートのセル（UseDate 付き）を全て取得
            all_cells = page.evaluate("""
() => {
    const TARGET_COURTS = [
        '文花テニスコート', '錦糸公園テニスコート',
        '堤通公園テニスコート', '大横川親水公園テニスコート'
    ];
    const cells = [];
    const form = document.forms.namedItem('myform');
    if (!form) return [];
    for (const tr of form.querySelectorAll('tr')) {
        const startdate = tr.querySelector('td.startdate');
        if (!startdate) continue;
        const courtName = startdate.textContent.trim();
        if (!TARGET_COURTS.some(kw => courtName.includes(kw))) continue;
        for (const td of tr.querySelectorAll('td[data-toggle="buttons"]')) {
            const h = td.querySelector('input[type="hidden"][name*="IsChecked"]');
            const ud = td.querySelector('input[name*="UseDate"]');
            if (h && ud) cells.push({ name: h.name, useDate: ud.value.slice(0, 10) });
        }
    }
    return cells;
}
""")
            # Python 側で土日祝のみに絞り込む
            def _is_weekend_or_holiday(date_str: str) -> bool:
                try:
                    d = date.fromisoformat(date_str)
                    return d.weekday() >= 5 or jpholiday.is_holiday(d)
                except ValueError:
                    return False

            cell_names = [c["name"] for c in all_cells if _is_weekend_or_holiday(c["useDate"])]
            print(
                f"[sumida] 対象セル数（全体:{len(all_cells)}, 土日祝:{len(cell_names)}）",
                file=sys.stdout
            )
            if not cell_names:
                print("[sumida] 対象コートのセルが見つかりません。", file=sys.stdout)
                return slots

            # 11+12. 30件ずつバッチ処理（サーバー制限 E-203-000018 対策）
            BATCH_SIZE = 30
            selectdays_url = page.url

            for batch_start in range(0, len(cell_names), BATCH_SIZE):
                batch = cell_names[batch_start:batch_start + BATCH_SIZE]
                batch_num = batch_start // BATCH_SIZE + 1
                print(f"[sumida] バッチ{batch_num}: {len(batch)}件", file=sys.stdout)

                page.set_default_timeout(30000)
                api_result = page.evaluate("""
async (batch) => {
    const form = document.forms.namedItem('myform');
    if (!form) return { error: 'myform not found' };
    const data = new FormData(form);
    for (const h of form.querySelectorAll('input[type="hidden"][name*="IsChecked"]'))
        data.set(h.name, '');
    for (const name of batch) data.set(name, 'true');
    try {
        const resp = await axios.post('AvailabilityCheckApplySelectDays/Next', data);
        let d = resp.data;
        if (typeof d === 'string') { try { d = JSON.parse(d); } catch(_) {} }
        const isObj = d && typeof d === 'object';
        return {
            result: isObj ? (d.Result ?? null) : null,
            info:   isObj ? (d.Information ?? null) : null,
        };
    } catch(e) {
        return { error: String(e) };
    }
}
""", batch)
                page.set_default_timeout(15000)
                print(f"[sumida] バッチ{batch_num} API応答: {api_result}", file=sys.stdout)

                if not isinstance(api_result, dict) or api_result.get("error"):
                    print(f"[sumida] バッチ{batch_num} エラー: {api_result}", file=sys.stdout)
                elif api_result.get("result") != "Ok":
                    print(f"[sumida] バッチ{batch_num} 失敗: {api_result}", file=sys.stdout)
                else:
                    info = api_result.get("info") or {}
                    redirect_url = info.get("MessageId") if isinstance(info, dict) else info
                    if not redirect_url:
                        print(f"[sumida] バッチ{batch_num} リダイレクトURL不明", file=sys.stdout)
                    else:
                        if not redirect_url.startswith("http"):
                            redirect_url = urljoin(selectdays_url, redirect_url)
                        page.goto(redirect_url)
                        page.wait_for_load_state("networkidle", timeout=20000)

                        raw = page.evaluate(_JS_EXTRACT_TIME_SLOTS)
                        print(f"[sumida] バッチ{batch_num} 抽出スロット数: {len(raw)}", file=sys.stdout)
                        for item in raw:
                            date_str = (item.get("date") or "").strip()
                            court = (item.get("court") or "").strip()
                            time_label = (item.get("time") or "").strip()
                            if not date_str or not court or not time_label:
                                continue
                            try:
                                slot_day = date.fromisoformat(date_str)
                            except ValueError:
                                continue
                            court_short = court.replace("テニスコート", " ").strip()
                            slots.append(AvailableSlot(day=slot_day, label=f"{court_short} {time_label}"))

                # 次バッチがある場合は SelectDays に戻る
                if batch_start + BATCH_SIZE < len(cell_names):
                    page.go_back()
                    page.wait_for_load_state("networkidle", timeout=20000)
                    if "AvailabilityCheckApplySelectDays" not in page.url:
                        print("[sumida] SelectDaysへの復帰失敗、以降のバッチをスキップ", file=sys.stdout)
                        break
                    page.wait_for_selector(
                        "td[data-toggle='buttons'] input[type='hidden'][name*='IsChecked']",
                        state="attached", timeout=15000
                    )

        except Exception as e:
            print(f"[sumida] スクレイピングエラー: {e}", file=sys.stdout)
        finally:
            context.close()
            browser.close()

    # 重複排除
    uniq: dict[tuple[date, str], AvailableSlot] = {}
    for s in slots:
        uniq[(s.day, s.label)] = s
    return list(uniq.values())
