"""Webスクレイピング"""

import re
import sys
from datetime import date, timedelta

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from config import START_URL, SPORT_LABEL, PARK_LABEL, is_debug_slots
from date_utils import seven_days_from_anchor
from models import AvailableSlot


def _extract_week_slots_from_page_eval() -> str:
    """Playwright の page.evaluate に渡す JS。

    検索結果の週表示テーブルから **空きセル**（数字・● 等）を列→日付に紐づけ、`{ dayIso, label }[]` を返す。

    現行サイトは「●」ではなく **空き面数の数字** と「x」で表記するため、それを空き判定に含める。
    """

    return r"""
      (params) => {
        const normalize = (s) => (s || '').replace(/\s+/g, ' ').trim();
        /** 利用日〜その翌6日まで（サイトが列に並べる順） */
        const weekDatesFromAnchor = (params && params.weekDatesFromAnchor) || [];

        /** 半角・全角数字を半角に */
        const toHalfDigits = (s) =>
          (s || '').replace(/[０-９]/g, (c) =>
            String.fromCharCode(c.charCodeAt(0) - 0xfee0)
          );

        /**
         * 週表示マトリックスの **単一セル** に「空き」があるか（table td 前提）。
         * サイトの script など長文へ誤ヒットしないよう長さ上限を設ける。
         */
        const cellHasAvailability = (raw) => {
          const sr = String(raw ?? '');
          if (!sr.trim() || sr.trim().length > 24) return false;
          const n = normalize(toHalfDigits(sr));
          if (!n) return false;
          if (/^[x×Ｘ]$/i.test(n)) return false;
          if (n === '-' || n === '―' || n === 'ー' || n === '--') return false;
          if (n.includes('●')) return true;
          if (/^\d+$/.test(n)) return parseInt(n, 10) > 0;
          return false;
        };

        /** ヘッダ文字列から M/D を拾って返す（年はページ側、アンカー年は呼び出し側で調整済み前提） */
        const parseMdFromText = (t) => {
          const n = normalize(t);
          let m =
            n.match(/^(\d{1,4})[/-](\d{1,2})[/-](\d{1,2})$/) ||
            n.match(/(\d{1,2})[／/](\d{1,2})/);
          if (!m) {
            const mJa = n.match(/(\d{1,2})月\s*(\d{1,2})\s*日?/);
            if (mJa) return { mm: Number(mJa[1]), dd: Number(mJa[2]) };
            return null;
          }
          if (m.length === 4 && m[3]) return { yyyy: Number(m[1]), mm: Number(m[2]), dd: Number(m[3]) };
          return { mm: Number(m[1]), dd: Number(m[2]) };
        };

        const pad2 = (n) => String(n).padStart(2, '0');

        /** @type {{ dayIso?: string }} */
        const ymdIso = (yyyy, mm, dd) => `${yyyy}-${pad2(mm)}-${pad2(dd)}`;

        const resolveDayIso = (hdrText, colIndex, fallbackFromWeek) => {
          const parsed = parseMdFromText(hdrText || '');
          if (parsed && parsed.yyyy != null && parsed.mm != null && parsed.dd != null) {
            return ymdIso(parsed.yyyy, parsed.mm, parsed.dd);
          }
          if (parsed && parsed.mm != null && parsed.dd != null && params.anchorYear != null) {
            const yyyy = Number(params.anchorYear);
            return ymdIso(yyyy, parsed.mm, parsed.dd);
          }
          if (
            fallbackFromWeek != null &&
            weekDatesFromAnchor[fallbackFromWeek]
          ) {
            return weekDatesFromAnchor[fallbackFromWeek];
          }
          return '';
        };

        const getCellText = (cell) => normalize(cell?.textContent || '');

        const findFirstDataColumnIndex = (table) => {
          const scanTheadCells = (cells) => {
            for (let i = 0; i < cells.length; i++) {
              const ht = cells[i].textContent || '';
              if (/[\/／月]/.test(ht) || /\(\s*[日月火水木金土]\s*\)/.test(ht)) {
                return i;
              }
            }
            /** 「30」「1」… のみの日付行（tbody の空き面数と混同しないよう thead でのみ使用） */
            const dayOnlyIdxs = [];
            for (let i = 0; i < cells.length; i++) {
              const stripped = normalize(
                toHalfDigits((cells[i].textContent || '').replace(/\([^)]*\)/g, '').trim())
              );
              if (/^\d{1,2}$/.test(stripped)) {
                const v = parseInt(stripped, 10);
                if (v >= 1 && v <= 31) dayOnlyIdxs.push(i);
              }
            }
            if (dayOnlyIdxs.length >= 5) return dayOnlyIdxs[0];
            return -1;
          };

          const scanBodyCellsLoose = (cells) => {
            for (let i = 0; i < cells.length; i++) {
              const ht = cells[i].textContent || '';
              if (/[\/／月]/.test(ht) || /\(\s*[日月火水木金土]\s*\)/.test(ht)) {
                return i;
              }
            }
            return -1;
          };

          const theadRows = Array.from(table.querySelectorAll('thead tr'));
          for (const hr of theadRows) {
            const cells = Array.from(hr.querySelectorAll('th, td'));
            const idx = scanTheadCells(cells);
            if (idx >= 0) return idx;
          }
          const fb = table.querySelector('tbody tr');
          if (fb) {
            const cells = Array.from(fb.querySelectorAll('th, td'));
            const idx = scanBodyCellsLoose(cells);
            if (idx >= 0) return idx;
          }
          return 1;
        };

        const getHeaderTextsForCells = (table) => {
          const theadRows = Array.from(table.querySelectorAll('thead tr'));
          const probeRows = theadRows.length
            ? theadRows.slice(-3)
            : [];

          /** @type {string[]} */
          const merged = [];

          probeRows.concat([table.querySelector('tbody tr')]).forEach((row) => {
            if (!row) return;
            Array.from(row.querySelectorAll('th, td')).forEach((cell, ix) => {
              const txt = getCellText(cell);
              if (!merged[ix] && txt) merged[ix] = txt;
              else if (!merged[ix]) merged[ix] = '';
            });
          });

          /** @returns {string[]} */
          return merged;
        };

        const getRowLabel = (cell) => {
          const tr = cell.closest('tr');
          if (!tr) return '';
          const th = tr.querySelector('th');
          const thText = getCellText(th);
          if (thText) return thText;
          const first = tr.querySelector('td');
          return getCellText(first);
        };

        /** @returns {{ dayIso?: string }} */
        const extractFromTable = (table) => {
          const rows = [];
          const firstDataCol = findFirstDataColumnIndex(table);
          const headerTexts = getHeaderTextsForCells(table);

          const cells = Array.from(table.querySelectorAll('td')).filter((td) =>
            cellHasAvailability(td.textContent || '')
          );

          cells.forEach((td) => {
            const ci = typeof td.cellIndex === 'number' ? td.cellIndex : -1;
            if (ci < firstDataCol) return;

            const hdr = headerTexts[ci] ? String(headerTexts[ci]) : '';
            const weekIdx = ci - firstDataCol;
            const dayIso =
              resolveDayIso(hdr, ci, weekIdx) ||
              '';

            const rowLabel = getRowLabel(td);
            const colLabelHdr = hdr;
            const selfText = getCellText(td);

            const parts = [];
            if (rowLabel) parts.push(rowLabel);
            if (
              colLabelHdr &&
              normalize(colLabelHdr) !== normalize(rowLabel)
            )
              parts.push(colLabelHdr);
            const extra = normalize(toHalfDigits(selfText).replace(/●/g, ''));
            if (/^\d+$/.test(extra)) parts.push(`空き ${extra}`);
            else if (extra) parts.push(extra);
            else parts.push('空き');

            const label = normalize(parts.join(' '));
            rows.push({ dayIso, label });
          });
          return rows;
        };

        /** 「空き」の div 総取りフォールバックはしない（ページ全体や script と誤検出する） */
        const allTbl = Array.from(document.querySelectorAll('table')).sort(
          (a, b) =>
            (b.querySelectorAll('td') || []).length - (a.querySelectorAll('td') || []).length,
        );

        /** td が多く、時間帯または x/数字がある表を優先して週間マトリックスとみなす */
        const tablesFlagged = allTbl.filter((t) => {
          const tdList = Array.from(t.querySelectorAll('td'));
          const tx = t.textContent || '';
          if (tx.includes('●')) return true;
          if (tdList.length < 10) return false;
          let shortLike = false;
          for (let i = 0; i < tdList.length; i++) {
            const s = (tdList[i].textContent || '').trim();
            if (cellHasAvailability(s)) {
              shortLike = true;
              break;
            }
            /** x / — 等のみ（空きなしセル）はマトリックスの証拠として使える */
            if (s.length <= 4 && /^[x×Ｘ－ー―]$/iu.test(normalize(toHalfDigits(s)))) {
              shortLike = true;
              break;
            }
          }
          if (!shortLike && /\d\s*[:：]\s*\d{2}|9\s*[:：]\s*00/.test(tx)) shortLike = true;
          return shortLike;
        });

        /** 見つからなければ td 数最多のテーブルを1枚だけ試す（Ajax 後にヘッダが薄いとき） */
        const tables =
          tablesFlagged.length > 0
            ? tablesFlagged
            : allTbl.length > 0 && allTbl[0].querySelectorAll('td').length >= 21
              ? [allTbl[0]]
              : [];

        /** @type {{ dayIso?: string }} */
        let out = [];
        for (const t of tables) {
          out = out.concat(extractFromTable(t));
        }

        return out.slice(0, 200);
      }
    """


def _evaluate_week_slots_everywhere(page, eval_params: dict) -> list[dict[str, str]]:
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
            chunk = fr.evaluate(js, eval_params)
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
) -> list[AvailableSlot]:
    """
    都立公園スポーツレクリエーション予約システムで **1回** 「利用日」を指定して検索し、
    画面上の **週表示** マトリックスから空きセル（数字・● 等）を列挙する。

    通知対象のみ従来通り「土日祝」に絞る。過剰アクセスを避けるため日付ごとの検索ループは行わない。
    """

    from date_utils import is_weekend_or_holiday

    week_from_anchor = seven_days_from_anchor(use_day)
    eval_params = {
        "weekDatesFromAnchor": [d.isoformat() for d in week_from_anchor],
        "anchorYear": use_day.year,
    }

    slots: list[AvailableSlot] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=slow_down_ms)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(30000)

        def goto_home() -> None:
            page.goto(START_URL, wait_until="domcontentloaded")
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
            _select_option_in_any_select(page, option_label=SPORT_LABEL)
            _select_option_in_any_select(page, option_label=PARK_LABEL)
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
            page.wait_for_timeout(1600)
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            pass

        try:
            # Ajax で結果表が載るまで待つ（週送りリンクが無いときはタイムアウトして続行）
            page.get_by_text("前週", exact=False).first.wait_for(timeout=25000)
        except Exception:
            pass

        try:
            # 「週表示」が <details> 等で畳まれていると表が DOM に無い／空に見えることがある
            folded = page.locator("details:not([open])").filter(
                has=page.get_by_text("週表示", exact=False)
            )
            if folded.count() > 0:
                folded.locator("summary").first.click(timeout=3000)
                page.wait_for_timeout(400)
        except Exception:
            pass

        try:
            # スクショの「施設ごと」タブ：月表示側であればマトリックス用の表示に寄せる
            page.locator("a, button, [role='tab']").filter(has_text="施設ごと").first.click(
                timeout=5000
            )
            page.wait_for_timeout(500)
        except Exception:
            pass

        try:
            # 週間マトリックスは「週表示」タブ／ラジオを選ばないと <table> に載らない（td 数も少ないまま）
            page.locator("a, button, label, [role='tab']").filter(
                has_text=re.compile(r"週.?表示")
            ).first.click(timeout=5000)
            page.wait_for_timeout(700)
        except Exception:
            pass

        raw = _evaluate_week_slots_everywhere(page, eval_params)

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