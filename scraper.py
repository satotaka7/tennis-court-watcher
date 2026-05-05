"""Webスクレイピング"""

import re
import sys
from datetime import date

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import START_URL, is_debug_slots
from models import AvailableSlot


def _extract_week_slots_from_page_eval() -> str:
    """Playwright の page.evaluate に渡す JS。

    td.id="YYYYMMDD_N" と class="available" を直接使って空きスロットを抽出する。
    ヘッダーのテキスト解析は行わない。
    """
    return r"""
      () => {
        const toHalfDigits = (s) =>
          (s || '').replace(/[０-９]/g, (c) =>
            String.fromCharCode(c.charCodeAt(0) - 0xfee0)
          );

        // class="available" か、<span> に正の整数を持つセルを空きと判定
        const isAvailable = (td) => {
          if (td.classList.contains('available')) return true;
          for (const span of td.querySelectorAll('span')) {
            const t = (span.textContent || '').trim();
            if (/^\d+$/.test(t) && parseInt(t, 10) > 0) return true;
          }
          return false;
        };

        const results = [];
        const seen = new Set();

        // id="YYYYMMDD_N" を持つ全 td を対象にする
        for (const td of document.querySelectorAll('td[id]')) {
          const m = (td.id || '').match(/^(\d{4})(\d{2})(\d{2})_\d+$/);
          if (!m) continue;
          if (!isAvailable(td)) continue;
          const dayIso = `${m[1]}-${m[2]}-${m[3]}`;

          // 行の <th> から時間ラベルを取得（例: "　９時" → "9時"）
          const tr = td.closest('tr');
          const th = tr ? tr.querySelector('th') : null;
          if (!th) continue;
          const raw = toHalfDigits((th.textContent || '').replace(/\s+/g, ' ').trim());
          const lm = raw.match(/(\d{1,2})時/);
          if (!lm) continue;
          const label = `${lm[1]}時`;

          const key = `${dayIso}_${label}`;
          if (seen.has(key)) continue;
          seen.add(key);
          results.push({ dayIso, label });
        }

        return results;
      }
    """


def _evaluate_week_slots_everywhere(page) -> list[dict[str, str]]:
    """空き表が iframe 内にある場合に備え、全フレームで evaluate してマージする"""

    js = _extract_week_slots_from_page_eval()
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    frames: list = [page.main_frame]
    try:
        frames.extend([f for f in page.frames if f is not page.main_frame])
    except Exception:
        pass

    for fr in frames:
        try:
            chunk = fr.evaluate(js)
        except Exception:
            continue
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if not isinstance(item, dict):
                continue
            iso = (item.get("dayIso") or "").strip()
            lab = (item.get("label") or "").strip()
            k = (iso, lab)
            if k in seen:
                continue
            seen.add(k)
            merged.append(item)

    return merged


def _click_home_vacancy_search(page) -> bool:
    """ページ先頭にある「検索」ではなく、空き状況検索ブロック内の検索を優先して押す"""

    scoped = page.locator("xpath=(//*[contains(., '空き状況検索')])[1]")
    try:
        if scoped.count() > 0:
            scoped.locator("input[type='submit']").first.click(timeout=8000)
            return True
    except Exception:
        pass

    try:
        if scoped.count() > 0:
            scoped.locator("button").filter(has_text=re.compile(r"\s*検索\s*")).first.click(
                timeout=8000
            )
            return True
    except Exception:
        pass

    for search_selector in [
        "button:has-text('検索')",
        "input[type='submit']",
        "text=検索",
    ]:
        try:
            page.locator(search_selector).first.click(timeout=8000)
            return True
        except PlaywrightTimeoutError:
            continue

    return False


def _select_option_in_any_select(page, *, option_label: str) -> None:
    """“種目/公園” の select を id/name で固定できないため、
    option の中身に目的ラベルが含まれる select を探して選択する
    """
    selects = page.locator("select")
    for i in range(selects.count()):
        s = selects.nth(i)
        try:
            options_text = (s.locator("option").all_text_contents() or [])
        except Exception:
            continue
        if any(option_label in (t or "") for t in options_text):
            s.select_option(label=option_label)
            return

    # combobox role 経由でも最後に試す
    for cb in page.get_by_role("combobox").all():
        try:
            cb.select_option(label=option_label)
            return
        except Exception:
            continue


def _fill_date_input(page, use_day: date) -> bool:
    """利用日を入力"""
    date_str_date_input = use_day.isoformat()
    date_str_text_input = use_day.strftime("%Y/%m/%d")

    filled = False
    for date_selector in [
        "input[type='text']",
        "input[name*='date' i]",
        "input[name*='Day' i]",
    ]:
        try:
            date_inputs = page.locator(date_selector)
            if date_inputs.count() == 0:
                continue
            first = date_inputs.first
            input_type = (first.get_attribute("type") or "").lower()
            first.fill(
                date_str_date_input if input_type == "date" else date_str_text_input,
                timeout=5000,
            )
            filled = True
            break
        except PlaywrightTimeoutError:
            continue

    return filled


def fetch_availability_slots(
    *,
    use_day: date,
    slow_down_ms: int = 0,
    park_label: str,
    sport_label: str,
) -> list[AvailableSlot]:
    """
    都立公園スポーツレクリエーション予約システムで **1回** 「利用日」を指定して検索し、
    画面上の **週表示** マトリックスから空きセル（数字・● 等）を列挙する。

    通知対象は「土日祝」に絞る。過剰アクセスを避けるため日付ごとの検索ループは行わない。
    """

    from date_utils import is_weekend_or_holiday

    slots: list[AvailableSlot] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_down_ms)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(30000)

        def goto_home() -> None:
            try:
                page.goto(START_URL, wait_until="domcontentloaded")
            except Exception as e:
                if "Download is starting" not in str(e):
                    raise
            # ホームから「施設の予約」を開く（テキストが変わっても動くよう複数候補）。
            for selector in [
                "text=施設の予約",
                "a:has-text('施設の予約')",
            ]:
                try:
                    page.locator(selector).first.click(timeout=5000)
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                    break
                except PlaywrightTimeoutError:
                    continue

        goto_home()

        filled = _fill_date_input(page, use_day)

        try:
            _select_option_in_any_select(page, option_label=sport_label)
            _select_option_in_any_select(page, option_label=park_label)
        except Exception:
            context.close()
            browser.close()
            return []

        if not filled:
            context.close()
            browser.close()
            return []

        if not _click_home_vacancy_search(page):
            context.close()
            browser.close()
            return []

        try:
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            pass

        try:
            # 「施設ごと」タブをクリックして週表示に切り替える
            page.locator("a, button, [role='tab']").filter(has_text="施設ごと").first.click(
                timeout=5000
            )
        except Exception:
            pass

        try:
            # 週表示タブに切り替える
            page.locator("a, button, label, [role='tab']").filter(
                has_text=re.compile(r"週.?表示")
            ).first.click(timeout=5000)
        except Exception:
            pass

        try:
            # AJAX でセルが埋まるまで待つ（週表示テーブル内に id 付き td が現れるのを確認）
            page.wait_for_selector("#week-info td[id]", timeout=30000)
        except PlaywrightTimeoutError:
            pass

        if is_debug_slots():
            print(f"[DEBUG] URL: {page.url}", file=sys.stderr)
            print(f"[DEBUG] title: {page.title()}", file=sys.stderr)
            td_count = page.evaluate("() => document.querySelectorAll('td[id]').length")
            avail_count = page.evaluate("() => document.querySelectorAll('td.available').length")
            week_table = page.evaluate("() => !!document.getElementById('week-info')")
            print(f"[DEBUG] td[id]={td_count}, td.available={avail_count}, week-info={week_table}", file=sys.stderr)

        raw = _evaluate_week_slots_everywhere(page)

        if is_debug_slots():
            print(f"[DEBUG_SLOTS] raw_len={len(raw)} sample={raw[:8]!r}", file=sys.stderr)

        for item in raw:
            iso = (item.get("dayIso") or "").strip()
            lab = (item.get("label") or "").strip()
            if not lab:
                continue
            if not iso:
                continue
            try:
                slot_day = date.fromisoformat(iso)
            except ValueError:
                continue

            if not is_weekend_or_holiday(slot_day):
                continue

            slots.append(AvailableSlot(day=slot_day, label=lab))

        context.close()
        browser.close()

    # 重複排除
    uniq: dict[tuple[date, str], AvailableSlot] = {}
    for s in slots:
        uniq[(s.day, s.label)] = s
    return list(uniq.values())